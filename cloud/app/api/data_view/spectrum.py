from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.algorithms.statistics import analyze_time_domain
from app.algorithms.transforms import compute_spectrum, compute_stft
from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis.signal_utils import denoise_signal, DenoisingError
from .errors import denoising_http_error
from . import router, prepare_signal, _get_channel_name

import asyncio
import logging

logger = logging.getLogger(__name__)


def _limited_signal(record, detrend: bool):
    """DataView 业务上限为 5 秒；必须先截断再执行去趋势和慢去噪。"""
    sample_rate = record.sample_rate or 25600
    max_samples = int(sample_rate * 5)
    return prepare_signal(record.data[:max_samples], detrend=detrend), sample_rate


@router.get("/{device_id}/{batch_index}/{channel}/fft")
async def get_channel_fft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd"),
    db: Session = Depends(get_db)
):
    """实时计算 Hann 单边峰值幅值谱；响应字段保持兼容。"""
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        signal, sample_rate = _limited_signal(record, detrend)
        signal = await asyncio.to_thread(denoise_signal, signal, denoise)
        spectrum = await asyncio.to_thread(compute_spectrum, signal, sample_rate)
        if max_freq is not None:
            spectrum = spectrum.truncated(float(max_freq))

        device = db.query(Device).filter(Device.device_id == device_id).first()
        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "fft_freq": [round(float(value), 2) for value in spectrum.frequency_hz],
                "fft_amp": [round(float(value), 4) for value in spectrum.amplitude],
            }
        }
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    except Exception as e:
        logger.error(f"FFT 计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"FFT 计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/stft")
async def get_channel_stft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    nperseg: int = Query(default=512, ge=64, le=4096, description="STFT 窗口长度（点数）"),
    noverlap: int = Query(default=256, ge=0, le=4095, description="STFT 窗口重叠长度（点数）"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd"),
    db: Session = Depends(get_db)
):
    """实时 STFT；time 为帧中心秒，freq 为 Hz，magnitude 为单边幅值 dB。"""
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        signal, sample_rate = _limited_signal(record, detrend)
        signal = await asyncio.to_thread(denoise_signal, signal, denoise)

        ns = min(nperseg, len(signal))
        nov = min(noverlap, ns - 1)
        nfft = max(1024, ns)
        representation = await asyncio.to_thread(
            compute_stft,
            signal,
            sample_rate,
            nperseg=ns,
            noverlap=nov,
            nfft=nfft,
        )
        if max_freq is not None:
            mask = representation.frequency_hz <= max_freq
            frequency = representation.frequency_hz[mask]
            magnitude_db = representation.amplitude_db()[mask, :]
            time = representation.time_s
        else:
            frequency = representation.frequency_hz
            magnitude_db = representation.amplitude_db()
            time = representation.time_s

        device = db.query(Device).filter(Device.device_id == device_id).first()
        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "time": [round(float(value), 4) for value in time],
                "freq": [round(float(value), 2) for value in frequency],
                "magnitude": [
                    [round(float(value), 2) for value in row]
                    for row in magnitude_db
                ],
            }
        }
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    except Exception as e:
        logger.error(f"STFT 计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"STFT 计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/stats")
async def get_channel_stats(
    device_id: str,
    batch_index: int,
    channel: int,
    window_size: int = Query(default=1024, ge=64, le=8192, description="加窗窗口大小（点数）"),
    step: int = Query(default=None, ge=1, le=4096, description="滑动步长（点数），默认窗口大小的一半"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(default="none", description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd"),
    db: Session = Depends(get_db)
):
    """实时总体统计与周期 Hann 加窗序列；算法层不序列化数组。"""
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        signal, sample_rate = _limited_signal(record, detrend)
        signal = await asyncio.to_thread(denoise_signal, signal, denoise)
        analysis = await asyncio.to_thread(
            analyze_time_domain,
            signal,
            sample_rate,
            window_size=window_size,
            step=step,
        )
        overall = analysis.overall
        windowed = analysis.windowed

        device = db.query(Device).filter(Device.device_id == device_id).first()
        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "peak": round(overall.peak, 6),
                "rms": round(overall.rms, 6),
                "kurtosis": round(overall.kurtosis, 4),
                "skewness": round(overall.skewness, 4),
                "margin": round(overall.margin, 4),
                "shape_factor": round(overall.shape_factor, 4),
                "impulse_factor": round(overall.impulse_factor, 4),
                "crest_factor": round(overall.crest_factor, 4),
                "windowed_kurtosis": round(windowed.mean_kurtosis, 4),
                "window_series": {
                    "time": [round(float(value), 4) for value in windowed.time_s],
                    "kurtosis": [round(float(value), 4) for value in windowed.kurtosis],
                    "skewness": [round(float(value), 4) for value in windowed.skewness],
                    "rms": [round(float(value), 6) for value in windowed.rms],
                    "peak": [round(float(value), 6) for value in windowed.peak],
                    "margin": [round(float(value), 4) for value in windowed.margin],
                    "crest_factor": [round(float(value), 4) for value in windowed.crest_factor],
                    "shape_factor": [round(float(value), 4) for value in windowed.shape_factor],
                    "impulse_factor": [round(float(value), 4) for value in windowed.impulse_factor],
                },
                "window_params": {
                    "window_size": analysis.window_size,
                    "step": analysis.step,
                },
            }
        }
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    except Exception as e:
        logger.error(f"统计指标计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"统计指标计算失败: {e}")
