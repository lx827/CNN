"""精确缓存、显式重评与串行重分析 HTTP 接口。"""
from typing import Optional
from fastapi import Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device, Diagnosis
from app.schemas import DiagnosisResponse
from app.services.diagnosis.domain import DiagnosisKey
from app.services.diagnosis.assessment import reassess_diagnosis
from app.services.diagnosis_store import read_diagnosis, save_diagnosis, cache_query
from app.services.diagnosis_workflow import process_batch
from . import router, _sanitize_for_json


@router.put("/{device_id}/{batch_index}/diagnosis")
async def update_batch_diagnosis(device_id: str, batch_index: int,
                                 rot_freq: Optional[float] = Body(default=None, embed=True),
                                 db: Session = Depends(get_db)):
    """只更新准确 batch/none 转频缓存；不创建诊断或修改通道缓存。"""
    import math
    if rot_freq is None or not math.isfinite(rot_freq) or rot_freq <= 0:
        raise HTTPException(422, detail="rot_freq 必须为有限正数")
    row = cache_query(db, DiagnosisKey(device_id, batch_index, 0, "none")).first()
    if row is None:
        raise HTTPException(404, detail="批次诊断不存在，请先运行诊断")
    row.rot_freq = rot_freq
    db.commit()
    return {"code": 200, "message": "批次转频已更新"}


@router.get("/{device_id}/{batch_index}/{channel}/diagnosis", response_model=DiagnosisResponse)
def get_channel_diagnosis(device_id: str, batch_index: int, channel: int,
                          denoise_method: str = Query(default="none"), db: Session = Depends(get_db)):
    result = read_diagnosis(db, DiagnosisKey(device_id, batch_index, channel, denoise_method))
    if result is None:
        raise HTTPException(404, detail="当前通道与去噪组合暂无诊断缓存")
    return {"code": 200, "data": _sanitize_for_json(result)}


@router.post("/{device_id}/{batch_index}/{channel}/reevaluate", response_model=DiagnosisResponse)
def reevaluate_channel(device_id: str, batch_index: int, channel: int,
                       denoise_method: str = Query(default="none"), db: Session = Depends(get_db)):
    key = DiagnosisKey(device_id, batch_index, channel, denoise_method)
    payload = read_diagnosis(db, key)
    if payload is None:
        raise HTTPException(404, detail="诊断缓存不存在")
    if payload.get("reason") == "stored_contract_requires_reanalysis":
        raise HTTPException(409, detail="旧诊断缺少规范证据，请重新分析")
    result = {**payload, **reassess_diagnosis(payload).to_dict()}
    save_diagnosis(db, key, result)
    db.commit()
    return {"code": 200, "data": result}


@router.post("/{device_id}/{batch_index}/reanalyze", response_model=DiagnosisResponse)
async def reanalyze_batch(device_id: str, batch_index: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(404, detail="设备不存在")
    try:
        result = await process_batch(db, device, batch_index)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {"code": 200, "data": result}


@router.post("/{device_id}/reanalyze-all")
async def reanalyze_all_batches(device_id: str, db: Session = Depends(get_db)):
    from app.models import SensorData
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(404, detail="设备不存在")
    batches = db.query(SensorData.batch_index).filter(SensorData.device_id == device_id).distinct().order_by(SensorData.batch_index).all()
    results, errors = [], []
    for (batch_index,) in batches:
        try:
            value = await process_batch(db, device, batch_index)
            results.append({"batch_index": batch_index, "evaluation_status": value["evaluation_status"],
                            "diagnosis_conclusion": value["diagnosis_conclusion"], "health_score": value["health_score"]})
        except Exception as exc:
            db.rollback()
            errors.append({"batch_index": batch_index, "reason": str(exc)})
    return {"code": 200, "data": {"total": len(batches), "updated": len(results), "results": results, "errors": errors}}
