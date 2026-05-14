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
)
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)
from app.services.diagnosis.rule_based import _rule_based_analyze
from app.services.diagnosis.features import _get_channel_params


def _safe_result(msg="分析失败", health=100):
    """崩溃安全默认结果"""
    return {
        "health_score": health, "status": "normal",
        "fault_probabilities": {"正常运行": 1.0},
        "imf_energy": {}, "order_analysis": None, "rot_freq": None,
        "_error": msg,
    }


def _params_valid(params: Optional[Dict], kind: str) -> bool:
    """判断轴承/齿轮参数是否有效（含通道级 None 值处理）"""
    if not params or not isinstance(params, dict):
        return False
    if kind == "bearing":
        try:
            n = params.get("n")
            d = params.get("d")
            D = params.get("D")
            return all(v is not None for v in [n, d, D]) and float(n or 0) > 0 and float(d or 0) > 0 and float(D or 0) > 0
        except (TypeError, ValueError):
            return False
    if kind == "gear":
        try:
            z_in = params.get("input")
            return z_in is not None and float(z_in) > 0
        except (TypeError, ValueError):
            return False
    return False


def analyze_device(
    channels_data: Dict[str, List[float]],
    sample_rate: int = 25600,
    device=None,
    rot_freq: Optional[float] = None,
    denoise_method: str = "none",
):
    """
    综合分析 — 按通道配置自动分派轴承/齿轮/混合分析

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
        strategy = getattr(device, "diagnosis_strategy", "advanced") if device else "advanced"
        bearing_method = getattr(device, "bearing_method", "kurtogram") if device else "kurtogram"
        gear_method = getattr(device, "gear_method", "standard") if device else "standard"
        denoise = denoise_method if denoise_method != "none" else (
            getattr(device, "denoise_method", "none") if device else "none"
        )

        channel_results = []
        for ch_idx, (ch_name, signal) in enumerate(channels_data.items(), start=1):
            try:
                sig_arr = np.array(signal, dtype=np.float64)
            except (TypeError, ValueError):
                continue

            ch_bp = _get_channel_params(device, ch_idx, "bearing_params")
            ch_gt = _get_channel_params(device, ch_idx, "gear_teeth")

            # 判断该通道有效配置
            has_bearing = _params_valid(ch_bp, "bearing")
            has_gear = _params_valid(ch_gt, "gear")

            engine = DiagnosisEngine(
                strategy=strategy, bearing_method=bearing_method,
                gear_method=gear_method, denoise_method=denoise,
                bearing_params=ch_bp, gear_teeth=ch_gt,
            )
            result = engine.analyze_comprehensive(
                sig_arr, sample_rate, rot_freq=rot_freq,
                skip_bearing=False,
                skip_gear=False,
            )
            channel_results.append((ch_name, result))

        if not channel_results:
            return _safe_result("所有通道数据格式异常", 90)

        health_values = [int(r["health_score"]) for _, r in channel_results]
        worst_health = min(health_values)
        avg_health = sum(health_values) / len(health_values)
        # 通道可弱融合，但不假设远距离传感器一定强相关。
        device_health = int(round(0.35 * worst_health + 0.65 * avg_health))
        worst_status = max(
            ([r["status"] for _, r in channel_results]),
            key=lambda s: {"normal": 0, "warning": 1, "fault": 2}.get(s, 0)
        )
        if worst_status == "fault" and avg_health >= 75:
            device_status = "warning"
        elif device_health >= 85:
            device_status = "normal"
        elif device_health >= 60:
            device_status = "warning"
        else:
            device_status = "fault"

        merged = {}
        for _, r in channel_results:
            for fname, prob in r.get("bearing", {}).get("fault_indicators", {}).items():
                if fname.endswith("_stat") or not isinstance(prob, dict):
                    continue
                if prob.get("significant"):
                    snr_val = float(prob.get("snr", 0))
                    merged["轴承" + fname] = max(merged.get("轴承" + fname, 0), min(1.0, snr_val / 10))
            for fname, prob in r.get("gear", {}).get("fault_indicators", {}).items():
                if not isinstance(prob, dict):
                    continue
                key = "齿轮" + fname
                if prob.get("critical"):
                    merged[key] = max(merged.get(key, 0), 0.6)
                elif prob.get("warning"):
                    merged[key] = max(merged.get(key, 0), 0.3)

        fault_probs = {"正常运行": round(float(max(0.0, 1.0 - sum(merged.values()))), 4)}
        for k, v in merged.items():
            fault_probs[k] = round(float(v), 4)

        first_result = channel_results[0][1]
        rf = first_result.get("bearing", {}).get("rot_freq_hz")
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
                    "method": "weak_channel_fusion",
                    "worst_health": worst_health,
                    "average_health": round(avg_health, 2),
                    "worst_status": worst_status,
                },
            },
            "rot_freq": rf,
        }

    except Exception as e:
        logger.error(f"[分析] 新诊断引擎异常: {e}\n{_tb.format_exc()}")

    try:
        logger.info("[分析] 回退到规则算法")
        return _rule_based_analyze(channels_data, sample_rate, device)
    except Exception as e2:
        logger.error(f"[分析] 规则算法也失败: {e2}\n{_tb.format_exc()}")

    return _safe_result(f"所有诊断算法均失败", 85)
