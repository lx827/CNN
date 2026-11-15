"""统一波形显示读取，以及仅诊断入口使用的采样率校验。"""

from dataclasses import dataclass

import numpy as np

from app.models import SensorData


class WaveformNotFoundError(ValueError):
    """请求的设备、批次或真实通道没有波形记录。"""


@dataclass
class WaveformBatch:
    """一个可显示批次的内存波形；records 保留持久化身份与分析标记。"""

    signals: dict[str, np.ndarray]
    sample_rate: int
    records: list[SensorData]


def _read_signal(record):
    source = record.data
    if isinstance(source, dict) and source.get("kind") == "dc24_counts":
        counts = np.memmap(source["path"], dtype="<i4", mode="r").reshape(-1, 4)
        return counts[
            source["start_sample"] : source["end_sample"], record.channel - 1
        ].astype(np.float64)
    return np.asarray(source, dtype=np.float64)


def waveform_from_records(records):
    """只校验显示采样率；诊断 override 不参与显示可用性判断。"""
    if not records:
        raise WaveformNotFoundError("batch_data_not_found")
    rates = {record.sample_rate for record in records}
    if not all(rates):
        raise ValueError("batch_sample_rate_missing")
    if len(rates) != 1:
        raise ValueError("batch_channel_sample_rates_must_match")
    return WaveformBatch(
        signals={
            f"ch{record.channel}": _read_signal(record) for record in records
        },
        sample_rate=next(iter(rates)),
        records=records,
    )


def get_diagnosis_sample_rate(batch):
    """仅在诊断入口解析历史覆盖；0/缺失和跨通道不一致明确拒绝。"""
    rates = {
        record.diagnosis_sample_rate_override
        if record.diagnosis_sample_rate_override is not None
        else record.sample_rate
        for record in batch.records
    }
    if not all(rates):
        raise ValueError("batch_sample_rate_missing")
    if len(rates) != 1:
        raise ValueError("batch_channel_diagnosis_sample_rates_must_match")
    return next(iter(rates))


def load_waveform(db, device_id, batch_index, channel=None):
    """读取一个批次；数据库数组或 DC24 文件区段只在内存转换为 float64。

    文件来源复用 SensorData.data JSON：kind=dc24_counts，并保存 job_id、path、
    start_sample、end_sample；通道号 1~4 映射到四路交错文件的列 0~3。
    """
    query = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
    )
    if channel is not None:
        query = query.filter(SensorData.channel == channel)
    records = query.order_by(SensorData.channel.asc()).all()
    if not records:
        raise WaveformNotFoundError("batch_data_not_found")
    return waveform_from_records(records)
