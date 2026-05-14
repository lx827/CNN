from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum as _estimate_rot_freq_spectrum
from app.services.diagnosis import DiagnosisEngine, BearingMethod
from . import router, prepare_signal, _get_channel_name
from datetime import datetime
import logging
import numpy as np
import asyncio

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/envelope")
async def get_channel_envelope(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 1000,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    method: str = Query(default="envelope", description="包络分析方法: envelope/kurtogram/cpw/med"),
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的包络谱（Envelope Spectrum）
    支持多种轴承诊断方法：标准包络 / Fast Kurtogram / CPW / MED
    请求时计算，不预存。
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data, detrend=detrend)

        # 限制信号长度，防止超长数据导致计算超时（最多取 5 秒）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        # 获取设备参数
        device = db.query(Device).filter(Device.device_id == device_id).first()
        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = device.bearing_params or {}
            gear_teeth = device.gear_teeth or {}
        # 兼容前端通道级格式 {"1":{n:9,d:7.94}} → 设备级 {n:9,d:7.94}
        def _extract_device_param(params, device_keys):
            if not params or not isinstance(params, dict):
                return params
            if any(k in params for k in device_keys):
                return params
            for key in sorted(params.keys()):
                ch = params.get(key)
                if ch and isinstance(ch, dict) and any(k in ch for k in device_keys):
                    return ch
            return params
        bearing_params = _extract_device_param(bearing_params, ("n", "d", "D", "alpha"))
        gear_teeth = _extract_device_param(gear_teeth, ("input", "output"))

        # 【默认诊断逻辑】若该设备未配置有效轴承参数，使用内置默认参数执行包络分析，
        # 确保用户点击"包络分析"时始终能看到结果。详见 DIAGNOSIS_LOGIC.md §2.3
        def _has_valid_bearing(bp):
            if not bp or not isinstance(bp, dict):
                return False
            try:
                return all(v is not None for v in [bp.get("n"), bp.get("d"), bp.get("D")]) and float(bp.get("n", 0)) > 0 and float(bp.get("d", 0)) > 0 and float(bp.get("D", 0)) > 0
            except (TypeError, ValueError):
                return False
        if not _has_valid_bearing(bearing_params):
            bearing_params = {"n": 9, "d": 7.94, "D": 39.04, "alpha": 0}   # 6205-2RS 默认

        # 方法映射
        method_map = {
            "envelope": BearingMethod.ENVELOPE,
            "kurtogram": BearingMethod.KURTOGRAM,
            "cpw": BearingMethod.CPW,
            "med": BearingMethod.MED,
        }
        bearing_method = method_map.get(method, BearingMethod.ENVELOPE)

        engine = DiagnosisEngine(
            bearing_method=bearing_method,
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        # CPU 密集型轴承分析放入线程池
        result = await asyncio.to_thread(engine.analyze_bearing, signal, sample_rate)

        # 兼容原有返回格式
        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "method": result.get("method", method),
                "envelope_freq": result.get("envelope_freq", []),
                "envelope_amp": result.get("envelope_amp", []),
                "optimal_fc": result.get("optimal_fc"),
                "optimal_bw": result.get("optimal_bw"),
                "max_kurtosis": result.get("max_kurtosis"),
                "comb_frequencies": result.get("comb_frequencies"),
                "med_filter_len": result.get("med_filter_len"),
                "kurtosis_before": result.get("kurtosis_before"),
                "kurtosis_after": result.get("kurtosis_after"),
                "features": result.get("features", {}),
                "fault_indicators": result.get("fault_indicators", {}),
            }
        }
    except Exception as e:
        logger.error(f"包络谱计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"包络谱计算失败: {e}")


