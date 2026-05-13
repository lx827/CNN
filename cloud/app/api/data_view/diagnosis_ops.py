from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from app.services.analyzer import analyze_device
from . import router
from datetime import datetime
import logging
import asyncio
import numpy as np

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj):
    """递归将 numpy 类型转换为 Python 原生类型，确保 JSON 可序列化"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj

@router.put("/{device_id}/{batch_index}/diagnosis")
async def update_batch_diagnosis(
    device_id: str,
    batch_index: int,
    order_analysis: Optional[dict] = Body(default=None),
    rot_freq: Optional[float] = Body(default=None),
    db: Session = Depends(get_db)
):
    """
    更新批次诊断结果（order_analysis / rot_freq）。
    用于阶次追踪重新计算后，把新的转频写回数据库覆盖原始数据。
    """
    diag = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id,
        Diagnosis.batch_index == batch_index
    ).first()

    if diag:
        if order_analysis is not None:
            existing = _sanitize_for_json(diag.order_analysis or {})
            existing.update(_sanitize_for_json(order_analysis))
            diag.order_analysis = existing
        if rot_freq is not None:
            diag.rot_freq = rot_freq
        diag.analyzed_at = datetime.utcnow()
    else:
        diag = Diagnosis(
            device_id=device_id,
            batch_index=batch_index,
            health_score=100,
            fault_probabilities={"正常运行": 1.0},
            imf_energy={},
            order_analysis=order_analysis or {},
            rot_freq=rot_freq,
            status="normal",
            analyzed_at=datetime.utcnow(),
        )
        db.add(diag)

    db.commit()
    return {"code": 200, "message": "诊断数据已更新"}



@router.get("/{device_id}/{batch_index}/{channel}/diagnosis")
def get_channel_diagnosis(
    device_id: str,
    batch_index: int,
    channel: int,
    denoise_method: Optional[str] = Query(default=None, description="去噪方法过滤: none/wavelet/vmd/med"),
    db: Session = Depends(get_db)
):
    """
    查询指定批次通道的诊断结果。
    优先返回通道级 engine_result，如果没有则返回批次级诊断记录。
    若指定 denoise_method，优先匹配该去噪方法的结果。
    """
    # 1. 若指定了去噪方法，先精确匹配
    if denoise_method:
        diag = db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id,
            Diagnosis.batch_index == batch_index,
            Diagnosis.channel == channel,
            Diagnosis.denoise_method == denoise_method,
        ).order_by(Diagnosis.analyzed_at.desc()).first()

        if diag and (diag.engine_result or diag.full_analysis):
            return {
                "code": 200,
                "data": diag.engine_result or diag.full_analysis,
            }

    # 2. 查该通道的最新诊断结果（不限去噪方法）
    diag = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id,
        Diagnosis.batch_index == batch_index,
        Diagnosis.channel == channel,
    ).order_by(Diagnosis.analyzed_at.desc()).first()

    if diag and (diag.engine_result or diag.full_analysis):
        return {
            "code": 200,
            "data": diag.engine_result or diag.full_analysis,
        }

    # 3. 再查批次级诊断记录（兼容旧数据）
    diag_batch = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id,
        Diagnosis.batch_index == batch_index,
    ).order_by(Diagnosis.analyzed_at.desc()).first()

    if diag_batch:
        return {
            "code": 200,
            "data": {
                "health_score": diag_batch.health_score,
                "status": diag_batch.status,
                "fault_probabilities": diag_batch.fault_probabilities,
                "imf_energy": diag_batch.imf_energy,
                "order_analysis": diag_batch.order_analysis,
                "rot_freq": diag_batch.rot_freq,
            }
        }

    raise HTTPException(status_code=404, detail="诊断数据不存在")


@router.post("/{device_id}/{batch_index}/reanalyze")
async def reanalyze_batch(
    device_id: str,
    batch_index: int,
    db: Session = Depends(get_db)
):
    """
    重新分析指定批次的所有通道数据，并更新/覆盖诊断结果。
    """
    # 1. 获取设备
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 2. 获取该批次所有通道数据
    records = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index
    ).all()

    if not records:
        raise HTTPException(status_code=404, detail="批次数据不存在")

    # 3. 组装通道数据
    channels_data = {}
    for r in records:
        channels_data[f"ch{r.channel}"] = r.data

    # 4. 执行分析（重新诊断跳过耗时去噪，避免 VMD 超时/内存不足）
    sample_rate = records[0].sample_rate or device.sample_rate or 25600

    # 使用 proxy 对象传入 analyze_device，避免修改 SQLAlchemy device 对象
    class _DeviceProxy:
        __slots__ = ("_device",)
        def __init__(self, device):
            self._device = device
        def __getattr__(self, name):
            if name == "denoise_method":
                return "none"
            return getattr(self._device, name)

    proxy = _DeviceProxy(device)
    try:
        result = await asyncio.to_thread(analyze_device, channels_data, sample_rate, proxy)
    except Exception as e:
        logger.error(f"重新诊断失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重新诊断失败: {e}")

    # 5. 更新或创建诊断记录（含 JSON 安全转换）
    try:
        logger.info(f"[重新诊断] 步骤5: 查询/创建诊断记录, device={device_id}, batch={batch_index}")
        diag = db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id,
            Diagnosis.batch_index == batch_index
        ).first()

        safe_fault_probs = _sanitize_for_json(result["fault_probabilities"])
        safe_imf = _sanitize_for_json(result["imf_energy"])
        safe_order = _sanitize_for_json(result.get("order_analysis"))

        if diag:
            logger.info(f"[重新诊断] 更新已有诊断记录, id={diag.id}")
            diag.health_score = result["health_score"]
            diag.fault_probabilities = safe_fault_probs
            diag.imf_energy = safe_imf
            diag.order_analysis = safe_order
            diag.rot_freq = result.get("rot_freq")
            diag.status = result["status"]
            diag.analyzed_at = datetime.utcnow()
        else:
            logger.info(f"[重新诊断] 创建新诊断记录")
            diag = Diagnosis(
                device_id=device_id,
                batch_index=batch_index,
                health_score=result["health_score"],
                fault_probabilities=safe_fault_probs,
                imf_energy=safe_imf,
                order_analysis=safe_order,
                rot_freq=result.get("rot_freq"),
                status=result["status"],
                analyzed_at=datetime.utcnow(),
            )
            db.add(diag)

        # 6. 标记批次为已分析
        logger.info(f"[重新诊断] 步骤6: 标记批次为已分析, 记录数={len(records)}")
        for r in records:
            r.is_analyzed = 1
            r.analyzed_at = datetime.utcnow()

        # 7. 更新设备健康度
        logger.info(f"[重新诊断] 步骤7: 更新设备健康度, health_score={result['health_score']}, status={result['status']}")
        device.health_score = result["health_score"]
        device.status = result["status"]

        logger.info(f"[重新诊断] 步骤8: 提交数据库事务")
        db.commit()
        logger.info(f"[重新诊断] 步骤9: 事务提交成功")
    except Exception as db_err:
        logger.error(f"[重新诊断] 数据库写入失败: {db_err}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"诊断结果保存失败: {db_err}")

    return {
        "code": 200,
        "message": "重新诊断完成",
        "data": {
            "health_score": result["health_score"],
            "status": result["status"],
            "fault_probabilities": result["fault_probabilities"],
            "rot_freq": result.get("rot_freq"),
            "order_analysis": result.get("order_analysis"),
        }
    }
