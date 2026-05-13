from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from datetime import datetime
from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod, DiagnosisStrategy
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum as _estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)
from . import router, prepare_signal, _get_channel_name
from .diagnosis_ops import _sanitize_for_json
from datetime import datetime
import logging
import numpy as np
import asyncio

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/gear")
async def get_channel_gear(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    method: str = Query(default="standard", description="齿轮诊断方法: standard/advanced"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet/vmd"),
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的齿轮诊断分析
    支持标准边频带分析和高级时域指标。
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

        device = db.query(Device).filter(Device.device_id == device_id).first()
        gear_teeth = {}
        if device:
            gear_teeth = device.gear_teeth or {}

        method_map = {
            "standard": GearMethod.STANDARD,
            "advanced": GearMethod.ADVANCED,
        }
        denoise_map = {"none": DenoiseMethod.NONE, "wavelet": DenoiseMethod.WAVELET, "vmd": DenoiseMethod.VMD}
        gear_method = method_map.get(method, GearMethod.STANDARD)
        denoise_method = denoise_map.get(denoise, DenoiseMethod.NONE)

        engine = DiagnosisEngine(
            gear_method=gear_method,
            denoise_method=denoise_method,
            gear_teeth=gear_teeth,
        )

        # CPU 密集型齿轮分析放入线程池
        result = await asyncio.to_thread(engine.analyze_gear, signal, sample_rate)

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
                "rot_freq_hz": result.get("rot_freq_hz"),
                "mesh_freq_hz": result.get("mesh_freq_hz"),
                "mesh_order": result.get("mesh_order"),
                "ser": result.get("ser"),
                "sidebands": result.get("sidebands", []),
                "fm0": result.get("fm0"),
                "fm4": result.get("fm4"),
                "car": result.get("car"),
                "m6a": result.get("m6a"),
                "m8a": result.get("m8a"),
                "fault_indicators": result.get("fault_indicators", {}),
            }
        }
    except Exception as e:
        logger.error(f"齿轮诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"齿轮诊断失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/analyze")
async def get_channel_analyze(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    strategy: str = Query(default="standard", description="诊断策略: standard/advanced/expert"),
    bearing_method: str = Query(default="envelope", description="轴承方法: envelope/kurtogram/cpw/med"),
    gear_method: str = Query(default="standard", description="齿轮方法: standard/advanced"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet"),
    db: Session = Depends(get_db)
):
    """
    综合故障诊断分析（新诊断引擎统一入口）

    支持前端配置选择诊断策略、轴承方法、齿轮方法和预处理方法。
    返回轴承诊断、齿轮诊断、时域特征和综合健康度评分。
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

        device = db.query(Device).filter(Device.device_id == device_id).first()
        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = device.bearing_params or {}
            gear_teeth = device.gear_teeth or {}

        # 映射前端参数到枚举
        strategy_map = {"standard": "standard", "advanced": "advanced", "expert": "expert"}
        bearing_map = {
            "envelope": BearingMethod.ENVELOPE,
            "kurtogram": BearingMethod.KURTOGRAM,
            "cpw": BearingMethod.CPW,
            "med": BearingMethod.MED,
        }
        gear_map = {"standard": GearMethod.STANDARD, "advanced": GearMethod.ADVANCED}
        denoise_map = {"none": DenoiseMethod.NONE, "wavelet": DenoiseMethod.WAVELET, "vmd": DenoiseMethod.VMD}

        engine = DiagnosisEngine(
            strategy=strategy_map.get(strategy, "standard"),
            bearing_method=bearing_map.get(bearing_method, BearingMethod.ENVELOPE),
            gear_method=gear_map.get(gear_method, GearMethod.STANDARD),
            denoise_method=denoise_map.get(denoise, DenoiseMethod.NONE),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        # CPU 密集型综合分析放入线程池
        result = await asyncio.to_thread(engine.analyze_comprehensive, signal, sample_rate)

        response_data = {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": sample_rate,
            "is_special": bool(record.is_special),
            "strategy": strategy,
            "bearing_method": bearing_method,
            "gear_method": gear_method,
            "denoise": denoise,
            **result,
        }

        # 写入/更新数据库（实时计算覆盖数据库）
        try:
            safe_data = _sanitize_for_json(response_data)
            diag = db.query(Diagnosis).filter(
                Diagnosis.device_id == device_id,
                Diagnosis.batch_index == batch_index,
                Diagnosis.channel == channel,
                Diagnosis.denoise_method == denoise,
            ).first()
            if diag:
                diag.health_score = result.get("health_score", 100)
                diag.status = result.get("status", "normal")
                diag.engine_result = safe_data
                diag.analyzed_at = datetime.utcnow()
            else:
                db.add(Diagnosis(
                    device_id=device_id,
                    batch_index=batch_index,
                    channel=channel,
                    health_score=result.get("health_score", 100),
                    status=result.get("status", "normal"),
                    engine_result=safe_data,
                    denoise_method=denoise,
                    analyzed_at=datetime.utcnow(),
                ))
            db.commit()
        except Exception as db_err:
            logger.warning(f"诊断结果写入数据库失败: {db_err}")
            db.rollback()

        return {
            "code": 200,
            "data": response_data,
        }
    except Exception as e:
        logger.error(f"综合分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"综合分析失败: {e}")




@router.get("/{device_id}/{batch_index}/{channel}/full-analysis")
async def get_channel_full_analysis(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet/vmd"),
    db: Session = Depends(get_db)
):
    """
    全算法对比分析（运行所有轴承方法和所有齿轮方法）

    返回所有诊断方法的详细结果和检出结论对比，便于前端展示：
    - 各轴承方法（包络 / Kurtogram / CPW / MED）分别检出了什么故障
    - 各齿轮方法（标准边频带 / 高级指标）的详细参数和阈值判定
    - 综合结论和建议
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

        # 限制信号长度（最多 5 秒）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        device = db.query(Device).filter(Device.device_id == device_id).first()
        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = device.bearing_params or {}
            gear_teeth = device.gear_teeth or {}

        denoise_map = {"none": DenoiseMethod.NONE, "wavelet": DenoiseMethod.WAVELET, "vmd": DenoiseMethod.VMD}

        engine = DiagnosisEngine(
            strategy=DiagnosisStrategy.EXPERT,
            bearing_method=BearingMethod.ENVELOPE,
            gear_method=GearMethod.STANDARD,
            denoise_method=denoise_map.get(denoise, DenoiseMethod.NONE),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        # CPU 密集型全算法分析放入线程池
        result = await asyncio.to_thread(engine.analyze_all_methods, signal, sample_rate)

        response_data = {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": sample_rate,
            "is_special": bool(record.is_special),
            "denoise": denoise,
            **result,
        }

        # 写入/更新数据库（实时计算覆盖数据库）
        try:
            safe_data = _sanitize_for_json(response_data)
            diag = db.query(Diagnosis).filter(
                Diagnosis.device_id == device_id,
                Diagnosis.batch_index == batch_index,
                Diagnosis.channel == channel,
                Diagnosis.denoise_method == denoise,
            ).first()
            if diag:
                diag.health_score = result.get("health_score", 100)
                diag.status = result.get("status", "normal")
                diag.full_analysis = safe_data
                diag.analyzed_at = datetime.utcnow()
            else:
                db.add(Diagnosis(
                    device_id=device_id,
                    batch_index=batch_index,
                    channel=channel,
                    health_score=result.get("health_score", 100),
                    status=result.get("status", "normal"),
                    full_analysis=safe_data,
                    denoise_method=denoise,
                    analyzed_at=datetime.utcnow(),
                ))
            db.commit()
        except Exception as db_err:
            logger.warning(f"全算法分析结果写入数据库失败: {db_err}")
            db.rollback()

        return {
            "code": 200,
            "data": response_data,
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"全算法分析失败: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"全算法分析失败: {e}\n{tb}")
