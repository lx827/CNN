"""原生旋转机械与序列数值核；只适配 dtype/layout，不做领域评估。

输入一维 float64 连续缓冲区同步借用，其他输入在边界连续化；结果独立拥有，
由 NumPy capsule 保持 C++ 缓冲区生命周期。计算释放 GIL，不另建线程。
"""
from ._native import rotation as _native
from .emd import _signal


def integrate(time, speed):
    """严格递增时间上的梯形积分，累计转数从零开始。"""
    return _native.integrate(_signal(time), _signal(speed))


def interpolate(axis, values, target, *, zero_outside=False):
    """线性插值；默认端点常数外推，可显式选择范围外为零。"""
    return _native.interpolate(_signal(axis), _signal(values), _signal(target), zero_outside)


def angle_resample(signal, phase, samples_per_revolution):
    """累计转数 k/spr 处插值，输出长度 floor(phase[-1]*spr+1e-9)。"""
    return _native.angle_resample(_signal(signal), _signal(phase), samples_per_revolution)


def amplitude_spectrum(signal, *, center=True):
    """周期 Hann 单边峰值幅值；DC 与偶数 N 的 Nyquist 不翻倍。"""
    return _native.amplitude_spectrum(_signal(signal), center)


def periodic_components(cycle, orders):
    """整转 DFT 精确保留指定整数阶次，独立输出同长信号。"""
    return _native.periodic_components(_signal(cycle), _signal(list(orders)))


def tsa(signal, samples_per_revolution, minimum_revolutions=4):
    """完整转数算术同步平均，返回单圈与平铺信号；丢弃末尾不完整圈。"""
    return _native.tsa(_signal(signal), samples_per_revolution, minimum_revolutions)


def tsa_components(cycle, mesh_orders, regular_orders, revolutions):
    """一次单圈DFT产生mesh/regular/residual/differential和完整TSA的Hann幅值谱。"""
    return _native.tsa_components(_signal(cycle), _signal(list(mesh_orders)), _signal(list(regular_orders)), revolutions)


def zoom_spectrum(signal, sample_rate, low, high, points):
    """Bluestein CZT 在 [low,high) 密集采样，周期Hann幅值刻度。"""
    return _native.zoom_spectrum(_signal(signal), sample_rate, low, high, points)


def real_cepstrum(signal):
    """中心化与周期Hann后的实log幅值倒谱，返回非负倒频率半部。"""
    return _native.real_cepstrum(_signal(signal))


def amfm(signal, sample_rate):
    """Hilbert AM 与相邻点相位差 FM；相位幅值零点明确拒绝。"""
    return _native.amfm(_signal(signal), sample_rate)


def band_envelope(signal, sample_rate, low, high):
    """4阶Butterworth双向滤波与Hilbert幅值，复用公共模块执行实现。"""
    return _native.band_envelope(_signal(signal), sample_rate, low, high)


def window_peaks(axis, values, centers, half_width, *, disjoint=False):
    """窗口内最大值，空窗口或要求互斥时重叠抛 ValueError。"""
    return _native.window_peaks(_signal(axis), _signal(values), _signal(centers), half_width, disjoint)


def band_sum(axis, values, center, half_width):
    """闭区间谱窗口内幅值和。"""
    return _native.band_sum(_signal(axis), _signal(values), center, half_width)


def local_peak(axis, amplitude, center, half_width, background_inner=2.0, background_outer=4.0, *, exclusions=(), median_background=False):
    """返回局部峰位置/幅值/背景/背景bin数/峰有效性；背景可取均值或中位数。"""
    return _native.local_peak(_signal(axis), _signal(amplitude), center, half_width,
        background_inner, background_outer, _signal(exclusions), median_background)


def car_features(axis, cepstrum, targets, half_width):
    """目标窗内绝对倒谱峰及最后目标窗外独立背景中位数；保留实际峰位置。"""
    return _native.car_features(_signal(axis), _signal(cepstrum), _signal(targets), half_width)


def order_statistics(amplitude):
    """返回最高5峰能量占比与谱峰度；领域零能量状态由调用方保留。"""
    return _native.order_statistics(_signal(amplitude))


def spectrum_speed(signal, fs, low, high, harmonics=5, bandwidth=3.0, smoothing=1.5):
    """频谱、包络、Welch、自相关候选仲裁，返回频率/来源/不可判定原因。"""
    return _native.spectrum_speed(_signal(signal), fs, low, high, harmonics, bandwidth, smoothing)


def autocorrelation_speed(signal, fs, low, high):
    """FFT归一自相关显著滞后峰；返回频率/来源/原因。"""
    return _native.autocorrelation_speed(_signal(signal), fs, low, high)


def envelope_speed(signal, fs, carrier, low, high, bandwidth=60.0):
    """Butterworth双向带通、Hilbert包络与搜索频带峰。"""
    return _native.envelope_speed(_signal(signal), fs, carrier, low, high, bandwidth)


def speed_ridge(signal, fs, low, high, window, hop, parameters):
    """STFT可靠脊线与局部线性边缘外推；每帧临时频谱复用，存储O(N+window)。"""
    return _native.speed_ridge(_signal(signal), fs, low, high, window, hop,
        parameters.minimum_peak_to_background, parameters.minimum_local_energy_fraction,
        parameters.minimum_reliable_frame_fraction, parameters.maximum_consecutive_boundary_frames,
        parameters.maximum_boundary_frame_fraction)


def cvs(signal, carrier, planet, azimuth, sensor, half_width, spr):
    """空间通过片段按真实行星相位插值并逐圈清空累加器，返回独立圈/源窗口/覆盖。"""
    return _native.cvs(_signal(signal), _signal(carrier), _signal(planet), azimuth, sensor, half_width, spr)

