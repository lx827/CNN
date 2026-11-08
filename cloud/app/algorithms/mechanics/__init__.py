"""机械对象的运动学模型。当前提供滚动轴承特征频率。"""
from dataclasses import dataclass

import numpy as np


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
            "BSF": self.pitch_diameter / (2.0 * self.roller_diameter)
            * rot_frequency_hz * (1.0 - ratio**2),
            "FTF": 0.5 * rot_frequency_hz * (1.0 - ratio),
        }
