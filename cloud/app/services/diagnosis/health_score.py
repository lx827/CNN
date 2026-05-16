"""
健康度评分模块

核心改动：离散阶梯扣分 → 连续 sigmoid 衰减扣分（来自 health_score_continuous.py）
消除阈值边界处的不连续跳变（如 kurt=5→5.01 导致 15 分跃变）。

D-S 融合闭环：从 fusion_bridge.py 接收 D-S 融合结果，
当 dominant_probability > 0.4 且 uncertainty < 0.3 时，
将 D-S 主导故障类型纳入 fault_label。
当 conflict > 0.8 时降低置信度并在建议中提示复核。
"""
from typing import Dict, Optional, Tuple

# 峰值因子单独作为统计证据门控的阈值。
CREST_EVIDENCE_THRESHOLD = 10.0

# 连续衰减扣分模块
from .health_score_continuous import compute_continuous_deductions, cascade_deduction, sigmoid_deduction

# 权重配置
from app.core.config import DIAGNOSIS_WEIGHTS

# 扣分名称 → 权重键的映射表
DEDUCTION_WEIGHT_MAP = {
    # 时域指标
    "kurtosis_extreme": "kurtosis", "kurtosis_high": "kurtosis",
    "kurtosis_moderate": "kurtosis", "kurtosis_mild": "kurtosis",
    "crest_very_high": "crest_factor", "crest_high": "crest_factor", "crest_moderate": "crest_factor",
    # 动态基线/趋势
    "dynamic_baseline_extreme": "kurtosis", "dynamic_baseline_warning": "kurtosis",
    "trend_drift_warning": "kurtosis",
    # 轴承频率匹配
    "bearing_multi_freq": "bpfo", "bearing_single_freq": "bpfo",
    "bearing_statistical_abnormal": "kurtosis", "bearing_statistical_hint": "kurtosis",
    # 轴承边带密度
    "bearing_sideband_density": "sideband",
    "bearing_sideband_asymmetry": "sideband",
    # 轴承 SC/SCoh
    "bearing_sc_scoh_evidence": "scoh_evidence",
    # 齿轮指标
    "gear_ser_critical": "ser", "gear_ser_warning": "ser",
    "gear_sb_critical": "gear_sideband", "gear_sb_warning": "gear_sideband",
    "gear_tsa_residual_kurtosis_critical": "fm4", "gear_tsa_residual_kurtosis_warning": "fm4",
    "gear_na4_trend_critical": "na4_nb4", "gear_na4_trend_warning": "na4_nb4",
    "gear_car_critical": "car", "gear_car_warning": "car",
    "gear_order_stat_critical": "car", "gear_order_stat_warning": "car",
    # 小波包能量熵
    "gear_wp_entropy_critical": "wp_entropy", "gear_wp_entropy_warning": "wp_entropy",
    "gear_mesh_concentration_critical": "wp_entropy", "gear_mesh_concentration_warning": "wp_entropy",
    # D-S 冲突
    "ds_conflict_penalty": "ds_conflict",
}


def _compute_health_score(
    gear_teeth: Optional[Dict],
    time_features: Dict,
    bearing_result: Dict,
    gear_result: Dict,
    ds_fusion_result: Optional[Dict] = None,
) -> Tuple[int, str]:
    """
    综合健康度评分 (0-100) — 连续衰减版本

    核心思想：时域统计指标定基调（区分正常/异常），频率匹配标类型（哪种故障）。
    所有扣分使用 sigmoid 连续衰减函数，消除阈值边界跳变。
    """
    # 使用连续衰减扣分替代原离散阶梯
    deductions = compute_continuous_deductions(
        time_features, gear_teeth, bearing_result, gear_result,
    )

    # ═══════ D-S 融合闭环 ═══════
    ds_label = None
    ds_conflict_high = False
    if ds_fusion_result and isinstance(ds_fusion_result, dict):
        dominant_prob = 0.0
        uncertainty = 1.0
        conflict = 0.0
        try:
            dominant_prob = float(ds_fusion_result.get("dominant_probability", 0))
            uncertainty = float(ds_fusion_result.get("uncertainty", 1))
            conflict = float(ds_fusion_result.get("conflict_coefficient", 0))
        except (TypeError, ValueError):
            pass

        # D-S 主导故障纳入 fault_label（仅当置信度足够高）
        if dominant_prob > 0.4 and uncertainty < 0.3:
            ds_label = ds_fusion_result.get("dominant_fault")

        # 高冲突标记：方法间不一致
        ds_conflict_high = conflict > 0.8

        # 高冲突时降低健康度（降低 5~10 分）
        if ds_conflict_high:
            deductions.append(("ds_conflict_penalty", 8))

    # ═══════ 综合评分（加权扣分） ═══════
    weighted_total = 0.0
    for ded_name, ded_value in deductions:
        weight_key = DEDUCTION_WEIGHT_MAP.get(ded_name, "kurtosis")  # 未映射的默认用 kurtosis 权重
        weight = DIAGNOSIS_WEIGHTS.get(weight_key, 1.0)
        weighted_total += ded_value * weight
    total = min(weighted_total, 75)
    score = 100.0 - total
    hs = int(max(0, min(100, round(score))))

    # 状态判定
    def _sf(val, default=0.0):
        try: return float(val) if val is not None else default
        except: return default

    kurt = _sf(time_features.get("kurtosis"), 3.0)
    crest = _sf(time_features.get("crest_factor"), 5.0)
    rms_mad_z = _sf(time_features.get("rms_mad_z"), 0.0)
    cusum_score = _sf(time_features.get("cusum_score"), 0.0)

    has_critical = any("critical" in d[0] for d in deductions)
    time_abnormal = kurt > 5 or crest > 10 or rms_mad_z > 4 or cusum_score > 8

    if hs >= 85:
        status = "normal"
    elif hs >= 60:
        status = "warning" if (has_critical or time_abnormal) else "normal"
    else:
        status = "fault" if has_critical else "warning"

    # D-S 融合可能将 status 从 normal 提升为 warning
    if ds_conflict_high and status == "normal" and hs < 90:
        status = "warning"

    return hs, status, deductions


def get_ds_label(ds_fusion_result: Optional[Dict]) -> Optional[str]:
    """从 D-S 融合结果提取主导故障标签（用于 fault_label）"""
    if not ds_fusion_result or not isinstance(ds_fusion_result, dict):
        return None
    dominant_prob = 0.0
    uncertainty = 1.0
    try:
        dominant_prob = float(ds_fusion_result.get("dominant_probability", 0))
        uncertainty = float(ds_fusion_result.get("uncertainty", 1))
    except (TypeError, ValueError):
        pass
    if dominant_prob > 0.4 and uncertainty < 0.3:
        return ds_fusion_result.get("dominant_fault")
    return None


def is_ds_conflict_high(ds_fusion_result: Optional[Dict]) -> bool:
    """判断 D-S 融合是否高冲突（用于建议中提示复核）"""
    if not ds_fusion_result or not isinstance(ds_fusion_result, dict):
        return False
    try:
        return float(ds_fusion_result.get("conflict_coefficient", 0)) > 0.8
    except (TypeError, ValueError):
        return False