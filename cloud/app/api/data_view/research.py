from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
import asyncio
import logging

from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis import DiagnosisEngine, DenoiseMethod
from . import router, prepare_signal, _get_channel_name
from .gear import _extract_device_param
from .diagnosis_ops import _sanitize_for_json

logger = logging.getLogger(__name__)


@router.get("/{device_id}/{batch_index}/{channel}/research-analysis")
async def get_channel_research_analysis(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="whether to linearly detrend"),
    profile: str = Query(default="balanced", description="runtime/balanced/exhaustive"),
    denoise: str = Query(default="none", description="none/wavelet/vmd"),
    max_seconds: float = Query(default=5.0, ge=1.0, le=10.0),
    db: Session = Depends(get_db),
):
    """
    Run a user-triggered, multi-algorithm research diagnosis.

    This endpoint is intentionally separate from real-time monitoring because
    kurtogram, MED, TEO and TSA metrics are CPU-heavy.
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel,
    ).first()
    if not record or not record.data:
        raise HTTPException(status_code=404, detail="data not found")

    device = db.query(Device).filter(Device.device_id == device_id).first()

    profile = profile if profile in {"runtime", "balanced", "exhaustive"} else "balanced"
    denoise_map = {
        "none": DenoiseMethod.NONE,
        "wavelet": DenoiseMethod.WAVELET,
        "vmd": DenoiseMethod.VMD,
    }

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data, detrend=detrend)

        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = _extract_device_param(device.bearing_params or {}, ("n", "d", "D", "alpha"))
            gear_teeth = _extract_device_param(device.gear_teeth or {}, ("input", "output"))

        engine = DiagnosisEngine(
            denoise_method=denoise_map.get(denoise, DenoiseMethod.NONE),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        result = await asyncio.to_thread(
            engine.analyze_research_ensemble,
            signal,
            sample_rate,
            None,
            profile,
            max_seconds,
        )

        response_data = {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": sample_rate,
            "is_special": bool(record.is_special),
            "profile": profile,
            "denoise": denoise,
            **result,
        }
        return {"code": 200, "data": _sanitize_for_json(response_data)}
    except Exception as exc:
        logger.error("research analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"research analysis failed: {exc}")
