"""将完成的 DC24 采集记录登记为统一诊断批次。

ZIP 与流式保存共用本模块；调用方在同一事务中提交批次和任务终态。
"""

from sqlalchemy import func

from app.core import config
from app.models import AcquisitionAgent, Device, SensorData


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
    batch_index = (
        db.query(func.max(SensorData.batch_index))
        .filter(SensorData.device_id == device_id, SensorData.is_special == 1)
        .scalar()
        or 100
    ) + 1
    source_path = str(counts_path.resolve())
    batches = []
    for start in range(0, count, window_samples):
        end = min(start + window_samples, count)
        for channel in channels:
            db.add(
                SensorData(
                    device_id=device_id,
                    batch_index=batch_index,
                    channel=channel,
                    data={
                        "kind": "dc24_counts",
                        "job_id": job.id,
                        "path": source_path,
                        "start_sample": start,
                        "end_sample": end,
                    },
                    sample_rate=job.sample_rate,
                    is_analyzed=0,
                    is_special=1,
                )
            )
        batches.append(batch_index)
        batch_index += 1

    job.result_metadata = {
        **job.result_metadata,
        "diagnosis_device_id": device_id,
        "diagnosis_batches": batches,
    }
    return batches
