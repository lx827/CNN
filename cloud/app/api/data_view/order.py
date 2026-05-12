from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum as _estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum,
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
    _order_tracking,
)
from . import router, prepare_signal
from datetime import datetime
import logging
import numpy as np
import asyncio

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/order")
async def get_channel_order(
    device_id: str,
    batch_index: int,
    channel: int,
    freq_min: float = Query(default=10.0, ge=1.0, le=500.0, description="转频搜索下限 (Hz)"),
    freq_max: float = Query(default=100.0, ge=1.0, le=500.0, description="转频搜索上限 (Hz)"),
    samples_per_rev: int = Query(default=1024, ge=64, le=4096, description="每转采样点数"),
    max_order: int = Query(default=50, ge=5, le=200, description="返回的最大阶次"),
    rot_freq: Optional[float] = Query(default=None, ge=1.0, le=500.0, description="直接指定转频(Hz)，传入则跳过自动估计"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    实时计算阶次谱（Order Tracking / 阶次跟踪）
    改进：采用短时多帧平均，自适应处理缓慢转速变化；支持直接传入转频。

    流程：
      1. 若传入 rot_freq，直接用它做阶次跟踪（跳过估计）
      2. 否则将信号分帧（默认 1 秒/帧，50% 重叠）
      3. 每帧估计转频（频谱法 + 包络解调辅助），并用 MAD 剔除异常帧
      4. 各帧独立阶次跟踪后，插值到公共阶次轴并平均
      5. 返回平均阶次谱 + 转速变化信息

    参数：
      freq_min/freq_max: 转频搜索范围，默认 10~100 Hz
      samples_per_rev:   每转采样点数，默认 1024
      max_order:         返回的最大阶次，默认 50
      rot_freq:          直接指定转频(Hz)，传入则跳过自动估计

    返回：
      rot_freq:      中位数转频 (Hz)
      rot_rpm:       中位数转速 (RPM)
      rot_freq_std:  转频标准差 (Hz)，反映转速波动程度
      orders:        阶次轴
      spectrum:      阶次谱幅值
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

        # 参数校验
        if freq_min >= freq_max:
            raise ValueError("freq_min 必须小于 freq_max")

        if rot_freq is not None:
            # 直接指定转频，做单帧阶次跟踪
            order_axis, spectrum = await asyncio.to_thread(
                _compute_order_spectrum, sig, sample_rate, rot_freq, samples_per_rev
            )
            mask = order_axis <= max_order
            order_axis = order_axis[mask]
            spectrum = spectrum[mask]
            rot_freq_val = float(rot_freq)
            rot_freq_std = 0.0
            tracking_method = "single_frame"
        else:
            # 先用多帧法估计转速及变化程度
            order_axis, spectrum, rot_freq_val, rot_freq_std = await asyncio.to_thread(
                _compute_order_spectrum_multi_frame,
                sig, sample_rate,
                freq_range=(freq_min, freq_max),
                samples_per_rev=samples_per_rev,
                max_order=max_order,
                frame_duration=1.0,
                overlap=0.5,
            )
            tracking_method = "multi_frame"

            # 若转速变化剧烈（变异系数 > 10%），启用变速阶次跟踪
            if rot_freq_val > 0 and (rot_freq_std / rot_freq_val) > 0.10:
                order_axis, spectrum, rot_freq_val, rot_freq_std = await asyncio.to_thread(
                    _compute_order_spectrum_varying_speed,
                    sig, sample_rate,
                    freq_range=(freq_min, freq_max),
                    samples_per_rev=samples_per_rev,
                    max_order=max_order,
                )
                tracking_method = "varying_speed"

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
                "rot_freq": round(rot_freq_val, 3),
                "rot_rpm": round(rot_freq_val * 60.0, 1),
                "rot_freq_std": round(rot_freq_std, 3),
                "tracking_method": tracking_method,
                "samples_per_rev": samples_per_rev,
                "orders": [round(float(o), 3) for o in order_axis.tolist()],
                "spectrum": [round(float(a), 4) for a in spectrum.tolist()],
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"阶次谱计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"阶次谱计算失败: {e}")


