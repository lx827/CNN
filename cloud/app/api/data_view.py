"""
振动数据查看接口
支持：
  1. 查询某设备的最近批次（含普通和特殊数据）
  2. 查询某批次某通道的原始时域数据
  3. 实时计算 FFT 频谱
  4. 实时计算 STFT 时频谱
  5. 实时计算包络谱（轴承故障诊断）
  6. 实时计算阶次谱（阶次跟踪分析）
  7. 删除整条批次数据（支持普通和特殊数据）

所有频谱都是请求时实时计算，不预存。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.models import SensorData, Device, Diagnosis, Alarm
from app.services.analyzer import compute_fft, compute_envelope_spectrum
from typing import Optional, Tuple
import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy import signal as scipy_signal
import io

router = APIRouter(prefix="/api/data", tags=["振动数据查看"])


def _estimate_rot_freq_spectrum(
    sig: np.ndarray, fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    harmonics_num: int = 5
) -> float:
    """通过频谱峰值估计转频

    改进：增加基频能量约束，避免将啮合频率的约数误判为转频
    （如齿轮磨损信号中 180Hz 的 1/2=90Hz 会被旧算法误判）。
    """
    N = len(sig)
    spectrum = np.abs(rfft(sig))
    freqs = rfftfreq(N, d=1.0 / fs)

    spectrum = spectrum / (spectrum.max() + 1e-10)
    mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
    search_freqs = freqs[mask]
    search_spectrum = spectrum[mask]

    if len(search_freqs) == 0:
        return freq_range[0]

    best_freq = search_freqs[0]
    best_energy = 0.0

    for f in search_freqs:
        # 基频本身必须有显著能量（≥ 最大值的 10%），
        # 防止将啮合频率的约数（本身无能量）误判为转频
        idx_base = np.argmin(np.abs(freqs - f))
        if spectrum[idx_base] < 0.1:
            continue

        energy = 0.0
        for h in range(1, harmonics_num + 1):
            harmonic_freq = f * h
            if harmonic_freq > fs / 2:
                break
            idx = np.argmin(np.abs(freqs - harmonic_freq))
            weight = 1.0 / h
            energy += spectrum[idx] * weight
        if energy > best_energy:
            best_energy = energy
            best_freq = f

    # 如果所有候选基频都太弱，fallback 到搜索范围内最强峰值
    if best_energy == 0.0:
        best_idx = np.argmax(search_spectrum)
        best_freq = search_freqs[best_idx]

    return float(best_freq)


def _order_tracking(
    sig: np.ndarray, fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024
) -> Tuple[np.ndarray, np.ndarray]:
    """阶次跟踪：时域 → 角域重采样"""
    duration = len(sig) / fs
    num_revs = duration * rot_freq
    n_points = int(num_revs * samples_per_rev)

    if n_points < 10:
        raise ValueError(f"转数太少 ({num_revs:.1f})，无法进行阶次跟踪")

    times = np.arange(len(sig)) / fs
    target_times = np.linspace(0, duration, n_points, endpoint=False)
    sig_order = np.interp(target_times, times, sig)
    orders = np.arange(n_points) / num_revs
    return sig_order, orders


def _compute_order_spectrum(
    sig: np.ndarray, fs: float,
    rot_freq: float,
    samples_per_rev: int = 1024
) -> Tuple[np.ndarray, np.ndarray]:
    """计算阶次谱（加 Hanning 窗减少频谱泄漏）"""
    sig_order, orders = _order_tracking(sig, fs, rot_freq, samples_per_rev)
    sig_order = sig_order - sig_order.mean()
    N = len(sig_order)
    # Hanning 窗减少频谱泄漏
    window = np.hanning(N)
    sig_windowed = sig_order * window
    # 幅度恢复补偿：Hanning 窗能量损失约 1.633 倍
    amplitude_scale = np.sqrt(N / np.sum(window ** 2))
    spectrum = np.abs(rfft(sig_windowed))[:N // 2] * amplitude_scale
    order_axis = orders[:N // 2]
    return order_axis, spectrum


def _compute_cepstrum(
    sig: np.ndarray, fs: float,
    max_quefrency_ms: float = 500.0
) -> Tuple[np.ndarray, np.ndarray, list]:
    """
    计算功率倒谱（Power Cepstrum）

    流程：FFT → log(|FFT|) → IFFT → 倒谱
    倒谱峰值位置对应频谱中的周期性结构。
    """
    N = len(sig)
    # 1. FFT
    spectrum = np.fft.fft(sig)
    # 2. 对数幅度谱（加极小值避免 log(0)）
    log_spectrum = np.log(np.abs(spectrum) + 1e-10)
    # 3. IFFT 得到倒谱
    cepstrum = np.real(np.fft.ifft(log_spectrum))
    # 4. 倒频率轴（秒）→ 毫秒
    quefrency = np.arange(N) / fs
    half = N // 2
    quef_ms = quefrency[:half] * 1000.0
    cep = cepstrum[:half]
    # 5. 按最大倒频率截断
    mask = quef_ms <= max_quefrency_ms
    quef_ms = quef_ms[mask]
    cep = cep[mask]
    # 6. 峰值检测：自适应找倒谱中显著的多峰值
    # 策略：按幅值排序，当前峰值 < 最高峰值50%时自动截断，数量自适应
    peaks = []
    if len(cep) > 10:
        # 排除近零区域和超高倒频率噪声，关注 3ms ~ 200ms
        search_mask = (quef_ms >= 3.0) & (quef_ms <= 200.0)
        search_cep = cep[search_mask]
        search_quef = quef_ms[search_mask]

        if len(search_cep) > 10:
            # distance=50 排除紧邻旁瓣（约 2ms 间隔）
            peak_indices, _ = scipy_signal.find_peaks(search_cep, distance=50)
            # 按幅值降序
            sorted_indices = sorted(peak_indices, key=lambda i: search_cep[i], reverse=True)

            top_amp = None
            for idx in sorted_indices:
                amp = float(search_cep[idx])
                # 首个峰值记录为基准，后续低于其50%时截断
                if top_amp is None:
                    top_amp = amp
                elif amp < top_amp * 0.5:
                    break
                q_ms = float(search_quef[idx])
                # 排除与已选峰值距离 < 3ms 的点（同一主瓣的旁瓣）
                too_close = any(abs(p["quefrency_ms"] - q_ms) < 3.0 for p in peaks)
                if too_close:
                    continue
                freq_hz = 1000.0 / q_ms if q_ms > 0 else 0.0
                peaks.append({
                    "quefrency_ms": round(q_ms, 2),
                    "freq_hz": round(freq_hz, 2),
                    "amplitude": round(amp, 4),
                })
    return quef_ms, cep, peaks


def _get_channel_name(device: Device, channel_num: int) -> str:
    """从设备配置获取通道名称"""
    if device and device.channel_names:
        name = device.channel_names.get(str(channel_num))
        if name:
            return name
    defaults = {
        1: "通道1-轴承附近",
        2: "通道2-驱动端",
        3: "通道3-风扇端",
    }
    return defaults.get(channel_num, f"通道{channel_num}")


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

        batches = []
        for batch_index, created_at, is_special, ch_count, sr in batch_records:
            batches.append({
                "batch_index": batch_index,
                "created_at": created_at.isoformat() if created_at else None,
                "is_special": bool(is_special),
                "channel_count": ch_count,
                "sample_rate": sr or 25600,
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
        func.count(SensorData.channel).label("channel_count"),
        func.max(SensorData.is_special).label("is_special"),
        func.max(SensorData.sample_rate).label("sample_rate"),
    ).filter(
        SensorData.device_id == device_id
    )

    if not include_special:
        query = query.filter(SensorData.is_special == 0)

    batch_records = query.group_by(
        SensorData.batch_index
    ).order_by(
        desc(func.max(SensorData.created_at))
    ).limit(50).all()

    items = []
    for batch_index, created_at, ch_count, is_special, sr in batch_records:
        # 检查该批次是否已分析
        analyzed = db.query(SensorData).filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == batch_index,
            SensorData.is_analyzed == 1
        ).first()

        items.append({
            "batch_index": batch_index,
            "channel_count": ch_count,
            "is_analyzed": 1 if analyzed else 0,
            "is_special": bool(is_special),
            "sample_rate": sr or 25600,
            "created_at": created_at.isoformat() if created_at else None,
        })

    return {"code": 200, "data": items}


@router.get("/{device_id}/{batch_index}/{channel}")
def get_channel_data(
    device_id: str,
    batch_index: int,
    channel: int,
    db: Session = Depends(get_db)
):
    """
    获取某批次某通道的原始时域数据
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

    return {
        "code": 200,
        "data": {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": record.sample_rate,
            "data": record.data,
            "is_analyzed": record.is_analyzed,
            "is_special": bool(record.is_special),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
    }


@router.get("/{device_id}/{batch_index}/{channel}/fft")
def get_channel_fft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
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
        freq, amp = compute_fft(record.data, sample_rate)
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
        raise HTTPException(status_code=500, detail=f"FFT 计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/stft")
def get_channel_stft(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 5000,
    nperseg: int = Query(default=512, ge=64, le=4096, description="STFT 窗口长度（点数）"),
    noverlap: int = Query(default=256, ge=0, le=4095, description="STFT 窗口重叠长度（点数）"),
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
        signal = np.array(record.data)
        sample_rate = record.sample_rate or 25600

        # 如果数据太长，截取前 5 秒做 STFT（避免计算量过大）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        # 确保参数合理
        ns = min(nperseg, len(signal))
        nov = min(noverlap, ns - 1)
        nfft = max(1024, ns)

        f, t, Zxx = stft(signal, fs=sample_rate, nperseg=ns, noverlap=nov, nfft=nfft)

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
        raise HTTPException(status_code=500, detail=f"STFT 计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/stats")
def get_channel_stats(
    device_id: str,
    batch_index: int,
    channel: int,
    window_size: int = Query(default=1024, ge=64, le=8192, description="加窗窗口大小（点数）"),
    step: int = Query(default=None, ge=1, le=4096, description="滑动步长（点数），默认窗口大小的一半"),
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
        signal = np.array(record.data)
        sample_rate = record.sample_rate or 25600

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
        raise HTTPException(status_code=500, detail=f"统计指标计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/envelope")
def get_channel_envelope(
    device_id: str,
    batch_index: int,
    channel: int,
    max_freq: Optional[int] = 1000,
    db: Session = Depends(get_db)
):
    """
    实时计算某批次某通道的包络谱（Envelope Spectrum）
    用于轴承故障诊断，请求时计算，不预存。
    自动适配实际采样率。
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
        freq, amp = compute_envelope_spectrum(record.data, sample_rate, max_freq)

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
                "envelope_freq": freq,
                "envelope_amp": amp,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"包络谱计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/order")
def get_channel_order(
    device_id: str,
    batch_index: int,
    channel: int,
    freq_min: float = Query(default=10.0, ge=1.0, le=500.0, description="转频搜索下限 (Hz)"),
    freq_max: float = Query(default=100.0, ge=1.0, le=500.0, description="转频搜索上限 (Hz)"),
    samples_per_rev: int = Query(default=1024, ge=64, le=4096, description="每转采样点数"),
    max_order: int = Query(default=50, ge=5, le=200, description="返回的最大阶次"),
    db: Session = Depends(get_db)
):
    """
    实时计算阶次谱（Order Tracking / 阶次跟踪）

    流程：
      1. 通过频谱峰值法估计转频（rot_freq）
      2. 时域信号 → 角域重采样（等角度间隔）
      3. 角域 FFT → 阶次谱

    参数：
      freq_min/freq_max: 转频搜索范围，默认 10~100 Hz
      samples_per_rev:   每转采样点数，默认 1024
      max_order:         返回的最大阶次，默认 50

    返回：
      rot_freq: 估计转频 (Hz)
      rot_rpm:  估计转速 (RPM)
      orders:   阶次轴
      spectrum: 阶次谱幅值
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sig = np.array(record.data)
        sample_rate = record.sample_rate or 25600

        # 参数校验
        if freq_min >= freq_max:
            raise ValueError("freq_min 必须小于 freq_max")

        # 1. 估计转频
        rot_freq = _estimate_rot_freq_spectrum(
            sig, sample_rate,
            freq_range=(freq_min, freq_max)
        )

        # 2. 阶次跟踪 + 阶次谱
        order_axis, spectrum = _compute_order_spectrum(
            sig, sample_rate, rot_freq, samples_per_rev
        )

        # 3. 限制最大阶次
        mask = order_axis <= max_order
        order_axis = order_axis[mask]
        spectrum = spectrum[mask]

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
                "rot_freq": round(rot_freq, 3),
                "rot_rpm": round(rot_freq * 60.0, 1),
                "samples_per_rev": samples_per_rev,
                "orders": [round(float(o), 3) for o in order_axis.tolist()],
                "spectrum": [round(float(a), 4) for a in spectrum.tolist()],
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"阶次谱计算失败: {e}")


@router.get("/{device_id}/{batch_index}/{channel}/cepstrum")
def get_channel_cepstrum(
    device_id: str,
    batch_index: int,
    channel: int,
    max_quefrency: float = Query(default=500.0, ge=10.0, le=2000.0, description="最大倒频率 (ms)"),
    db: Session = Depends(get_db)
):
    """
    实时计算功率倒谱（Cepstrum / 倒谱分析）

    流程：
      1. FFT → 对数幅度谱 → IFFT → 倒谱
      2. 倒频率轴反映频谱中的周期性结构
      3. 自动检测显著峰值并标注对应频率

    参数：
      max_quefrency: 最大倒频率（毫秒），默认 500 ms

    返回：
      quefrency:  倒频率轴（ms）
      cepstrum:   倒谱幅值
      peaks:      检测到的峰值列表 [{quefrency_ms, freq_hz, amplitude}]
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel
    ).first()

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sig = np.array(record.data)
        sample_rate = record.sample_rate or 25600

        quef_ms, cep, peaks = _compute_cepstrum(sig, sample_rate, max_quefrency)

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
                "max_quefrency": max_quefrency,
                "quefrency": [round(float(q), 2) for q in quef_ms.tolist()],
                "cepstrum": [round(float(c), 4) for c in cep.tolist()],
                "peaks": peaks,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"倒谱计算失败: {e}")


@router.delete("/{device_id}/special")
def delete_special_batches(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    删除某设备的所有特殊数据批次
    同时删除关联的诊断结果

    ⚠️ 注意：此路由必须放在 /{device_id}/{batch_index} 之前，
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

        # 删除关联的告警（可选，根据业务需求）
        # db.query(Alarm).filter(
        #     Alarm.device_id == device_id,
        #     Alarm.batch_index == batch_index
        # ).delete(synchronize_session=False)

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


@router.get("/{device_id}/{batch_index}/{channel}/export")
def export_channel_csv(
    device_id: str,
    batch_index: int,
    channel: int,
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

    signal = record.data or []
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
