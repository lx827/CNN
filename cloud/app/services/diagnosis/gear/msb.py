"""MSB研究响应适配；不再猜测carrier=mesh/100或声称峰值等价于齿轮故障。"""
import numpy as np
from app.algorithms.composite.msb import MSBParameters
from app.algorithms.pipelines.composite import ModulationBispectrumPipeline
from ..composite import composite_to_dict


def msb_residual_sideband_analysis(signal, fs, mesh_freq, carrier_freq=None, n_segments=8):
    if carrier_freq is None or not np.isfinite(carrier_freq) or carrier_freq <= 0:
        raise ValueError("explicit_modulation_frequency_required_no_mesh_ratio_default")
    if isinstance(n_segments, bool) or not isinstance(n_segments, int) or n_segments < 2:
        raise ValueError("MSB requires at least two segments")
    values = np.asarray(signal, dtype=float)[:int(fs * 5)]
    length = max(32, min(1024, len(values) // n_segments))
    df = fs / length
    modulation = np.unique(np.r_[np.arange(df, min(mesh_freq * .8, carrier_freq * 3), df), carrier_freq])
    return composite_to_dict(ModulationBispectrumPipeline(MSBParameters(length)).run(
        values, fs, [mesh_freq], modulation))
