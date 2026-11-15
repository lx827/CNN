"""通用信号变换公共接口；各表示保留 NumPy 数组和明确单位。"""

from .display import decimate_extrema
from .envelope import compute_bandpass_hilbert_envelope
from .spectrum import FourierSpectrum, compute_spectrum
from .stft import STFTRepresentation, compute_stft

__all__ = [
    "FourierSpectrum",
    "STFTRepresentation",
    "compute_bandpass_hilbert_envelope",
    "compute_spectrum",
    "compute_stft",
    "decimate_extrema",
]
