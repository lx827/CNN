"""
统一敏感分量选择模块 (Sensitive Component Selector)

为小波包节点、EMD IMF、VMD模态提供统一的评分与筛选策略，
避免各模块重复实现相似的选择逻辑。

参考: wavelet_and_modality_decomposition.md §13

评分公式:
    Score(s) = Σ w_m · normalize(I_m(s))

权重配置:
    轴承诊断: corr=0.30, kurt=0.45, env_entropy=0.15, energy=0.05, freq_match=0.05
    齿轮诊断: corr=0.20, kurt=0.30, env_entropy=0.10, energy=0.25, freq_match=0.15
"""
import numpy as np
from typing import Dict, List, Tuple, Optional


# ──────────────────────────────────────────────────────────
# 权重配置
# ──────────────────────────────────────────────────────────

BEARING_WEIGHTS: Dict[str, float] = {
    "corr": 0.30,        # 与原始信号的整体相关性
    "kurt": 0.45,        # 峭度（对冲击主导）
    "env_entropy": 0.15, # 包络熵（越小越周期性，反转）
    "energy": 0.05,      # 能量占比
    "freq_match": 0.05,  # 中心频率与目标频带的距离
}

GEAR_WEIGHTS: Dict[str, float] = {
    "corr": 0.20,
    "kurt": 0.30,
    "env_entropy": 0.10,
    "energy": 0.25,       # 齿轮诊断能量占比更重要
    "freq_match": 0.15,   # 齿轮诊断需要匹配啮合频率
}


# ──────────────────────────────────────────────────────────
# 基础指标计算
# ──────────────────────────────────────────────────────────

def compute_correlation(component: np.ndarray, original: np.ndarray) -> float:
    """互相关系数"""
    c = np.asarray(component, dtype=np.float64)
    o = np.asarray(original[:len(c)], dtype=np.float64)
    c_z = c - np.mean(c)
    o_z = o - np.mean(o)
    sc = np.std(c_z)
    so = np.std(o_z)
    if sc < 1e-12 or so < 1e-12:
        return 0.0
    return float(np.abs(np.corrcoef(c_z, o_z)[0, 1]))


def compute_excess_kurtosis(component: np.ndarray) -> float:
    """Excess kurtosis（正态=0）"""
    arr = np.asarray(component, dtype=np.float64)
    if len(arr) < 4:
        return 0.0
    mu = np.mean(arr)
    s2 = np.var(arr)
    if s2 < 1e-18:
        return 0.0
    return float(np.mean((arr - mu) ** 4) / (s2 ** 2) - 3.0)


def compute_envelope_entropy(component: np.ndarray) -> float:
    """包络 Shannon 熵（越小 → 周期性越强 → 故障信息越丰富）"""
    from scipy.signal import hilbert
    arr = np.asarray(component, dtype=np.float64)
    if len(arr) < 8:
        return 10.0  # 无意义，给大值使其不被选中
    env = np.abs(hilbert(arr))
    env = env - np.mean(env)
    env = np.abs(env) + 1e-12
    total = np.sum(env)
    probs = env / total
    probs = probs[probs > 1e-12]
    return float(-np.sum(probs * np.log2(probs)))


def compute_energy_ratio(component: np.ndarray, total_energy: float) -> float:
    """能量占比"""
    e = float(np.sum(np.asarray(component, dtype=np.float64) ** 2))
    return e / (total_energy + 1e-12)


def compute_center_freq(component: np.ndarray, fs: float) -> float:
    """分量中心频率（功率谱加权平均）"""
    arr = np.asarray(component, dtype=np.float64)
    N = len(arr)
    if N < 8:
        return 0.0
    spec = np.abs(np.fft.rfft(arr))
    freqs = np.fft.rfftfreq(N, 1.0 / fs)
    power = spec ** 2
    total = np.sum(power) + 1e-12
    return float(np.sum(freqs * power) / total)


def compute_freq_match_score(center_freq: float, target_freq: float) -> float:
    """中心频率与目标频率的匹配度（越近越高，返回 0~1）"""
    if target_freq <= 0 or center_freq <= 0:
        return 0.0
    delta = abs(center_freq - target_freq) / target_freq
    # delta < 0.05 → 1.0; delta > 0.5 → 0.0; 中间线性衰减
    return float(np.clip(1.0 - delta * 2.0, 0.0, 1.0))


# ──────────────────────────────────────────────────────────
# 综合评分
# ──────────────────────────────────────────────────────────

def _normalize(values: List[float]) -> List[float]:
    """Min-max 归一化到 [0, 1]，全相同时返回 [0.5]"""
    mn, mx = min(values), max(values)
    if mx - mn < 1e-12:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def score_components(
    components: List[np.ndarray],
    original: np.ndarray,
    fs: float,
    target_freq: float = 0.0,
    mode: str = "bearing",
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    对多个分量（WP节点/IMF/VMD模态）计算综合评分

    Args:
        components: 分量列表
        original: 原始信号
        fs: 采样率
        target_freq: 目标中心频率（啮合频率/共振频率），0=不使用频率匹配
        mode: "bearing" 或 "gear"，决定默认权重
        weights: 自定义权重覆盖默认值

    Returns:
        每个分量的评分详情:
        [
            {
                "index": int,
                "score": float,       # 综合评分
                "corr": float,
                "kurt": float,
                "env_entropy": float,
                "energy_ratio": float,
                "center_freq": float,
                "freq_match": float,
            },
            ...
        ]
    """
    w = weights or (BEARING_WEIGHTS if mode == "bearing" else GEAR_WEIGHTS)

    # 计算原始指标
    total_energy = float(np.sum(np.asarray(original, dtype=np.float64) ** 2))

    raw_corr = [compute_correlation(c, original) for c in components]
    raw_kurt = [compute_excess_kurtosis(c) for c in components]
    raw_env_ent = [compute_envelope_entropy(c) for c in components]
    raw_energy = [compute_energy_ratio(c, total_energy) for c in components]
    raw_center = [compute_center_freq(c, fs) for c in components]
    raw_freq_match = [compute_freq_match_score(cf, target_freq) for cf in raw_center]

    # 归一化（包络熵反转：越小越好 → 归一化后反转）
    norm_corr = _normalize(raw_corr)
    norm_kurt = _normalize(raw_kurt)
    norm_env_ent_inv = _normalize(raw_env_ent)  # 原始值越小越好 → 归一化后越大越差
    # 反转：1 - normalized，使小熵得分高
    norm_env_ent_inv = [1.0 - v for v in norm_env_ent_inv]
    norm_energy = _normalize(raw_energy)
    norm_freq_match = _normalize(raw_freq_match)

    scores = []
    for i in range(len(components)):
        s = (
            w.get("corr", 0) * norm_corr[i]
            + w.get("kurt", 0) * norm_kurt[i]
            + w.get("env_entropy", 0) * norm_env_ent_inv[i]
            + w.get("energy", 0) * norm_energy[i]
            + w.get("freq_match", 0) * norm_freq_match[i]
        )
        scores.append({
            "index": i,
            "score": round(s, 4),
            "corr": round(raw_corr[i], 4),
            "kurt": round(raw_kurt[i], 4),
            "env_entropy": round(raw_env_ent[i], 4),
            "energy_ratio": round(raw_energy[i], 4),
            "center_freq": round(raw_center[i], 2),
            "freq_match": round(raw_freq_match[i], 4),
        })

    return scores


def select_top_components(
    scored: List[Dict],
    top_n: int = 1,
    min_score: float = 0.0,
) -> List[int]:
    """选择评分最高的 top_n 个分量索引（得分 >= min_score）"""
    valid = [s for s in scored if s["score"] >= min_score]
    if not valid:
        # 回退：选最高评分的（不论阈值）
        valid = scored
    sorted_ = sorted(valid, key=lambda s: s["score"], reverse=True)
    return [s["index"] for s in sorted_[:top_n]]


# ──────────────────────────────────────────────────────────
# 便捷函数：按分量类型封装
# ──────────────────────────────────────────────────────────

def select_wp_sensitive_nodes(
    wp_coeffs: Dict[str, np.ndarray],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[str], List[Dict]]:
    """
    小波包节点敏感度选择

    Args:
        wp_coeffs: {节点路径: 系数数组}
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率（啮合频率/共振频率）
        top_n: 选择前N个

    Returns:
        (selected_paths, score_details)
    """
    paths = list(wp_coeffs.keys())
    components = [wp_coeffs[p] for p in paths]
    scored = score_components(components, original, fs, target_freq, mode)
    indices = select_top_components(scored, top_n)
    selected_paths = [paths[i] for i in indices]
    return selected_paths, scored


def select_emd_sensitive_imfs(
    imfs: List[np.ndarray],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[int], List[Dict]]:
    """
    EMD/CEEMDAN IMF 敏感度选择

    自动排除:
    - IMF0（极高频噪声，中心频率 > 0.4*fs）
    - 最后1~2个IMF（低频趋势，中心频率 < 2*rot_freq）

    Args:
        imfs: IMF列表
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率
        top_n: 选择前N个

    Returns:
        (selected_indices, score_details)
    """
    scored = score_components(imfs, original, fs, target_freq, mode)

    # 排除规则（参考 §13.2）
    for s in scored:
        i = s["index"]
        cf = s["center_freq"]
        # 排除极高频噪声层
        if i == 0 and cf > 0.4 * fs:
            s["score"] = 0.0
        # 排除低频趋势层（最后2个IMF，中心频率极低）
        if i >= len(imfs) - 2 and cf < max(target_freq * 2, 5.0):
            s["score"] *= 0.3  # 大幅降分而非直接排除（可能含齿轮信息）

    indices = select_top_components(scored, top_n)
    return indices, scored


def select_vmd_sensitive_modes(
    modes: List[np.ndarray],
    center_freqs: List[float],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[int], List[Dict]]:
    """
    VMD 模态敏感度选择

    利用 VMD 已知的中心频率信息增强 freq_match 评分

    Args:
        modes: VMD 模态列表
        center_freqs: 各模态中心频率（Hz）
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率
        top_n: 选择前N个

    Returns:
        (selected_indices, score_details)
    """
    scored = score_components(modes, original, fs, target_freq, mode)

    # 用 VMD 精确中心频率覆盖 estimate
    for s in scored:
        i = s["index"]
        cf_val = float(center_freqs[i]) if i < len(center_freqs) else 0.0
        if cf_val > 0:
            s["center_freq"] = round(cf_val, 2)
            s["freq_match"] = round(compute_freq_match_score(cf_val, target_freq), 4)

    # 重新计算综合评分（因为 freq_match 更新了）
    w = BEARING_WEIGHTS if mode == "bearing" else GEAR_WEIGHTS
    all_scores = [s["score"] for s in scored]
    norm_all = _normalize(all_scores)
    # 不重算全部，只在 freq_match 变化时局部调整
    # VMD 的 freq_match 更精确，信任它
    for s in scored:
        i = s["index"]
        # 补偿 freq_match 更新对总分的影响
        orig_match = compute_freq_match_score(compute_center_freq(modes[i], fs), target_freq)
        vmd_match = s["freq_match"]
        delta = (vmd_match - orig_match) * w.get("freq_match", 0)
        s["score"] = round(s["score"] + delta, 4)

    indices = select_top_components(scored, top_n)
    return indices, scored