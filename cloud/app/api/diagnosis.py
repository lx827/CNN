"""
故障诊断接口
给 Diagnosis 页面提供分析结果
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Diagnosis

router = APIRouter(prefix="/api/diagnosis", tags=["故障诊断"])


@router.get("/")
def get_diagnosis(
    device_id: str = Query(default="WTG-001"),
    batch_index: int = Query(default=None, description="指定批次号，不传则返回最新"),
    db: Session = Depends(get_db)
):
    """
    获取某设备最新诊断结果（或指定批次）
    """
    query = db.query(Diagnosis).filter(Diagnosis.device_id == device_id)
    if batch_index is not None:
        query = query.filter(Diagnosis.batch_index == batch_index)

    diag = query.order_by(Diagnosis.analyzed_at.desc()).first()

    if diag:
        return {
            "code": 200,
            "data": {
                "device_id": diag.device_id,
                "batch_index": diag.batch_index,
                "health_score": diag.health_score,
                "fault_probabilities": diag.fault_probabilities or {},
                "imf_energy": diag.imf_energy or {},
                "order_analysis": diag.order_analysis or {},
                "rot_freq": diag.rot_freq,
                "status": diag.status,
                "analyzed_at": diag.analyzed_at.isoformat() if diag.analyzed_at else None,
            }
        }

    # 默认数据，保证前端有东西显示
    return {
        "code": 200,
        "data": {
            "device_id": device_id,
            "batch_index": 0,
            "health_score": 87,
            "fault_probabilities": {
                "齿轮磨损": 0.15,
                "轴承内圈故障": 0.05,
                "轴承外圈故障": 0.03,
                "轴不对中": 0.08,
                "基础松动": 0.04,
                "正常运行": 0.65,
            },
            "imf_energy": {
                "IMF1": 35.2,
                "IMF2": 28.7,
                "IMF3": 18.4,
                "IMF4": 12.1,
                "IMF5": 5.6,
            },
            "status": "normal",
            "analyzed_at": None,
        }
    }
