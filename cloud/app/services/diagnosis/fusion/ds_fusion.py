"""
Dempster-Shafer 证据理论融合模块

将多种诊断算法的结果通过 D-S 证据理论进行融合，得到综合故障概率分布。
支持标准 Dempster 组合规则和 Murphy 平均修正法（用于高冲突场景）。

典型用法：
    from app.services.diagnosis.fusion import dempster_shafer_fusion

    method_results = {
        "none:envelope": {"confidence": 0.65, "abnormal": True, "hits": ["bpfo"]},
        "wavelet:cpw":   {"confidence": 0.55, "abnormal": True, "hits": ["bpfi"]},
        "none:advanced": {"confidence": 0.25, "abnormal": False, "hits": []},
    }
    result = dempster_shafer_fusion(method_results)
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════════════
# 默认故障类型集合（识别框架 Θ 的子集）
# ═══════════════════════════════════════════════════════════════
DEFAULT_FAULT_TYPES: List[str] = [
    "轴承外圈故障",
    "轴承内圈故障",
    "轴承滚动体故障",
    "齿轮磨损",
    "齿轮裂纹",
    "齿轮断齿",
    "正常",
]

# 轴承故障子集名称 → 对应的故障类型列表
BEARING_FAULT_NAMES: Dict[str, List[str]] = {
    "bpfo":  ["轴承外圈故障"],
    "bpfi":  ["轴承内圈故障"],
    "bsf":   ["轴承滚动体故障"],
    "ftf":   ["轴承滚动体故障"],  # 保持架故障归入滚动体
    "bpfo_stat":  ["轴承外圈故障"],
    "bpfi_stat":  ["轴承内圈故障"],
    "bsf_stat":   ["轴承滚动体故障"],
    "ftf_stat":   ["轴承滚动体故障"],
    "envelope_peak_snr":    ["轴承内圈故障", "轴承外圈故障"],
    "envelope_kurtosis":    ["轴承内圈故障", "轴承外圈故障"],
    "moderate_kurtosis":    ["轴承外圈故障"],
    "high_freq_ratio":      ["轴承内圈故障"],
    "peak_concentration":   ["轴承内圈故障", "轴承外圈故障"],
}

# 齿轮故障子集名称 → 对应的故障类型列表
GEAR_FAULT_NAMES: Dict[str, List[str]] = {
    "ser":                ["齿轮磨损", "齿轮断齿"],
    "sideband_count":     ["齿轮裂纹", "齿轮断齿"],
    "car":                ["齿轮磨损", "齿轮裂纹"],
    "fm4":                ["齿轮断齿", "齿轮裂纹"],
    "na4":                ["齿轮磨损"],
    "order_kurtosis":     ["齿轮断齿", "齿轮裂纹"],
    "order_peak_concentration": ["齿轮裂纹"],
    "fm0":                ["齿轮断齿"],
    "gear_mesh":          ["齿轮磨损"],
}

# 轴承方法标识关键词
BEARING_METHOD_KEYWORDS = frozenset({
    "envelope", "kurtogram", "cpw", "med", "teager",
    "spectral_kurtosis", "bearing",
})

# 齿轮方法标识关键词
GEAR_METHOD_KEYWORDS = frozenset({
    "standard", "advanced", "gear",
})


# ═══════════════════════════════════════════════════════════════
# 识别框架与基本概率分配
# ═══════════════════════════════════════════════════════════════

class EvidenceFrame:
    """D-S 识别框架，包含故障类型集合与 Θ（全集 = 不确定性）。

    Θ 在 D-S 理论中是识别框架的全集 Ω，包含所有可能的假设（故障类型）。
    m(Θ) 表示"不确定属于哪种具体故障，任何故障都有可能"。
    交集运算时 A∩Θ=A（Θ包含所有元素），这是正确融合的关键。
    """

    def __init__(self, fault_types: List[str]):
        # 去重并排序，保证一致性
        self.fault_types: List[str] = sorted(set(fault_types))
        # Θ = 全集 Ω，在代码中用 frozenset(fault_types) 表示
        # 这样 A∩Θ=A 自然成立（Θ包含所有元素）
        self.theta_label: str = "Θ"

    @property
    def all_elements(self) -> List[str]:
        """识别框架的全部元素（故障类型列表）。"""
        return self.fault_types

    def make_singleton_key(self, fault: str) -> FrozenSet[str]:
        """生成单元素焦元键。"""
        return frozenset({fault})

    def make_full_key(self) -> FrozenSet[str]:
        """Θ 焦元键（全集 = Ω = 所有故障类型的集合）。

        Θ 在 D-S 理论中表示"不确定性"，即所有可能假设的集合。
        用 frozenset(fault_types) 表示使得交集运算正确：
        A∩Θ=A, Θ∩Θ=Θ, A∩B=∅(当A,B无公共元素)。
        """
        return frozenset(self.fault_types)


class BPA:
    """基本概率分配（Basic Probability Assignment / Mass Function）。

    每个诊断方法的结果映射为 BPA，表示该方法对各故障类型的置信度。
    满足：sum(m(A)) = 1, m(∅) = 0
    """

    def __init__(self, frame: EvidenceFrame, masses: Dict[FrozenSet[str], float]):
        self.frame = frame
        self.masses: Dict[FrozenSet[str], float] = {}

        # 归一化：确保总和为 1，空集概率为 0
        total = sum(v for k, v in masses.items() if k != frozenset())
        if total > 0:
            for k, v in masses.items():
                if k == frozenset():
                    continue
                self.masses[k] = v / total
        # 补齐 Θ 使得总和为 1
        current_sum = sum(self.masses.values())
        theta_key = frame.make_full_key()
        if current_sum < 1.0:
            self.masses[theta_key] = 1.0 - current_sum
        elif current_sum > 1.0:
            # 重新归一化
            for k in self.masses:
                self.masses[k] /= current_sum

    def get_mass(self, focal: FrozenSet[str]) -> float:
        """获取指定焦元的质量。"""
        return self.masses.get(focal, 0.0)


# ═══════════════════════════════════════════════════════════════
# Dempster 组合规则
# ═══════════════════════════════════════════════════════════════

def dempster_combination(bpa1: BPA, bpa2: BPA) -> Tuple[BPA, float]:
    """
    标准 Dempster 组合规则，融合两个 BPA。

    m_12(A) = Σ_{B∩C=A} m1(B)·m2(C) / (1 - K)
    K = Σ_{B∩C=∅} m1(B)·m2(C)  （冲突系数）

    参数:
        bpa1: 第一个 BPA
        bpa2: 第二个 BPA

    返回:
        (融合后的 BPA, 冲突系数 K)
    """
    K = 0.0  # 冲突系数
    new_masses: Dict[FrozenSet[str], float] = {}

    for b_key, b_mass in bpa1.masses.items():
        for c_key, c_mass in bpa2.masses.items():
            intersect = b_key & c_key
            product = b_mass * c_mass

            if len(intersect) == 0:
                # B∩C=∅ → 冲突
                K += product
            else:
                # B∩C≠∅ → 累加到对应焦元
                new_masses[intersect] = new_masses.get(intersect, 0.0) + product

    # 归一化：除以 (1-K)
    if K >= 1.0:
        # 完全冲突，无法融合，保留 Θ
        theta_key = bpa1.frame.make_full_key()
        new_masses = {theta_key: 1.0}
        K = 1.0
    elif K > 0:
        denominator = 1.0 - K
        for key in new_masses:
            new_masses[key] /= denominator

    return BPA(bpa1.frame, new_masses), K


# ═══════════════════════════════════════════════════════════════
# Murphy 平均修正法
# ═══════════════════════════════════════════════════════════════

def murphy_average_combination(bpas: List[BPA]) -> Tuple[BPA, float]:
    """
    Murphy 平均法：先对所有 BPA 取平均，再与自身反复组合。

    用于高冲突场景（K > 0.8），标准 Dempster 规则会产生不合理结果，
    Murphy 平均法通过平均化降低冲突，再逐次组合。

    步骤：
    1. 计算所有 BPA 的平均 BPA: m_avg(A) = Σ_i m_i(A) / n
    2. 用 m_avg 与 m_avg 组合 n-1 次（等效于与自身反复组合）

    参数:
        bpas: 待融合的 BPA 列表

    返回:
        (融合后的 BPA, 最终冲突系数)
    """
    if not bpas:
        frame = EvidenceFrame(DEFAULT_FAULT_TYPES)
        theta_key = frame.make_full_key()
        return BPA(frame, {theta_key: 1.0}), 0.0

    n = len(bpas)
    frame = bpas[0].frame

    # 1. 计算平均 BPA
    avg_masses: Dict[FrozenSet[str], float] = {}
    for bpa in bpas:
        for key, mass in bpa.masses.items():
            avg_masses[key] = avg_masses.get(key, 0.0) + mass / n

    avg_bpa = BPA(frame, avg_masses)

    # 2. 与自身组合 n-1 次
    result = avg_bpa
    final_K = 0.0
    for _ in range(n - 1):
        result, K = dempster_combination(result, avg_bpa)
        final_K = max(final_K, K)

    return result, final_K


# ═══════════════════════════════════════════════════════════════
# 从 method_results 构建 BPA
# ═══════════════════════════════════════════════════════════════

def _classify_method(method_key: str) -> str:
    """判断方法类型：'bearing'、'gear' 或 'unknown'。

    方法键格式如 "none:envelope"、"wavelet:cpw"、"none:advanced" 等。
    """
    parts = method_key.lower().split(":")
    method_name = parts[-1] if len(parts) > 1 else parts[0]

    for kw in BEARING_METHOD_KEYWORDS:
        if kw in method_name:
            return "bearing"
    for kw in GEAR_METHOD_KEYWORDS:
        if kw in method_name:
            return "gear"
    return "unknown"


def _map_hits_to_faults(
    hits: List[str],
    method_type: str,
    fault_types: List[str],
) -> List[str]:
    """将诊断指标命中列表映射到故障类型集合中的具体故障。"""
    mapped = []
    name_map = BEARING_FAULT_NAMES if method_type == "bearing" else GEAR_FAULT_NAMES

    for hit in hits:
        fault_list = name_map.get(hit, [])
        for f in fault_list:
            if f in fault_types and f not in mapped:
                mapped.append(f)

    return mapped


def build_bpa_from_method(
    method_key: str,
    method_result: Dict[str, Any],
    frame: EvidenceFrame,
) -> BPA:
    """
    从单个诊断方法结果构建 BPA。

    分配逻辑：
    - 轴承方法 confidence > 0.55 → 轴承故障 BPA（根据 hits 分配质量）
    - 轴承方法 confidence 0.2~0.55 → 弱证据 BPA（部分质量给故障，更多给 Θ）
    - 齿轮方法 confidence > 0.55 → 齿轮故障 BPA
    - 齿轮方法 confidence 0.2~0.55 → 弱证据 BPA
    - confidence < 0.2 → Θ 占主导（几乎无信息）
    - 时域证据（kurtosis > 12）→ 冲击型故障 BPA
    """
    confidence = float(method_result.get("confidence", 0.0))
    abnormal = bool(method_result.get("abnormal", False))
    hits = list(method_result.get("hits", []) or [])
    method_type = _classify_method(method_key)

    masses: Dict[FrozenSet[str], float] = {}
    theta_key = frame.make_full_key()

    # ──── 强证据路径 (confidence > 0.55) ────
    if confidence > 0.55 and abnormal:
        fault_names = _map_hits_to_faults(hits, method_type, frame.fault_types)

        if fault_names:
            # 有具体故障命中：将 confidence 均分到命中故障类型
            per_fault = confidence / len(fault_names)
            for fn in fault_names:
                key = frame.make_singleton_key(fn)
                masses[key] = masses.get(key, 0.0) + per_fault
        else:
            # 无具体命中但 confidence 高：分配到对应类别集合
            if method_type == "bearing":
                bearing_faults = [f for f in frame.fault_types if f.startswith("轴承")]
                key = frozenset(bearing_faults)
                masses[key] = confidence * 0.6
                masses[theta_key] = confidence * 0.4
            elif method_type == "gear":
                gear_faults = [f for f in frame.fault_types if f.startswith("齿轮")]
                key = frozenset(gear_faults)
                masses[key] = confidence * 0.6
                masses[theta_key] = confidence * 0.4
            else:
                masses[theta_key] = confidence

        # Θ 分配剩余不确定性
        current = sum(masses.values())
        if current < 1.0:
            masses[theta_key] = masses.get(theta_key, 0.0) + (1.0 - current)

    # ──── 弱证据路径 (confidence 0.2~0.55) ────
    elif 0.2 <= confidence <= 0.55:
        fault_names = _map_hits_to_faults(hits, method_type, frame.fault_types)

        if fault_names:
            # 弱证据：分配较少质量给故障，大部分给 Θ
            weak_mass = confidence * 0.5  # 减半分配
            per_fault = weak_mass / len(fault_names)
            for fn in fault_names:
                key = frame.make_singleton_key(fn)
                masses[key] = masses.get(key, 0.0) + per_fault
            masses[theta_key] = 1.0 - weak_mass
        else:
            # 无具体命中：大部分给 Θ
            masses[theta_key] = 1.0 - confidence * 0.3
            if method_type == "bearing":
                bearing_faults = [f for f in frame.fault_types if f.startswith("轴承")]
                key = frozenset(bearing_faults)
                masses[key] = confidence * 0.3
            elif method_type == "gear":
                gear_faults = [f for f in frame.fault_types if f.startswith("齿轮")]
                key = frozenset(gear_faults)
                masses[key] = confidence * 0.3

    # ──── 极弱/无证据路径 (confidence < 0.2) ────
    else:
        # 几乎无信息，Θ 占主导
        masses[theta_key] = 1.0
        if abnormal and hits:
            # confidence 低但标记为异常：给极小质量
            fault_names = _map_hits_to_faults(hits, method_type, frame.fault_types)
            tiny_mass = 0.05
            per_fault = tiny_mass / max(len(fault_names), 1)
            for fn in fault_names[:3]:  # 最多分配3个
                key = frame.make_singleton_key(fn)
                masses[key] = per_fault
            masses[theta_key] = 1.0 - tiny_mass

    return BPA(frame, masses)


def build_time_domain_bpa(
    time_features: Dict[str, Any],
    frame: EvidenceFrame,
) -> BPA:
    """
    从时域特征构建冲击型故障 BPA。

    当 kurtosis > 12 时，信号中存在明显冲击，
    分配质量到冲击型故障（轴承内圈、齿轮断齿等）。
    """
    masses: Dict[FrozenSet[str], float] = {}
    theta_key = frame.make_full_key()

    kurt = float(time_features.get("kurtosis", 3.0))
    crest = float(time_features.get("crest_factor", 5.0))

    # 冲击证据门控：kurtosis > 12 表示存在显著冲击
    if kurt > 12:
        # 强冲击：分配质量到冲击型故障
        shock_mass = min(0.3, (kurt - 12) / 40.0 + 0.15)  # kurt=12→0.15, kurt=52→0.3
        # 冲击型故障：轴承内圈（高频冲击）、齿轮断齿（周期冲击）
        shock_faults = ["轴承内圈故障", "轴承外圈故障", "齿轮断齿"]
        valid_faults = [f for f in shock_faults if f in frame.fault_types]
        if valid_faults:
            per_fault = shock_mass / len(valid_faults)
            for fn in valid_faults:
                key = frame.make_singleton_key(fn)
                masses[key] = per_fault
        masses[theta_key] = 1.0 - shock_mass
    elif kurt > 5 or crest > 10:
        # 中等冲击：微量分配
        mild_mass = 0.08
        shock_faults = ["轴承内圈故障", "轴承外圈故障"]
        valid_faults = [f for f in shock_faults if f in frame.fault_types]
        if valid_faults:
            per_fault = mild_mass / len(valid_faults)
            for fn in valid_faults:
                key = frame.make_singleton_key(fn)
                masses[key] = per_fault
        masses[theta_key] = 1.0 - mild_mass
    else:
        # 无冲击证据：Θ 占满
        masses[theta_key] = 1.0
        # 正常状态分配小量质量
        normal_key = frame.make_singleton_key("正常")
        masses[normal_key] = 0.15
        masses[theta_key] = 0.85

    return BPA(frame, masses)


# ═══════════════════════════════════════════════════════════════
# 信念函数与似然函数
# ═══════════════════════════════════════════════════════════════

def compute_belief(bpa: BPA, focal: FrozenSet[str]) -> float:
    """
    信念函数 Bel(A) = Σ_{B⊆A} m(B)
    表示对 A 的最低置信度。
    """
    belief = 0.0
    for key, mass in bpa.masses.items():
        if key <= focal:  # B ⊆ A
            belief += mass
    return belief


def compute_plausibility(bpa: BPA, focal: FrozenSet[str]) -> float:
    """
    似然函数 Pl(A) = Σ_{B∩A≠∅} m(B)
    表示对 A 的最高可能置信度。
    """
    plausibility = 0.0
    for key, mass in bpa.masses.items():
        if len(key & focal) > 0:  # B∩A ≠ ∅
            plausibility += mass
    return plausibility


# ═══════════════════════════════════════════════════════════════
# 主入口函数
# ═══════════════════════════════════════════════════════════════

def dempster_shafer_fusion(
    method_results: Dict[str, Dict],
    fault_types: List[str] = None,
    time_features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    D-S 证据理论融合：将多种诊断方法的结果融合为综合故障概率分布。

    参数:
        method_results: 各诊断方法的结果，格式：
            {
                "none:envelope": {
                    "confidence": 0.65,
                    "abnormal": True,
                    "hits": ["bpfo"],
                },
                "wavelet:cpw": {
                    "confidence": 0.55,
                    "abnormal": True,
                    "hits": ["bpfi"],
                },
                ...
            }
        fault_types: 识别框架的故障类型集合，默认使用 DEFAULT_FAULT_TYPES
        time_features: 时域特征字典（可选），用于构建冲击型 BPA

    返回:
        {
            "fused_bpa":          Dict[故障类型, 概率],
            "fused_belief":       Dict[故障类型, 信念],
            "fused_plausibility": Dict[故障类型, 似然],
            "conflict_coefficient": float,     # 冲突系数 K
            "dominant_fault":     str,         # 最高概率故障类型
            "dominant_probability": float,     # 最高概率值
            "uncertainty":        float,       # Θ（不确定性）的概率
        }
    """
    # ──── 空输入安全处理 ────
    if not method_results and time_features is None:
        frame = EvidenceFrame(fault_types or DEFAULT_FAULT_TYPES)
        theta_key = frame.make_full_key()
        result = {
            "fused_bpa": {ft: 0.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "fused_belief": {ft: 0.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "fused_plausibility": {ft: 1.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "conflict_coefficient": 0.0,
            "dominant_fault": "未知",
            "dominant_probability": 0.0,
            "uncertainty": 1.0,
        }
        return result

    # ──── 建立识别框架 ────
    frame = EvidenceFrame(fault_types or DEFAULT_FAULT_TYPES)

    # ──── 从各方法结果构建 BPA ────
    bpas: List[BPA] = []
    bpa_sources: List[str] = []  # 记录 BPA 来源

    for method_key, method_result in method_results.items():
        # 过滤掉错误结果
        if "error" in method_result:
            continue
        bpa = build_bpa_from_method(method_key, method_result, frame)
        # 避免纯 Θ BPA 参与融合（无信息量）
        theta_key = frame.make_full_key()
        if bpa.get_mass(theta_key) < 0.99:
            bpas.append(bpa)
            bpa_sources.append(method_key)

    # ──── 时域证据 BPA ────
    if time_features is not None:
        time_bpa = build_time_domain_bpa(time_features, frame)
        theta_key = frame.make_full_key()
        if time_bpa.get_mass(theta_key) < 0.99:
            bpas.append(time_bpa)
            bpa_sources.append("time_domain")

    # ──── 无有效 BPA 时返回纯 Θ ────
    if not bpas:
        theta_key = frame.make_full_key()
        result = {
            "fused_bpa": {ft: 0.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "fused_belief": {ft: 0.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "fused_plausibility": {ft: 1.0 for ft in frame.fault_types} | {"Θ": 1.0},
            "conflict_coefficient": 0.0,
            "dominant_fault": "未知",
            "dominant_probability": 0.0,
            "uncertainty": 1.0,
        }
        return result

    # ──── 融合策略选择 ────
    # 先用标准 Dempster 规则逐步融合，记录最大冲突系数
    # 若冲突系数 K > 0.8，切换到 Murphy 平均法

    max_K = 0.0
    fused = bpas[0]

    if len(bpas) == 1:
        # 仅一个 BPA，无需融合
        fused = bpas[0]
    else:
        # 标准 Dempster 逐步融合
        for i in range(1, len(bpas)):
            fused, K = dempster_combination(fused, bpas[i])
            max_K = max(max_K, K)

        # ──── 高冲突修正 ────
        # K > 0.8 时标准 Dempster 规则不可靠，切换到 Murphy 平均法
        if max_K > 0.8:
            fused, max_K = murphy_average_combination(bpas)

    # ──── 计算信念与似然 ────
    fused_bpa_dict: Dict[str, float] = {}
    fused_belief_dict: Dict[str, float] = {}
    fused_plaus_dict: Dict[str, float] = {}

    # 单元素焦元（各故障类型）
    for ft in frame.fault_types:
        singleton_key = frame.make_singleton_key(ft)
        mass = fused.get_mass(singleton_key)
        belief = compute_belief(fused, singleton_key)
        plaus = compute_plausibility(fused, singleton_key)
        fused_bpa_dict[ft] = round(float(mass), 6)
        fused_belief_dict[ft] = round(float(belief), 6)
        fused_plaus_dict[ft] = round(float(plaus), 6)

    # Θ（全集）的质量、信念、似然
    theta_key = frame.make_full_key()
    theta_mass = fused.get_mass(theta_key)
    # Θ = Ω（全集），Bel(Ω) = Σ m(A) for all A⊆Ω = 1.0（所有焦元都是全集的子集）
    # Pl(Ω) = Σ m(A) for all A∩Ω≠∅ = 1.0（所有焦元都与全集相交）
    fused_bpa_dict["Θ"] = round(float(theta_mass), 6)
    fused_belief_dict["Θ"] = round(float(compute_belief(fused, theta_key)), 6)
    fused_plaus_dict["Θ"] = round(float(compute_plausibility(fused, theta_key)), 6)

    # ──── 确定主导故障 ────
    # 取概率最高的故障类型（排除 Θ 和 "正常"）
    fault_masses = {
        ft: fused_bpa_dict[ft]
        for ft in frame.fault_types
        if ft != "正常"
    }
    if fault_masses:
        dominant_fault = max(fault_masses, key=lambda k: fault_masses[k])
        dominant_prob = fault_masses[dominant_fault]
    else:
        dominant_fault = "正常"
        dominant_prob = fused_bpa_dict.get("正常", 0.0)

    # 如果所有故障概率都极低，认为正常
    if dominant_prob < 0.05:
        dominant_fault = "正常"
        dominant_prob = fused_bpa_dict.get("正常", 0.0)

    return {
        "fused_bpa": fused_bpa_dict,
        "fused_belief": fused_belief_dict,
        "fused_plausibility": fused_plaus_dict,
        "conflict_coefficient": round(float(max_K), 6),
        "dominant_fault": dominant_fault,
        "dominant_probability": round(float(dominant_prob), 6),
        "uncertainty": round(float(theta_mass), 6),
    }