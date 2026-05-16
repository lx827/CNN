"""
评价框架通用工具函数
"""
import json
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats

warnings.filterwarnings("ignore")

# matplotlib设置
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "KaiTi", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

from .config import CACHE_DIR, OUTPUT_DIR, HEALTH_THRESHOLD, MAX_SAMPLES


# ═══════════════════════════════════════════════════════════
# 信号质量指标
# ═══════════════════════════════════════════════════════════

def compute_snr_db(clean: np.ndarray, noisy: np.ndarray) -> float:
    """计算信噪比 (dB)"""
    noise = noisy - clean
    signal_power = np.mean(clean ** 2)
    noise_power = np.mean(noise ** 2)
    if noise_power < 1e-18:
        return 100.0
    return 10.0 * np.log10(signal_power / noise_power)


def compute_mse(clean: np.ndarray, estimated: np.ndarray) -> float:
    """计算均方误差"""
    return float(np.mean((clean - estimated) ** 2))


def compute_correlation(clean: np.ndarray, estimated: np.ndarray) -> float:
    """计算Pearson相关系数"""
    if len(clean) != len(estimated):
        estimated = estimated[:len(clean)]
    c = np.corrcoef(clean, estimated)[0, 1]
    return float(c) if not np.isnan(c) else 0.0


def add_awgn(signal: np.ndarray, target_snr_db: float) -> np.ndarray:
    """添加加性高斯白噪声"""
    sig_power = np.mean(signal ** 2)
    noise_power = sig_power / (10 ** (target_snr_db / 10.0))
    noise = np.random.normal(0, np.sqrt(noise_power), len(signal))
    return signal + noise


# ═══════════════════════════════════════════════════════════
# 谱分析辅助
# ═══════════════════════════════════════════════════════════

def estimate_fault_freq_snr(envelope_freq, envelope_amp, rot_freq, target_freq_coeff):
    """估计特定故障频率在包络谱中的SNR

    修复: 背景估计排除峰值本身及其紧邻邻域(±3%)，避免SNR被系统性低估。
    """
    if rot_freq is None or rot_freq <= 0 or not len(envelope_freq):
        return 0.0
    target_freq = target_freq_coeff * rot_freq
    freqs = np.array(envelope_freq)
    amps = np.array(envelope_amp)
    if len(freqs) == 0:
        return 0.0
    idx = np.argmin(np.abs(freqs - target_freq))
    peak_amp = amps[idx]

    # 整个 ±10% 频带
    band_mask = (freqs >= target_freq * 0.9) & (freqs <= target_freq * 1.1)
    # 排除峰值本身 ±3%（避免背景包含峰值）
    exclude_mask = np.abs(freqs - target_freq) < (target_freq * 0.03)
    background_mask = band_mask & (~exclude_mask)

    if np.sum(background_mask) <= 0:
        # 无可用背景区域，退化为整体谱均值（仍排除峰值）
        bg_amps = amps[~exclude_mask]
        background = np.mean(bg_amps) if len(bg_amps) > 0 else np.mean(amps)
    else:
        background = np.mean(amps[background_mask])

    if background < 1e-12:
        background = 1e-12
    return float(peak_amp / background)


def count_harmonics(envelope_freq, envelope_amp, rot_freq, max_harmonics=5, threshold=2.0):
    """计数检出的谐波数"""
    if rot_freq is None or rot_freq <= 0:
        return 0
    freqs = np.array(envelope_freq)
    amps = np.array(envelope_amp)
    if len(freqs) == 0:
        return 0
    count = 0
    for n in range(1, max_harmonics + 1):
        f_target = n * rot_freq
        if f_target > freqs[-1]:
            break
        idx = np.argmin(np.abs(freqs - f_target))
        peak = amps[idx]
        band = (freqs >= f_target * 0.85) & (freqs <= f_target * 1.15)
        bg = np.mean(amps[band]) if np.sum(band) > 0 else 1e-12
        if bg < 1e-12:
            bg = 1e-12
        if peak / bg > threshold:
            count += 1
    return count


def compute_peak_clarity(envelope_amp):
    """谱峰清晰度"""
    if len(envelope_amp) < 2:
        return 1.0
    amps = np.array(envelope_amp)
    sorted_amps = np.sort(amps)[::-1]
    if sorted_amps[1] < 1e-12:
        return sorted_amps[0] / 1e-12
    return float(sorted_amps[0] / sorted_amps[1])


# ═══════════════════════════════════════════════════════════
# 分类与统计
# ═══════════════════════════════════════════════════════════

def health_score_to_binary(hs: int, threshold: int = HEALTH_THRESHOLD) -> int:
    """健康度转二分类：1=异常, 0=正常"""
    return 1 if hs < threshold else 0


def compute_classification_metrics(health_scores: Dict[str, List[int]]) -> Dict[str, Any]:
    """
    从健康度分数计算分类指标
    health_scores: {label: [hs1, hs2, ...]}
    """
    healthy_scores = health_scores.get("healthy", [])
    fault_scores = []
    for label, scores in health_scores.items():
        if label != "healthy":
            fault_scores.extend(scores)

    if not healthy_scores or not fault_scores:
        return {}

    y_true = [0] * len(healthy_scores) + [1] * len(fault_scores)
    y_pred = [health_score_to_binary(hs) for hs in healthy_scores + fault_scores]

    tp = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 1)
    fp = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 1)
    tn = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 0)
    fn = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0.0

    healthy_mean = np.mean(healthy_scores)
    fault_mean = np.mean(fault_scores)
    separation = healthy_mean - fault_mean

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1_score": round(f1, 4),
        "detection_rate": round(recall, 4),
        "false_alarm_rate": round(1.0 - specificity, 4),
        "separation": round(separation, 2),
        "healthy_mean": round(healthy_mean, 2),
        "fault_mean": round(fault_mean, 2),
    }


def wilcoxon_test(healthy_scores: List[float], fault_scores: List[float]) -> Dict:
    """Wilcoxon秩和检验"""
    if len(healthy_scores) < 3 or len(fault_scores) < 3:
        return {"statistic": 0.0, "pvalue": 1.0, "significant": False}
    try:
        stat, pval = stats.ranksums(healthy_scores, fault_scores)
        return {
            "statistic": round(float(stat), 4),
            "pvalue": round(float(pval), 6),
            "significant": pval < 0.05,
        }
    except Exception:
        return {"statistic": 0.0, "pvalue": 1.0, "significant": False}


def compute_auc_manual(y_true: List[int], y_scores: List[float]) -> float:
    """手动计算 ROC-AUC（Mann-Whitney U 统计量），无需 sklearn"""
    pos_scores = [s for s, t in zip(y_scores, y_true) if t == 1]
    neg_scores = [s for s, t in zip(y_scores, y_true) if t == 0]
    if not pos_scores or not neg_scores:
        return 0.5
    # Mann-Whitney U
    u_stat = sum(1 for ps in pos_scores for ns in neg_scores if ps > ns) + \
             0.5 * sum(1 for ps in pos_scores for ns in neg_scores if ps == ns)
    return u_stat / (len(pos_scores) * len(neg_scores))


def compute_excess_kurtosis(signal: np.ndarray) -> float:
    """计算 excess kurtosis（正态分布 = 0），与 scipy.stats.kurtosis 一致"""
    x = np.asarray(signal, dtype=np.float64)
    if len(x) < 4:
        return 0.0
    mu = np.mean(x)
    sigma2 = np.var(x)
    if sigma2 < 1e-18:
        return 0.0
    return float(np.mean((x - mu) ** 4) / (sigma2 ** 2) - 3.0)


# ═══════════════════════════════════════════════════════════
# 缓存与IO
# ═══════════════════════════════════════════════════════════

def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def save_cache(name: str, data: Any):
    try:
        with open(cache_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"[WARN] 缓存保存失败 {name}: {e}")


def load_cache(name: str) -> Optional[Any]:
    cp = cache_path(name)
    if cp.exists():
        try:
            with open(cp, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_figure(fig, name: str, subdir: str = ""):
    """保存图片"""
    d = OUTPUT_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def load_npy(path: Path, max_samples: int = MAX_SAMPLES) -> np.ndarray:
    """加载npy文件并截断"""
    data = np.load(path)
    if len(data) > max_samples:
        data = data[:max_samples]
    return np.array(data, dtype=np.float64)
