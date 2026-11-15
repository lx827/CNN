"""机械对象的运动学模型；长度单位为一致单位，频率单位为 Hz。"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FixedAxisGearGeometry:
    """定轴齿轮副；输入轴是阶次与 TSA 的同步轴。"""

    input_teeth: int
    output_teeth: int | None = None

    def __post_init__(self) -> None:
        for name, value, required in (
            ("输入轮齿数", self.input_teeth, True),
            ("输出轮齿数", self.output_teeth, False),
        ):
            if value is None and not required:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise ValueError(f"{name}必须是整数")
            if value < 2:
                raise ValueError(f"{name}必须不小于 2")

    @property
    def mesh_order(self) -> float:
        """相对输入轴转频的啮合阶次，无量纲。"""
        return float(self.input_teeth)

    def mesh_frequency_hz(self, input_speed_hz: float) -> float:
        """输入轴转频与返回值均为 Hz。"""
        if not np.isfinite(input_speed_hz) or input_speed_hz <= 0:
            raise ValueError("输入轴转频必须是有限正数")
        return self.mesh_order * float(input_speed_hz)


@dataclass(frozen=True)
class BearingGeometry:
    """滚动轴承几何参数；长度单位只需保持一致。"""

    roller_count: int
    roller_diameter: float
    pitch_diameter: float
    contact_angle_deg: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.roller_count, bool) or not isinstance(
            self.roller_count, (int, np.integer)
        ):
            raise ValueError("滚动体数量必须是整数")
        if self.roller_count <= 0:
            raise ValueError("滚动体数量必须为正整数")
        diameters = (self.roller_diameter, self.pitch_diameter)
        if not all(np.isfinite(value) and value > 0 for value in diameters):
            raise ValueError("滚动体直径和节圆直径必须是有限正数")
        if not np.isfinite(self.contact_angle_deg):
            raise ValueError("接触角必须是有限数")
        ratio = self.diameter_ratio
        if not np.isfinite(ratio) or not 1e-12 < ratio < 1.0:
            raise ValueError("滚动体直径比及接触角必须满足 0 < d/D*cos(alpha) < 1")

    @property
    def diameter_ratio(self) -> float:
        """无量纲直径比 d/D*cos(alpha)。"""
        return float(
            self.roller_diameter
            / self.pitch_diameter
            * np.cos(np.radians(self.contact_angle_deg))
        )

    def fault_frequencies(self, rot_frequency_hz: float) -> dict[str, float]:
        """计算 BPFO/BPFI/BSF/FTF，输入和输出单位均为 Hz。"""
        if not np.isfinite(rot_frequency_hz) or rot_frequency_hz <= 0:
            raise ValueError("转频必须是有限正数")
        ratio = self.diameter_ratio
        return {
            "BPFO": self.roller_count / 2.0 * rot_frequency_hz * (1.0 - ratio),
            "BPFI": self.roller_count / 2.0 * rot_frequency_hz * (1.0 + ratio),
            "BSF": self.pitch_diameter
            / (2.0 * self.roller_diameter)
            * rot_frequency_hz
            * (1.0 - ratio**2),
            "FTF": 0.5 * rot_frequency_hz * (1.0 - ratio),
        }
