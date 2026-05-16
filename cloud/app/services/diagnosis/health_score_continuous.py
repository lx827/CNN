"""
连续衰减扣分函数模块

将 health_score.py 中原有的离散阶梯扣分替换为连续衰减函数，
消除阈值边界处的不连续跳变（如 kurt=5→5.01 导致 15 分跃变）。

核心函数：sigmoid_deduction — 在阈值附近平滑过渡，
远离阈值时趋近于 0（低于阈值）或 max_deduction（远高于阈值）。
"""
import math
from typing import Dict, Optional

# 默认斜率：控制过渡带宽度。slope=2.0 时过渡带约 ±3 个单位。
DEFAULT_SLOPE = 2.0


def sigmoid_deduction(
    value: float,
    threshold: float,
    max_deduction: float,
    slope: float = DEFAULT_SLOPE,
) -> float:
    """
    连续 sigmoid 衰减扣分函数

    f(x) = max_deduction × sigmoid((x - threshold) × slope)
    sigmoid(t) = 1 / (1 + exp(-t))

    特性：
    - value < threshold 时扣分趋近 0
    - value > threshold 时扣分趋近 max_deduction
    - 在 threshold 附近平滑过渡，无阶跃

    Args:
        value: 当前指标值（如 kurtosis=5.01）
        threshold: 阈值（如 5.0）
        max_deduction: 最大扣分值（如 15.0）
        slope: 过渡斜率（越大过渡越陡，越小越缓）
               slope=1: ±6 单位过渡带
               slope=2: ±3 单位过渡带
               slope=3: ±2 单位过渡带

    Returns:
        float: 连续扣分值（0 ~ max_deduction）
    """
    t = (value - threshold) * slope
    # 防溢出：t > 20 时 sigmoid ≈ 1，t < -20 时 ≈ 0
    if t > 20:
        return max_deduction
    if t < -20:
        return 0.0
    sig = 1.0 / (1.0 + math.exp(-t))
    return max_deduction * sig


def multi_threshold_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = DEFAULT_SLOPE,
) -> float:
    """
    多阈值连续扣分（替代 elif 阶梯链）

    原阶梯逻辑：
      if kurt > 20: deduction = 40
      elif kurt > 12: deduction = 30
      elif kurt > 8: deduction = 22
      elif kurt > 5: deduction = 15

    连续替代：取各阈值 sigmoid 扣分的最大值，
    确保低阈值在 value 远高于时也能贡献扣分。

    Args:
        value: 当前指标值
        thresholds: 阈值列表，从小到大 [5, 8, 12, 20]
        max_deductions: 对应扣分列表 [15, 22, 30, 40]
        slope: 过渡斜率

    Returns:
        float: 连续扣分值
    """
    if not thresholds or not max_deductions:
        return 0.0
    # 从小到大排序
    pairs = sorted(zip(thresholds, max_deductions), key=lambda p: p[0])
    # 取各阈值贡献的最大值
    total = 0.0
    for th, mx in pairs:
        d = sigmoid_deduction(value, th, mx, slope)
        # 只累加超过上一级阈值的增量部分
        # 这样避免了 sigmoid 在高阈值处叠加导致总扣分超出预期
        total = max(total, d)
    return total


def cascade_deduction(
    value: float,
    thresholds: list,
    max_deductions: list,
    slope: float = DEFAULT_SLOPE,
) -> float:
    """
    级联连续扣分（替代 elif 阶梯链 — 更精确）

    原阶梯逻辑中 elif 意味着每级只扣一次，
    总扣分等于 value 所跨越的最高阶梯的扣分值。

    级联替代：每级 sigmoid 扣分贡献的是"本级增量"，
    即本级 max_deduction 减去上一级 max_deduction 的差值。
    最终总扣分 = Σ 各级增量 × sigmoid(value, 本级阈值, slope)

    示例（轴承峭度 thresholds=[5,8,12,20], deductions=[15,22,30,40]）：
    - kurt=4.5: 所有 sigmoid ≈ 0 → 总扣分 ≈ 0
    - kurt=6.0: sigmoid(6,5)≈0.73 增量15, sigmoid(6,8)≈0 增量7 → ≈15×0.73 = 10.95
    - kurt=10: sigmoid(10,5)≈1.0 增量15, sigmoid(10,8)≈0.73 增量7, sigmoid(10,12)≈0 增量8 → ≈15+7×0.73 = 20.1
    - kurt=13: ≈15+7+8×0.73 = 28.8
    - kurt=25: ≈15+7+8+10 = 40

    Args:
        value: 当前指标值
        thresholds: 阈值列表，从小到大 [5, 8, 12, 20]
        max_deductions: 对应扣分列表 [15, 22, 30, 40]
        slope: 过渡斜率

    Returns:
        float: 连续扣分值（不超过 max(max_deductions)）
    """
    if not thresholds or not max_deductions:
        return 0.0
    pairs = sorted(zip(thresholds, max_deductions), key=lambda p: p[0])

    total = 0.0
    prev_deduction = 0.0
    for th, mx in pairs:
        increment = mx - prev_deduction  # 本级增量
        if increment > 0:
            d = sigmoid_deduction(value, th, increment, slope)
            total += d
        prev_deduction = mx

    # 确保不超过最高阶梯的最大扣分
    cap = max(max_deductions) if max_deductions else 0.0
    return min(total, cap)


def compute_continuous_deductions(
    time_features: Dict,
    gear_teeth: Optional[Dict],
    bearing_result: Dict,
    gear_result: Dict,
) -> list:
    """
    连续衰减扣分计算 — 替代 health_score.py 中的离散阶梯扣分

    返回格式与原 health_score.py 的 deductions 列表一致：
    [("deduction_name", float_deduction_value), ...]

    这样 health_score.py 可以直接替换调用，不改变下游逻辑。
    """
    deductions = []

    def _sf(val, default=0.0):
        try: return float(val) if val is not None else default
        except: return default

    # ═══════ 时域特征 ═══════
    kurt = _sf(time_features.get("kurtosis"), 3.0)
    crest = _sf(time_features.get("crest_factor"), 5.0)
    rms = _sf(time_features.get("rms"), 0.0)

    CREST_EVIDENCE_THRESHOLD = 10.0

    try:
        is_gear_device = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        is_gear_device = False

    # 峭度连续扣分
    if is_gear_device:
        # 齿轮设备: thresholds=[10, 12, 20], deductions=[15, 25, 40]
        kurt_ded = cascade_deduction(kurt, [10, 12, 20], [15, 25, 40])
    else:
        # 轴承设备: thresholds=[5, 8, 12, 20], deductions=[15, 22, 30, 40]
        kurt_ded = cascade_deduction(kurt, [5, 8, 12, 20], [15, 22, 30, 40])
    if kurt_ded > 0.5:
        # 精细标注：根据主要扣分来源标注名称
        if kurt > 20:
            deductions.append(("kurtosis_extreme", kurt_ded))
        elif kurt > 12:
            deductions.append(("kurtosis_high", kurt_ded))
        elif kurt > 8 if not is_gear_device else kurt > 10:
            deductions.append(("kurtosis_moderate", kurt_ded))
        else:
            deductions.append(("kurtosis_mild", kurt_ded))

    # 峰值因子连续扣分
    if is_gear_device:
        crest_ded = cascade_deduction(crest, [12, 15], [10, 15])
    else:
        crest_ded = cascade_deduction(crest, [7, 10, 15], [5, 10, 15])
    if crest_ded > 0.5:
        if crest > 15:
            deductions.append(("crest_very_high", crest_ded))
        elif crest > CREST_EVIDENCE_THRESHOLD:
            deductions.append(("crest_high", crest_ded))
        else:
            deductions.append(("crest_moderate", crest_ded))

    # ═══════ 动态基线/趋势 ═══════
    rms_mad_z = _sf(time_features.get("rms_mad_z"), 0.0)
    kurt_mad_z = _sf(time_features.get("kurtosis_mad_z"), 0.0)
    ewma_drift = _sf(time_features.get("ewma_drift"), 0.0)
    cusum_score = _sf(time_features.get("cusum_score"), 0.0)

    baseline_has_evidence = (kurt > 5.0 or crest > CREST_EVIDENCE_THRESHOLD)
    if baseline_has_evidence:
        baseline_max = max(rms_mad_z, kurt_mad_z)
        baseline_ded = cascade_deduction(baseline_max, [4, 6], [10, 18])
        if baseline_ded > 0.5:
            if baseline_max > 6:
                deductions.append(("dynamic_baseline_extreme", baseline_ded))
            else:
                deductions.append(("dynamic_baseline_warning", baseline_ded))

        trend_val = max(cusum_score, ewma_drift * 2)  # ewma_drift 阈值是 4，等效
        trend_ded = sigmoid_deduction(trend_val, 8, 8, slope=1.5)
        if trend_ded > 0.5:
            deductions.append(("trend_drift_warning", trend_ded))

    # ═══════ 轴承故障扣分 ═══════
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
    rotation_dominant = False
    low_freq_ind = bearing_ind.get("low_freq_ratio")
    if isinstance(low_freq_ind, dict):
        rotation_dominant = low_freq_ind.get("rotation_harmonic_dominant", False)

    # 频率匹配路径：时域有冲击(kurt>5)时频率匹配才有效
    # 连续过渡：kurt 从 4→6 时门控从 0→1
    kurt_gate = sigmoid_deduction(kurt, 5.0, 1.0, slope=2.0)
    if kurt_gate > 0.1:
        freq_ded = 0.0
        if freq_sig_count >= 2:
            freq_ded = 10.0 * kurt_gate
        elif freq_sig_count == 1:
            freq_ded = 5.0 * kurt_gate
        if freq_ded > 0.5:
            if freq_sig_count >= 2:
                deductions.append(("bearing_multi_freq", round(freq_ded, 2)))
            else:
                deductions.append(("bearing_single_freq", round(freq_ded, 2)))

        # 边带密度增强扣分：high_density 或 high_asymmetry 标记时追加扣分
        # 边带密度高说明故障频率周围调制边带丰富，是轴承故障的强证据
        sideband_high_count = sum(
            v.get("high_density", False) for k, v in bearing_ind.items()
            if isinstance(v, dict) and not k.endswith("_stat")
        )
        sideband_asym_count = sum(
            v.get("high_asymmetry", False) for k, v in bearing_ind.items()
            if isinstance(v, dict) and not k.endswith("_stat")
        )
        if sideband_high_count >= 1 and kurt_gate > 0.3:
            sb_ded = 4.0 * kurt_gate  # 边带密度高追加 4 分扣分
            deductions.append(("bearing_sideband_density", round(sb_ded, 2)))
        if sideband_asym_count >= 1 and kurt_gate > 0.3:
            sb_asym_ded = 3.0 * kurt_gate  # 边带不对称追加 3 分扣分
            deductions.append(("bearing_sideband_asymmetry", round(sb_asym_ded, 2)))

    # 统计路径门控连续化
    stat_impulse = sigmoid_deduction(kurt, 5.0, 1.0, slope=2.0) + sigmoid_deduction(crest, CREST_EVIDENCE_THRESHOLD, 1.0, slope=2.0)
    stat_gate = min(1.0, stat_impulse) if not rotation_dominant else 0.0
    if stat_gate > 0.1:
        if stat_sig_count >= 2:
            stat_ded = 10.0 * stat_gate
            deductions.append(("bearing_statistical_abnormal", round(stat_ded, 2)))
        elif stat_sig_count == 1:
            stat_ded = 5.0 * stat_gate
            deductions.append(("bearing_statistical_hint", round(stat_ded, 2)))

    # ═══════ 齿轮故障扣分 ═══════
    gear_ind = gear_result.get("fault_indicators", {})
    try:
        has_gear = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        has_gear = False

    GEAR_KURT_THRESHOLD = 12.0
    GEAR_CREST_THRESHOLD = 12.0

    # 从轴承或齿轮指标中判断旋转谐波主导
    low_freq_ind = bearing_ind.get("low_freq_ratio") if bearing_ind else None
    if isinstance(low_freq_ind, dict):
        rotation_dominant = low_freq_ind.get("rotation_harmonic_dominant", rotation_dominant)
    low_freq_gear = gear_ind.get("low_freq_ratio") if isinstance(gear_ind.get("low_freq_ratio"), dict) else None
    if low_freq_gear and low_freq_gear.get("rotation_harmonic_dominant"):
        rotation_dominant = True

    if has_gear:
        gear_impulse = sigmoid_deduction(kurt, GEAR_KURT_THRESHOLD, 1.0, slope=2.0) + sigmoid_deduction(crest, GEAR_CREST_THRESHOLD, 1.0, slope=2.0)
        gear_gate = min(1.0, gear_impulse) if not rotation_dominant else 0.0
        if gear_gate > 0.1:
            ser = gear_ind.get("ser", {}) if isinstance(gear_ind.get("ser"), dict) else {}
            if ser.get("critical"):
                ser_ded = 12.0 * gear_gate
                deductions.append(("gear_ser_critical", round(ser_ded, 2)))
            elif ser.get("warning"):
                ser_ded = 6.0 * gear_gate
                deductions.append(("gear_ser_warning", round(ser_ded, 2)))

            sb = gear_ind.get("sideband_count", {}) if isinstance(gear_ind.get("sideband_count"), dict) else {}
            if sb.get("critical"):
                sb_ded = 8.0 * gear_gate
                deductions.append(("gear_sb_critical", round(sb_ded, 2)))
            elif sb.get("warning"):
                sb_ded = 4.0 * gear_gate
                deductions.append(("gear_sb_warning", round(sb_ded, 2)))

    # TSA 残差峭度路径（独立门控）
    tsa_env_result = gear_result.get("planetary_tsa_demod") or {}
    if isinstance(tsa_env_result, dict) and "error" not in tsa_env_result:
        tsa_residual_kurt = float(tsa_env_result.get("residual_kurtosis", 0.0))
        tsa_ded = cascade_deduction(tsa_residual_kurt, [3.0, 5.0], [8, 15])
        # rotation_dominant 时降权
        if rotation_dominant:
            tsa_ded *= 0.3
        if tsa_ded > 0.5:
            if tsa_residual_kurt > 5.0:
                deductions.append(("gear_tsa_residual_kurtosis_critical", round(tsa_ded, 2)))
            else:
                deductions.append(("gear_tsa_residual_kurtosis_warning", round(tsa_ded, 2)))

    if not has_gear:
        car = gear_ind.get("car", {}) if isinstance(gear_ind.get("car"), dict) else {}
        order_peak = gear_ind.get("order_peak_concentration", {}) if isinstance(gear_ind.get("order_peak_concentration"), dict) else {}
        order_kurt = gear_ind.get("order_kurtosis", {}) if isinstance(gear_ind.get("order_kurtosis"), dict) else {}

        gear_stat_impulse = sigmoid_deduction(kurt, 5.0, 1.0, slope=2.0) + sigmoid_deduction(crest, CREST_EVIDENCE_THRESHOLD, 1.0, slope=2.0)
        gear_stat_gate = min(1.0, gear_stat_impulse) if not rotation_dominant else 0.0
        if gear_stat_gate > 0.1:
            if car.get("critical"):
                deductions.append(("gear_car_critical", round(8.0 * gear_stat_gate, 2)))
            elif car.get("warning"):
                deductions.append(("gear_car_warning", round(4.0 * gear_stat_gate, 2)))
            if order_peak.get("critical") or order_kurt.get("critical"):
                deductions.append(("gear_order_stat_critical", round(8.0 * gear_stat_gate, 2)))
            elif order_peak.get("warning") or order_kurt.get("warning"):
                deductions.append(("gear_order_stat_warning", round(4.0 * gear_stat_gate, 2)))

    # ═══════ SC/SCoh 循环平稳补充扣分 ═══════
    # 轴承 SC/SCoh 结果：scoh_peak > 0.3 时作为弱证据补充
    scoh_result = bearing_result.get("fault_indicators", {})
    # SC_SCOH 方法的 fault_indicators 包含各故障频率的 scoh_peak
    # 仅当 SC/SCoh 是分析方法时才提取（避免从 envelope 结果中误读）
    bearing_method = bearing_result.get("method", "")
    if bearing_method == "sc_scoh":
        scoh_max = _sf(bearing_result.get("sc_max_value", 0) or
                       max((v.get("scoh_peak", 0) for k, v in scoh_result.items()
                            if isinstance(v, dict) and "scoh_peak" in v), default=0), 0.0)
        # SCoh > 0.3 时作为补充扣分（不受 kurt>5 门控限制）
        # 但权重减半，避免误报
        scoh_ded = sigmoid_deduction(scoh_max, 0.3, 5.0, slope=4.0)
        if scoh_ded > 0.5:
            deductions.append(("bearing_sc_scoh_evidence", round(scoh_ded, 2)))

    # ═══════ NA4/NB4 齿轮趋势指标 ═══════
    # NA4: 归一化差值信号峭度（局部故障趋势指标）
    # NB4: 归一化差值信号包络峭度（更敏感的局部故障趋势指标）
    # NA4 > 3.0 → warning, NA4 > 5.0 → critical（渐进性磨损/裂纹）
    # NB4 > 3.0 → warning, NB4 > 5.0 → critical
    na4_val = _sf(gear_result.get("na4"), 0.0)
    nb4_val = _sf(gear_result.get("nb4"), 0.0)

    if has_gear or (gear_result and any(k in gear_result for k in ["na4", "nb4"])):
        na4_max = max(na4_val, nb4_val)
        if na4_max > 2.0:
            # NA4/NB4 门控：需要齿轮参数或统计证据
            # 渐进性磨损时 kurt 可能不高（行星箱 kurt=8~10），
            # 但 NA4/NB4 趋势指标持续升高
            na4_ded = cascade_deduction(na4_max, [3.0, 5.0], [6, 10])
            # NA4/NB4 > 5 且无 rotation_dominant → 渐进性磨损/裂纹
            # NA4/NB4 > 5 且 rotation_dominant → 可能是转速波动
            if rotation_dominant:
                na4_ded *= 0.3
            if na4_ded > 0.5:
                if na4_max > 5.0:
                    deductions.append(("gear_na4_trend_critical", round(na4_ded, 2)))
                else:
                    deductions.append(("gear_na4_trend_warning", round(na4_ded, 2)))

    # ═══════ 小波包能量熵扣分（齿轮频带能量重分布） ═══════
    # normalized_entropy 过高 → 频带能量异常集中（故障指示）
    # mesh_band_concentration 过高 → 啮合频带能量异常集中
    wp_entropy = gear_result.get("wavelet_packet_entropy")
    if isinstance(wp_entropy, dict):
        wp_ind = gear_ind.get("wavelet_packet_entropy") if isinstance(gear_ind.get("wavelet_packet_entropy"), dict) else {}
        mesh_conc_ind = gear_ind.get("mesh_band_concentration") if isinstance(gear_ind.get("mesh_band_concentration"), dict) else {}
        # 门控：齿轮冲击证据 + 无旋转谐波主导
        wp_gate = min(1.0, gear_impulse if has_gear else gear_stat_impulse) if not rotation_dominant else 0.0
        if wp_gate > 0.1:
            if wp_ind.get("critical"):
                wp_ded = 8.0 * wp_gate
                deductions.append(("gear_wp_entropy_critical", round(wp_ded, 2)))
            elif wp_ind.get("warning"):
                wp_ded = 4.0 * wp_gate
                deductions.append(("gear_wp_entropy_warning", round(wp_ded, 2)))
            if mesh_conc_ind.get("critical"):
                mc_ded = 6.0 * wp_gate
                deductions.append(("gear_mesh_concentration_critical", round(mc_ded, 2)))
            elif mesh_conc_ind.get("warning"):
                mc_ded = 3.0 * wp_gate
                deductions.append(("gear_mesh_concentration_warning", round(mc_ded, 2)))

    return deductions