"""
故障分析引擎

分析流程：
  1. 优先调用神经网络模型（nn_predictor.py）
  2. 如果神经网络未启用，调用新诊断引擎（DiagnosisEngine，支持多种算法配置）
  3. 如果新引擎失败，回退到简化规则算法（FFT + IMF能量 + 阈值判断）

注意：旧规则算法保留作为回退方案，新引擎为默认诊断方式。
"""
import logging
import numpy as np
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from app.services.nn_predictor import predict as nn_predict
from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.signal_utils import (
    estimate_rot_freq_spectrum as _estimate_rot_freq_spectrum,
    _order_band_energy,
    DenoisingError,
)
from app.services.diagnosis.rule_based import _rule_based_analyze
from app.services.diagnosis.features import _get_channel_params, has_bearing_params, has_gear_params
from app.services.diagnosis.channel_consensus import cross_channel_consensus
from app.core.config import DIAGNOSIS_WEIGHTS, ANALYZE_DENOISE_METHOD
from app.services.diagnosis.probability_calibration import calibrate_fault_probabilities
from app.services.diagnosis.gear.planetary import gear_config_for_channel


def _safe_result(msg="分析失败"):
    """崩溃安全默认结果"""
    return {
        "health_score": None, "status": "indeterminate",
        "fault_probabilities": {},
        "imf_energy": {}, "order_analysis": {"channels": {}}, "rot_freq": None,
        "_error": msg,
    }


def analyze_device(
    channels_data: Dict[str, List[float]],
    sample_rate: int = 25600,
    device=None,
    rot_freq: Optional[float] = None,
    denoise_method: str = "",
):
    """
    综合分析 — 按通道配置自动分派轴承/齿轮/混合分析

    denoise_method 参数：
    - "" (空字符串): 使用配置默认值 (ANALYZE_DENOISE_METHOD, 默认 "wavelet")
    - "none": 不使用去噪
    - "wavelet"/"vmd"/"wavelet_vmd"/"wavelet_lms": 使用对应去噪方法

    诊断逻辑（详见 DIAGNOSIS_LOGIC.md）：
      - 每通道独立判断 bearing_params 和 gear_teeth 是否有效
      - 仅有轴承参数 → 只跑轴承分析，跳过齿轮
      - 仅有齿轮参数 → 只跑齿轮分析，跳过轴承
      - 两者都有     → 综合（轴承+齿轮）
      - 两者都无     → 不注入默认机械参数，改用统计指标尽量判断是否异常
    """
    import traceback as _tb

    if not channels_data:
        return _safe_result("空通道数据")

    try:
        nn_result = nn_predict(channels_data, sample_rate)
        if nn_result is not None:
            return nn_result
    except Exception:
        pass

    try:
        strategy = (getattr(device, "diagnosis_strategy", None) or "advanced") if device else "advanced"
        bearing_method = (getattr(device, "bearing_method", None) or "filter_bank_sk") if device else "filter_bank_sk"
        gear_method = (getattr(device, "gear_method", None) or "standard") if device else "standard"
        # 去噪方法优先级：1) 调用方显式传入非空值 2) 设备属性 3) 全局配置默认
        if denoise_method:
            denoise = denoise_method
        elif device and getattr(device, "denoise_method", None):
            denoise = device.denoise_method
        else:
            denoise = ANALYZE_DENOISE_METHOD
        try:
            DenoiseMethod(denoise)
        except ValueError as exc:
            raise DenoisingError(str(denoise), "未知去噪方法") from exc

        channel_results = []
        for ch_idx, (ch_name, signal) in enumerate(channels_data.items(), start=1):
            try:
                sig_arr = np.array(signal, dtype=np.float64)
            except (TypeError, ValueError):
                continue

            ch_bp = _get_channel_params(device, ch_idx, "bearing_params")
            ch_gt = gear_config_for_channel(getattr(device, "gear_teeth", None), ch_idx)

            # 判断该通道有效配置
            has_bearing = has_bearing_params(ch_bp)
            has_gear = has_gear_params(ch_gt)

            engine = DiagnosisEngine(
                strategy=strategy, bearing_method=bearing_method,
                gear_method=gear_method, denoise_method=denoise,
                bearing_params=ch_bp, gear_teeth=ch_gt,
            )
            try:
                result = engine.analyze_research_ensemble(
                    sig_arr, sample_rate, rot_freq=rot_freq,
                    profile="runtime",
                )
            except DenoisingError as exc:
                # 请求的前处理未完成，不能用未经该处理的规则回退假装成功。
                # 保留失败通道，同时允许其他有效通道形成自己的诊断。
                result = {"health_score": None, "status": "indeterminate",
                          "rot_freq_hz": None, "denoise": exc.method,
                          "reason": exc.reason, "error": str(exc),
                          "bearing": {}, "gear": {}}
            channel_results.append((ch_name, result))

        if not channel_results:
            return _safe_result("所有通道数据格式异常")

        evaluable_channels = [(name, result) for name, result in channel_results
                              if result.get("health_score") is not None and result.get("status") != "indeterminate"]
        if not evaluable_channels:
            return {
                "health_score": None, "status": "indeterminate", "fault_probabilities": {},
                "imf_energy": {}, "rot_freq": channel_results[0][1].get("rot_freq_hz"),
                "order_analysis": {
                    "engine_result": channel_results[0][1], "channels": dict(channel_results),
                    "aggregation": {"method": "no_evaluable_channels", "evaluable_channel_count": 0},
                },
            }
        health_values = [int(r["health_score"]) for _, r in evaluable_channels]
        worst_health = min(health_values)
        avg_health = sum(health_values) / len(health_values)

        # 多通道一致性投票
        consensus = cross_channel_consensus([r for _, r in evaluable_channels])

        # 通道可弱融合，但不假设远距离传感器一定强相关。
        # 一致性投票调整融合权重：一致时最差通道权重更高，不一致时降低最差通道权重
        worst_weight = DIAGNOSIS_WEIGHTS.get("worst_channel", 0.35) if consensus["consensus_boost"] >= 1.1 else 0.20
        avg_weight = 1.0 - worst_weight
        device_health = int(round(worst_weight * worst_health + avg_weight * avg_health))

        # 单通道异常惩罚：仅单通道检出且无一致性故障时，扣分降低
        if consensus["single_channel_penalty"] < 1.0:
            # 无一致性故障，降低设备健康度扣分幅度
            penalty_reduction = int(round((100 - device_health) * (1.0 - consensus["single_channel_penalty"])))
            device_health = min(100, device_health + penalty_reduction)

        worst_status = max(
            ([r["status"] for _, r in evaluable_channels]),
            key=lambda s: {"normal": 0, "warning": 1, "fault": 2, "critical": 3}.get(s, 0)
        )
        if worst_status in ("fault", "critical") and avg_health >= 75:
            device_status = "warning"
        elif worst_status == "critical":
            device_status = "critical"
        elif device_health >= 85:
            device_status = "normal"
        elif device_health >= 60:
            device_status = "warning"
        else:
            device_status = "fault"

        merged = {}
        for _, r in channel_results:
            for fname, prob in r.get("bearing", {}).get("evaluation", {}).get("indicators", {}).items():
                if fname.endswith("_stat") or not isinstance(prob, dict):
                    continue
                if prob.get("significant"):
                    snr_val = float(prob.get("snr", 0))
                    # 将轴承参数级指标映射为标准中文故障类型名
                    # BPFO → 轴承外圈故障, BPFI → 轴承内圈故障, BSF → 滚动体故障
                    # 其他轴承指标统一归入"轴承异常"
                    fault_key = "轴承异常"
                    if "BPFO" in fname or "bpfo" in fname:
                        fault_key = "轴承外圈故障"
                    elif "BPFI" in fname or "bpfi" in fname:
                        fault_key = "轴承内圈故障"
                    elif "BSF" in fname or "bsf" in fname:
                        fault_key = "滚动体故障"
                    merged[fault_key] = max(merged.get(fault_key, 0), min(1.0, snr_val / 10))
            for fname, prob in r.get("gear", {}).get("fault_indicators", {}).items():
                if not isinstance(prob, dict):
                    continue
                # 齿轮指标统一归入"齿轮磨损"
                severity = 0.6 if prob.get("critical") else 0.3 if prob.get("warning") else 0
                if severity > 0:
                    merged["齿轮异常"] = max(merged.get("齿轮异常", 0), severity)

        # 概率校准：将原始 SNR/值映射的概率转换为更真实的故障似然
        fault_probs = calibrate_fault_probabilities(merged)

        first_result = channel_results[0][1]
        rf = first_result.get("rot_freq_hz")
        if rf is not None:
            rf = round(float(rf), 3)

        try:
            from app.services.diagnosis.features import compute_imf_energy
            imf_energy = compute_imf_energy(list(channels_data.values())[0], sample_rate)
        except Exception:
            imf_energy = {}

        return {
            "health_score": device_health, "status": device_status,
            "fault_probabilities": fault_probs, "imf_energy": imf_energy,
            "order_analysis": {
                "engine_result": first_result,
                "channels": {ch: r for ch, r in channel_results},
                "aggregation": {
                    "method": "weak_channel_fusion_with_consensus",
                    "worst_health": worst_health,
                    "average_health": round(avg_health, 2),
                    "evaluable_channel_count": len(evaluable_channels),
                    "unavailable_channels": [name for name, result in channel_results if result.get("health_score") is None],
                    "worst_status": worst_status,
                    "consensus": consensus,
                },
            },
            "rot_freq": rf,
            "consensus_hint": consensus.get("recommendation_hint", ""),
        }

    except DenoisingError as e:
        return _safe_result(str(e))
    except Exception as e:
        logger.error(f"[分析] 新诊断引擎异常: {e}\n{_tb.format_exc()}")

    try:
        logger.info("[分析] 回退到规则算法")
        return _rule_based_analyze(channels_data, sample_rate, device)
    except Exception as e2:
        logger.error(f"[分析] 规则算法也失败: {e2}\n{_tb.format_exc()}")

    return _safe_result("所有诊断算法均失败")
