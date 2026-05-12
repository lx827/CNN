from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from . import router, _get_channel_name, prepare_signal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@router.get("/devices")
def get_all_device_data(
    db: Session = Depends(get_db)
):
    """
    获取所有设备的批次列表（表格展示用）
    返回每个设备的所有批次，含时间和特殊标记
    """
    devices = db.query(Device).all()
    result = []

    for dev in devices:
        # 查询该设备的所有批次
        batch_records = db.query(
            SensorData.batch_index,
            func.max(SensorData.created_at).label("created_at"),
            func.max(SensorData.is_special).label("is_special"),
            func.count(SensorData.channel).label("channel_count"),
            func.max(SensorData.sample_rate).label("sample_rate"),
        ).filter(
            SensorData.device_id == dev.device_id
        ).group_by(
            SensorData.batch_index
        ).order_by(
            desc(func.max(SensorData.created_at))
        ).all()

        # 预加载该设备的所有诊断结果（按 batch_index）
        diag_records = db.query(Diagnosis).filter(
            Diagnosis.device_id == dev.device_id
        ).all()
        diag_map = {}
        for d in diag_records:
            # 同一 batch 可能有多次诊断，保留最新的
            if d.batch_index not in diag_map or (d.analyzed_at and d.analyzed_at > diag_map[d.batch_index].analyzed_at):
                diag_map[d.batch_index] = d

        batches = []
        for batch_index, created_at, is_special, ch_count, sr in batch_records:
            diag = diag_map.get(batch_index)
            # 提取概率最高的故障类型
            top_fault = None
            if diag and diag.fault_probabilities:
                top = max(diag.fault_probabilities.items(), key=lambda x: x[1])
                if top[1] > 0.3:
                    top_fault = f"{top[0]} ({top[1]*100:.0f}%)"
            batches.append({
                "batch_index": batch_index,
                "created_at": created_at.isoformat() if created_at else None,
                "is_special": bool(is_special),
                "channel_count": ch_count,
                "sample_rate": sr or 25600,
                "diagnosis_status": diag.status if diag else None,
                "health_score": diag.health_score if diag else None,
                "top_fault": top_fault,
                "analyzed_at": diag.analyzed_at.isoformat() if diag and diag.analyzed_at else None,
                "order_analysis": diag.order_analysis if diag else None,
                "rot_freq": diag.rot_freq if diag else None,
            })

        result.append({
            "device_id": dev.device_id,
            "device_name": dev.name,
            "channel_count": dev.channel_count,
            "channel_names": dev.channel_names,
            "batches": batches,
        })

    return {"code": 200, "data": result}


@router.get("/{device_id}/batches")
def get_device_batches(
    device_id: str,
    include_special: bool = Query(default=True, description="包含特殊数据"),
    db: Session = Depends(get_db)
):
    """
    获取某设备最近批次（普通+特殊）的概要信息
    特殊数据会用 is_special 标记
    """
    query = db.query(
        SensorData.batch_index,
        func.max(SensorData.created_at).label("created_at"),
        func.max(SensorData.is_special).label("is_special"),
        func.count(SensorData.channel).label("channel_count"),
        func.max(SensorData.sample_rate).label("sample_rate"),
    ).filter(
        SensorData.device_id == device_id
    ).group_by(
        SensorData.batch_index
    ).order_by(
        desc(func.max(SensorData.created_at))
    )

    if not include_special:
        query = query.filter(SensorData.is_special == 0)

    batch_records = query.all()

    # 预加载诊断结果
    diag_records = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id
    ).all()
    diag_map = {d.batch_index: d for d in diag_records}

    batches = []
    for batch_index, created_at, is_special, ch_count, sr in batch_records:
        diag = diag_map.get(batch_index)
        batches.append({
            "batch_index": batch_index,
            "created_at": created_at.isoformat() if created_at else None,
            "is_special": bool(is_special),
            "channel_count": ch_count,
            "sample_rate": sr or 25600,
            "diagnosis_status": diag.status if diag else None,
            "health_score": diag.health_score if diag else None,
            "analyzed_at": diag.analyzed_at.isoformat() if diag and diag.analyzed_at else None,
        })

    return {"code": 200, "data": batches}


@router.get("/{device_id}/{batch_index}/{channel}")
def get_channel_data(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    查询某批次某通道的原始时域数据
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="数据不存在")

    # 获取通道名称
    device = db.query(Device).filter(Device.device_id == device_id).first()

    # 时域波形返回去均值后的数据，便于观察
    dc_removed = prepare_signal(record.data, detrend=detrend).tolist()

    return {
        "code": 200,
        "data": {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": record.sample_rate,
            "data": dc_removed,
            "is_analyzed": record.is_analyzed,
            "is_special": bool(record.is_special),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
    }


@router.delete("/{device_id}/special")
def delete_special_batches(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    删除某设备的所有特殊数据批次
    同时删除关联的诊断结果

    注意：此路由必须放在 /{device_id}/{batch_index} 之前，
    否则 "special" 会被当成 batch_index 导致 422 错误。
    """
    # 查询该设备的所有特殊批次
    special_batches = db.query(SensorData.batch_index).filter(
        SensorData.device_id == device_id,
        SensorData.is_special == 1
    ).distinct().all()

    if not special_batches:
        return {
            "code": 200,
            "message": "该设备没有特殊数据",
            "data": {"deleted_batches": 0}
        }

    batch_indices = [b[0] for b in special_batches]
    deleted_count = 0

    try:
        for bi in batch_indices:
            # 删除传感器数据
            db.query(SensorData).filter(
                SensorData.device_id == device_id,
                SensorData.batch_index == bi
            ).delete(synchronize_session=False)

            # 删除关联的诊断结果
            db.query(Diagnosis).filter(
                Diagnosis.device_id == device_id,
                Diagnosis.batch_index == bi
            ).delete(synchronize_session=False)

            deleted_count += 1

        db.commit()

        return {
            "code": 200,
            "message": f"已删除 {deleted_count} 个特殊批次",
            "data": {
                "device_id": device_id,
                "deleted_batches": deleted_count,
                "batch_indices": batch_indices,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@router.delete("/{device_id}/{batch_index}")
def delete_batch(
    device_id: str,
    batch_index: int,
    db: Session = Depends(get_db)
):
    """
    删除某设备的整条批次数据（包括该批次的所有通道）
    同时删除关联的诊断结果和告警记录
    """
    # 先查询确认数据存在
    records = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index
    ).all()

    if not records:
        raise HTTPException(status_code=404, detail="批次不存在")

    is_special = any(r.is_special for r in records)

    try:
        # 删除传感器数据
        db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == batch_index
        ).delete(synchronize_session=False)

        # 删除关联的诊断结果
        db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id,
            Diagnosis.batch_index == batch_index
        ).delete(synchronize_session=False)

        db.commit()

        return {
            "code": 200,
            "message": f"批次 {batch_index} 删除成功",
            "data": {
                "device_id": device_id,
                "batch_index": batch_index,
                "deleted_channels": len(records),
                "is_special": is_special,
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
