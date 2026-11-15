"""转速、连续相位、角域重采样与阶次谱的纯计算算法。"""

from .estimation import (
    SpeedTrajectoryEstimate,
    estimate_autocorrelation_speed,
    estimate_envelope_speed,
    estimate_spectrum_speed,
    estimate_stft_speed_trajectory,
    resolve_stft_window_samples,
)
from .pipeline import (
    AutomaticOrderPipeline,
    ConstantSpeedOrderPipeline,
    FastVaryingSpeedOrderPipeline,
    SlowVaryingSpeedOrderPipeline,
    select_retained_speed_frames,
)
from .resampling import (
    compute_order_spectrum,
    integrate_speed_trajectory,
    order_band_amplitude_sum,
    resample_constant_speed,
    resample_to_phase,
)
from .types import (
    AngleDomainSignal,
    FrameParameters,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    OrderSpectrum,
    PhaseTrajectory,
    RidgeParameters,
    ScalarSpeed,
    SpeedSearchRange,
    SpeedTrajectory,
    TachometerPulses,
)

__all__ = [
    "AngleDomainSignal",
    "AutomaticOrderPipeline",
    "ConstantSpeedOrderPipeline",
    "FastVaryingSpeedOrderPipeline",
    "FrameParameters",
    "LocalSpeedEstimates",
    "OrderAnalysis",
    "OrderParameters",
    "OrderSpectrum",
    "PhaseTrajectory",
    "RidgeParameters",
    "ScalarSpeed",
    "SlowVaryingSpeedOrderPipeline",
    "SpeedSearchRange",
    "SpeedTrajectory",
    "SpeedTrajectoryEstimate",
    "TachometerPulses",
    "compute_order_spectrum",
    "estimate_autocorrelation_speed",
    "estimate_envelope_speed",
    "estimate_spectrum_speed",
    "estimate_stft_speed_trajectory",
    "integrate_speed_trajectory",
    "order_band_amplitude_sum",
    "resample_constant_speed",
    "resample_to_phase",
    "resolve_stft_window_samples",
    "select_retained_speed_frames",
]
