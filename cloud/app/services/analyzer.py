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


def analyze_device(
    channels_data: Dict[str, List[float]],
    sample_rate: int = 25600,
    device=None,
    rot_freq: Optional[float] = None,
    denoise_method: str = "none",
):
    """
    综合分析主函数 — 崩溃安全版本
    """
    import traceback as _tb

    if not channels_data:
        return _safe_result("空通道数据")

    # === 神经网络（预留）===
    try:
        nn_result = nn_predict(channels_data, sample_rate)
        if nn_result is not None:
            return nn_result
    except Exception:
        pass

    # === 新诊断引擎 ===
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
                logger.warning(f"[分析] 通道 {ch_name} 数据格式异常，跳过")
                continue

            ch_bp = _get_channel_params(device, ch_idx, "bearing_params")
            ch_gt = _get_channel_params(device, ch_idx, "gear_teeth")

            engine = DiagnosisEngine(
                strategy=strategy, bearing_method=bearing_method,
                gear_method=gear_method, denoise_method=denoise,
                bearing_params=ch_bp, gear_teeth=ch_gt,
            )
            result = engine.analyze_comprehensive(sig_arr, sample_rate, rot_freq=rot_freq)
            channel_results.append((ch_name, result))

        if not channel_results:
            return _safe_result("所有通道数据格式异常", 90)

        # 最差健康度
        worst_health = int(min(r["health_score"] for _, r in channel_results))
        worst_status = max(
            ([r["status"] for _, r in channel_results]),
            key=lambda s: {"normal": 0, "warning": 1, "fault": 2}.get(s, 0)
        )

        # 合并故障概率
        merged = {}
        for _, r in channel_results:
            for fname, prob in r.get("bearing", {}).get("fault_indicators", {}).items():
                if fname.endswith("_stat"):
                    continue
                if isinstance(prob, dict) and prob.get("significant"):
                    snr_val = float(prob.get("snr", 0))
                    key = "轴承" + fname
                    merged[key] = max(merged.get(key, 0), min(1.0, snr_val / 10))
            for fname, prob in r.get("gear", {}).get("fault_indicators", {}).items():
                if isinstance(prob, dict):
                    key = "齿轮" + fname
                    if prob.get("critical"):
                        merged[key] = max(merged.get(key, 0), 0.6)
                    elif prob.get("warning"):
                        merged[key] = max(merged.get(key, 0), 0.3)

        fault_probs = {"正常运行": round(float(max(0.0, 1.0 - sum(merged.values()))), 4)}
        for k, v in merged.items():
            fault_probs[k] = round(float(v), 4)

        # 转频
        first_result = channel_results[0][1]
        rf = first_result.get("bearing", {}).get("rot_freq_hz")
        if rf is not None:
            rf = round(float(rf), 3)

        # IMF 能量
        try:
            from app.services.diagnosis.features import compute_imf_energy
            imf_energy = compute_imf_energy(list(channels_data.values())[0], sample_rate)
        except Exception:
            imf_energy = {}

        return {
            "health_score": worst_health,
            "status": worst_status,
            "fault_probabilities": fault_probs,
            "imf_energy": imf_energy,
            "order_analysis": {
                "engine_result": first_result,
                "channels": {ch: r for ch, r in channel_results},
            },
            "rot_freq": rf,
        }

    except Exception as e:
        logger.error(f"[分析] 新诊断引擎异常: {e}\n{_tb.format_exc()}")

    # === 回退：规则算法 ===
    try:
        logger.info("[分析] 回退到规则算法")
        return _rule_based_analyze(channels_data, sample_rate, device)
    except Exception as e2:
        logger.error(f"[分析] 规则算法也失败: {e2}\n{_tb.format_exc()}")

    return _safe_result(f"所有诊断算法均失败: {e}", 85)
