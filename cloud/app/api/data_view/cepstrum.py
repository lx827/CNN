from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device
from . import router, prepare_signal, _get_channel_name, _compute_cepstrum
from datetime import datetime
import logging
import numpy as np

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/cepstrum")
async def get_channel_cepstrum(
    device_id: str,
    batch_index: int,
    channel: int,
    max_quefrency: float = Query(default=500.0, ge=10.0, le=2000.0, description="最大倒频率 (ms)"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    实时计算功率倒谱（Cepstrum / 倒谱分析）

    流程：
      1. FFT → 对数幅度谱 → IFFT → 倒谱
      2. 倒频率轴反映频谱中的周期性结构
      3. 自动检测显著峰值并标注对应频率

    参数：
      max_quefrency: 最大倒频率（毫秒），默认 500 ms

    返回：
      quefrency:  倒频率轴（ms）
      cepstrum:   倒谱幅值
      peaks:      检测到的峰值列表 [{quefrency_ms, freq_hz, amplitude}]
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sig = prepare_signal(record.data, detrend=detrend)
        sample_rate = record.sample_rate or 25600

        # 限制信号长度，防止超长数据导致计算超时（最多取 5 秒）
        max_samples = sample_rate * 5
        if len(sig) > max_samples:
            sig = sig[:max_samples]

        # CPU 密集型倒谱计算放入线程池
        quef_ms, cep, peaks = await asyncio.to_thread(_compute_cepstrum, sig, sample_rate, max_quefrency)

        device = db.query(Device).filter(Device.device_id == device_id).first()

        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "max_quefrency": max_quefrency,
                "quefrency": [round(float(q), 2) for q in quef_ms.tolist()],
                "cepstrum": [round(float(c), 4) for c in cep.tolist()],
                "peaks": peaks,
            }
        }
    except Exception as e:
        logger.error(f"倒谱计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"倒谱计算失败: {e}")


