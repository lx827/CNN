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


# ═══════════════════════════════════════════════════════════
# 论文级分类指标（新增）
# ═══════════════════════════════════════════════════════════

def compute_confusion_matrix(y_true: List[str], y_pred: List[str], labels: List[str]) -> np.ndarray:
    """计算多分类混淆矩阵"""
    n = len(labels)
    cm = np.zeros((n, n), dtype=int)
    label_to_idx = {l: i for i, l in enumerate(labels)}
    for yt, yp in zip(y_true, y_pred):
        i = label_to_idx.get(yt, -1)
        j = label_to_idx.get(yp, -1)
        if i >= 0 and j >= 0:
            cm[i, j] += 1
    return cm


def compute_balanced_accuracy(y_true: List[str], y_pred: List[str], labels: List[str]) -> float:
    """计算 Balanced Accuracy = (TPR + TNR) / 2 的多分类平均"""
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    n = len(labels)
    per_class_tpr = []
    per_class_tnr = []
    for i in range(n):
        tp = cm[i, i]
        fn = sum(cm[i, :]) - tp
        fp = sum(cm[:, i]) - tp
        tn = sum(cm) - tp - fn - fp
        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        per_class_tpr.append(tpr)
        per_class_tnr.append(tnr)
    return float(np.mean(per_class_tpr) + np.mean(per_class_tnr)) / 2


def compute_cohen_kappa(y_true: List[str], y_pred: List[str], labels: List[str]) -> float:
    """计算 Cohen's Kappa = (p_o - p_e) / (1 - p_e)"""
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    total = sum(cm)
    if total == 0:
        return 0.0
    p_o = sum(cm[i, i] for i in range(len(labels))) / total
    row_sums = [sum(cm[i, :]) for i in range(len(labels))]
    col_sums = [sum(cm[:, i]) for i in range(len(labels))]
    p_e = sum(r * c for r, c in zip(row_sums, col_sums)) / (total * total)
    if p_e >= 1.0:
        return 0.0
    return (p_o - p_e) / (1 - p_e)


def compute_mcc(y_true: List[str], y_pred: List[str], labels: List[str]) -> float:
    """计算多分类 MCC（基于全局混淆矩阵的公式）"""
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    n = len(labels)
    if n < 2:
        return 0.0
    # 多分类 MCC: (c * s - sum_k(p_k * t_k)) / sqrt((c^2 - sum(p_k^2)) * (s^2 - sum(t_k^2)))
    c = sum(cm)
    s = sum(cm[i, j] for i in range(n) for j in range(n) if i != j) + sum(cm[i, i] for i in range(n))
    # 简化: 使用二分类公式对每类 One-vs-Rest 取平均
    mccs = []
    for k in range(n):
        tp = cm[k, k]
        fn = sum(cm[k, :]) - tp
        fp = sum(cm[:, k]) - tp
        tn = c - tp - fn - fp
        denom = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        if denom < 1e-12:
            mccs.append(0.0)
        else:
            mccs.append((tp * tn - fp * fn) / denom)
    return float(np.mean(mccs))


def compute_macro_f1(y_true: List[str], y_pred: List[str], labels: List[str]) -> float:
    """计算 Macro-F1 = 每类F1的算术平均"""
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    f1s = []
    for i, lbl in enumerate(labels):
        tp = cm[i, i]
        fp = sum(cm[:, i]) - tp
        fn = sum(cm[i, :]) - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return float(np.mean(f1s))


def compute_weighted_f1(y_true: List[str], y_pred: List[str], labels: List[str]) -> float:
    """计算 Weighted-F1 = 按样本数加权平均"""
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    total = sum(cm)
    if total == 0:
        return 0.0
    f1s = []
    weights = []
    for i, lbl in enumerate(labels):
        n_c = sum(cm[i, :])
        tp = cm[i, i]
        fp = sum(cm[:, i]) - tp
        fn = sum(cm[i, :]) - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
        weights.append(n_c / total)
    return float(sum(f1 * w for f1, w in zip(f1s, weights)))


def compute_fdr_far_mdr_fia(y_true: List[str], y_pred: List[str], labels: List[str]) -> Dict[str, float]:
    """计算 FDD 专用指标: FDR, FAR, MDR, FIA, Detection Score"""
    healthy_label = "healthy"
    fault_labels = [l for l in labels if l != healthy_label]
    cm = compute_confusion_matrix(y_true, y_pred, labels)
    total = sum(cm)

    # 全局二分类视角
    tp = sum(cm[i, i] for i, l in enumerate(labels) if l != healthy_label)
    fn = sum(sum(cm[i, :]) - cm[i, i] for i, l in enumerate(labels) if l != healthy_label)
    fp = sum(sum(cm[:, i]) - cm[i, i] for i, l in enumerate(labels) if l != healthy_label)
    tn = cm[labels.index(healthy_label), labels.index(healthy_label)] if healthy_label in labels else 0

    fdr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    far = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    mdr = fn / (tp + fn) if (tp + fn) > 0 else 0.0
    # FIA: 正确隔离数 / 总故障数
    fia = tp / (tp + fn) if (tp + fn) > 0 else 0.0  # 同 FDR 但含义不同
    detection_score = fdr - far

    return {
        "fdr": round(fdr, 4),
        "far": round(far, 4),
        "mdr": round(mdr, 4),
        "fia": round(fia, 4),
        "detection_score": round(detection_score, 4),
    }


# ═══════════════════════════════════════════════════════════
# ROC / PR 曲线计算
# ═══════════════════════════════════════════════════════════

def compute_roc_curve(y_true_binary: List[int], scores: List[float]) -> Dict[str, Any]:
    """计算单类 ROC 曲线 (FPR, TPR, AUC)"""
    if len(y_true_binary) != len(scores) or len(scores) < 2:
        return {"fpr": [], "tpr": [], "auc": 0.5}
    # 按分数降序排列
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    thresholds = [scores[i] for i in sorted_indices]
    y_sorted = [y_true_binary[i] for i in sorted_indices]

    total_pos = sum(y_sorted)
    total_neg = len(y_sorted) - total_pos
    if total_pos == 0 or total_neg == 0:
        return {"fpr": [0, 1], "tpr": [0, 1], "auc": 0.5}

    fpr_list = [0.0]
    tpr_list = [0.0]
    tp = 0
    fp = 0
    for y in y_sorted:
        if y == 1:
            tp += 1
        else:
            fp += 1
        fpr_list.append(fp / total_neg)
        tpr_list.append(tp / total_pos)

    # 计算 AUC (梯形法)
    auc = 0.0
    for i in range(1, len(fpr_list)):
        auc += (fpr_list[i] - fpr_list[i - 1]) * (tpr_list[i] + tpr_list[i - 1]) / 2

    return {"fpr": fpr_list, "tpr": tpr_list, "auc": round(auc, 4)}


def compute_pr_curve(y_true_binary: List[int], scores: List[float]) -> Dict[str, Any]:
    """计算单类 PR 曲线 (Recall, Precision, AUC)"""
    if len(y_true_binary) != len(scores) or len(scores) < 2:
        return {"recall": [], "precision": [], "auc": 0.0}
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    y_sorted = [y_true_binary[i] for i in sorted_indices]
    total_pos = sum(y_sorted)
    if total_pos == 0:
        return {"recall": [0, 1], "precision": [1, 0], "auc": 0.0}

    recall_list = [0.0]
    precision_list = [1.0]
    tp = 0
    fp = 0
    for y in y_sorted:
        if y == 1:
            tp += 1
        else:
            fp += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / total_pos
        recall_list.append(rec)
        precision_list.append(prec)

    # AUC-PR
    auc = 0.0
    for i in range(1, len(recall_list)):
        auc += (recall_list[i] - recall_list[i - 1]) * (precision_list[i] + precision_list[i - 1]) / 2

    return {"recall": recall_list, "precision": precision_list, "auc": round(auc, 4)}


def compute_multiclass_roc_pr(y_true: List[str], scores: List[float], labels: List[str]) -> Dict[str, Any]:
    """计算多分类 One-vs-Rest ROC 和 PR 曲线"""
    result = {"roc": {}, "pr": {}, "macro_auc_roc": 0.0, "macro_auc_pr": 0.0}
    auc_roc_list = []
    auc_pr_list = []
    for lbl in labels:
        y_binary = [1 if yt == lbl else 0 for yt in y_true]
        roc = compute_roc_curve(y_binary, scores)
        pr = compute_pr_curve(y_binary, scores)
        result["roc"][lbl] = roc
        result["pr"][lbl] = pr
        auc_roc_list.append(roc["auc"])
        auc_pr_list.append(pr["auc"])
    result["macro_auc_roc"] = round(float(np.mean(auc_roc_list)), 4)
    result["macro_auc_pr"] = round(float(np.mean(auc_pr_list)), 4)
    return result


# ═══════════════════════════════════════════════════════════
# 去噪补充指标
# ═══════════════════════════════════════════════════════════

def compute_psnr(clean: np.ndarray, denoised: np.ndarray) -> float:
    """计算 PSNR = 20 * log10(max(|x|) / sqrt(MSE))"""
    mse = float(np.mean((clean - denoised) ** 2))
    if mse < 1e-18:
        return 100.0
    max_val = float(np.max(np.abs(clean)))
    if max_val < 1e-18:
        return 0.0
    return 20.0 * np.log10(max_val / np.sqrt(mse))


def compute_prd(clean: np.ndarray, denoised: np.ndarray) -> float:
    """计算 PRD (百分比均方根差) = sqrt(sum((d-c)^2)) / sqrt(sum(c^2)) * 100"""
    diff_sq = float(np.sum((clean - denoised) ** 2))
    clean_sq = float(np.sum(clean ** 2))
    if clean_sq < 1e-18:
        return 100.0
    return float(np.sqrt(diff_sq / clean_sq) * 100)


def compute_ncc(clean: np.ndarray, denoised: np.ndarray) -> float:
    """计算归一化互相关 NCC"""
    if len(clean) != len(denoised):
        denoised = denoised[:len(clean)]
    c_mean = np.mean(clean)
    d_mean = np.mean(denoised)
    c_centered = clean - c_mean
    d_centered = denoised - d_mean
    denom = np.sqrt(np.sum(c_centered ** 2) * np.sum(d_centered ** 2))
    if denom < 1e-18:
        return 0.0
    return float(np.sum(c_centered * d_centered) / denom)


def compute_crest_factor(signal: np.ndarray) -> float:
    """计算峰值因子 = max(|x|) / RMS(x)"""
    rms = float(np.sqrt(np.mean(signal ** 2)))
    peak = float(np.max(np.abs(signal)))
    if rms < 1e-18:
        return 0.0
    return peak / rms


# ═══════════════════════════════════════════════════════════
# 健康度趋势指标 (PHM 领域)
# ═══════════════════════════════════════════════════════════

def compute_monotonicity(hi_series: List[float]) -> float:
    """计算 HI 单调性 Monotonicity = |#(d>0) - #(d<0)| / (K-1), 范围 [0,1]"""
    if len(hi_series) < 2:
        return 0.0
    diffs = [hi_series[i + 1] - hi_series[i] for i in range(len(hi_series) - 1)]
    pos_count = sum(1 for d in diffs if d > 0)
    neg_count = sum(1 for d in diffs if d < 0)
    return abs(pos_count - neg_count) / (len(hi_series) - 1)


def compute_trendability(hi_series: List[float], time_points: List[float]) -> float:
    """计算 HI 与时间的 Pearson 相关系数"""
    if len(hi_series) != len(time_points) or len(hi_series) < 3:
        return 0.0
    r, _ = stats.pearsonr(hi_series, time_points)
    return abs(float(r))


def compute_prognosability(hi_series_at_start: List[float], hi_series_at_end: List[float]) -> float:
    """计算 Prognosability = exp(-std(end_values) / mean(|start - end|))"""
    if not hi_series_at_end or not hi_series_at_start:
        return 0.0
    std_end = float(np.std(hi_series_at_end))
    diffs = [abs(s - e) for s, e in zip(hi_series_at_start, hi_series_at_end)]
    mean_diff = float(np.mean(diffs)) if diffs else 1e-12
    if mean_diff < 1e-12:
        return 1.0
    return float(np.exp(-std_end / mean_diff))


def compute_hi_robustness(hi_series: List[float], noise_std: float = 0.5) -> float:
    """计算 HI 对随机波动的鲁棒性（指数衰减平均）"""
    if len(hi_series) < 3:
        return 0.0
    diffs = [abs(hi_series[i + 1] - hi_series[i]) for i in range(len(hi_series) - 1)]
    mean_diff = float(np.mean(diffs))
    # 鲁棒性 = exp(-mean_diff / noise_std)
    if noise_std < 1e-12:
        return 0.0
    return float(np.exp(-mean_diff / noise_std))


def plot_confusion_matrix(cm: np.ndarray, labels: List[str], title: str,
                          subdir: str = "classification", normalize: bool = True) -> Path:
    """绘制并保存混淆矩阵图"""
    if normalize:
        cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
        cm_norm = np.nan_to_num(cm_norm)
        display_cm = cm_norm
        fmt = ".2f"
    else:
        display_cm = cm
        fmt = "d"

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.8), max(5, len(labels) * 0.7)))
    im = ax.imshow(display_cm, cmap="Blues", interpolation="nearest")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_title(title)
    ax.set_xlabel("预测标签")
    ax.set_ylabel("真实标签")

    for i in range(len(labels)):
        for j in range(len(labels)):
            text = format(display_cm[i, j], fmt)
            ax.text(j, i, text, ha="center", va="center",
                    color="white" if display_cm[i, j] > 0.5 else "black")

    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    path = save_figure(fig, f"confusion_matrix_{title.replace(' ', '_').lower()}.png", subdir)
    return path


def plot_roc_curves(roc_data: Dict[str, Dict], title: str, subdir: str = "classification") -> Path:
    """绘制多分类 ROC 曲线"""
    fig, ax = plt.subplots(figsize=(7, 6))
    for lbl, roc in roc_data.items():
        fpr = roc.get("fpr", [0, 1])
        tpr = roc.get("tpr", [0, 1])
        auc_val = roc.get("auc", 0.5)
        ax.plot(fpr, tpr, label=f"{lbl} (AUC={auc_val:.3f})")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="随机")
    ax.set_xlabel("FPR (虚警率)")
    ax.set_ylabel("TPR (检出率)")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    return save_figure(fig, f"roc_{title.replace(' ', '_').lower()}.png", subdir)


def plot_pr_curves(pr_data: Dict[str, Dict], title: str, subdir: str = "classification") -> Path:
    """绘制多分类 PR 曲线"""
    fig, ax = plt.subplots(figsize=(7, 6))
    for lbl, pr in pr_data.items():
        recall = pr.get("recall", [0, 1])
        precision = pr.get("precision", [1, 0])
        auc_val = pr.get("auc", 0.0)
        ax.plot(recall, precision, label=f"{lbl} (AUC={auc_val:.3f})")
    ax.set_xlabel("Recall (检出率)")
    ax.set_ylabel("Precision (精确率)")
    ax.set_title(title)
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    plt.tight_layout()
    return save_figure(fig, f"pr_{title.replace(' ', '_').lower()}.png", subdir)
