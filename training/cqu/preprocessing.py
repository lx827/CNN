"""10kHz现场波形转为8192Hz单通道O9窗口，不做单位换算或数据增强。"""

import csv
import hashlib
from pathlib import Path

import numpy as np
from scipy.signal import firwin, resample_poly


PROTOCOL = {
    "version": "cqu_o9_8192_window_zscore_v1",
    "source_sample_rate_hz": 10000,
    "target_sample_rate_hz": 8192,
    "resample_up": 512,
    "resample_down": 625,
    "resample_filter": {"design": "firwin", "numtaps": 62501,
                        "cutoff_hz": 4096, "design_sample_rate_hz": 5120000,
                        "window": ["kaiser", 8.6], "scale": True},
    "resample_padtype": "line",
    "resample_dc_policy": "subtract_full_record_mean_then_restore_after_resampling",
    "requested_start_seconds": 0.1,
    "target_start_sample": 819,
    "effective_start_seconds": 819 / 8192,
    "duration_seconds": 30,
    "window_samples": 4096,
    "stride_samples": 4096,
    "windows_per_record_channel": 60,
    "normalization": "per_window_population_zscore",
    "normalization_compute_dtype": "float64",
    "minimum_window_std_mps2": 1e-12,
    "output_dtype": "float32",
    "unit_before_normalization": "m/s²",
    "unit_conversion": "none_even_if_legacy_header_says_g",
    "augmentation": "none",
}


def read_record(path: Path, record: dict) -> np.ndarray:
    """返回[N,4]的float64原值；校验表头、点数和既有数值哈希。"""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = [cell.strip() for cell in next(reader)]
        first = next(reader)
    if header != record["original_header"]:
        raise ValueError(f"表头发生变化：{path.name}")
    if first[0].strip().rstrip(".") != record["capture_start_csv"]:
        raise ValueError(f"首行采集时间不符：{path.name}")
    values = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(1, 2, 3, 4),
                        encoding="utf-8-sig", dtype=np.float64)
    if values.shape != (record["samples_per_channel"], 4) or not np.isfinite(values).all():
        raise ValueError(f"点数、通道数或有限值检查失败：{path.name}")
    numeric_hash = hashlib.sha256(values.astype("<f8", copy=False).tobytes()).hexdigest()
    if numeric_hash != record["numeric_sha256_prior_qc"]:
        raise ValueError(f"数值与已核验原值不符：{path.name}")
    return values


def preprocess_channel(signal: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """整记录抗混叠重采样，再取统一30秒并切60个不重叠窗口。"""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1 or not np.isfinite(signal).all():
        raise ValueError("输入须为有限的单通道一维波形")
    if signal.size < 302000:
        raise ValueError("记录不足30.2秒，不能保留统一窗口和首尾余量")
    # 明确过渡带和阻带抑制；默认短滤波器在4.5kHz仍会留下较明显混叠。
    coefficients = firwin(62501, cutoff=4096, fs=5120000,
                         window=("kaiser", 8.6), scale=True)
    offset = signal.mean()
    resampled = resample_poly(signal - offset, up=512, down=625,
                              window=coefficients, padtype="line") + offset
    start = PROTOCOL["target_start_sample"]
    stop = start + 60 * 4096
    windows = resampled[start:stop].reshape(60, 4096)
    means = windows.mean(axis=1)
    stds = windows.std(axis=1, ddof=0)
    if np.any(stds <= PROTOCOL["minimum_window_std_mps2"]):
        raise ValueError("存在常量或近常量窗口，拒绝静默补零或改变标准化")
    normalized = ((windows - means[:, None]) / stds[:, None]).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError("预处理后出现非有限值")
    stats = []
    for index in range(60):
        target_start = start + index * 4096
        stats.append({
            "window_index": index,
            "target_start_sample": target_start,
            "target_stop_sample_exclusive": target_start + 4096,
            "source_start_sample_coordinate": target_start * 625 / 512,
            "start_seconds": target_start / 8192,
            "duration_seconds": 0.5,
            "resampled_mean_mps2": float(means[index]),
            "resampled_std_mps2": float(stds[index]),
            "resampled_rms_mps2": float(np.sqrt(np.mean(windows[index] ** 2))),
        })
    return normalized[:, None, :], stats
