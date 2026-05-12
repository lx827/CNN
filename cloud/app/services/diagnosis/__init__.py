"""
故障诊断算法模块

提供轴承/齿轮故障诊断的完整算法体系，支持前端配置选择不同的诊断策略。

使用方式：
    from app.services.diagnosis import DiagnosisEngine

    engine = DiagnosisEngine(strategy="advanced")
    result = engine.analyze(signal, sample_rate, bearing_params, gear_teeth)
"""
from .core import DiagnosisEngine, DiagnosisStrategy, BearingMethod, GearMethod, DenoiseMethod
from .bearing import (
    envelope_analysis,
    fast_kurtogram,
    cpw_envelope_analysis,
    med_envelope_analysis,
)
from .gear import (
    compute_fm0,
    compute_fm4,
    compute_na4,
    compute_ser,
    compute_car,
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

__all__ = [
    "DiagnosisEngine",
    "DiagnosisStrategy",
    "envelope_analysis",
    "fast_kurtogram",
    "cpw_envelope_analysis",
    "med_envelope_analysis",
    "compute_fm0",
    "compute_fm4",
    "compute_na4",
    "compute_ser",
    "compute_car",
    "wavelet_denoise",
    "cepstrum_pre_whitening",
    "minimum_entropy_deconvolution",
    "compute_time_features",
    "compute_fft_features",
    "compute_envelope_features",
]
