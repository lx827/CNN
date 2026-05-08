"""
采集任务接口

核心流程：
  1. 前端点击"请求采集" → POST /api/collect/request → 创建 pending 任务
  2. 边端轮询 → GET /api/collect/tasks → 获取 pending 任务
  3. 边端采集上传 → 标记任务为 completed

支持两种模式：
  - 普通采集：边端自动定时执行（is_special=0）
  - 手动采集：前端触发，边端响应（is_special=1）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import CollectionTask, Device
from datetime import datetime
from typing import List, Optional

router = APIRouter(prefix="/api/collect", tags=["采集任务"])


@router.post("/request")
def request_collection(
    device_id: str,
    sample_rate: int = 25600,
    duration: int = 10,
    db: Session = Depends(get_db)
):
    """
    前端请求对指定设备进行手动采集（特殊数据）
    创建采集任务，等待边端轮询执行
    """
    # 检查设备是否存在
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 不存在")

    # 检查是否有未完成的同名任务（避免重复创建）
    existing = db.query(CollectionTask).filter(
        CollectionTask.device_id == device_id,
        CollectionTask.status.in_(["pending", "processing"])
    ).first()

    if existing:
        return {
            "code": 200,
            "message": "已有采集任务在执行中",
            "data": {
                "task_id": existing.id,
                "status": existing.status,
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }
        }

    task = CollectionTask(
        device_id=device_id,
        status="pending",
        sample_rate=sample_rate,
        duration=duration,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "code": 200,
        "message": "采集任务已创建，等待边端响应",
        "data": {
            "task_id": task.id,
            "device_id": device_id,
            "status": "pending",
            "sample_rate": sample_rate,
            "duration": duration,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
    }


@router.get("/tasks")
def get_pending_tasks(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    边端轮询接口：查询该设备的待采集任务
    边端应每隔几秒调用一次
    """
    # 获取最早的 pending 任务
    task = db.query(CollectionTask).filter(
        CollectionTask.device_id == device_id,
        CollectionTask.status == "pending"
    ).order_by(CollectionTask.created_at.asc()).first()

    if not task:
        return {"code": 200, "data": {"has_task": False}}

    # 标记为 processing
    task.status = "processing"
    task.started_at = datetime.utcnow()
    db.commit()

    return {
        "code": 200,
        "data": {
            "has_task": True,
            "task_id": task.id,
            "device_id": task.device_id,
            "sample_rate": task.sample_rate,
            "duration": task.duration,
        }
    }


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    batch_index: int,
    db: Session = Depends(get_db)
):
    """
    边端完成采集上传后，通知云端任务已完成
    由 ingest.py 内部调用，无需前端直接调用
    """
    task = db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task.status = "completed"
    task.completed_at = datetime.utcnow()
    task.result_batch_index = batch_index
    db.commit()

    return {"code": 200, "message": "任务已完成"}


@router.get("/tasks/{task_id}/status")
def get_task_status(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    前端查询采集任务状态
    用于轮询"采集中..."的进度
    """
    task = db.query(CollectionTask).filter(CollectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "code": 200,
        "data": {
            "task_id": task.id,
            "device_id": task.device_id,
            "status": task.status,
            "sample_rate": task.sample_rate,
            "duration": task.duration,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result_batch_index": task.result_batch_index,
            "error_message": task.error_message,
        }
    }


@router.get("/history")
def get_collection_history(
    device_id: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    查询采集历史（含普通和特殊采集记录）
    """
    query = db.query(CollectionTask)
    if device_id:
        query = query.filter(CollectionTask.device_id == device_id)

    tasks = query.order_by(desc(CollectionTask.created_at)).limit(limit).all()

    items = []
    for t in tasks:
        items.append({
            "task_id": t.id,
            "device_id": t.device_id,
            "status": t.status,
            "sample_rate": t.sample_rate,
            "duration": t.duration,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "result_batch_index": t.result_batch_index,
        })

    return {"code": 200, "data": items}
