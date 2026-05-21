"""Multi-method diagnosis ensemble for high-recall fault detection.

The module keeps the heavy, research-style algorithms callable without making
the real-time pages depend on a single fragile threshold. It uses weak voting:
each algorithm contributes evidence, but a channel is not marked faulty unless
several independent indicators agree.

Health score and status are now computed via `_compute_health_score()` from
`health_score.py`, ensuring consistency with the single-method diagnosis path.
The ensemble voting results are preserved for detailed display but no longer
override the authoritative health score.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .engine import BearingMethod, DenoiseMethod, DiagnosisEngine, DiagnosisStrategy, GearMethod
from .features import compute_time_features, has_bearing_params, has_gear_params
from .health_score import _compute_health_score, get_ds_label, is_ds_conflict_high, _infer_gear_subtype_from_indicators
from .hyperparams import HyperParams
from .recommendation import _generate_recommendation


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_denoise(value: str) -> DenoiseMethod:
    try:
        return DenoiseMethod(value)
    except ValueError:
        return DenoiseMethod.NONE


def _profile_config(profile: str, denoise_method: str) -> Dict[str, list]:
    configured_denoise = _safe_denoise(denoise_method).value
    denoise_methods = ["none"]
    if configured_denoise != "none":
        denoise_methods.append(configured_denoise)

    if profile == "exhaustive":
        return {
            "denoise": list(dict.fromkeys(denoise_methods + ["wavelet", "vmd", "wavelet_vmd", "wavelet_lms", "emd", "ceemdan", "savgol", "wavelet_packet", "eemd"])),
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.KURTOGRAM,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
                BearingMethod.MED,
                BearingMethod.SC_SCOH,
                BearingMethod.MCKD,
                BearingMethod.WP,
                BearingMethod.DWT,
                BearingMethod.EMD_ENVELOPE,
                BearingMethod.CEEMDAN_ENVELOPE,
                BearingMethod.VMD_ENVELOPE,
            ],
            "gear": [GearMethod.STANDARD, GearMethod.ADVANCED],
        }

    if profile == "balanced":
        return {
            "denoise": denoise_methods,
            "bearing": [
                BearingMethod.ENVELOPE,
                BearingMethod.KURTOGRAM,
                BearingMethod.CPW,
                BearingMethod.TEAGER,
                BearingMethod.SPECTRAL_KURTOSIS,
                BearingMethod.MCKD,
                BearingMethod.EMD_ENVELOPE,
                BearingMethod.VMD_ENVELOPE,
            ],
            "gear": [GearMethod.ADVANCED],
        }

    return {
        "denoise": denoise_methods[:1],
        "bearing": [
            BearingMethod.ENVELOPE,
            BearingMethod.KURTOGRAM,
            BearingMethod.CPW,
            BearingMethod.TEAGER,
        ],
        "gear": [GearMethod.ADVANCED],
    }


def _bearing_confidence(result: Dict, time_features: Dict) -> Dict[str, Any]:
    indicators = result.get("fault_indicators", {}) or {}
    param_hits = 0
    stat_hits = 0
    strongest_snr = 0.0
    hit_names = []

    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        significant = bool(item.get("significant"))
        strongest_snr = max(strongest_snr, _as_float(item.get("snr")))
        if name.endswith("_stat") or name in {
            "envelope_peak_snr",
            "envelope_kurtosis",
            "moderate_kurtosis",
            "envelope_crest_factor",
            "high_freq_ratio",
            "peak_concentration",
        }:
            if significant:
                stat_hits += 1
                hit_names.append(name)
        elif significant:
            param_hits += 1
            hit_names.append(name)

    kurt = _as_float(time_features.get("kurtosis"), 3.0)
    crest = _as_float(time_features.get("crest_factor"), 5.0)
    rms_mad_z = _as_float(time_features.get("rms_mad_z"), 0.0)
    cusum = _as_float(time_features.get("cusum_score"), 0.0)
    _crest_ev = HyperParams().get_float("diagnosis.bearing.crest_evidence_threshold", 10.0)
    _kurt_ctx = HyperParams().get_float("diagnosis.bearing.impulse_context_kurt", 5.0)
    impulse_context = kurt > _kurt_ctx or crest > _crest_ev

    # 低频优势度：仅用于弱证据（stat_hits=1）场景的辅助判断
    low_freq_dominance = False
    low_freq_indicator = indicators.get("low_freq_ratio", {})
    low_freq_ratio_raw = _as_float(low_freq_indicator.get("value") if isinstance(low_freq_indicator, dict) else low_freq_indicator, 0.0)
    if low_freq_ratio_raw > 0.55:
        low_freq_dominance = True

    confidence = 0.0
    if param_hits >= 2:
        confidence = 0.85
    elif param_hits == 1 and (stat_hits >= 1 or impulse_context):
        confidence = 0.65
    elif stat_hits >= 3 and impulse_context:
        confidence = 0.65
    elif stat_hits >= 2 and impulse_context:
        # 双统计指标 + 冲击背景：内圈/外圈/球故障典型模式
        # moderate_kurtosis 使外圈也能进入此路径
        confidence = 0.55
    elif stat_hits >= 1 and impulse_context and strongest_snr > 12:
        # 单统计指标 + 冲击背景 + 较显著 SNR：
        # 外圈故障仅触发 moderate_kurtosis 而无 envelope_kurtosis 时的兜底
        # 若包络谱低频占优（轴频谐波），则降权抑制误报
        if low_freq_dominance:
            confidence = 0.28
        else:
            confidence = 0.45
    elif stat_hits >= 2:
        confidence = 0.35
    elif strongest_snr > 18 and impulse_context:
        confidence = 0.5

    return {
        "confidence": round(float(confidence), 4),
        "param_hits": int(param_hits),
        "stat_hits": int(stat_hits),
        "strongest_snr": round(float(strongest_snr), 3),
        "hits": hit_names,
        "abnormal": bool(confidence >= 0.55),
    }


def _gear_confidence(result: Dict, has_gear_params: bool, time_features: Optional[Dict] = None) -> Dict[str, Any]:
    indicators = result.get("fault_indicators", {}) or {}
    warning_hits = 0
    critical_hits = 0
    hit_names = []

    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        if item.get("critical"):
            critical_hits += 1
            hit_names.append(name)
        elif item.get("warning"):
            warning_hits += 1
            hit_names.append(name)

    # 齿轮专用证据阈值
    kurt = _as_float(time_features.get("kurtosis") if time_features else None, 3.0)
    crest = _as_float(time_features.get("crest_factor") if time_features else None, 5.0)

    # 行星齿轮箱时域特征与健康/故障严重重叠，需单独处理
    is_planetary = bool(result.get("planet_count", 0) >= 3)
    if is_planetary:
        # 行星箱健康 kurt=7~13, crest=7~11；故障分布极宽
        # crack 时 kurt 显著降低（3.9~5.5），双向门控：高峭度 + 低峭度
        # 从 HyperParams 加载，默认 6.0/8.0（Bug #13b）
        GEAR_KURT_THRESHOLD = HyperParams().get_float("diagnosis.gear.gear_kurt_threshold", 6.0)
        GEAR_CREST_THRESHOLD = HyperParams().get_float("diagnosis.gear.gear_crest_threshold", 8.0)
        impulse_context = kurt > GEAR_KURT_THRESHOLD or crest > GEAR_CREST_THRESHOLD or kurt < 5.5
    else:
        # 定轴齿轮箱：齿轮故障主要表现为频域调制边带，时域冲击不一定明显
        GEAR_KURT_THRESHOLD = HyperParams().get_float("diagnosis.gear.gear_kurt_threshold", 8.0)
        GEAR_CREST_THRESHOLD = HyperParams().get_float("diagnosis.gear.gear_crest_threshold", 8.0)
        impulse_context = kurt > GEAR_KURT_THRESHOLD or crest > GEAR_CREST_THRESHOLD
        # 频域指标强时即使时域证据弱也打开门控
        if not impulse_context:
            critical_count = sum(1 for v in indicators.values() if isinstance(v, dict) and v.get("critical"))
            warning_count = sum(1 for v in indicators.values() if isinstance(v, dict) and v.get("warning"))
            if critical_count >= 2 or (critical_count >= 1 and warning_count >= 2):
                impulse_context = True

    # TSA 残差峭度证据：区分力=3.31，行星箱最有效的补充指标
    # TSA 消除同步啮合成分后残差峭度 > 2.5 时增加齿轮置信度
    tsa_residual_kurt = 0.0
    tsa_env_result = result.get("planetary_tsa_demod") or {}
    if isinstance(tsa_env_result, dict) and "error" not in tsa_env_result:
        tsa_residual_kurt = _as_float(tsa_env_result.get("residual_kurtosis"), 0.0)
    TSA_RESIDUAL_KURT_THRESHOLD = HyperParams().get_float("diagnosis.gear.tsa_residual_kurt_threshold", 5.0)
    tsa_evidence = tsa_residual_kurt > TSA_RESIDUAL_KURT_THRESHOLD

    # 检查低频优势（旋转谐波主导时齿轮指标无效）
    rotation_dominant = False
    low_freq_ind = indicators.get("low_freq_ratio")
    if isinstance(low_freq_ind, dict):
        lf_value = _as_float(low_freq_ind.get("value"), 0.0)
        if lf_value > 0.55:
            rotation_dominant = True

    confidence = 0.0
    if has_gear_params:
        # 有齿轮参数时：SER/sideband 是频率匹配指标，更有区分力
        # 但仍需要时域冲击证据来排除旋转谐波导致的假阳性
        if impulse_context and not rotation_dominant:
            if critical_hits >= 1 and (warning_hits + critical_hits) >= 2:
                confidence = 0.8
            elif critical_hits >= 1 or warning_hits >= 2:
                confidence = 0.6
            elif warning_hits == 1:
                confidence = 0.35
            elif tsa_evidence:
                # kurt>12 但无频域指标时，TSA 残差峭度可作为补充证据
                confidence = 0.35
        elif tsa_evidence and not rotation_dominant:
            # 无传统时域证据(kurt<12) 但 TSA 残差峭度 > 5.0
            # 这捕捉了 kurt 与健康重叠(8~10)但 TSA 残差显著(>5.0)的故障
            confidence = 0.35
        else:
            # 无时域冲击证据或旋转谐波主导：齿轮指标降权
            if is_planetary:
                # 行星箱频域指标有独立区分力，warning hits 也给予弱置信度
                if critical_hits >= 1 and warning_hits >= 1:
                    confidence = 0.35
                elif critical_hits >= 1:
                    confidence = 0.3
                elif warning_hits >= 2:
                    confidence = 0.25
                elif warning_hits == 1:
                    confidence = 0.15
                else:
                    confidence = 0.0
            else:
                # 旋转谐波的边频带/SER/CAR 都会触发指标，但不是真实齿轮故障
                if critical_hits >= 3 and warning_hits >= 1:
                    confidence = 0.35  # 仅弱证据
                elif critical_hits >= 2:
                    confidence = 0.25
                else:
                    confidence = 0.0
    else:
        # Without gear geometry, CAR/order statistics are weak evidence only.
        if impulse_context and not rotation_dominant:
            if critical_hits >= 2:
                confidence = 0.35
            elif critical_hits == 1 and warning_hits >= 1:
                confidence = 0.3
            elif warning_hits >= 2:
                confidence = 0.25
            elif tsa_evidence:
                confidence = 0.25
        elif tsa_evidence and not rotation_dominant:
            confidence = 0.25
        else:
            # 无时域证据时，CAR/order 统计指标不可靠
            confidence = 0.0

    return {
        "confidence": round(float(confidence), 4),
        "warning_hits": int(warning_hits),
        "critical_hits": int(critical_hits),
        "hits": hit_names,
        "abnormal": bool(confidence >= 0.55),
    }


def _time_confidence(time_features: Dict) -> float:
    kurt = _as_float(time_features.get("kurtosis"), 3.0)
    crest = _as_float(time_features.get("crest_factor"), 5.0)

    score = 0.0
    if kurt > 20:
        score = max(score, 0.85)
    elif kurt > 12:
        score = max(score, 0.7)
    elif kurt > 8:
        score = max(score, 0.55)
    elif kurt > 5:
        score = max(score, 0.35)

    _crest_ev = HyperParams().get_float("diagnosis.bearing.crest_evidence_threshold", 10.0)
    if crest > 15:
        score = max(score, 0.65)
    elif crest > _crest_ev:
        score = max(score, 0.45)

    # 动态基线不作为冲击证据——变速工况下基线指标天然偏高
    return round(float(score), 4)


def _fault_label(best_bearing: Dict, best_gear: Dict, bearing_score: float, gear_score: float) -> str:
    # 齿轮路径优先：当齿轮有指标时优先选齿轮标签，避免轴承在纯齿轮数据上误报
    gear_subtype = _infer_gear_subtype_from_indicators(best_gear)
    if gear_score >= 0.55 or (gear_score > 0 and gear_subtype):
        if gear_subtype:
            return f"gear_{gear_subtype}"
        if gear_score >= 0.55:
            return "gear_abnormal"
    # 齿轮有微弱信号但不足以判定 → 尝试轴承
    if gear_score > bearing_score and gear_subtype:
        return f"gear_{gear_subtype}"

    indicators = best_bearing.get("fault_indicators", {}) if best_bearing else {}
    param_hits = [
        (name, float(item.get("snr", 0.0)))
        for name, item in indicators.items()
        if isinstance(item, dict) and item.get("significant") and not name.endswith("_stat")
    ]
    if param_hits:
        # 按 SNR 降序取主导故障类型，避免多故障拼接导致子串误判
        param_hits.sort(key=lambda x: x[1], reverse=True)
        dominant = param_hits[0][0].lower()
        return f"bearing_{dominant}"
    if bearing_score >= 0.55:
        return "bearing_abnormal"
    return "unknown"


def run_research_ensemble(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    gear_teeth: Optional[Dict] = None,
    denoise_method: str = "none",
    rot_freq: Optional[float] = None,
    profile: str = "runtime",
    max_seconds: float = 5.0,
    dataset: str = "default",
) -> Dict[str, Any]:
    arr = np.array(signal, dtype=np.float64)
    if max_seconds and max_seconds > 0:
        max_samples = int(fs * max_seconds)
        if len(arr) > max_samples:
            arr = arr[:max_samples]

    config = _profile_config(profile, denoise_method)
    has_gear = has_gear_params(gear_teeth)
    has_bearing = has_bearing_params(bearing_params)

    # 参数有效性驱动的分析跳过逻辑：
    # - 仅配置轴承参数 → 只做轴承诊断，跳过齿轮（避免齿轮统计指标误报）
    # - 仅配置齿轮参数 → 只做齿轮诊断，跳过轴承（避免轴承统计指标误报）
    # - 都未配置 → 跑轴承统计指标（始终计算）+ 齿轮统计指标（仅 CAR/阶次峭度）
    # - 都配置 → 综合（轴承+齿轮）全跑
    skip_bearing = not has_bearing and has_gear
    skip_gear = not has_gear and has_bearing

    bearing_results: Dict[str, Dict] = {}
    gear_results: Dict[str, Dict] = {}
    bearing_votes: Dict[str, Dict] = {}
    gear_votes: Dict[str, Dict] = {}
    rot_freq_by_denoise: Dict[str, float] = {}

    best_time_features: Optional[Dict] = None
    best_bearing_key = None
    best_gear_key = None

    for denoise in config["denoise"]:
        base = DiagnosisEngine(
            strategy=DiagnosisStrategy.STANDARD,
            denoise_method=_safe_denoise(denoise),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
            dataset=dataset,
        )
        proc = base.preprocess(arr)
        time_features = compute_time_features(proc)
        if best_time_features is None:
            best_time_features = time_features

        rf = rot_freq
        cached_oa = cached_os = None
        if rf is None:
            try:
                rf, cached_oa, cached_os, _, _ = base._estimate_rot_freq(proc, fs)
            except Exception:
                rf = 0.0
        rot_freq_by_denoise[denoise] = round(float(rf or 0.0), 3)

        for method in config["bearing"]:
            if skip_bearing:
                continue
            key = f"{denoise}:{method.value}"
            try:
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.STANDARD,
                    bearing_method=method,
                    denoise_method=_safe_denoise(denoise),
                    bearing_params=bearing_params,
                    gear_teeth=gear_teeth,
                    dataset=dataset,
                )
                result = engine.analyze_bearing(proc, fs, rf, preprocess=False)
                result["denoise"] = denoise
                bearing_results[key] = result
                vote = _bearing_confidence(result, time_features)
                bearing_votes[key] = vote
                if best_bearing_key is None or vote["confidence"] > bearing_votes[best_bearing_key]["confidence"]:
                    best_bearing_key = key
            except Exception as exc:
                bearing_results[key] = {"error": str(exc), "denoise": denoise, "method": method.value}
                bearing_votes[key] = {"confidence": 0.0, "abnormal": False, "error": str(exc)}

        for method in config["gear"]:
            if skip_gear:
                continue
            key = f"{denoise}:{method.value}"
            try:
                engine = DiagnosisEngine(
                    strategy=DiagnosisStrategy.STANDARD,
                    gear_method=method,
                    denoise_method=_safe_denoise(denoise),
                    bearing_params=bearing_params,
                    gear_teeth=gear_teeth,
                    dataset=dataset,
                )
                # exhaustive profile 启用行星箱慢方法（VMD/SC/SCoh/MSB）
                if profile == "exhaustive":
                    engine._run_slow_methods = True
                result = engine.analyze_gear(
                    proc,
                    fs,
                    rf,
                    preprocess=False,
                    _cached_oa=cached_oa,
                    _cached_os=cached_os,
                )
                result["denoise"] = denoise
                gear_results[key] = result
                vote = _gear_confidence(result, has_gear, time_features)
                gear_votes[key] = vote
                if best_gear_key is None or vote["confidence"] > gear_votes[best_gear_key]["confidence"]:
                    best_gear_key = key
            except Exception as exc:
                gear_results[key] = {"error": str(exc), "denoise": denoise, "method": method.value}
                gear_votes[key] = {"confidence": 0.0, "abnormal": False, "error": str(exc)}

    time_features = best_time_features or compute_time_features(arr)
    time_score = _time_confidence(time_features)

    bearing_conf = [v.get("confidence", 0.0) for v in bearing_votes.values()]
    gear_conf = [v.get("confidence", 0.0) for v in gear_votes.values()]
    bearing_vote_fraction = (
        sum(1 for v in bearing_conf if v >= 0.55) / len(bearing_conf)
        if bearing_conf else 0.0
    )
    gear_vote_fraction = (
        sum(1 for v in gear_conf if v >= 0.55) / len(gear_conf)
        if gear_conf else 0.0
    )

    # 被跳过的分析路径 score 强制为 0
    bearing_score = (max(bearing_conf or [0.0]) * 0.55 + bearing_vote_fraction * 0.45) if not skip_bearing else 0.0
    gear_score = (max(gear_conf or [0.0]) * 0.65 + gear_vote_fraction * 0.35) if not skip_gear else 0.0
    likelihood = max(time_score * 0.6, bearing_score, gear_score)

    best_bearing = bearing_results.get(best_bearing_key, {}) if best_bearing_key else {}
    best_gear = gear_results.get(best_gear_key, {}) if best_gear_key else {}
    fault_label = _fault_label(best_bearing, best_gear, bearing_score, gear_score)

    # ── D-S 证据融合 ──
    # 将轴承和齿轮的投票结果通过 Dempster-Shafer 证据理论融合，
    # 得到综合故障概率分布。融合结果参与最终决策：
    # - dominant_probability > 0.4 且 uncertainty < 0.3 时纳入 fault_label
    # - conflict > 0.8 时降低健康度并提示人工复核
    ds_fusion_result = {}
    try:
        from .fusion.ds_fusion import dempster_shafer_fusion
        # 合并轴承和齿轮的投票为统一 method_results
        all_method_votes = {}
        for key, vote in bearing_votes.items():
            all_method_votes[key] = {
                "confidence": vote.get("confidence", 0.0),
                "abnormal": vote.get("abnormal", False),
                "hits": vote.get("hits", []),
            }
        for key, vote in gear_votes.items():
            all_method_votes[key] = {
                "confidence": vote.get("confidence", 0.0),
                "abnormal": vote.get("abnormal", False),
                "hits": vote.get("hits", []),
            }
        ds_fusion_result = dempster_shafer_fusion(all_method_votes, time_features=time_features)
    except Exception as exc:
        ds_fusion_result = {"error": str(exc)}

    # 使用 health_score.py 的连续衰减评分逻辑计算健康度和状态
    # D-S 融合结果参与决策：高冲突扣分、主导故障纳入 fault_label
    health_score, status, deductions = _compute_health_score(
        gear_teeth,
        time_features,
        best_bearing,
        best_gear,
        ds_fusion_result=ds_fusion_result,
    )

    # D-S 融合主导故障标签
    ds_fault_label = get_ds_label(ds_fusion_result)
    if ds_fault_label:
        fault_label = ds_fault_label

    return {
        "health_score": health_score,
        "status": status,
        "fault_likelihood": round(float(likelihood), 4),
        "fault_label": fault_label,
        "rot_freq_hz": next(iter(rot_freq_by_denoise.values()), None),
        "time_features": time_features,
        "bearing": best_bearing,
        "gear": best_gear,
        "bearing_results": bearing_results,
        "gear_results": gear_results,
        "ensemble": {
            "profile": profile,
            "rot_freq_by_denoise": rot_freq_by_denoise,
            "bearing_votes": bearing_votes,
            "gear_votes": gear_votes,
            "bearing_vote_fraction": round(float(bearing_vote_fraction), 4),
            "gear_vote_fraction": round(float(gear_vote_fraction), 4),
            "time_confidence": time_score,
            "bearing_confidence": round(float(bearing_score), 4),
            "gear_confidence": round(float(gear_score), 4),
            "best_bearing": best_bearing_key,
            "best_gear": best_gear_key,
            "skip_bearing": skip_bearing,
            "skip_gear": skip_gear,
            "has_bearing_params": has_bearing,
            "has_gear_params": has_gear,
            "ds_fusion": ds_fusion_result,
        },
        "recommendation": _generate_recommendation(
            best_bearing, best_gear, status,
            ds_conflict_high=is_ds_conflict_high(ds_fusion_result),
            deductions=deductions,
        ),
    }
