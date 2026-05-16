"""
故障诊断算法模块

提供轴承/齿轮故障诊断的完整算法体系，支持前端配置选择不同的诊断策略。

使用方式：
    from app.services.diagnosis import DiagnosisEngine

    engine = DiagnosisEngine(strategy="advanced")
    result = engine.analyze(signal, sample_rate, bearing_params, gear_teeth)
"""
from .engine import DiagnosisEngine, DiagnosisStrategy, BearingMethod, GearMethod, DenoiseMethod
from .bearing import (
    envelope_analysis,
    fast_kurtogram,
    cpw_envelope_analysis,
    med_envelope_analysis,
    teager_envelope_analysis,
    spectral_kurtosis_envelope_analysis,
)
from .gear import (
    compute_fm0,
    compute_fm4,
    compute_na4,
    compute_nb4,
    compute_ser,
    compute_car,
    msb_residual_sideband_analysis,
)
from .preprocessing import (
    wavelet_denoise,
    cepstrum_pre_whitening,
    minimum_entropy_deconvolution,
)
from .features import (
    compute_time_features,
    compute_fft_features,
    compute_envelope_features,
)
from .ensemble import run_research_ensemble
from .fusion import (
    dempster_shafer_fusion,
    EvidenceFrame,
    BPA,
    dempster_combination,
    murphy_average_combination,
    DEFAULT_FAULT_TYPES,
)
from .trend_prediction import (
    holt_winters_forecast,
    kalman_smooth_health_scores,
)

__all__ = [
    "DiagnosisEngine",
    "DiagnosisStrategy",
    "envelope_analysis",
    "fast_kurtogram",
    "cpw_envelope_analysis",
    "med_envelope_analysis",
    "teager_envelope_analysis",
    "spectral_kurtosis_envelope_analysis",
    "compute_fm0",
    "compute_fm4",
    "compute_na4",
    "compute_nb4",
    "compute_ser",
    "compute_car",
    "msb_residual_sideband_analysis",
    "wavelet_denoise",
    "cepstrum_pre_whitening",
    "minimum_entropy_deconvolution",
    "compute_time_features",
    "compute_fft_features",
    "compute_envelope_features",
    "run_research_ensemble",
    # D-S 证据融合
    "dempster_shafer_fusion",
    "EvidenceFrame",
    "BPA",
    "dempster_combination",
    "murphy_average_combination",
    "DEFAULT_FAULT_TYPES",
    # 趋势预测
    "holt_winters_forecast",
    "kalman_smooth_health_scores",
]
