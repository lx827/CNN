"""
通用工具函数
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft, rfftfreq
from typing import Tuple, Optional, List


def remove_dc(signal: np.ndarray) -> np.ndarray:
    """去除直流分量（零均值化）"""
    return signal - np.mean(signal)


def linear_detrend(signal: np.ndarray) -> np.ndarray:
    """线性去趋势"""
    return scipy_signal.detrend(signal, type='linear')


def prepare_signal(signal, detrend: bool = False) -> np.ndarray:
    """
    信号预处理：零均值化或线性去趋势
    detrend=False: 去直流（零均值化）
    detrend=True:  线性去趋势（消除 y=kx+b 漂移）
    """
    arr = np.array(signal, dtype=np.float64)
    if detrend:
        return scipy_signal.detrend(arr, type='linear')
    return arr - np.mean(arr)


def bandpass_filter(
    signal: np.ndarray,
    fs: float,
    f_low: float,
    f_high: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 带通滤波"""
    nyq = fs / 2.0
    low = max(1e-6, f_low / nyq)
    high = min(1.0 - 1e-6, f_high / nyq)
    b, a = scipy_signal.butter(order, [low, high], btype='band')
    return scipy_signal.filtfilt(b, a, signal)


def lowpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 低通滤波"""
    nyq = fs / 2.0
    cut = min(1.0 - 1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='low')
    return scipy_signal.filtfilt(b, a, signal)


def highpass_filter(
    signal: np.ndarray,
    fs: float,
    f_cut: float,
    order: int = 4,
) -> np.ndarray:
    """Butterworth 高通滤波"""
    nyq = fs / 2.0
    cut = max(1e-6, f_cut / nyq)
    b, a = scipy_signal.butter(order, cut, btype='high')
    return scipy_signal.filtfilt(b, a, signal)


def compute_fft_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算 FFT 频谱，返回 (频率轴, 幅值)"""
    arr = prepare_signal(signal)
    n = len(arr)
    yf = np.abs(rfft(arr))
    xf = rfftfreq(n, 1.0 / fs)
    return xf, yf


def compute_power_spectrum(
    signal: np.ndarray,
    fs: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """计算功率谱（幅值平方）"""
    xf, yf = compute_fft_spectrum(signal, fs)
    return xf, yf ** 2


def find_peaks_in_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    target_freq: float,
    tolerance_hz: float = 2.0,
    n_harmonics: int = 5,
) -> dict:
    """
    在频谱中搜索目标频率及其谐波族

    Returns:
        {
            "fundamental": {"freq": float, "amp": float, "snr": float},
            "harmonics": [{"freq": float, "amp": float, "order": int}, ...],
            "sidebands": [{"freq": float, "amp": float, "offset_hz": float}, ...],
        }
    """
    result = {
        "fundamental": None,
        "harmonics": [],
        "sidebands": [],
    }
    df = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0
    background = np.median(amps)

    # 搜索基频
    mask = np.abs(freqs - target_freq) <= tolerance_hz
    if np.any(mask):
        idx = np.argmax(amps[mask])
        abs_idx = np.where(mask)[0][idx]
        result["fundamental"] = {
            "freq": float(freqs[abs_idx]),
            "amp": float(amps[abs_idx]),
            "snr": float(amps[abs_idx] / background) if background > 0 else 0.0,
        }

    # 搜索谐波
    for h in range(2, n_harmonics + 1):
        hf = target_freq * h
        if hf > freqs[-1]:
            break
        hmask = np.abs(freqs - hf) <= tolerance_hz
        if np.any(hmask):
            idx = np.argmax(amps[hmask])
            abs_idx = np.where(hmask)[0][idx]
            result["harmonics"].append({
                "freq": float(freqs[abs_idx]),
                "amp": float(amps[abs_idx]),
                "order": h,
            })

    return result


def compute_snr(peak_amp: float, spectrum: np.ndarray, method: str = "median") -> float:
    """计算峰值信噪比"""
    if method == "median":
        background = np.median(spectrum)
    elif method == "mean":
        background = np.mean(spectrum)
    else:
        background = np.percentile(spectrum, 75)
    if background <= 0:
        background = 1e-12
    return peak_amp / background


def kurtosis(signal: np.ndarray, fisher: bool = False) -> float:
    """计算峭度，fisher=False 时正态分布=3"""
    from scipy import stats
    return float(stats.kurtosis(signal, fisher=fisher))


def skewness(signal: np.ndarray) -> float:
    """计算偏度"""
    from scipy import stats
    return float(stats.skew(signal))


def rms(signal: np.ndarray) -> float:
    """均方根"""
    return float(np.sqrt(np.mean(signal ** 2)))


def peak_value(signal: np.ndarray) -> float:
    """峰值（最大绝对值）"""
    return float(np.max(np.abs(signal)))


def crest_factor(signal: np.ndarray) -> float:
    """峰值因子 = Peak / RMS"""
    r = rms(signal)
    return peak_value(signal) / r if r > 1e-12 else 0.0


def parabolic_interpolation(freqs, spectrum, idx):
    """抛物线插值精确定位谱峰频率"""
    if idx <= 0 or idx >= len(spectrum) - 1:
        return freqs[idx]
    alpha = spectrum[idx - 1]
    beta = spectrum[idx]
    gamma = spectrum[idx + 1]
    if beta <= max(alpha, gamma):
        return freqs[idx]
    p = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
    return float(freqs[idx] + p * (freqs[1] - freqs[0]))


def _band_energy(freq, amp, center: float, bandwidth: float) -> float:
    """计算指定频带能量"""
    freq = np.asarray(freq)
    amp = np.asarray(amp)
    mask = (freq >= center - bandwidth) & (freq <= center + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(amp[mask] ** 2))


def _order_band_energy(order_axis, spectrum, center_order: float, bandwidth: float) -> float:
    """计算指定阶次带能量"""
    order_axis = np.asarray(order_axis)
    spectrum = np.asarray(spectrum)
    mask = (order_axis >= center_order - bandwidth) & (order_axis <= center_order + bandwidth)
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum[mask] ** 2))


def estimate_rot_freq_envelope(
    sig: np.ndarray, fs: float,
    f_center: float,
    bw: float = 60.0,
    freq_range: Tuple[float, float] = (10, 100)
) -> Optional[float]:
    """在指定中心频率附近做带通滤波+包络解调，返回包络谱峰值频率"""
    low = max(10.0, f_center - bw)
    high = min(fs / 2 - 10.0, f_center + bw)
    b, a = scipy_signal.butter(4, [low / (fs / 2), high / (fs / 2)], btype='band')
    bp_sig = scipy_signal.filtfilt(b, a, sig)
    envelope = np.abs(scipy_signal.hilbert(bp_sig))
    envelope = envelope - np.mean(envelope)
    env_spec = np.abs(rfft(envelope))
    env_freqs = rfftfreq(len(envelope), d=1.0 / fs)
    mask = (env_freqs >= freq_range[0]) & (env_freqs <= freq_range[1])
    if not np.any(mask):
        return None
    peak_idx = np.argmax(env_spec[mask])
    return float(env_freqs[mask][peak_idx])


def estimate_rot_freq_spectrum(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    harmonics_num: int = 5,
    bandwidth_hz: float = 3.0,
    smooth_win_hz: float = 1.5,
) -> float:
    """
    通过频谱峰值法估计转频（改进版：平滑 + 频带积分 + 插值 + 包络解调辅助）
    针对齿轮箱等啮合频率强、基频弱的数据，引入包络解调和齿数整数验证启发式。
    """
    N = len(sig)
    spectrum = np.abs(rfft(sig))
    freqs = rfftfreq(N, d=1.0 / fs)
    df = freqs[1] - freqs[0]

    # 1. 谱平滑：抑制随机噪声尖峰
    if smooth_win_hz > 0 and df > 0:
        kernel_size = max(1, int(round(smooth_win_hz / df)))
        if kernel_size > 1:
            kernel = np.ones(kernel_size) / kernel_size
            spectrum = np.convolve(spectrum, kernel, mode='same')

    # 2. 归一化
    spectrum_norm = spectrum / (spectrum.max() + 1e-10)

    mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
    search_freqs = freqs[mask]
    search_spectrum = spectrum_norm[mask]

    if len(search_freqs) == 0:
        return freq_range[0]

    bw_bins = max(1, int(round(bandwidth_hz / df / 2)))
    # 降低阈值，让弱基频也能参与竞争
    min_base_energy = 0.015 * (2 * bw_bins + 1)

    best_freq_spec = search_freqs[0]
    best_energy = 0.0
    best_idx_global = None

    # 预收集子谐波惩罚信息（避免在循环中重复计算）
    def _sub_harmonic_penalty(f_candidate: float) -> float:
        """如果 f_candidate 的子谐波（f/2, f/3, f/4, f/5）也有明显能量，说明它可能是谐波而非基频"""
        penalty = 0.0
        for div in [2, 3, 4, 5]:
            sub_f = f_candidate / div
            if sub_f < freq_range[0]:
                continue
            idx_sub = np.argmin(np.abs(freqs - sub_f))
            band_sub = spectrum_norm[
                max(0, idx_sub - bw_bins):min(len(spectrum), idx_sub + bw_bins + 1)
            ]
            sub_energy = float(np.sum(band_sub))
            if sub_energy > min_base_energy * 0.6:
                # 子谐波能量越强，惩罚越大；div 越大惩罚越小
                penalty += sub_energy * (1.0 / div) * 0.5
        return penalty

    for f in search_freqs:
        idx_base = np.argmin(np.abs(freqs - f))
        base_band = spectrum_norm[
            max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)
        ]
        base_energy = float(np.sum(base_band))
        if base_energy < min_base_energy:
            continue

        energy = 0.0
        for h in range(1, harmonics_num + 1):
            harmonic_freq = f * h
            if harmonic_freq > fs / 2:
                break
            idx = np.argmin(np.abs(freqs - harmonic_freq))
            band = spectrum_norm[
                max(0, idx - bw_bins):min(len(spectrum), idx + bw_bins + 1)
            ]
            weight = 1.0 / h
            energy += float(np.sum(band)) * weight

        energy -= _sub_harmonic_penalty(f)

        if energy > best_energy:
            best_energy = energy
            best_freq_spec = f
            best_idx_global = idx_base

    if best_energy == 0.0:
        # fallback：搜索范围内最强峰
        best_local_idx = int(np.argmax(search_spectrum))
        best_idx_global = int(np.argmin(np.abs(freqs - search_freqs[best_local_idx])))
        best_freq_spec = freqs[best_idx_global]
    else:
        best_freq_spec = parabolic_interpolation(freqs, spectrum, best_idx_global)

    # 记录 best_freq 的基频能量（用于子谐波后处理判断）
    best_base_energy = float(np.sum(spectrum_norm[
        max(0, best_idx_global - bw_bins):min(len(spectrum), best_idx_global + bw_bins + 1)
    ])) if best_idx_global is not None else 0.0

    # ---------- 子谐波后处理：防止谐波冒充基频 ----------
    # 如果 best_freq 是某个较低频率的整数倍谐波，且该较低频率也有明显能量，
    # 则优先选择较低频率作为真实基频（常见于轴承数据基频弱、谐波强的情况）
    for div in [5, 4, 3, 2]:
        candidate_base = best_freq_spec / div
        if candidate_base < freq_range[0]:
            continue
        idx_base = np.argmin(np.abs(freqs - candidate_base))
        base_band = spectrum_norm[
            max(0, idx_base - bw_bins):min(len(spectrum), idx_base + bw_bins + 1)
        ]
        base_energy = float(np.sum(base_band))
        # 条件1：候选基频能量不能仅由噪声构成
        if base_energy < min_base_energy * 0.2:
            continue
        # 条件2：候选基频能量应占 best_freq 能量的显著比例，
        #        防止在纯正弦波等 best_freq 本身极强的情况下误修正
        if base_energy < best_base_energy * 0.12:
            continue
        ratio = best_freq_spec / candidate_base
        if abs(ratio - round(ratio)) < 0.12:
            # 验证该候选基频的谐波能量是否也足够可观
            # 注意：跳过 h=div，因为该谐波就是当前的 best_freq 本身，
            # 不能让它成为"自我证明"的循环依据
            base_harmonic_energy = 0.0
            for h in range(1, harmonics_num + 1):
                if h == div:
                    continue
                hf = candidate_base * h
                if hf > fs / 2:
                    break
                idx_h = np.argmin(np.abs(freqs - hf))
                band_h = spectrum_norm[
                    max(0, idx_h - bw_bins):min(len(spectrum), idx_h + bw_bins + 1)
                ]
                base_harmonic_energy += float(np.sum(band_h)) * (1.0 / h)
            if base_harmonic_energy > best_energy * 0.15:
                best_freq_spec = parabolic_interpolation(freqs, spectrum, idx_base)
                best_idx_global = idx_base
                break

    # ---------- 包络解调辅助 ----------
    # 对啮合频率常见区域（200~500Hz）和全局高频峰做包络解调，收集候选
    candidates = [(best_freq_spec, "spectrum")]

    # 中频带（200~500Hz）：常见啮合频率区域
    mid_mask = (freqs >= 200) & (freqs <= 500)
    if np.any(mid_mask):
        mid_peak = freqs[mid_mask][np.argmax(spectrum[mid_mask])]
        env_est = estimate_rot_freq_envelope(sig, fs, mid_peak, freq_range=freq_range)
        if env_est:
            candidates.append((env_est, "envelope_mesh"))

    # 全局高频最强峰（100Hz ~ fs/4）
    high_mask = (freqs >= 100) & (freqs <= fs / 4)
    if np.any(high_mask):
        top_idx = np.argmax(spectrum[high_mask])
        high_peak = freqs[high_mask][top_idx]
        env_est = estimate_rot_freq_envelope(sig, fs, high_peak, freq_range=freq_range)
        if env_est:
            candidates.append((env_est, "envelope_high"))

    # ---------- 启发式仲裁 ----------
    # 优先选择通过"齿数整数"验证的包络法候选：
    # 如果带通中心频率 / 候选转频 ≈ 整数，且齿数在合理范围（8~50），
    # 说明该候选与啮合频率强相关，可信度最高。
    for f_est, method in candidates:
        if method.startswith("envelope"):
            # 0) 频谱基频支持验证：包络候选必须在原始频谱中有足够基频能量，
            #    防止带通滤波在噪声峰上产生虚假包络峰值
            idx_env = np.argmin(np.abs(freqs - f_est))
            env_band = spectrum_norm[
                max(0, idx_env - bw_bins):min(len(spectrum), idx_env + bw_bins + 1)
            ]
            env_base_energy = float(np.sum(env_band))
            if env_base_energy < min_base_energy * 0.3:
                continue

            # 1) 齿数整数验证
            if method == "envelope_mesh":
                f_center = freqs[mid_mask][np.argmax(spectrum[mid_mask])]
            else:
                f_center = freqs[high_mask][np.argmax(spectrum[high_mask])]
            teeth = f_center / f_est
            teeth_rounded = round(teeth)
            if abs(teeth - teeth_rounded) < 0.30 and 10 <= teeth_rounded <= 50:
                return float(f_est)

    # 没有通过齿数验证的包络候选，fallback 到频谱法
    return float(best_freq_spec)


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


def _compute_order_spectrum_multi_frame(
    sig: np.ndarray, fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    samples_per_rev: int = 1024,
    max_order: int = 50,
    frame_duration: float = 1.0,
    overlap: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """
    短时/分帧阶次跟踪（自适应多帧平均）
    适用于转速缓慢变化的工况。
    """
    frame_len = int(frame_duration * fs)
    hop = int(frame_len * (1 - overlap))

    # 如果信号比一帧还短，直接 fallback 到单帧
    if frame_len >= len(sig):
        rot_freq = estimate_rot_freq_spectrum(sig, fs, freq_range)
        order_axis, spectrum = _compute_order_spectrum(sig, fs, rot_freq, samples_per_rev)
        mask = order_axis <= max_order
        return order_axis[mask], spectrum[mask], float(rot_freq), 0.0

    frames = []
    rot_freqs = []

    start = 0
    while start + frame_len <= len(sig):
        frame = sig[start:start + frame_len]
        rot_freq = estimate_rot_freq_spectrum(frame, fs, freq_range)
        rot_freqs.append(rot_freq)
        frames.append(frame)
        start += hop

    rot_freqs_arr = np.array(rot_freqs)
    median_rf = float(np.median(rot_freqs_arr))
    mad = float(np.median(np.abs(rot_freqs_arr - median_rf)))
    if mad < 1e-6:
        mad = 1e-6

    # MAD 离群值剔除：偏离中位数超过 2.5 个 MAD 的帧扔掉
    valid_mask = np.abs(rot_freqs_arr - median_rf) <= 2.5 * mad
    valid_indices = np.where(valid_mask)[0]

    if len(valid_indices) == 0:
        valid_indices = np.arange(len(rot_freqs_arr))

    # 公共阶次轴
    common_orders = np.linspace(0, max_order, samples_per_rev)

    spectra_list = []
    for idx in valid_indices:
        frame = frames[idx]
        rf = rot_freqs_arr[idx]

        sig_order, _ = _order_tracking(frame, fs, rf, samples_per_rev)
        sig_order = sig_order - sig_order.mean()
        N = len(sig_order)
        if N < 10:
            continue

        window = np.hanning(N)
        sig_windowed = sig_order * window
        amplitude_scale = np.sqrt(N / np.sum(window ** 2))
        spectrum = np.abs(rfft(sig_windowed)) * amplitude_scale

        # 该帧阶次轴
        duration = len(frame) / fs
        num_revs = duration * rf
        orders_frame = np.arange(len(spectrum)) / num_revs

        # 插值到公共阶次轴
        spectrum_interp = np.interp(
            common_orders,
            orders_frame,
            spectrum,
            left=0.0,
            right=0.0
        )
        spectra_list.append(spectrum_interp)

    if not spectra_list:
        # fallback
        rot_freq = estimate_rot_freq_spectrum(sig, fs, freq_range)
        order_axis, spectrum = _compute_order_spectrum(sig, fs, rot_freq, samples_per_rev)
        mask = order_axis <= max_order
        return order_axis[mask], spectrum[mask], float(rot_freq), 0.0

    avg_spectrum = np.mean(spectra_list, axis=0)
    std_rf = float(np.std(rot_freqs_arr[valid_indices]))

    return common_orders, avg_spectrum, median_rf, std_rf


def _compute_order_spectrum_varying_speed(
    sig: np.ndarray,
    fs: float,
    freq_range: Tuple[float, float] = (10, 100),
    samples_per_rev: int = 1024,
    max_order: int = 50,
    nperseg: int = 512,
    noverlap: int = 384,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """
    变速工况阶次跟踪（基于 STFT 瞬时频率积分 + 等角度重采样）

    适用于转速剧烈变化（如启停机、扫频）的信号。
    核心思想：
      1. STFT 时频谱峰值追踪得到瞬时频率 f_inst(t)
      2. 对 f_inst 做 Savitzky-Golay 平滑去噪
      3. 数值积分得到瞬时相位 phi(t) = 2*pi * cumsum(f_inst) * dt
      4. 在等相位点（等角度）重采样 → 角域信号
      5. FFT 得到阶次谱

    Args:
        sig: 时域信号
        fs: 采样率
        freq_range: 转频搜索范围
        samples_per_rev: 每转采样点数（角域分辨率）
        max_order: 返回最大阶次
        nperseg: STFT 窗口长度
        noverlap: STFT 重叠长度

    Returns:
        (orders, spectrum, median_rot_freq, rot_freq_std)
    """
    import numpy as np
    from scipy import signal as scipy_signal
    from scipy.fft import rfft

    arr = np.array(sig, dtype=np.float64)

    # 1. STFT 时频分析
    f, t, Zxx = scipy_signal.stft(arr, fs=fs, nperseg=nperseg, noverlap=noverlap)
    magnitude = np.abs(Zxx)

    # 2. 在 freq_range 内追踪每个时间片的峰值频率（瞬时频率）
    freq_mask = (f >= freq_range[0]) & (f <= freq_range[1])
    search_f = f[freq_mask]
    search_mag = magnitude[freq_mask, :]

    if search_f.size == 0 or search_mag.shape[1] == 0:
        # fallback 到单帧
        rot_freq = estimate_rot_freq_spectrum(arr, fs, freq_range)
        order_axis, spectrum = _compute_order_spectrum(arr, fs, rot_freq, samples_per_rev)
        mask = order_axis <= max_order
        return order_axis[mask], spectrum[mask], float(rot_freq), 0.0

    inst_freq = np.array([
        float(search_f[np.argmax(search_mag[:, i])])
        for i in range(search_mag.shape[1])
    ])

    # 3. 平滑瞬时频率（Savitzky-Golay，抑制 STFT 峰值噪声）
    sg_win = min(11, len(inst_freq) // 2 * 2 + 1)
    if sg_win >= 5:
        inst_freq = scipy_signal.savgol_filter(inst_freq, sg_win, 3)

    # 4. 插值到每个采样点
    times_stft = t
    times_sig = np.arange(len(arr)) / fs
    inst_freq_per_sample = np.interp(
        times_sig, times_stft, inst_freq,
        left=inst_freq[0], right=inst_freq[-1]
    )

    # 5. 数值积分得到瞬时相位
    dt = 1.0 / fs
    inst_phase = 2.0 * np.pi * np.cumsum(inst_freq_per_sample) * dt

    # 6. 等相位（等角度）重采样
    total_revs = inst_phase[-1] / (2.0 * np.pi)
    n_points = max(10, int(total_revs * samples_per_rev))
    target_phase = np.linspace(0, inst_phase[-1], n_points, endpoint=False)
    sig_order = np.interp(target_phase, inst_phase, arr, left=arr[0], right=arr[-1])
    sig_order = sig_order - np.mean(sig_order)

    # 7. FFT 阶次谱
    N = len(sig_order)
    window = np.hanning(N)
    sig_windowed = sig_order * window
    amplitude_scale = np.sqrt(N / np.sum(window ** 2))
    spectrum = np.abs(rfft(sig_windowed)) * amplitude_scale

    # 阶次轴：每阶对应一个转频倍数
    orders = np.arange(len(spectrum)) / total_revs
    mask = orders <= max_order

    median_rf = float(np.median(inst_freq))
    std_rf = float(np.std(inst_freq))

    return orders[mask], spectrum[mask], median_rf, std_rf
