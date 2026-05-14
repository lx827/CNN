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
    综合健康度评分 (0-100)

    核心思想：时域统计指标定基调（区分正常/异常），频率匹配标类型（哪种故障）。
    """
    score = 100.0
    deductions = []

    def _sf(val, default=0.0):
        try: return float(val) if val is not None else default
        except: return default

    # ═══════ 时域特征（主要判断）═══════
    kurt = _sf(time_features.get("kurtosis"), 3.0)
    crest = _sf(time_features.get("crest_factor"), 5.0)
    rms = _sf(time_features.get("rms"), 0.0)

    # 峭度：冲击信号的核心指标
    if kurt > 20:
        deductions.append(("kurtosis_extreme", 40))
    elif kurt > 12:
        deductions.append(("kurtosis_high", 30))
    elif kurt > 8:
        deductions.append(("kurtosis_moderate", 22))
    elif kurt > 5:
        deductions.append(("kurtosis_mild", 15))

    # 峰值因子：单大冲击 vs 持续振动
    if crest > 15:
        deductions.append(("crest_very_high", 15))
    elif crest > 10:
        deductions.append(("crest_high", 10))
    elif crest > 7:
        deductions.append(("crest_moderate", 5))

    # 动态基线/趋势：本批次窗口内出现持续漂移或突变时扣分。
    rms_mad_z = _sf(time_features.get("rms_mad_z"), 0.0)
    kurt_mad_z = _sf(time_features.get("kurtosis_mad_z"), 0.0)
    ewma_drift = _sf(time_features.get("ewma_drift"), 0.0)
    cusum_score = _sf(time_features.get("cusum_score"), 0.0)

    if rms_mad_z > 6 or kurt_mad_z > 6:
        deductions.append(("dynamic_baseline_extreme", 18))
    elif rms_mad_z > 4 or kurt_mad_z > 4:
        deductions.append(("dynamic_baseline_warning", 10))

    if cusum_score > 8 or ewma_drift > 4:
        deductions.append(("trend_drift_warning", 8))

    # ═══════ 轴承故障扣分（时域峭度是前提）═══════
    bearing_ind = bearing_result.get("fault_indicators", {})
    freq_sig_count = sum(
        v.get("significant") for k, v in bearing_ind.items()
        if isinstance(v, dict) and not k.endswith("_stat")
    )
    stat_sig_count = sum(
        v.get("significant") for k, v in bearing_ind.items()
        if isinstance(v, dict) and (k.endswith("_stat") or k in {
            "envelope_peak_snr", "envelope_kurtosis", "high_freq_ratio", "peak_concentration"
        })
    )
    # 只有时域也有冲击特征时，频率匹配才有意义
    if kurt > 5.0:
        if freq_sig_count >= 2:
            deductions.append(("bearing_multi_freq", 10))
        elif freq_sig_count == 1:
            deductions.append(("bearing_single_freq", 5))
    if stat_sig_count >= 2:
        deductions.append(("bearing_statistical_abnormal", 10))
    elif stat_sig_count == 1 and (kurt > 5.0 or crest > 7.0):
        deductions.append(("bearing_statistical_hint", 5))

    # ═══════ 齿轮故障扣分（故障类型注释）═══════
    gear_ind = gear_result.get("fault_indicators", {})
    try:
        has_gear = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        has_gear = False

    if has_gear:
        ser = gear_ind.get("ser", {}) if isinstance(gear_ind.get("ser"), dict) else {}
        if ser.get("critical"):
            deductions.append(("gear_ser_critical", 12))
        elif ser.get("warning"):
            deductions.append(("gear_ser_warning", 6))

        sb = gear_ind.get("sideband_count", {}) if isinstance(gear_ind.get("sideband_count"), dict) else {}
        if sb.get("critical"):
            deductions.append(("gear_sb_critical", 8))
        elif sb.get("warning"):
            deductions.append(("gear_sb_warning", 4))

    if not has_gear:
        car = gear_ind.get("car", {}) if isinstance(gear_ind.get("car"), dict) else {}
        if car.get("critical"):
            deductions.append(("gear_car_critical", 8))
        elif car.get("warning"):
            deductions.append(("gear_car_warning", 4))

        order_peak = gear_ind.get("order_peak_concentration", {}) if isinstance(gear_ind.get("order_peak_concentration"), dict) else {}
        order_kurt = gear_ind.get("order_kurtosis", {}) if isinstance(gear_ind.get("order_kurtosis"), dict) else {}
        if order_peak.get("critical") or order_kurt.get("critical"):
            deductions.append(("gear_order_stat_critical", 8))
        elif order_peak.get("warning") or order_kurt.get("warning"):
            deductions.append(("gear_order_stat_warning", 4))

    # ═══════ 综合评分 ═══════
    total = min(sum(d[1] for d in deductions), 75)
    score -= total
    hs = int(max(0, min(100, score)))

    # 状态判定
    has_critical = any("critical" in d[0] for d in deductions)
    freq_has_fault = freq_sig_count >= 1
    time_abnormal = kurt > 5 or crest > 10 or rms_mad_z > 4 or cusum_score > 8

    if hs >= 85:
        status = "normal"
    elif hs >= 60:
        status = "warning" if (has_critical or time_abnormal) else "normal"
    else:
        status = "fault" if has_critical else "warning"

    return hs, status
