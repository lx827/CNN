from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Device
from . import router, prepare_signal, _load_channel_waveform
from app.services.diagnosis.signal_utils import denoise_signal, DenoisingError
from .errors import denoising_http_error
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
    denoise: str = Query(
        default="none",
        description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd",
    ),
    db: Session = Depends(get_db),
):
    """
    导出某批次某通道的时域数据为 CSV
    格式：时间(s), 振幅
    """
    waveform = _load_channel_waveform(db, device_id, batch_index, channel)
    record = waveform.records[0]

    signal = prepare_signal(waveform.signals[f"ch{channel}"], detrend=detrend)
    try:
        signal = denoise_signal(signal, denoise).tolist()
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    sample_rate = waveform.sample_rate

    # 生成 CSV
    output = io.StringIO()
    output.write("时间(s),振幅\n")
    for i, val in enumerate(signal):
        t = i / sample_rate
        output.write(f"{t:.6f},{val}\n")

    output.seek(0)
    filename = f"{device_id}_batch{batch_index}_ch{channel}.csv"

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
