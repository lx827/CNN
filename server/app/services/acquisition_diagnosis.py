"""将完成的 DC24 采集记录登记为统一诊断批次。

ZIP 与流式保存共用本模块；调用方在同一事务中提交批次和任务终态。
"""

from pathlib import Path

from sqlalchemy import func
import numpy as np

from app.core import config
from app.models import AcquisitionAgent, Device, SensorData


def validate_channels(channels):
    if not channels or len(set(channels)) != len(channels):
        raise ValueError("至少启用一路采集通道，且通道不能重复")
    if any(channel not in config.DC24_CHANNELS for channel in channels):
        raise ValueError(f"采集通道必须属于 {list(config.DC24_CHANNELS)}")
    return sorted(channels)


def next_special_batch_index(db, device_id):
    return (
        db.query(func.max(SensorData.batch_index))
        .filter(SensorData.device_id == device_id, SensorData.is_special == 1)
        .scalar()
        or 100
    ) + 1


def register_counts_window(
    db,
    *,
    device_id,
    batch_index,
    job_id,
    counts_path,
    sample_rate,
    start_sample,
    end_sample,
    channels,
):
    """登记一个永久文件窗口；调用方负责事务和文件范围校验。"""
    source_path = str(counts_path.resolve())
    for channel in channels:
        db.add(
            SensorData(
                device_id=device_id,
                batch_index=batch_index,
                channel=channel,
                data={
                    "kind": "dc24_counts",
                    "job_id": job_id,
                    "path": source_path,
                    "start_sample": start_sample,
                    "end_sample": end_sample,
                },
                sample_rate=sample_rate,
                is_analyzed=0,
                is_special=1,
            )
        )


def register_reanalysis_window(db, records, start_sample, end_sample, channels):
    """从同一 DC24 原件选段创建新批次，原批次与原始文件保持不变。"""
    if not records or any(
        not isinstance(record.data, dict)
        or record.data.get("kind") != "dc24_counts"
        for record in records
    ):
        raise ValueError("只有 DC24 文件批次支持选段或通道重新分析")
    first = records[0]
    if not first.sample_rate:
        raise ValueError("batch_sample_rate_missing")
    if any(
        record.data["job_id"] != first.data["job_id"]
        or record.data["path"] != first.data["path"]
        or record.sample_rate != first.sample_rate
        for record in records
    ):
        raise ValueError("文件批次的来源或采样率不一致")
    counts = np.memmap(first.data["path"], dtype="<i4", mode="r")
    sample_count = counts.size // 4
    if not 0 <= start_sample < end_sample <= sample_count:
        raise ValueError("重新分析区间必须位于原始记录内，且起始样本小于结束样本")
    batch_index = next_special_batch_index(db, first.device_id)
    register_counts_window(
        db,
        device_id=first.device_id,
        batch_index=batch_index,
        job_id=first.data["job_id"],
        counts_path=Path(first.data["path"]),
        sample_rate=first.sample_rate,
        start_sample=start_sample,
        end_sample=end_sample,
        channels=channels,
    )
    return batch_index


def register_completed_acquisition(db, job, counts_path):
    """按配置窗口和启用通道创建永久批次；不提交事务，不复制波形。"""
    if job.result_metadata.get("diagnosis_batches") is not None:
        return job.result_metadata["diagnosis_batches"]

    agent = db.get(AcquisitionAgent, job.agent_id)
    device_id = job.agent_id
    device = db.query(Device).filter(Device.device_id == device_id).first()
    name = agent.state.get("name") or job.agent_id
    channels = job.enabled_channels or list(config.DC24_CHANNELS)
    if device is None:
        device = Device(
            device_id=device_id,
            name=name,
            channel_count=len(channels),
            channel_names={str(channel): f"通道 {channel}" for channel in channels},
            sample_rate=job.sample_rate,
            is_online=1,
            last_seen_at=agent.last_seen_at,
        )
        db.add(device)
    else:
        device.name = name
        device.channel_count = len(channels)
        device.sample_rate = job.sample_rate
        device.is_online = 1
        device.last_seen_at = agent.last_seen_at

    count = job.result_metadata["samples_per_channel"]
    window_samples = int(job.sample_rate * config.DC24_DIAGNOSIS_WINDOW_SECONDS)
    batch_index = next_special_batch_index(db, device_id)
    batches = []
    for start in range(0, count, window_samples):
        register_counts_window(
            db,
            device_id=device_id,
            batch_index=batch_index,
            job_id=job.id,
            counts_path=counts_path,
            sample_rate=job.sample_rate,
            start_sample=start,
            end_sample=min(start + window_samples, count),
            channels=channels,
        )
        batches.append(batch_index)
        batch_index += 1

    job.result_metadata = {
        **job.result_metadata,
        "diagnosis_device_id": device_id,
        "diagnosis_batches": batches,
    }
    return batches
