"""
健康度评分模块
"""
from typing import Dict, Optional

# 峰值因子单独作为统计证据门控的阈值。
# CW 健康数据 crest_factor 在 7.6~8.1，刚过 7.0 阈值就打开了统计扣分，
# 导致 false positive。提升至 10.0 — 峰值因子 7~9 在工业振动中属正常范围，
# 真正的冲击故障通常伴随 crest > 10 或 kurt > 5。
CREST_EVIDENCE_THRESHOLD = 10.0


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

    # 是否为齿轮设备：齿轮路径的峭度阈值需要更宽松
    # 行星齿轮箱健康峭度可达 8~10，轴承健康峭度 ≈ 3
    try:
        is_gear_device = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        is_gear_device = False

    # 峭度：冲击信号的核心指标
    # 齿轮设备使用更高的阈值（行星箱正常 kurt=8~10）
    # 轴承设备保持原阈值（轴承正常 kurt≈3）
    if is_gear_device:
        if kurt > 20:
            deductions.append(("kurtosis_extreme", 40))
        elif kurt > 12:
            deductions.append(("kurtosis_high", 25))
        elif kurt > 10:
            deductions.append(("kurtosis_moderate", 15))
    else:
        if kurt > 20:
            deductions.append(("kurtosis_extreme", 40))
        elif kurt > 12:
            deductions.append(("kurtosis_high", 30))
        elif kurt > 8:
            deductions.append(("kurtosis_moderate", 22))
        elif kurt > 5:
            deductions.append(("kurtosis_mild", 15))

    # 峰值因子：单大冲击 vs 持续振动
    # 齿轮设备使用更高阈值（行星箱正常 crest=5~9）
    if is_gear_device:
        if crest > 15:
            deductions.append(("crest_very_high", 15))
        elif crest > 12:
            deductions.append(("crest_high", 10))
    else:
        if crest > 15:
            deductions.append(("crest_very_high", 15))
        elif crest > 10:
            deductions.append(("crest_high", 10))
        elif crest > 7:
            deductions.append(("crest_moderate", 5))

    # 动态基线/趋势：本批次窗口内出现持续漂移或突变时扣分。
    # 变速工况下转速变化会导致 RMS/kurtosis 自然波动，
    # kurt_mad_z > 6 对变速信号是正常现象而非故障漂移。
    # 门控：只有时域冲击证据 (kurt>5 或 crest>10) 存在时才认为基线漂移有意义，
    # 否则 kurtosis 波动只是变速导致的统计噪声。
    rms_mad_z = _sf(time_features.get("rms_mad_z"), 0.0)
    kurt_mad_z = _sf(time_features.get("kurtosis_mad_z"), 0.0)
    ewma_drift = _sf(time_features.get("ewma_drift"), 0.0)
    cusum_score = _sf(time_features.get("cusum_score"), 0.0)

    baseline_has_evidence = (kurt > 5.0 or crest > CREST_EVIDENCE_THRESHOLD)
    if baseline_has_evidence:
        if rms_mad_z > 6 or kurt_mad_z > 6:
            deductions.append(("dynamic_baseline_extreme", 18))
        elif rms_mad_z > 4 or kurt_mad_z > 4:
            deductions.append(("dynamic_baseline_warning", 10))

        if cusum_score > 8 or ewma_drift > 4:
            deductions.append(("trend_drift_warning", 8))

    # ═══════ 轴承故障扣分 ═══════
    # 核心原则：频率匹配和统计路径都只有在时域也有冲击证据时才有效。
    # 健康轴承的旋转谐波也会在包络谱产生峰值，但时域峭度/峰值因子不会异常。
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
    # 检查旋转谐波主导：包络谱能量集中在低频（转频谐波）而非轴承故障频率
    rotation_dominant = False
    low_freq_ind = bearing_ind.get("low_freq_ratio")
    if isinstance(low_freq_ind, dict):
        rotation_dominant = low_freq_ind.get("rotation_harmonic_dominant", False)

    # 物理参数路径：时域有冲击(kurt>5)时频率匹配才有效
    if kurt > 5.0:
        if freq_sig_count >= 2:
            deductions.append(("bearing_multi_freq", 10))
        elif freq_sig_count == 1:
            deductions.append(("bearing_single_freq", 5))
    # 统计路径：必须同时有时域异常证据(kurt>5 或 crest>10) 且非旋转谐波主导
    # 否则健康数据也会被误判（旋转谐波的包络谱峰也能触发统计指标）
    # 注意：crest > 7~9 在 CW 健康数据上也能出现，提升证据阈值至 10
    stat_has_evidence = (kurt > 5.0 or crest > CREST_EVIDENCE_THRESHOLD) and not rotation_dominant
    if stat_has_evidence and stat_sig_count >= 2:
        deductions.append(("bearing_statistical_abnormal", 10))
    elif stat_has_evidence and stat_sig_count == 1:
        deductions.append(("bearing_statistical_hint", 5))

    # ═══════ 齿轮故障扣分（故障类型注释）═══════
    gear_ind = gear_result.get("fault_indicators", {})
    try:
        has_gear = bool(gear_teeth and float(gear_teeth.get("input") or 0) > 0)
    except (TypeError, ValueError):
        has_gear = False

    # 齿轮振动与轴承振动的时域证据标准不同：
    # 行星齿轮箱健康工况下 kurtosis 可达 8~10（行星轮系固有调制），
    # 而轴承健康数据 kurtosis ≈ 3。因此齿轮路径需要更严格的证据门控。
    # 齿轮冲击的证据阈值：kurtosis > 12 或 crest_factor > 12
    # （行星齿轮箱健康数据 kurt=8~10, crest=5~10.7；N1_45的crest=10.47刚低于12）
    # 真实齿轮故障中断齿Br_B1_35的crest=13.6 > 12，是唯一超过此阈值的断齿工况
    # 缺齿Mi的kurt=16~38远超12，磨损We_W1_20的kurt=14.65也超过12
    # 健康N1_45(kurt=21.9)仍会触发——这是已知局限（行星箱高转速健康峭度偏高）
    GEAR_KURT_THRESHOLD = 12.0
    GEAR_CREST_THRESHOLD = 12.0

    # 从轴承或齿轮指标中判断旋转谐波主导
    # 当轴承被 skip 时，bearing_ind 为空，需要从 gear_ind 中获取
    low_freq_ind = bearing_ind.get("low_freq_ratio") if bearing_ind else None
    if isinstance(low_freq_ind, dict):
        rotation_dominant = low_freq_ind.get("rotation_harmonic_dominant", rotation_dominant)
    # 齿轮数据中也可能有低频占优的指标
    low_freq_gear = gear_ind.get("low_freq_ratio") if isinstance(gear_ind.get("low_freq_ratio"), dict) else None
    if low_freq_gear and low_freq_gear.get("rotation_harmonic_dominant"):
        rotation_dominant = True

    if has_gear:
        # 齿轮频率匹配路径：使用齿轮专用证据阈值
        # 行星齿轮箱健康数据 kurt=8~10 不应打开齿轮扣分路径
        gear_freq_has_evidence = (kurt > GEAR_KURT_THRESHOLD or crest > GEAR_CREST_THRESHOLD) and not rotation_dominant
        if gear_freq_has_evidence:
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

    # TSA 残差峭度路径：行星齿轮箱最有效的补充指标（区分力=3.31）
    # TSA 消除同步啮合成分后残差峭度 > 2.5 时扣分
    # 健康median=1.19, 故障median=3.95, 区分力=3.31
    # 此路径独立于 gear_freq_has_evidence，不要求 kurt>12 作为前提
    tsa_env_result = gear_result.get("planetary_tsa_demod") or {}
    if isinstance(tsa_env_result, dict) and "error" not in tsa_env_result:
        tsa_residual_kurt = float(tsa_env_result.get("residual_kurtosis", 0.0))
        if tsa_residual_kurt > 5.0 and not rotation_dominant:
            deductions.append(("gear_tsa_residual_kurtosis_critical", 15))
        elif tsa_residual_kurt > 2.5 and not rotation_dominant:
            deductions.append(("gear_tsa_residual_kurtosis_warning", 8))

    if not has_gear:
        car = gear_ind.get("car", {}) if isinstance(gear_ind.get("car"), dict) else {}
        order_peak = gear_ind.get("order_peak_concentration", {}) if isinstance(gear_ind.get("order_peak_concentration"), dict) else {}
        order_kurt = gear_ind.get("order_kurtosis", {}) if isinstance(gear_ind.get("order_kurtosis"), dict) else {}
        # 齿轮统计指标同样需要时域证据门控
        # 无齿轮参数时使用轴承级别的证据阈值（kurt>5 或 crest>10）
        # 因为此时信号来自轴承传感器，轴承健康 kurt≈3
        gear_stat_has_evidence = (kurt > 5.0 or crest > CREST_EVIDENCE_THRESHOLD) and not rotation_dominant
        if gear_stat_has_evidence:
            if car.get("critical"):
                deductions.append(("gear_car_critical", 8))
            elif car.get("warning"):
                deductions.append(("gear_car_warning", 4))
            if order_peak.get("critical") or order_kurt.get("critical"):
                deductions.append(("gear_order_stat_critical", 8))
            elif order_peak.get("warning") or order_kurt.get("warning"):
                deductions.append(("gear_order_stat_warning", 4))
        # 无时域证据时，齿轮统计指标不扣分（仅在结果中标记，不影响健康度）
        # CAR > 3.0 可能是旋转谐波导致的倒谱峰值，不是真正的齿轮故障

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
