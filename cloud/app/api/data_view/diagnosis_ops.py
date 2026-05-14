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
            result = dict(diag.engine_result or diag.full_analysis)
            result["rot_freq"] = diag.rot_freq
            return {"code": 200, "data": result}

    # 2. 查该通道的最新诊断结果（不限去噪方法）
    diag = db.query(Diagnosis).filter(
        Diagnosis.device_id == device_id,
        Diagnosis.batch_index == batch_index,
        Diagnosis.channel == channel,
    ).order_by(Diagnosis.analyzed_at.desc()).first()

    if diag and (diag.engine_result or diag.full_analysis):
        result = dict(diag.engine_result or diag.full_analysis)
        result["rot_freq"] = diag.rot_freq
        return {"code": 200, "data": result}

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
    """重新分析指定批次的所有通道数据"""
    import traceback as _tb

    # 1. 获取设备和数据
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    records = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index
    ).all()
    if not records:
        raise HTTPException(status_code=404, detail="批次数据不存在")

    # 2. 组装通道数据
    channels_data = {}
    for r in records:
        channels_data[f"ch{r.channel}"] = r.data
    sample_rate = records[0].sample_rate or device.sample_rate or 25600

    # 3. 优先使用数据库已存的转频（阶次追踪权威值）
    saved_rot_freq = None
    try:
        diag_existing = db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id, Diagnosis.batch_index == batch_index
        ).first()
        if diag_existing and diag_existing.rot_freq and diag_existing.rot_freq > 0:
            saved_rot_freq = float(diag_existing.rot_freq)
    except Exception:
        pass

    # 4. 执行分析
    try:
        result = await asyncio.to_thread(
            analyze_device, channels_data, sample_rate, device,
            rot_freq=saved_rot_freq, denoise_method="none"
        )
    except Exception as e:
        logger.error(f"[重新诊断] 分析失败: {e}\n{_tb.format_exc()}")
        raise HTTPException(status_code=500, detail=f"分析引擎异常: {e}")

    # 4b. 检查分析结果是否有内部错误标记
    if result.get("_error"):
        logger.warning(f"[重新诊断] 分析引擎报告内部错误: {result['_error']}")

    # 5. 写入数据库
    try:
        safe_fault_probs = _sanitize_for_json(result["fault_probabilities"])
        safe_imf = _sanitize_for_json(result["imf_energy"])
        safe_order = _sanitize_for_json(result.get("order_analysis"))

        diag = db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id, Diagnosis.batch_index == batch_index
        ).first()

        if diag:
            diag.health_score = result["health_score"]
            diag.fault_probabilities = safe_fault_probs
            diag.imf_energy = safe_imf
            diag.order_analysis = safe_order
            diag.rot_freq = result.get("rot_freq")
            diag.status = result["status"]
            diag.analyzed_at = datetime.utcnow()
        else:
            db.add(Diagnosis(
                device_id=device_id, batch_index=batch_index,
                health_score=result["health_score"],
                fault_probabilities=safe_fault_probs,
                imf_energy=safe_imf,
                order_analysis=safe_order,
                rot_freq=result.get("rot_freq"),
                status=result["status"],
                analyzed_at=datetime.utcnow(),
            ))

        for r in records:
            r.is_analyzed = 1
            r.analyzed_at = datetime.utcnow()

        device.health_score = result["health_score"]
        device.status = result["status"]
        db.commit()
    except Exception as e:
        logger.error(f"[重新诊断] 数据库写入失败: {e}\n{_tb.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"诊断结果保存失败: {e}")

    return {
        "code": 200, "message": "重新诊断完成",
        "data": {
            "health_score": result["health_score"],
            "status": result["status"],
            "fault_probabilities": result["fault_probabilities"],
            "rot_freq": result.get("rot_freq"),
            "order_analysis": result.get("order_analysis"),
        },
    }


@router.post("/{device_id}/reanalyze-all")
async def reanalyze_all_batches(
    device_id: str,
    db: Session = Depends(get_db)
):
    """重新分析指定设备的所有批次数据，逐批次串行执行以避免 OOM"""
    import traceback as _tb

    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 查出所有批次号
    batch_indices = [
        row[0] for row in db.query(SensorData.batch_index)
        .filter(SensorData.device_id == device_id)
        .distinct().all()
    ]
    if not batch_indices:
        return {"code": 200, "message": "无数据可分析", "data": {"total": 0, "updated": 0}}

    results = []
    errors = []
    for bi in sorted(batch_indices):
        records = db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == bi
        ).all()
        if not records:
            continue

        channels_data = {}
        for r in records:
            channels_data[f"ch{r.channel}"] = r.data
        sample_rate = records[0].sample_rate or device.sample_rate or 25600

        # 优先使用已存转频
        saved_rot_freq = None
        try:
            diag_ex = db.query(Diagnosis).filter(
                Diagnosis.device_id == device_id, Diagnosis.batch_index == bi
            ).first()
            if diag_ex and diag_ex.rot_freq and diag_ex.rot_freq > 0:
                saved_rot_freq = float(diag_ex.rot_freq)
        except Exception:
            pass

        try:
            result = await asyncio.to_thread(
                analyze_device, channels_data, sample_rate, device,
                rot_freq=saved_rot_freq, denoise_method="none"
            )
            if result.get("_error"):
                logger.warning(f"[全部重新诊断] batch {bi} 内部错误: {result['_error']}")

            safe_fp = _sanitize_for_json(result["fault_probabilities"])
            safe_imf = _sanitize_for_json(result["imf_energy"])
            safe_oa = _sanitize_for_json(result.get("order_analysis"))

            diag = db.query(Diagnosis).filter(
                Diagnosis.device_id == device_id, Diagnosis.batch_index == bi
            ).first()
            if diag:
                diag.health_score = result["health_score"]
                diag.fault_probabilities = safe_fp
                diag.imf_energy = safe_imf
                diag.order_analysis = safe_oa
                diag.rot_freq = result.get("rot_freq")
                diag.status = result["status"]
                diag.analyzed_at = datetime.utcnow()
            else:
                db.add(Diagnosis(
                    device_id=device_id, batch_index=bi,
                    health_score=result["health_score"],
                    fault_probabilities=safe_fp,
                    imf_energy=safe_imf,
                    order_analysis=safe_oa,
                    rot_freq=result.get("rot_freq"),
                    status=result["status"],
                    analyzed_at=datetime.utcnow(),
                ))

            for r in records:
                r.is_analyzed = 1
                r.analyzed_at = datetime.utcnow()

            db.commit()
            results.append({"batch_index": bi, "health_score": result["health_score"], "status": result["status"]})
        except Exception as e:
            db.rollback()
            logger.error(f"[全部重新诊断] batch {bi} 失败: {e}\n{_tb.format_exc()}")
            errors.append({"batch_index": bi, "error": str(e)})

    # 用最后一个成功批次的结果更新设备状态
    if results:
        last = results[-1]
        device.health_score = last["health_score"]
        device.status = last["status"]
        db.commit()

    return {
        "code": 200,
        "message": f"全部重新诊断完成，成功 {len(results)}/{len(batch_indices)}",
        "data": {
            "total": len(batch_indices),
            "updated": len(results),
            "errors": errors,
            "results": results,
        },
    }
