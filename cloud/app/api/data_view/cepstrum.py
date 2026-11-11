from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.algorithms.cepstrum import analyze_cepstrum, compute_cepstrum
from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis.signal_utils import denoise_signal, DenoisingError
from .errors import denoising_http_error
from . import router, prepare_signal, _get_channel_name

import asyncio
import logging

logger = logging.getLogger(__name__)


@router.get("/{device_id}/{batch_index}/{channel}/cepstrum")
async def get_channel_cepstrum(
    device_id: str,
    batch_index: int,
    channel: int,
    max_quefrency: float = Query(
        default=500.0, ge=10.0, le=2000.0, description="最大倒频率 (ms)"
    ),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(
        default="none",
        description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd",
    ),
    db: Session = Depends(get_db),
):
    """实时 log-amplitude 实倒谱及显示峰；不输出机械故障结论。"""
    record = (
        db.query(SensorData)
        .filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == batch_index,
            SensorData.channel == channel,
        )
        .first()
    )

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sample_rate = record.sample_rate or 25600
        # 5 秒业务限制先于去趋势和慢去噪，避免对完整长记录做无效计算。
        max_samples = int(sample_rate * 5)
        signal = prepare_signal(record.data[:max_samples], detrend=detrend)
        signal = await asyncio.to_thread(denoise_signal, signal, denoise)
        representation = await asyncio.to_thread(compute_cepstrum, signal, sample_rate)
        analysis = await asyncio.to_thread(
            analyze_cepstrum,
            representation,
            max_quefrency_s=max_quefrency / 1000.0,
        )

        device = db.query(Device).filter(Device.device_id == device_id).first()
        quefrency_s = analysis.representation.quefrency_s
        cepstrum = analysis.representation.amplitude
        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "max_quefrency": max_quefrency,
                "quefrency": [round(float(value) * 1000.0, 2) for value in quefrency_s],
                "cepstrum": [round(float(value), 4) for value in cepstrum],
                "peaks": [
                    {
                        "quefrency_ms": round(peak.quefrency_s * 1000.0, 2),
                        "freq_hz": round(peak.frequency_hz, 2),
                        "amplitude": round(peak.amplitude, 4),
                    }
                    for peak in analysis.peaks
                ],
            },
        }
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    except Exception as e:
        logger.error(f"倒谱计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"倒谱计算失败: {e}")
