"""
实时监测接口
给 Monitor 页面提供最新振动数据和历史数据

FFT 频谱计算：
  后端对原始时域信号做 FFT，将频率轴和幅值一起返回给前端，
  前端直接绘制真实的频域谱图。

改造说明：
  - Monitor 页面不再自动轮询，改为手动触发采集后刷新
  - 优先返回最新的特殊数据（如果有），否则返回最新的普通数据
  - 返回通道名称（从设备配置获取）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from app.services.analyzer import compute_fft
from typing import List

router = APIRouter(prefix="/api/monitor", tags=["实时监测"])

# 从前端展示角度：25600Hz 下返回多少个点
# 2560 点 ≈ 0.1 秒，能显示几个完整周期，视觉上合适
TIME_DOMAIN_POINTS = 2560

# FFT 分析用多少点（取 1 秒数据 = 25600 点，频率分辨率 1 Hz）
FFT_POINTS = 25600

# FFT 返回的最高频率（风机故障主要集中在此范围）
FFT_MAX_FREQ = 5000


def _get_channel_name(device: Device, channel_num: int) -> str:
    """从设备配置获取通道名称，没有则返回默认名称"""
    if device and device.channel_names:
        name = device.channel_names.get(str(channel_num))
        if name:
            return name
    # 默认名称
    defaults = {
        1: "通道1-轴承附近",
        2: "通道2-驱动端",
        3: "通道3-风扇端",
    }
    return defaults.get(channel_num, f"通道{channel_num}")


@router.get("/latest")
def get_latest_monitor(
    device_id: str = Query(default="WTG-001"),
    prefer_special: bool = Query(default=False, description="优先返回特殊数据"),
    limit: int = Query(default=3, description="返回最近几条记录"),
    db: Session = Depends(get_db)
):
    """
    获取最新一批传感器数据（每个通道一条）
    同时返回时域数据和 FFT 频域数据

    如果 prefer_special=True，优先返回最新的特殊数据批次；
    否则返回最新的普通数据批次。
    """
    # 获取设备信息（通道名称等）
    device = db.query(Device).filter(Device.device_id == device_id).first()

    # 构建查询：先查特殊数据，再查普通数据
    if prefer_special:
        # 先尝试找最新的特殊数据
        latest_special = db.query(func.max(SensorData.batch_index)).filter(
            SensorData.device_id == device_id,
            SensorData.is_special == 1
        ).scalar()

        if latest_special:
            latest_batch = latest_special
            is_special_batch = True
        else:
            # 没有特殊数据，回退到普通数据
            latest_batch = db.query(func.max(SensorData.batch_index)).filter(
                SensorData.device_id == device_id,
                SensorData.is_special == 0
            ).scalar()
            is_special_batch = False
    else:
        # 默认找最新的（不分类型，取 batch_index 最大的）
        latest_batch = db.query(func.max(SensorData.batch_index)).filter(
            SensorData.device_id == device_id
        ).scalar()
        is_special_batch = False
        if latest_batch:
            # 判断这个批次是不是特殊的
            check = db.query(SensorData).filter(
                SensorData.device_id == device_id,
                SensorData.batch_index == latest_batch
            ).first()
            if check:
                is_special_batch = bool(check.is_special)

    results = []
    if latest_batch:
        records = db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == latest_batch
        ).order_by(SensorData.channel.asc()).all()

        for record in records:
            sample_rate = record.sample_rate or 25600
            channel_num = record.channel

            # 计算 FFT 频谱（用 1 秒数据，保证 1Hz 分辨率）
            try:
                signal_fft = record.data[:FFT_POINTS]
                freq, amp = compute_fft(signal_fft, sample_rate)
                freq_amp = [fa for fa in zip(freq, amp) if fa[0] <= FFT_MAX_FREQ]
                fft_freq = [round(f, 2) for f, a in freq_amp]
                fft_amp = [round(a, 4) for f, a in freq_amp]
            except Exception:
                fft_freq = []
                fft_amp = []

            results.append({
                "device_id": record.device_id,
                "channel": channel_num,
                "channel_name": _get_channel_name(device, channel_num),
                "batch_index": record.batch_index,
                "data": record.data[:TIME_DOMAIN_POINTS],
                "sample_rate": sample_rate,
                "is_analyzed": record.is_analyzed,
                "is_special": bool(record.is_special),
                "timestamp": record.created_at.isoformat() if record.created_at else None,
                "fft_freq": fft_freq,
                "fft_amp": fft_amp,
            })

    # 查询最新诊断结果，获取估计转频
    latest_diag = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id
    ).order_by(Diagnosis.analyzed_at.desc()).first()

    sensor_params = {}
    if latest_diag and latest_diag.rot_freq:
        sensor_params["estimated_rpm"] = round(latest_diag.rot_freq * 60, 1)
        sensor_params["rot_freq"] = round(latest_diag.rot_freq, 3)
        sensor_params["rpm_source"] = "estimated"

    # 如果没有真实数据，返回模拟数据保证前端不白屏
    if not results:
        import random
        channel_count = device.channel_count if device else 3
        for ch in range(1, channel_count + 1):
            mock_data = [random.uniform(-1, 1) for _ in range(TIME_DOMAIN_POINTS)]
            results.append({
                "device_id": device_id,
                "channel": ch,
                "channel_name": _get_channel_name(device, ch),
                "batch_index": 0,
                "data": mock_data,
                "sample_rate": 25600,
                "is_analyzed": 0,
                "is_special": False,
                "timestamp": None,
                "fft_freq": [],
                "fft_amp": [],
            })

    return {"code": 200, "data": results, "sensor_params": sensor_params}


@router.get("/history")
def get_monitor_history(
    device_id: str = Query(default="WTG-001"),
    channel: int = Query(default=1),
    batches: int = Query(default=16, description="最近多少批次"),
    include_special: bool = Query(default=True, description="是否包含特殊数据"),
    db: Session = Depends(get_db)
):
    """
    获取某通道最近 N 个批次的历史数据
    """
    query = db.query(SensorData.batch_index).filter(
        SensorData.device_id == device_id,
        SensorData.channel == channel
    )

    if not include_special:
        query = query.filter(SensorData.is_special == 0)

    batch_records = query.distinct().order_by(SensorData.batch_index.desc()).limit(batches).all()

    batch_indices = [r[0] for r in batch_records]

    items = []
    for bi in batch_indices:
        record = db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.channel == channel,
            SensorData.batch_index == bi
        ).first()

        if record:
            items.append({
                "batch_index": record.batch_index,
                "sample_rate": record.sample_rate,
                "is_analyzed": record.is_analyzed,
                "is_special": bool(record.is_special),
                "data": record.data[:TIME_DOMAIN_POINTS],
                "created_at": record.created_at.isoformat() if record.created_at else None,
            })

    return {
        "code": 200,
        "data": {
            "device_id": device_id,
            "channel": channel,
            "items": items,
        }
    }
