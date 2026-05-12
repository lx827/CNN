from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device
from . import router
from datetime import datetime
import io
import logging

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/export")
def export_channel_csv(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    导出某批次某通道的时域数据为 CSV
    格式：时间(s), 振幅
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="数据不存在")

    signal = prepare_signal(record.data, detrend=detrend).tolist() if record.data else []
    sample_rate = record.sample_rate or 25600

    # 生成 CSV
    output = io.StringIO()
    output.write("时间(s),振幅\n")
    for i, val in enumerate(signal):
        t = i / sample_rate
        output.write(f"{t:.6f},{val}\n")

    output.seek(0)
    filename = f"{device_id}_batch{batch_index}_ch{channel}.csv"

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


