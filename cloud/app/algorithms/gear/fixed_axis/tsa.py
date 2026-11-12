"""真实角域 TSA 与经典 regular/residual/differential 构造。"""

from __future__ import annotations

from cnn_compute import rotation as native

import numpy as np

from app.algorithms.order import AngleDomainSignal, OrderSpectrum

from .types import SynchronousAverage, TSARepresentation


def compute_synchronous_average(
    angle_domain: AngleDomainSignal,
    min_revolutions: int = 4,
) -> SynchronousAverage:
    """在完整转周期上做算术平均，不使用中位数周期代替经典 TSA。

    输入必须已经由准确恒速相位或可靠的连续相位重采样；本函数不接受
    原始采样率或标量转频，因此不会把角域采样率误写成 Hz。
    """
    if isinstance(min_revolutions, bool) or min_revolutions < 2:
        raise ValueError("TSA 至少需要 2 个完整转周期")
    spr = angle_domain.samples_per_revolution
    cycle, repeated = native.tsa(angle_domain.samples, spr, min_revolutions)
    count = len(repeated)
    trimmed = AngleDomainSignal(angle_revolutions=angle_domain.angle_revolutions[:count],
        samples=angle_domain.samples[:count], samples_per_revolution=spr)
    return SynchronousAverage(angle_domain=trimmed, tsa_cycle=cycle, tsa_signal=repeated, revolutions=count // spr)


def _periodic_components(
    cycle: np.ndarray,
    orders: set[int],
) -> np.ndarray:
    """用整转 DFT 精确保留指定整数阶次，避免移动平均伪差分。"""
    return native.periodic_components(cycle, orders)


def compute_tsa_representation(
    synchronous: SynchronousAverage,
    mesh_order: float,
    mesh_harmonics: int = 3,
    regular_sideband_order: int = 1,
    max_order: float = 50.0,
) -> TSARepresentation:
    """构造经典信号并计算同一 TSA 表示的单边幅值阶次谱。

    - mesh：各整数啮合谐波；
    - regular：mesh 加每个啮合谐波两侧指定阶数的边带；
    - residual：TSA-regular，去除啮合谐波及 regular 边带；
    - differential：regular-mesh，仅含 regular 边带，不是高通近似。
    """
    if (
        not np.isfinite(mesh_order)
        or mesh_order < 2
        or not float(mesh_order).is_integer()
    ):
        raise ValueError("定轴 TSA regular 构造要求不小于 2 的整数啮合阶次")
    if isinstance(mesh_harmonics, bool) or mesh_harmonics < 1:
        raise ValueError("啮合谐波数必须为正整数")
    if isinstance(regular_sideband_order, bool) or regular_sideband_order < 0:
        raise ValueError("regular 边带阶数必须是非负整数")
    mesh = int(mesh_order)
    nyquist = synchronous.angle_domain.samples_per_revolution / 2.0
    mesh_orders = tuple(
        float(mesh * harmonic) for harmonic in range(1, mesh_harmonics + 1)
    )
    if mesh_orders[-1] >= nyquist:
        raise ValueError("请求的啮合谐波超出角域奈奎斯特覆盖")
    mesh_bins = {int(order) for order in mesh_orders}
    sideband_bins: set[int] = set()
    for center in mesh_bins:
        for sideband in range(1, regular_sideband_order + 1):
            for candidate in (center - sideband, center + sideband):
                if candidate <= 0 or candidate >= nyquist:
                    raise ValueError("regular 边带超出有效阶次覆盖")
                sideband_bins.add(candidate)
    regular_orders = mesh_bins | sideband_bins
    if regular_orders and max(regular_orders) > max_order:
        raise ValueError("TSA 阶次谱未覆盖全部 regular 成分")

    mesh_signal, regular_signal, residual, differential, amplitudes = native.tsa_components(
        synchronous.tsa_cycle, mesh_bins, regular_orders, synchronous.revolutions)
    spr = synchronous.angle_domain.samples_per_revolution
    count = len(synchronous.tsa_signal)
    resolution = spr / count
    retained = min(len(amplitudes), int(np.floor(max_order / resolution + 1e-9)) + 1)
    bins = np.arange(retained, dtype=np.float64) * resolution
    spectrum = OrderSpectrum(order_bins=bins, amplitude=amplitudes[:retained],
        order_resolution=resolution, samples_per_revolution=spr, total_revolutions=count / spr)
    return TSARepresentation(
        synchronous=synchronous,
        mesh_order=float(mesh_order),
        mesh_signal=mesh_signal,
        regular_signal=regular_signal,
        residual_signal=np.asarray(residual, dtype=np.float64),
        differential_signal=np.asarray(differential, dtype=np.float64),
        spectrum=spectrum,
        mesh_orders=mesh_orders,
        regular_sideband_orders=tuple(float(order) for order in sorted(sideband_bins)),
        regular_sideband_order=regular_sideband_order,
    )
