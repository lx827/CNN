"""DWT/WP 公共契约与实现无关的分解、分量重构入口。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np
from numpy.typing import NDArray

from ..types import ValidInterval


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class DWTBand:
    """一个小波带；系数与重构信号使用各自明确的采样率。"""

    kind: str
    level: int
    coefficients: FloatArray
    reconstructed: FloatArray
    coefficient_sample_rate_hz: float
    frequency_band_hz: tuple[float, float]
    valid_interval: ValidInterval


@dataclass(frozen=True)
class DWTDecomposition:
    """``details`` 按 d1、d2、…、dL 排列，而非 PyWavelets 的倒序列表。"""

    input_length: int
    sample_rate_hz: float
    wavelet: str
    mode: str
    level: int
    approximation: DWTBand
    details: tuple[DWTBand, ...]
    valid_interval: ValidInterval

    @property
    def reconstructed(self) -> FloatArray:
        return self.approximation.reconstructed + sum(
            (detail.reconstructed for detail in self.details),
            start=np.zeros(self.input_length, dtype=np.float64),
        )


@dataclass(frozen=True)
class WaveletPacketNode:
    """WP 叶子节点；自然路径序和 Gray 频率序是两个独立字段。"""

    path: str
    level: int
    natural_index: int
    frequency_index: int
    coefficients: FloatArray
    reconstructed: FloatArray
    coefficient_sample_rate_hz: float
    frequency_band_hz: tuple[float, float]
    valid_interval: ValidInterval


@dataclass(frozen=True)
class WaveletPacketDecomposition:
    """完全 WP 树的一个层级；``nodes`` 始终保持自然路径序。"""

    input_length: int
    sample_rate_hz: float
    wavelet: str
    mode: str
    level: int
    nodes: tuple[WaveletPacketNode, ...]
    valid_interval: ValidInterval

    @property
    def nodes_in_frequency_order(self) -> tuple[WaveletPacketNode, ...]:
        return tuple(sorted(self.nodes, key=lambda node: node.frequency_index))

    def node_for_frequency(self, frequency_hz: float) -> WaveletPacketNode:
        """返回理想通带包含该频率的节点；Nyquist 归入最后一个节点。"""
        if not np.isfinite(frequency_hz) or not 0.0 <= frequency_hz <= self.sample_rate_hz / 2.0:
            raise ValueError("目标频率必须位于 [0, Nyquist]")
        index = min(
            int(frequency_hz / (self.sample_rate_hz / 2.0) * len(self.nodes)),
            len(self.nodes) - 1,
        )
        return self.nodes_in_frequency_order[index]


class WaveletImplementation(Protocol):
    """小波族专属 adapter seam；实现各自返回完整公共结果，不继承通用基类。"""

    def dwt(
        self, signal: FloatArray, sample_rate_hz: float,
        wavelet: str, level: int, mode: str,
    ) -> DWTDecomposition:
        ...

    def wavelet_packet(
        self, signal: FloatArray, sample_rate_hz: float,
        wavelet: str, level: int, mode: str,
    ) -> WaveletPacketDecomposition:
        ...


def _validate_signal(signal: FloatArray, sample_rate_hz: float) -> FloatArray:
    arr = np.asarray(signal, dtype=np.float64)
    if arr.ndim != 1 or len(arr) < 2:
        raise ValueError("小波分解输入必须是一维且至少包含 2 个采样点")
    if not np.all(np.isfinite(arr)):
        raise ValueError("输入信号不能包含 NaN 或无穷值")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("采样率必须是有限正数")
    return arr


def _validate_parameters(wavelet: str, level: int, mode: str) -> None:
    if not isinstance(wavelet, str) or not wavelet:
        raise ValueError("小波名称不能为空")
    if isinstance(level, bool) or not isinstance(level, int) or level <= 0:
        raise ValueError("分解层数必须是正整数")
    if not isinstance(mode, str) or not mode:
        raise ValueError("边界模式不能为空")


def _implementation(implementation: WaveletImplementation | None) -> WaveletImplementation:
    if implementation is not None:
        return implementation
    from .pywavelets_adapter import PyWaveletsImplementation
    return PyWaveletsImplementation()


def decompose_dwt(
    signal: FloatArray,
    sample_rate_hz: float,
    wavelet: str = "db8",
    level: int = 3,
    mode: str = "symmetric",
    implementation: WaveletImplementation | None = None,
) -> DWTDecomposition:
    """执行多层 DWT；每个频带同时给出抽取系数和原时间轴重构。"""
    arr = _validate_signal(signal, sample_rate_hz)
    _validate_parameters(wavelet, level, mode)
    return _implementation(implementation).dwt(arr, sample_rate_hz, wavelet, level, mode)


def reconstruct_dwt(
    decomposition: DWTDecomposition,
    detail_levels: Sequence[int] = (),
    include_approximation: bool = False,
) -> FloatArray:
    """只累加明确选中的频带；未选近似和细节严格为零。"""
    selected = set(detail_levels)
    valid_levels = {detail.level for detail in decomposition.details}
    if not selected.issubset(valid_levels):
        raise ValueError("选择的 DWT 细节层不存在或包含重复层级")
    if len(selected) != len(detail_levels):
        raise ValueError("选择的 DWT 细节层不能重复")
    output = np.zeros(decomposition.input_length, dtype=np.float64)
    if include_approximation:
        output += decomposition.approximation.reconstructed
    for detail in decomposition.details:
        if detail.level in selected:
            output += detail.reconstructed
    return output


def decompose_wavelet_packet(
    signal: FloatArray,
    sample_rate_hz: float,
    wavelet: str = "db8",
    level: int = 3,
    mode: str = "symmetric",
    implementation: WaveletImplementation | None = None,
) -> WaveletPacketDecomposition:
    """执行完全 WP 分解；freq->natural 为 Gray 码，natural->freq 使用逆 Gray。"""
    arr = _validate_signal(signal, sample_rate_hz)
    _validate_parameters(wavelet, level, mode)
    return _implementation(implementation).wavelet_packet(arr, sample_rate_hz, wavelet, level, mode)


def reconstruct_wavelet_packet(
    decomposition: WaveletPacketDecomposition,
    paths: Sequence[str],
) -> FloatArray:
    """只累加选中节点的原采样率重构，不把抽取系数与原信号直接比较。"""
    by_path = {node.path: node for node in decomposition.nodes}
    if len(set(paths)) != len(paths) or any(path not in by_path for path in paths):
        raise ValueError("WP 节点路径未知或重复")
    return sum(
        (by_path[path].reconstructed for path in paths),
        start=np.zeros(decomposition.input_length, dtype=np.float64),
    )
