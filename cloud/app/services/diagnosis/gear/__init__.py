"""齿轮服务层公共接口；定轴数学实现位于 app.algorithms.gear.fixed_axis。"""
from typing import Dict

from .msb import msb_residual_sideband_analysis
from .planetary_demod import (
    analyze_planetary_sidebands_order,
    planetary_envelope_order_analysis,
    planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis,
    planetary_tsa_envelope_analysis,
    planetary_hp_envelope_order_analysis,
    planetary_sc_scoh_analysis,
    planetary_msb_analysis,
    planetary_cvs_med_analysis,
    evaluate_planetary_demod_results,
)
from .vmd_demod import vmd_fixed_axis_demod_analysis

__all__ = [
    "msb_residual_sideband_analysis",
    "analyze_planetary_sidebands_order",
    "_evaluate_gear_faults",
    "planetary_envelope_order_analysis",
    "planetary_fullband_envelope_order_analysis",
    "planetary_vmd_demod_analysis",
    "planetary_tsa_envelope_analysis",
    "planetary_hp_envelope_order_analysis",
    "planetary_sc_scoh_analysis",
    "planetary_msb_analysis",
    "planetary_cvs_med_analysis",
    "evaluate_planetary_demod_results",
    "vmd_fixed_axis_demod_analysis",
]


def _evaluate_gear_faults(gear_result: Dict) -> Dict:
    """仅评估行星旧读模型；定轴阈值已迁移到 FixedAxisEvaluation。"""
    indicators = {}
    ser = gear_result.get("ser") if gear_result.get("ser") is not None else 0.0
    indicators["ser"] = {
        "value": round(ser, 4),
        "warning": ser > 8.0,
        "critical": ser > 10.0,
    }

    fm4 = gear_result.get("fm4")
    if fm4 is not None:
        indicators["fm4"] = {
            "value": round(fm4, 4),
            "warning": fm4 > 3.2,
            "critical": fm4 > 5.0,
        }
    car = gear_result.get("car")
    if car is not None:
        # 行星 CAR 健康/故障重叠，只记录，不触发告警。
        indicators["car"] = {"value": round(car, 4), "warning": False, "critical": False}

    sidebands = gear_result.get("sidebands", [])
    significant_count = sum(1 for sb in sidebands if sb.get("significant"))
    indicators["sideband_count"] = {
        "value": significant_count,
        "warning": significant_count >= 8,
        "critical": significant_count >= 10,
    }

    order_peak_conc = gear_result.get("order_peak_concentration")
    if order_peak_conc is not None:
        indicators["order_peak_concentration"] = {
            "value": round(order_peak_conc, 4),
            "warning": order_peak_conc > 0.3 or order_peak_conc < 0.1,
            "critical": order_peak_conc > 0.5 or order_peak_conc < 0.05,
        }
    order_kurt = gear_result.get("order_kurtosis")
    if order_kurt is not None:
        indicators["order_kurtosis"] = {
            "value": round(order_kurt, 2),
            "warning": order_kurt > 45.0 or order_kurt < 5.0,
            "critical": order_kurt > 55.0 or order_kurt < 0.0,
        }

    fullband = gear_result.get("planetary_fullband_demod")
    if isinstance(fullband, dict) and "error" not in fullband:
        fek = fullband.get("envelope_kurtosis")
        if fek is not None:
            indicators["planetary_fullband_env_kurt"] = {
                "value": round(float(fek), 4),
                "warning": float(fek) < 5.0,
                "critical": float(fek) < 3.0,
            }

    wp_entropy = gear_result.get("wavelet_packet_entropy")
    if isinstance(wp_entropy, dict):
        norm_entropy = wp_entropy.get("normalized_entropy")
        mesh_conc = wp_entropy.get("mesh_band_concentration")
        if norm_entropy is not None:
            indicators["wavelet_packet_entropy"] = {
                "value": round(norm_entropy, 4),
                "warning": norm_entropy > 0.85,
                "critical": norm_entropy > 0.92,
            }
        if mesh_conc is not None:
            indicators["mesh_band_concentration"] = {
                "value": round(mesh_conc, 6),
                "warning": mesh_conc > 0.6,
                "critical": mesh_conc > 0.75,
            }
    return indicators
