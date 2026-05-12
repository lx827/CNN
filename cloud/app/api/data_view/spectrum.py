from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis.features import compute_fft
from . import router, prepare_signal
from datetime import datetime
import logging
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy import signal as scipy_signal

logger = logging.getLogger(__name__)

@router.get("/{device_id}/{batch_index}/{channel}/fft")
def get_channel_fft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的 FFT 频谱
    请求时计算，不预存。自动适配实际采样率。
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data, detrend=detrend)
        freq, amp = compute_fft(signal.tolist(), sample_rate)
        freq_amp = [fa for fa in zip(freq, amp) if fa[0] <= max_freq]

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
                "fft_freq": [round(f, 2) for f, a in freq_amp],
                "fft_amp": [round(a, 4) for f, a in freq_amp],
            }
        }
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
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的 STFT 时频谱
    请求时计算，不预存。自动适配实际采样率。
    窗口长度 nperseg 和重叠 noverlap 可从前端调整。
    """
    import numpy as np
    from scipy.signal import stft

    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        signal = prepare_signal(record.data, detrend=detrend)
        sample_rate = record.sample_rate or 25600

        # 如果数据太长，截取前 5 秒做 STFT（避免计算量过大）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        # 确保参数合理
        ns = min(nperseg, len(signal))
        nov = min(noverlap, ns - 1)
        nfft = max(1024, ns)

        # CPU 密集型 STFT 计算放入线程池，避免阻塞事件循环
        f, t, Zxx = await asyncio.to_thread(
            stft, signal, fs=sample_rate, nperseg=ns, noverlap=nov, nfft=nfft
        )

        # 只保留 0~max_freq Hz 范围
        freq_mask = f <= max_freq
        f = f[freq_mask]
        Zxx = Zxx[freq_mask, :]

        # 幅度（dB）
        magnitude = np.abs(Zxx)
        magnitude_db = 20 * np.log10(magnitude + 1e-10)

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
                "time": [round(x, 4) for x in t.tolist()],
                "freq": [round(x, 2) for x in f.tolist()],
                "magnitude": [[round(val, 2) for val in row] for row in magnitude_db.tolist()],
            }
        }
    except Exception as e:
        logger.error(f"STFT 计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"STFT 计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/stats")
def get_channel_stats(
    device_id: str,
    batch_index: int,
    channel: int,
    window_size: int = Query(default=1024, ge=64, le=8192, description="加窗窗口大小（点数）"),
    step: int = Query(default=None, ge=1, le=4096, description="滑动步长（点数），默认窗口大小的一半"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的统计特征指标
    包括：峰值、RMS、峭度、偏度、裕度、波形因子、脉冲因子、峰值因子、加窗峰度
    加窗参数 window_size 和 step 可从前端调整
    """
    import numpy as np
    from scipy import stats

    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        signal = prepare_signal(record.data, detrend=detrend)
        sample_rate = record.sample_rate or 25600

        # 限制信号长度，防止超长数据导致计算超时（最多取 5 秒）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        # 基本统计量
        peak = float(np.max(np.abs(signal)))
        rms = float(np.sqrt(np.mean(signal ** 2)))
        mean_abs = float(np.mean(np.abs(signal)))

        # 峭度与偏度
        kurtosis = float(stats.kurtosis(signal, fisher=False))  # fisher=False 返回正态分布为3
        skewness = float(stats.skew(signal))

        # 无量纲指标
        margin = peak / rms if rms > 1e-12 else 0.0
        shape_factor = rms / mean_abs if mean_abs > 1e-12 else 0.0
        impulse_factor = peak / mean_abs if mean_abs > 1e-12 else 0.0
        crest_factor = peak / rms if rms > 1e-12 else 0.0

        # 加窗统计量（汉宁窗，窗口大小和步长可调）
        ws = min(window_size, len(signal))
        st = step if step is not None else ws // 2
        st = max(1, min(st, ws))
        windowed_series = {
            "time": [],
            "kurtosis": [],
            "skewness": [],
            "rms": [],
            "peak": [],
            "margin": [],
            "crest_factor": [],
            "shape_factor": [],
            "impulse_factor": [],
        }
        if len(signal) >= ws:
            window = np.hanning(ws)
            for start in range(0, len(signal) - ws + 1, st):
                seg = signal[start:start + ws] * window
                seg_peak = float(np.max(np.abs(seg)))
                seg_rms = float(np.sqrt(np.mean(seg ** 2)))
                seg_mean_abs = float(np.mean(np.abs(seg)))
                windowed_series["time"].append(round(start / sample_rate, 4))
                windowed_series["kurtosis"].append(float(stats.kurtosis(seg, fisher=False)))
                windowed_series["skewness"].append(float(stats.skew(seg)))
                windowed_series["rms"].append(seg_rms)
                windowed_series["peak"].append(seg_peak)
                windowed_series["margin"].append(round(seg_peak / seg_rms, 4) if seg_rms > 1e-12 else 0.0)
                windowed_series["crest_factor"].append(round(seg_peak / seg_rms, 4) if seg_rms > 1e-12 else 0.0)
                windowed_series["shape_factor"].append(round(seg_rms / seg_mean_abs, 4) if seg_mean_abs > 1e-12 else 0.0)
                windowed_series["impulse_factor"].append(round(seg_peak / seg_mean_abs, 4) if seg_mean_abs > 1e-12 else 0.0)

        device = db.query(Device).filter(Device.device_id == device_id).first()

        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "peak": round(peak, 6),
                "rms": round(rms, 6),
                "kurtosis": round(kurtosis, 4),
                "skewness": round(skewness, 4),
                "margin": round(margin, 4),
                "shape_factor": round(shape_factor, 4),
                "impulse_factor": round(impulse_factor, 4),
                "crest_factor": round(crest_factor, 4),
                "windowed_kurtosis": round(np.mean(windowed_series["kurtosis"]), 4) if windowed_series["kurtosis"] else 0.0,
                "window_series": {
                    "time": windowed_series["time"],
                    "kurtosis": [round(v, 4) for v in windowed_series["kurtosis"]],
                    "skewness": [round(v, 4) for v in windowed_series["skewness"]],
                    "rms": [round(v, 6) for v in windowed_series["rms"]],
                    "peak": [round(v, 6) for v in windowed_series["peak"]],
                    "margin": windowed_series["margin"],
                    "crest_factor": windowed_series["crest_factor"],
                    "shape_factor": windowed_series["shape_factor"],
                    "impulse_factor": windowed_series["impulse_factor"],
                },
                "window_params": {
                    "window_size": ws,
                    "step": st,
                },
            }
        }
    except Exception as e:
        logger.error(f"统计指标计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"统计指标计算失败: {e}")


