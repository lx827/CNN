"""
阶次跟踪算法模块

包含：
- 单帧阶次跟踪（恒定转速）
- 多帧平均阶次跟踪（转速缓变）
- 变速阶次跟踪（STFT + 等相位重采样）
"""
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft
from typing import Tuple

from .signal_utils import estimate_rot_freq_spectrum


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
