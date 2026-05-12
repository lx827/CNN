from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from app.services.analyzer import analyze_device
from . import router
from datetime import datetime
import logging
import asyncio

logger = logging.getLogger(__name__)

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
            existing = diag.order_analysis or {}
            existing.update(order_analysis)
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

    # 5. 更新或创建诊断记录
    logger.info(f"[重新诊断] 步骤5: 查询/创建诊断记录, device={device_id}, batch={batch_index}")
    diag = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id,
        Diagnosis.batch_index == batch_index
    ).first()

    if diag:
        logger.info(f"[重新诊断] 更新已有诊断记录, id={diag.id}")
        diag.health_score = result["health_score"]
        diag.fault_probabilities = result["fault_probabilities"]
        diag.imf_energy = result["imf_energy"]
        diag.order_analysis = result.get("order_analysis")
        diag.rot_freq = result.get("rot_freq")
        diag.status = result["status"]
        diag.analyzed_at = datetime.utcnow()
    else:
        logger.info(f"[重新诊断] 创建新诊断记录")
        diag = Diagnosis(
            device_id=device_id,
            batch_index=batch_index,
            health_score=result["health_score"],
            fault_probabilities=result["fault_probabilities"],
            imf_energy=result["imf_energy"],
            order_analysis=result.get("order_analysis"),
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
