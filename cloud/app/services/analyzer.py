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


def analyze_device(
    channels_data: Dict[str, List[float]],
    sample_rate: int = 25600,
    device=None,
    rot_freq: Optional[float] = None,
    denoise_method: str = "none",
):
    """
    综合分析主函数

    Args:
        channels_data: 通道数据字典 {ch_name: [samples...]}
        sample_rate: 采样率 Hz
        device: 设备配置对象（含齿轮/轴承参数等），可为 None
        rot_freq: 指定转频 Hz，传入则跳过自动估计
        denoise_method: 去噪方法 "none"/"wavelet"/"vmd"，默认 none
    """
    if not channels_data:
        return {
            "health_score": 100, "status": "normal",
            "fault_probabilities": {"正常运行": 1.0},
            "imf_energy": {}, "order_analysis": None, "rot_freq": None,
        }

    nn_result = nn_predict(channels_data, sample_rate)
    if nn_result is not None:
        logger.info("[分析] 使用神经网络模型预测结果")
        return nn_result

    try:
        strategy = getattr(device, "diagnosis_strategy", "advanced") if device else "advanced"
        bearing_method = getattr(device, "bearing_method", "kurtogram") if device else "kurtogram"
        gear_method = getattr(device, "gear_method", "standard") if device else "standard"
        # 优先使用传入的 denoise_method，其次取设备配置
        denoise = denoise_method if denoise_method != "none" else (
            getattr(device, "denoise_method", "none") if device else "none"
        )

        channel_results = []
        for ch_idx, (ch_name, signal) in enumerate(channels_data.items(), start=1):
            # 防御：确保 signal 是有效的数值数组
            try:
                sig_arr = np.array(signal, dtype=np.float64)
            except (TypeError, ValueError):
                logger.warning(f"[分析] 通道 {ch_name} 数据格式异常，跳过")
                continue

            ch_bearing_params = _get_channel_params(device, ch_idx, "bearing_params")
            ch_gear_teeth = _get_channel_params(device, ch_idx, "gear_teeth")

            engine = DiagnosisEngine(
                strategy=strategy,
                bearing_method=bearing_method,
                gear_method=gear_method,
                denoise_method=denoise,
                bearing_params=ch_bearing_params,
                gear_teeth=ch_gear_teeth,
            )
            result = engine.analyze_comprehensive(sig_arr, sample_rate, rot_freq=rot_freq)
            channel_results.append((ch_name, result))

        if not channel_results:
            logger.warning("[分析] 所有通道数据格式异常，返回默认结果")
            return {
                "health_score": 100, "status": "normal",
                "fault_probabilities": {"正常运行": 1.0},
                "imf_energy": {}, "order_analysis": None, "rot_freq": None,
            }

        worst_health = min(r["health_score"] for _, r in channel_results)
        worst_status = max(
            ([r["status"] for _, r in channel_results]),
            key=lambda s: {"normal": 0, "warning": 1, "fault": 2}[s]
        )

        merged_probs = {}
        for _, r in channel_results:
            for fault_name, prob in r.get("bearing", {}).get("fault_indicators", {}).items():
                if prob.get("significant"):
                    merged_probs.setdefault("轴承" + fault_name, 0)
                    merged_probs["轴承" + fault_name] = max(merged_probs["轴承" + fault_name], min(1.0, prob.get("snr", 0) / 10))
            for fault_name, prob in r.get("gear", {}).get("fault_indicators", {}).items():
                if isinstance(prob, dict):
                    merged_probs.setdefault("齿轮" + fault_name, 0)
                    if prob.get("warning"):
                        merged_probs["齿轮" + fault_name] = max(merged_probs["齿轮" + fault_name], 0.3)
                    if prob.get("critical"):
                        merged_probs["齿轮" + fault_name] = max(merged_probs["齿轮" + fault_name], 0.6)

        fault_probabilities = {"正常运行": max(0.0, 1.0 - sum(merged_probs.values()))}
        for k, v in merged_probs.items():
            fault_probabilities[k] = round(v, 4)

        first_ch, first_result = channel_results[0]

        # 计算 IMF 能量分布（兼容旧接口）
        from app.services.diagnosis.features import compute_imf_energy
        first_signal = list(channels_data.values())[0]
        imf_energy = compute_imf_energy(first_signal, sample_rate)

        legacy_result = {
            "health_score": worst_health,
            "status": worst_status,
            "fault_probabilities": fault_probabilities,
            "imf_energy": imf_energy,
            "order_analysis": {
                "engine_result": first_result,
                "channels": {ch: r for ch, r in channel_results},
            },
            "rot_freq": first_result.get("bearing", {}).get("rot_freq_hz"),
        }

        logger.info(f"[分析] 新诊断引擎完成，健康度={worst_health}，状态={worst_status}")
        return legacy_result

    except Exception as e:
        logger.error(f"[分析] 新诊断引擎异常: {e}，回退到规则算法")

    # 3. 回退到简化规则算法
    logger.info("[分析] 使用简化规则算法")
    return _rule_based_analyze(channels_data, sample_rate, device)
