"""
健康度评分模块
"""
from typing import Dict, Optional


def _compute_health_score(
    gear_teeth: Optional[Dict],
    time_features: Dict,
    bearing_result: Dict,
    gear_result: Dict,
) -> tuple:
    """
    计算综合健康度评分 (0-100)

    改进策略：
    - 多指标同时异常才大幅扣分（避免单一误检导致过度扣分）
    - 时域特征权重提高（峭度对冲击最敏感）
    - 无齿轮参数时跳过齿轮扣分
    - 轴承扣分权重降低，但多故障叠加时增强
    """
    score = 100.0
    deductions = []  # 记录各项扣分，用于调试

    # 防御性处理：确保 time_features 中的值都是有效数字
    def _safe_float(val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    # ===== 时域特征扣分 =====
    kurt = _safe_float(time_features.get("kurtosis"), 3.0)
    if kurt > 15:
        deductions.append(("kurtosis_critical", 15))
    elif kurt > 8:
        deductions.append(("kurtosis_warning", 8))
    elif kurt > 5:
        deductions.append(("kurtosis_mild", 4))

    crest = _safe_float(time_features.get("crest_factor"), 5.0)
    if crest > 12:
        deductions.append(("crest_critical", 8))
    elif crest > 9:
        deductions.append(("crest_warning", 4))

    # ===== 轴承故障扣分（权重降低，多故障叠加增强）=====
    bearing_ind = bearing_result.get("fault_indicators", {})
    bearing_significant = 0
    bearing_mild = 0
    for name, info in bearing_ind.items():
        if not isinstance(info, dict):
            continue
        if info.get("significant"):
            bearing_significant += 1
        else:
            snr = _safe_float(info.get("snr"), 0.0)
            if snr > 2:
                bearing_mild += 1

    if bearing_significant >= 2:
        deductions.append(("bearing_multi_warning", 12))  # 多故障特征同时显著
    elif bearing_significant == 1:
        deductions.append(("bearing_single_warning", 5))   # 单一故障特征
    if bearing_mild >= 2:
        deductions.append(("bearing_mild_warning", 3))

    # 无物理参数时的轴承统计扣分（包络谱统计特征）
    if bearing_significant == 0:
        env_peak_snr = _safe_float(
            bearing_ind.get("envelope_peak_snr", {}).get("value") if isinstance(bearing_ind.get("envelope_peak_snr"), dict) else None,
            0.0
        )
        env_kurt = _safe_float(
            bearing_ind.get("envelope_kurtosis", {}).get("value") if isinstance(bearing_ind.get("envelope_kurtosis"), dict) else None,
            0.0
        )
        hf_ratio = _safe_float(
            bearing_ind.get("high_freq_ratio", {}).get("value") if isinstance(bearing_ind.get("high_freq_ratio"), dict) else None,
            0.0
        )
        if env_peak_snr > 5.0:
            deductions.append(("bearing_stat_peak_warning", 8))
        if env_kurt > 5.0:
            deductions.append(("bearing_stat_kurt_warning", 6))
        if hf_ratio > 0.5:
            deductions.append(("bearing_stat_hf_warning", 4))

    # ===== 齿轮故障扣分 =====
    gear_ind = gear_result.get("fault_indicators", {})
    has_gear_params = gear_teeth and (gear_teeth.get("input") or 0) > 0

    if has_gear_params:
        ser_info = gear_ind.get("ser", {}) if isinstance(gear_ind.get("ser"), dict) else {}
        if ser_info.get("critical"):
            deductions.append(("gear_ser_critical", 12))
        elif ser_info.get("warning"):
            deductions.append(("gear_ser_warning", 6))

        sb_info = gear_ind.get("sideband_count", {}) if isinstance(gear_ind.get("sideband_count"), dict) else {}
        if sb_info.get("critical"):
            deductions.append(("gear_sb_critical", 8))
        elif sb_info.get("warning"):
            deductions.append(("gear_sb_warning", 4))

        fm0_info = gear_ind.get("fm0", {}) if isinstance(gear_ind.get("fm0"), dict) else {}
        if fm0_info.get("critical"):
            deductions.append(("gear_fm0_critical", 8))
        elif fm0_info.get("warning"):
            deductions.append(("gear_fm0_warning", 4))

    # 无齿轮参数时的齿轮统计扣分（阶次谱统计特征）
    if not has_gear_params:
        car_info = gear_ind.get("car", {}) if isinstance(gear_ind.get("car"), dict) else {}
        if car_info.get("critical"):
            deductions.append(("gear_stat_car_critical", 8))
        elif car_info.get("warning"):
            deductions.append(("gear_stat_car_warning", 4))

        order_kurt_info = gear_ind.get("order_kurtosis", {}) if isinstance(gear_ind.get("order_kurtosis"), dict) else {}
        if order_kurt_info.get("critical"):
            deductions.append(("gear_stat_kurt_critical", 6))
        elif order_kurt_info.get("warning"):
            deductions.append(("gear_stat_kurt_warning", 3))

        order_peak_info = gear_ind.get("order_peak_concentration", {}) if isinstance(gear_ind.get("order_peak_concentration"), dict) else {}
        if order_peak_info.get("critical"):
            deductions.append(("gear_stat_peak_critical", 6))
        elif order_peak_info.get("warning"):
            deductions.append(("gear_stat_peak_warning", 3))

    # ===== 计算总分（累加扣分，但封顶）=====
    total_deduction = sum(d[1] for d in deductions)
    # 封顶：最多扣 70 分，保留 30 分底线
    total_deduction = min(total_deduction, 70)
    score -= total_deduction

    health_score = int(max(0, min(100, score)))

    # 状态判定：结合分数 + 关键指标
    has_critical = any("critical" in d[0] for d in deductions)
    has_warning = any("warning" in d[0] for d in deductions)

    if health_score >= 85:
        status = "normal"
    elif health_score >= 60:
        status = "warning" if (has_warning or has_critical) else "normal"
    else:
        status = "fault" if has_critical else "warning"

    return health_score, status
