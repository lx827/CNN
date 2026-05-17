# `signal_utils.py` — 信号工具

**对应源码**：`cloud/app/services/diagnosis/signal_utils.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `remove_dc` | `remove_dc(signal) -> np.ndarray` | 去直流 |
| `linear_detrend` | `linear_detrend(signal) -> np.ndarray` | 线性去趋势 |
| `prepare_signal` | `prepare_signal(signal, detrend=False) -> np.ndarray` | 信号预处理 |
| `bandpass_filter` | `bandpass_filter(signal, fs, low, high, order=4) -> np.ndarray` | Butterworth 带通 |
| `lowpass_filter` | `lowpass_filter(signal, fs, cutoff, order=4) -> np.ndarray` | Butterworth 低通 |
| `highpass_filter` | `highpass_filter(signal, fs, cutoff, order=4) -> np.ndarray` | Butterworth 高通 |
| `compute_fft_spectrum` | `compute_fft_spectrum(signal, fs) -> Tuple[np.ndarray, np.ndarray]` | FFT 频谱 |
| `compute_power_spectrum` | `compute_power_spectrum(signal, fs) -> Tuple` | 功率谱 |
| `find_peaks_in_spectrum` | `find_peaks_in_spectrum(freq, spectrum, target_freq, tolerance_percent=3.0, min_snr=3.0) -> Tuple` | 频谱峰值搜索 |
| `compute_snr` | `compute_snr(peak_amp, spectrum, method="median") -> float` | 峰值 SNR |
| `kurtosis` | `kurtosis(signal, fisher=False) -> float` | 峭度 |
| `rms` | `rms(signal) -> float` | RMS |
| `peak_value` | `peak_value(signal) -> float` | 峰值 |
| `crest_factor` | `crest_factor(signal) -> float` | 峰值因子 |
| `skewness` | `skewness(signal) -> float` | 偏度 |
| `estimate_rot_freq_spectrum` | `estimate_rot_freq_spectrum(signal, fs) -> float` | 频谱法估计转频 |
| `estimate_rot_freq_autocorr` | `estimate_rot_freq_autocorr(signal, fs) -> float` | 自相关法估计转频 |
| `estimate_rot_freq_envelope` | `estimate_rot_freq_envelope(signal, fs) -> float` | 包络法估计转频 |
| `zoom_fft_analysis` | `zoom_fft_analysis(signal, fs, center_freq, bandwidth, n_fft) -> Tuple` | ZOOM-FFT 细化谱 |
| `_band_energy` | `_band_energy(freq, amp, center, bandwidth) -> float` | 频带能量积分 |
