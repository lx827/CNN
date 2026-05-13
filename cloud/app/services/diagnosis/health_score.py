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

    # 峭度：冲击信号的核心指标，权重加大
    if kurt > 20:
        deductions.append(("kurtosis_extreme", 35))
    elif kurt > 12:
        deductions.append(("kurtosis_high", 25))
    elif kurt > 8:
        deductions.append(("kurtosis_moderate", 18))
    elif kurt > 5:
        deductions.append(("kurtosis_mild", 10))

    # 峰值因子：单大冲击 vs 持续振动
    if crest > 15:
        deductions.append(("crest_very_high", 15))
    elif crest > 10:
        deductions.append(("crest_high", 10))
    elif crest > 7:
        deductions.append(("crest_moderate", 5))

    # ═══════ 轴承故障扣分（时域峭度是前提）═══════
    bearing_ind = bearing_result.get("fault_indicators", {})
    freq_sig_count = sum(
        v.get("significant") for k, v in bearing_ind.items()
        if isinstance(v, dict) and not k.endswith("_stat")
    )
    # 只有时域也有冲击特征时，频率匹配才有意义
    if kurt > 5.0:
        if freq_sig_count >= 2:
            deductions.append(("bearing_multi_freq", 10))
        elif freq_sig_count == 1:
            deductions.append(("bearing_single_freq", 5))

    # ═══════ 齿轮故障扣分（故障类型注释）═══════
    gear_ind = gear_result.get("fault_indicators", {})
    has_gear = gear_teeth and (gear_teeth.get("input") or 0) > 0

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

    # ═══════ 综合评分 ═══════
    total = min(sum(d[1] for d in deductions), 75)
    score -= total
    hs = int(max(0, min(100, score)))

    # 状态判定
    has_critical = any("critical" in d[0] for d in deductions)
    freq_has_fault = freq_sig_count >= 1
    time_abnormal = kurt > 5 or crest > 10

    if hs >= 85:
        status = "normal"
    elif hs >= 60:
        status = "warning" if (has_critical or time_abnormal) else "normal"
    else:
        status = "fault" if has_critical else "warning"

    return hs, status
