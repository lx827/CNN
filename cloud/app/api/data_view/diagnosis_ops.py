"""精确缓存、显式重评与串行重分析 HTTP 接口。"""

from typing import Optional
from fastapi import Depends, HTTPException, Body, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device, Diagnosis, SensorData
from app.schemas import DiagnosisResponse
from app.services.diagnosis.domain import DiagnosisKey
from app.services.diagnosis.assessment import reassess_diagnosis
from app.services.diagnosis_store import read_diagnosis, save_diagnosis, cache_query
from app.services.diagnosis_workflow import process_batch
from app.services.acquisition_diagnosis import (
    register_reanalysis_window,
    validate_channels,
)
from . import router, _sanitize_for_json


@router.put("/{device_id}/{batch_index}/diagnosis")
async def update_batch_diagnosis(
    device_id: str,
    batch_index: int,
    rot_freq: Optional[float] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
):
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


@router.get(
    "/{device_id}/{batch_index}/{channel}/diagnosis", response_model=DiagnosisResponse
)
def get_channel_diagnosis(
    device_id: str,
    batch_index: int,
    channel: int,
    denoise_method: str = Query(default="none"),
    db: Session = Depends(get_db),
):
    result = read_diagnosis(
        db, DiagnosisKey(device_id, batch_index, channel, denoise_method)
    )
    if result is None:
        raise HTTPException(404, detail="当前通道与去噪组合暂无诊断缓存")
    return {"code": 200, "data": _sanitize_for_json(result)}


@router.post(
    "/{device_id}/{batch_index}/{channel}/reevaluate", response_model=DiagnosisResponse
)
def reevaluate_channel(
    device_id: str,
    batch_index: int,
    channel: int,
    denoise_method: str = Query(default="none"),
    db: Session = Depends(get_db),
):
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


class ReanalyzeSelection(BaseModel):
    """DC24 文件批次的可选新窗口；空请求保持原批重新分析。"""

    start_sample: int | None = Field(default=None, ge=0)
    end_sample: int | None = Field(default=None, gt=0)
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)
    channels: list[int] | None = None

    @field_validator("channels")
    @classmethod
    def valid_channels(cls, channels):
        return validate_channels(channels) if channels is not None else None

    @model_validator(mode="after")
    def valid_range(self):
        sample_pair = (self.start_sample is not None, self.end_sample is not None)
        time_pair = (self.start_time is not None, self.end_time is not None)
        if any(sample_pair) and not all(sample_pair):
            raise ValueError("起止样本必须同时提供")
        if any(time_pair) and not all(time_pair):
            raise ValueError("起止时间必须同时提供")
        if any(sample_pair) and any(time_pair):
            raise ValueError("样本区间与时间区间只能选一种")
        if all(sample_pair) and self.start_sample >= self.end_sample:
            raise ValueError("起始样本必须小于结束样本")
        if all(time_pair) and self.start_time >= self.end_time:
            raise ValueError("起始时间必须小于结束时间")
        return self

    def has_selection(self):
        return any(
            value is not None
            for value in (
                self.start_sample,
                self.end_sample,
                self.start_time,
                self.end_time,
                self.channels,
            )
        )


@router.post("/{device_id}/{batch_index}/reanalyze", response_model=DiagnosisResponse)
async def reanalyze_batch(
    device_id: str,
    batch_index: int,
    selection: ReanalyzeSelection | None = Body(default=None),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(404, detail="设备不存在")
    target_batch = batch_index
    try:
        if selection is not None and selection.has_selection():
            records = (
                db.query(SensorData)
                .filter(
                    SensorData.device_id == device_id,
                    SensorData.batch_index == batch_index,
                )
                .order_by(SensorData.channel)
                .all()
            )
            if not records:
                raise HTTPException(404, detail="批次不存在")
            first = records[0]
            if selection.start_sample is not None:
                start = selection.start_sample
                end = selection.end_sample
            elif selection.start_time is not None:
                if not first.sample_rate:
                    raise ValueError("batch_sample_rate_missing")
                start = round(selection.start_time * first.sample_rate)
                end = round(selection.end_time * first.sample_rate)
            else:
                start = first.data.get("start_sample") if isinstance(first.data, dict) else None
                end = first.data.get("end_sample") if isinstance(first.data, dict) else None
            channels = selection.channels or [record.channel for record in records]
            target_batch = register_reanalysis_window(
                db, records, start, end, channels
            )
        result = await process_batch(db, device, target_batch)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, detail=str(exc)) from exc
    return {"code": 200, "data": {**result, "batch_index": target_batch}}


@router.post("/{device_id}/reanalyze-all")
async def reanalyze_all_batches(device_id: str, db: Session = Depends(get_db)):
    from app.models import SensorData

    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(404, detail="设备不存在")
    batches = (
        db.query(SensorData.batch_index)
        .filter(SensorData.device_id == device_id)
        .distinct()
        .order_by(SensorData.batch_index)
        .all()
    )
    results, errors = [], []
    for (batch_index,) in batches:
        try:
            value = await process_batch(db, device, batch_index)
            results.append(
                {
                    "batch_index": batch_index,
                    "evaluation_status": value["evaluation_status"],
                    "diagnosis_conclusion": value["diagnosis_conclusion"],
                    "health_score": value["health_score"],
                }
            )
        except Exception as exc:
            db.rollback()
            errors.append({"batch_index": batch_index, "reason": str(exc)})
    return {
        "code": 200,
        "data": {
            "total": len(batches),
            "updated": len(results),
            "results": results,
            "errors": errors,
        },
    }
