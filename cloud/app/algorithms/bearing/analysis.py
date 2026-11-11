"""包络谱原始指标提取；本模块不应用故障显著性阈值。"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.algorithms.core import SpectralPeak, Spectrum
from app.algorithms.mechanics import BearingGeometry


@dataclass(frozen=True)
class EnvelopeStatistics:
    # 真实谱峰/背景线性比，不是 dB。
    peak_snr: float
    kurtosis: float
    low_frequency_ratio: Optional[float]
    rotation_harmonic_energy_ratio: Optional[float]
    high_frequency_ratio: Optional[float]
    peak_concentration: float
    crest_factor: float


@dataclass(frozen=True)
class SidebandTarget:
    order: int
    side: str
    theory_frequency_hz: float


@dataclass(frozen=True)
class SidebandObservation:
    order: int
    side: str
    theory_frequency_hz: float
    # 局部峰/全谱背景中位数的线性比，不是 dB。
    snr: float


@dataclass(frozen=True)
class SidebandEvidence:
    """可观测理论目标与实际局部峰是两个独立集合。"""

    observations: tuple[SidebandObservation, ...]
    observable_targets: tuple[SidebandTarget, ...]
    asymmetry: Optional[float]

    @property
    def observable_count(self) -> int:
        return len(self.observable_targets)


@dataclass(frozen=True)
class EnvelopeFeatures:
    # 幅值平方和只是频谱功率代理，不是时域物理能量。
    spectral_power_proxy: float
    spectral_power_unit: str
    frequency_resolution_hz: float
    statistics: EnvelopeStatistics
    fault_frequency_hz: dict[str, float]
    energy_ratios: dict[str, float]
    harmonic_energy_ratios: dict[str, float]
    peaks: dict[str, SpectralPeak]
    peak_issues: dict[str, str]
    harmonic_snrs: dict[str, tuple[float, ...]]
    bpfi_sideband_snrs: tuple[float, ...]
    sidebands: dict[str, SidebandEvidence]

    def as_dict(self) -> dict:
        """输出业务评分消费的命名特征，不输出误导性的总物理能量。"""
        result = {
            "spectral_power_proxy": self.spectral_power_proxy,
            "spectral_power_unit": self.spectral_power_unit,
        }
        for name, value in self.energy_ratios.items():
            result[f"{name}_env_ratio"] = value
        for name, value in self.harmonic_energy_ratios.items():
            result[f"{name}_env_harmonic_ratio"] = value
        return result


@dataclass(frozen=True)
class EnvelopeAnalysis:
    """完整有效包络频带及一次提取的原始指标。"""

    spectrum: Spectrum
    features: EnvelopeFeatures
    rot_frequency_hz: Optional[float]
    rot_frequency_std_hz: float


def _background(amplitude: np.ndarray) -> float:
    return max(float(np.median(amplitude)), 1e-12)


def _is_local_peak(amplitude: np.ndarray, index: int) -> bool:
    value = amplitude[index]
    if index > 0 and value < amplitude[index - 1]:
        return False
    if index + 1 < len(amplitude) and value < amplitude[index + 1]:
        return False
    return True


def _unique_peak_assignments(
    spectrum: Spectrum,
    targets: dict[str, tuple[float, float]],
) -> tuple[dict[str, SpectralPeak], dict[str, str]]:
    """先收集容差内局部峰，再按幅值和距离做全局唯一分配。"""
    frequency = spectrum.frequency_hz
    amplitude = spectrum.amplitude
    resolution = float(frequency[1] - frequency[0]) if len(frequency) > 1 else 0.0
    issues = {}
    local_candidates: dict[str, list[int]] = {}
    candidate_pairs = []

    for key, (target, tolerance) in targets.items():
        if target <= 0:
            issues[key] = "invalid_target_frequency"
            continue
        if target > frequency[-1]:
            issues[key] = "target_above_analysis_bandwidth"
            continue
        if resolution <= 0:
            issues[key] = "insufficient_frequency_resolution"
            continue
        indices = np.flatnonzero(np.abs(frequency - target) <= tolerance)
        if len(indices) == 0:
            issues[key] = "target_not_resolvable"
            continue
        local_indices = [int(index) for index in indices if _is_local_peak(amplitude, int(index))]
        local_candidates[key] = local_indices
        for index in local_indices:
            normalized_distance = abs(float(frequency[index]) - target) / max(tolerance, 1e-12)
            candidate_pairs.append((
                -float(amplitude[index]),
                normalized_distance,
                index,
                key,
            ))

    # 全局排序与目标声明顺序无关：先比幅值，再比归一化距离。
    candidate_pairs.sort()
    peaks = {}
    assigned_targets = set()
    assigned_bins = set()
    background = _background(amplitude)
    for _, _, index, key in candidate_pairs:
        if key in assigned_targets or index in assigned_bins:
            continue
        assigned_targets.add(key)
        assigned_bins.add(index)
        amplitude_value = float(amplitude[index])
        peaks[key] = SpectralPeak(
            frequency_hz=float(frequency[index]),
            amplitude=amplitude_value,
            snr=amplitude_value / background,
        )

    for key, local_indices in local_candidates.items():
        if key not in peaks and local_indices:
            # 有局部峰但全部归属其他目标，不能把冲突证据分配给该目标。
            issues[key] = "shared_spectral_bin"
        # 没有局部峰且无冲突是有效阴性，不属于不可评估。
    return peaks, issues


def _band_energy(spectrum: Spectrum, center_hz: float, bandwidth_hz: float) -> float:
    mask = np.abs(spectrum.frequency_hz - center_hz) <= bandwidth_hz
    if not np.any(mask):
        return 0.0
    return float(np.sum(spectrum.amplitude[mask] ** 2))


def compute_sideband_metrics(
    observations: tuple[SidebandObservation, ...],
    observable_targets: tuple[SidebandTarget, ...],
) -> SidebandEvidence:
    """分别保存可观测理论目标和局部峰；任一侧无峰时不对称度为 None。"""
    upper = [item.snr for item in observations if item.side == "upper"]
    lower = [item.snr for item in observations if item.side == "lower"]
    asymmetry = None
    if upper and lower:
        asymmetry = abs(float(np.mean(upper)) - float(np.mean(lower))) / (
            float(np.mean(upper)) + float(np.mean(lower)) + 1e-12
        )
    return SidebandEvidence(
        observations=observations,
        observable_targets=observable_targets,
        asymmetry=asymmetry,
    )


def _extract_statistics(
    spectrum: Spectrum,
    rot_frequency_hz: Optional[float],
) -> EnvelopeStatistics:
    amplitude = spectrum.amplitude
    frequency = spectrum.frequency_hz
    background = float(np.median(amplitude))
    peak = float(np.max(amplitude))
    peak_snr = peak / background if background > 0 else 0.0
    normalized = amplitude / (np.mean(amplitude) + 1e-12)
    kurt = float(np.mean(normalized**4) / (np.mean(normalized**2) ** 2 + 1e-12) - 2.0)
    power_proxy = float(np.sum(amplitude**2)) + 1e-12
    top5 = float(np.sum(np.sort(amplitude)[::-1][:5] ** 2))
    rms = float(np.sqrt(np.mean(amplitude**2)))
    crest = peak / rms if rms > 1e-12 else 0.0
    resolution = float(frequency[1] - frequency[0]) if len(frequency) > 1 else 0.0

    low_ratio = harmonic_ratio = high_ratio = None
    if rot_frequency_hz is not None:
        low_cutoff = max(rot_frequency_hz * 3.0, 30.0)
        low_ratio = float(np.sum(amplitude[frequency <= low_cutoff] ** 2)) / power_proxy

        # 只累计转频整数倍附近的唯一 bin；与普通低频能量严格分开。
        harmonic_bins = set()
        tolerance = max(rot_frequency_hz * 0.02, resolution * 0.5)
        for harmonic in range(1, 11):
            target = harmonic * rot_frequency_hz
            if target > frequency[-1]:
                break
            index = int(np.argmin(np.abs(frequency - target)))
            if abs(float(frequency[index]) - target) <= tolerance:
                harmonic_bins.add(index)
        harmonic_ratio = (
            float(np.sum(amplitude[sorted(harmonic_bins)] ** 2)) / power_proxy
            if harmonic_bins else 0.0
        )

        high_cutoff = max(500.0, rot_frequency_hz * 2.0)
        mask = frequency >= high_cutoff
        high_ratio = float(np.sum(amplitude[mask] ** 2)) / power_proxy if np.any(mask) else 0.0
    return EnvelopeStatistics(
        peak_snr=peak_snr,
        kurtosis=kurt,
        low_frequency_ratio=low_ratio,
        rotation_harmonic_energy_ratio=harmonic_ratio,
        high_frequency_ratio=high_ratio,
        peak_concentration=top5 / power_proxy,
        crest_factor=crest,
    )


def analyze_envelope_spectrum(
    spectrum: Spectrum,
    geometry: Optional[BearingGeometry] = None,
    rot_frequency_hz: Optional[float] = None,
    rot_frequency_std_hz: float = 0.0,
) -> EnvelopeAnalysis:
    """一次提取完整频谱的原始指标，不执行 FFT，不受展示截断影响。"""
    if rot_frequency_hz is not None and (
        not np.isfinite(rot_frequency_hz) or rot_frequency_hz <= 0
    ):
        raise ValueError("转频必须是有限正数；未知转频请传 None")
    if not np.isfinite(rot_frequency_std_hz) or rot_frequency_std_hz < 0:
        raise ValueError("转频标准差必须是有限非负数")

    frequency = spectrum.frequency_hz
    amplitude = spectrum.amplitude
    resolution = float(frequency[1] - frequency[0]) if len(frequency) > 1 else 0.0
    power_proxy = float(np.sum(amplitude**2))
    statistics = _extract_statistics(spectrum, rot_frequency_hz)

    fault_frequencies = {}
    energy_ratios = {}
    harmonic_ratios = {}
    harmonic_snrs = {}
    bpfi_sideband_snrs = ()
    sidebands = {}
    targets: dict[str, tuple[float, float]] = {}
    if geometry is not None and rot_frequency_hz is not None:
        fault_frequencies = geometry.fault_frequencies(rot_frequency_hz)
        uncertainty = rot_frequency_std_hz / rot_frequency_hz

        def tolerance(target: float) -> float:
            # 仅覆盖最近 bin、3% 工程容差和转频不确定性，不再使用 2df 宽窗。
            return max(target * 0.03, target * uncertainty * 0.5, resolution * 0.5)

        for name in ("BPFO", "BPFI", "BSF"):
            target = fault_frequencies[name]
            targets[name] = (target, tolerance(target))
            for harmonic in range(2, 5):
                harmonic_target = target * harmonic
                targets[f"{name}:H{harmonic}"] = (
                    harmonic_target,
                    tolerance(harmonic_target),
                )
            modulation = rot_frequency_hz if name != "BSF" else fault_frequencies["FTF"]
            for order in range(1, 6):
                for side, sign in (("upper", 1.0), ("lower", -1.0)):
                    sideband_target = target + sign * order * modulation
                    targets[f"{name}:SB{order}:{side}"] = (
                        sideband_target,
                        tolerance(sideband_target),
                    )

    peaks, issues = _unique_peak_assignments(spectrum, targets)
    if fault_frequencies:
        denominator = power_proxy + 1e-12
        for name in ("BPFO", "BPFI", "BSF"):
            target = fault_frequencies[name]
            if name not in issues:
                energy_ratios[name] = _band_energy(
                    spectrum, target, max(1.0, target * 0.02)
                ) / denominator
            harmonic_energy = 0.0
            snrs = []
            for harmonic in range(2, 5):
                harmonic_target = target * harmonic
                key = f"{name}:H{harmonic}"
                if key not in issues and harmonic_target <= frequency[-1]:
                    harmonic_energy += _band_energy(
                        spectrum, harmonic_target, max(1.0, target * 0.02)
                    )
                if key in peaks:
                    snrs.append(peaks[key].snr)
            harmonic_ratios[name] = harmonic_energy / denominator
            harmonic_snrs[name] = tuple(snrs)

            observations = []
            observable_targets = []
            for order in range(1, 6):
                for side in ("upper", "lower"):
                    key = f"{name}:SB{order}:{side}"
                    theory, _ = targets[key]
                    if key not in issues:
                        observable_targets.append(SidebandTarget(
                            order=order,
                            side=side,
                            theory_frequency_hz=theory,
                        ))
                    peak = peaks.get(key)
                    if peak is not None:
                        observations.append(SidebandObservation(
                            order=order,
                            side=side,
                            theory_frequency_hz=theory,
                            snr=peak.snr,
                        ))
            sidebands[name] = compute_sideband_metrics(
                tuple(observations),
                tuple(observable_targets),
            )

        bpfi_sideband_snrs = tuple(
            item.snr for item in sidebands["BPFI"].observations if item.order == 1
        )

    return EnvelopeAnalysis(
        spectrum=spectrum,
        features=EnvelopeFeatures(
            spectral_power_proxy=power_proxy,
            spectral_power_unit=(f"({spectrum.amplitude_unit})^2" if "^" in spectrum.amplitude_unit
                                 else f"{spectrum.amplitude_unit}^2"),
            frequency_resolution_hz=resolution,
            statistics=statistics,
            fault_frequency_hz=fault_frequencies,
            energy_ratios=energy_ratios,
            harmonic_energy_ratios=harmonic_ratios,
            peaks={name: peaks[name] for name in ("BPFO", "BPFI", "BSF") if name in peaks},
            peak_issues=issues,
            harmonic_snrs=harmonic_snrs,
            bpfi_sideband_snrs=bpfi_sideband_snrs,
            sidebands=sidebands,
        ),
        rot_frequency_hz=rot_frequency_hz,
        rot_frequency_std_hz=rot_frequency_std_hz,
    )
