"""
故障诊断算法模块

提供轴承/齿轮故障诊断的完整算法体系，支持前端配置选择不同的诊断策略。

使用方式：
    from app.services.diagnosis import DiagnosisEngine

    engine = DiagnosisEngine(strategy="advanced")
    result = engine.analyze(signal, sample_rate, bearing_params, gear_teeth)
"""
from .engine import DiagnosisEngine, DiagnosisStrategy, BearingMethod, GearMethod, DenoiseMethod
from .features import (
    compute_time_features,
    compute_fft_features,
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
    "compute_time_features",
    "compute_fft_features",
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
