"""对象诊断 API；所有请求共用领域序列化与精确通道缓存。"""
import asyncio
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device, SensorData
from app.schemas import DiagnosisResponse
from app.services.diagnosis import DiagnosisEngine, DiagnosisKey
from app.services.diagnosis.gear.planetary import gear_config_for_channel
from app.services.diagnosis_store import save_diagnosis
from . import router, _sanitize_for_json

def _channel_params(values, channel):
    if not isinstance(values, dict):
        return {}
    return values if any(key in values for key in ("n", "d", "D")) else values.get(str(channel), {})

async def _run(db, device_id, batch_index, channel, denoise, mode, method="standard", rot_freq_hz=None):
    record = db.query(SensorData).filter(SensorData.device_id == device_id, SensorData.batch_index == batch_index, SensorData.channel == channel).first()
    if record is None:
        raise HTTPException(404, detail="通道数据不存在")
    device = db.query(Device).filter(Device.device_id == device_id).first()
    key = DiagnosisKey(device_id, batch_index, channel, denoise)
    try:
        engine = DiagnosisEngine(
            bearing_params=_channel_params(getattr(device, "bearing_params", None), channel),
            gear_teeth=gear_config_for_channel(getattr(device, "gear_teeth", None), channel),
            denoise_method=denoise, gear_method=method, diagnosis_key=key,
        )
        rate = record.sample_rate or getattr(device, "sample_rate", None)
        if not rate:
            raise ValueError("missing_sample_rate")
        signal = (record.data or [])[:int(rate * 5)]
        if mode == "gear":
            result = await asyncio.to_thread(engine.analyze_gear, signal, rate, rot_freq_hz)
        else:
            result = await asyncio.to_thread(engine.analyze_research_ensemble, signal, rate, rot_freq_hz,
                                             "exhaustive" if mode == "all" else "runtime")
        payload = {"device_id": device_id, "batch_index": batch_index, "channel": channel,
                   "channel_name": (getattr(device, "channel_names", None) or {}).get(str(channel), f"通道{channel}"),
                   "denoise": denoise, **result}
        save_diagnosis(db, key, payload)
        db.commit()
        return {"code": 200, "data": _sanitize_for_json(payload)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, detail=str(exc)) from exc

@router.get("/{device_id}/{batch_index}/{channel}/gear", response_model=DiagnosisResponse)
async def get_channel_gear(device_id: str, batch_index: int, channel: int,
                           method: str = Query("standard", pattern="^(standard|advanced)$"),
                           denoise: str = "none", rot_freq_hz: float | None = Query(None, gt=0),
                           db: Session = Depends(get_db)):
    return await _run(db, device_id, batch_index, channel, denoise, "gear", method, rot_freq_hz)

@router.get("/{device_id}/{batch_index}/{channel}/analyze", response_model=DiagnosisResponse)
async def get_channel_analyze(device_id: str, batch_index: int, channel: int,
                              denoise: str = "none", rot_freq_hz: float | None = Query(None, gt=0),
                              db: Session = Depends(get_db)):
    return await _run(db, device_id, batch_index, channel, denoise, "runtime", rot_freq_hz=rot_freq_hz)

@router.get("/{device_id}/{batch_index}/{channel}/full-analysis", response_model=DiagnosisResponse)
async def get_channel_full_analysis(device_id: str, batch_index: int, channel: int,
                                    denoise: str = "none", rot_freq_hz: float | None = Query(None, gt=0),
                                    db: Session = Depends(get_db)):
    return await _run(db, device_id, batch_index, channel, denoise, "all", rot_freq_hz=rot_freq_hz)
