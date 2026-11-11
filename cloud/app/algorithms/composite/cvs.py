"""显式单行星空间窗口与角相位的连续重组；不把载波TSA冒充CVS。"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CVSAlignment:
    """采集/编码器提供的真实相位；两相位与输入样本逐点同轴。

    planet_phase_rad 是选中行星相对行星架的连续自转相位，包含其绝对零位。
    相位零位不能由振动幅值或几何齿数猜测。重组仅在通过窗口覆盖整圈后输出。
    """
    carrier_phase_rad: np.ndarray
    planet_phase_rad: np.ndarray
    planet_azimuths_rad: tuple[float, ...]
    selected_planet: int
    sensor_azimuth_rad: float
    passage_half_width_rad: float
    planet_relative_frequency_hz: float
    samples_per_planet_revolution: int = 1024
    minimum_reconstructed_cycles: int = 2


@dataclass(frozen=True)
class CVSRepresentation:
    status: str
    signal: np.ndarray | None
    sample_rate_hz: float | None
    selected_planet: int | None
    source_window_intervals: tuple[tuple[int, int], ...]
    cycles: int
    coverage_fraction: float
    reason: str | None = None


def reconstruct_continuous_planet_signal(signal, sample_rate_hz, alignment: CVSAlignment | None):
    """单行星通过窗口→相对自转相位网格→全圈覆盖→独立连续圈拼接。

    每个全圈由不同通过窗口补足；每次覆盖完整后清空累加器，不复制/周期延拓
    一个平均片段冒充长记录。缺相位、重叠空间窗口或覆盖不全均无信号输出。
    线性角域插值要求输出采样率不低于原采样率，避免隐式降采样混叠。
    """
    def unavailable(reason, windows=(), coverage=0.0):
        return CVSRepresentation("indeterminate", None, None, None, tuple(windows), 0, coverage, reason)

    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or len(values) < 64 or not np.all(np.isfinite(values)):
        raise ValueError("CVS requires a finite vector with >=64 samples")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("CVS sampling rate must be positive Hz")
    if alignment is None:
        return unavailable("missing_spatial_passage_and_planet_phase_alignment")
    carrier = np.asarray(alignment.carrier_phase_rad, dtype=float)
    planet = np.asarray(alignment.planet_phase_rad, dtype=float)
    if carrier.shape != values.shape or planet.shape != values.shape or not np.all(np.isfinite(carrier)) or not np.all(np.isfinite(planet)):
        return unavailable("phase_signal_time_axis_mismatch")
    if np.any(np.diff(carrier) <= 0) or np.any(np.diff(planet) <= 0):
        return unavailable("continuous_positive_carrier_and_relative_planet_phase_required")
    azimuths = np.asarray(alignment.planet_azimuths_rad, dtype=float)
    selected = alignment.selected_planet
    if azimuths.ndim != 1 or len(azimuths) < 2 or not np.all(np.isfinite(azimuths)) or isinstance(selected, bool) or not isinstance(selected, int) or not 0 <= selected < len(azimuths):
        return unavailable("invalid_planet_identity_or_spatial_layout")
    if not np.isfinite(alignment.sensor_azimuth_rad) or not np.isfinite(alignment.passage_half_width_rad) or alignment.passage_half_width_rad <= 0:
        return unavailable("invalid_sensor_passage_window")
    separations = np.abs(np.angle(np.exp(1j * (azimuths[:, None] - azimuths[None, :]))))
    np.fill_diagonal(separations, np.inf)
    if 2 * alignment.passage_half_width_rad >= np.min(separations):
        return unavailable("overlapping_planet_passage_windows")
    frequency = alignment.planet_relative_frequency_hz
    spr = alignment.samples_per_planet_revolution
    minimum_cycles = alignment.minimum_reconstructed_cycles
    if not np.isfinite(frequency) or frequency <= 0 or isinstance(spr, bool) or not isinstance(spr, int) or not 64 <= spr <= 8192:
        return unavailable("invalid_relative_planet_frequency_or_angular_sampling")
    if isinstance(minimum_cycles, bool) or not isinstance(minimum_cycles, int) or minimum_cycles < 2:
        return unavailable("at_least_two_independently_reconstructed_cycles_required")
    if frequency * spr < sample_rate_hz:
        return unavailable("angular_sampling_would_alias_input")
    instantaneous = np.diff(planet) * sample_rate_hz / (2 * np.pi)
    if not np.allclose(instantaneous, frequency, rtol=0.01, atol=0):
        return unavailable("CVS_uniform_time_reassembly_requires_constant_relative_speed")
    spatial = np.angle(np.exp(1j * (carrier + azimuths[selected] - alignment.sensor_azimuth_rad)))
    mask = np.abs(spatial) <= alignment.passage_half_width_rad
    transitions = np.diff(np.r_[False, mask, False].astype(int))
    intervals = tuple(zip(np.flatnonzero(transitions == 1).tolist(), np.flatnonzero(transitions == -1).tolist()))
    sums, counts = np.zeros(spr), np.zeros(spr, dtype=int)
    cycles = []
    used = []
    pending = []
    for start, stop in intervals:
        if stop - start < 3:
            continue
        # 仅窗口内部可插值的角样点；所有源样本均属于选定行星经过传感器的窗口。
        first = int(np.ceil(planet[start] / (2 * np.pi) * spr))
        last = int(np.floor(planet[stop - 1] / (2 * np.pi) * spr))
        grid = np.arange(first, last + 1, dtype=np.int64)
        if not len(grid):
            continue
        reconstructed = np.interp(grid * (2 * np.pi / spr), planet[start:stop], values[start:stop])
        bins = grid % spr
        np.add.at(sums, bins, reconstructed)
        np.add.at(counts, bins, 1)
        pending.append((start, stop))
        if np.all(counts > 0):
            cycles.append(sums / counts)
            used.extend(pending)
            pending = []
            sums, counts = np.zeros(spr), np.zeros(spr, dtype=int)
    coverage = float(np.mean(counts > 0))
    if len(cycles) < minimum_cycles:
        return unavailable("insufficient_full_planet_phase_coverage_for_continuous_reassembly", used + pending, coverage)
    return CVSRepresentation("computed", np.concatenate(cycles), float(frequency * spr), selected,
                              tuple(used), len(cycles), 1.0)
