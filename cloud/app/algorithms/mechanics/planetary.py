"""固定齿圈、同模数简单行星排；Willis 方程和啮合事件模型。"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlanetaryGearGeometry:
    """参考轴必须明确为 sun 或 carrier；不支持浮动齿圈或复合行星排。

    齿数满足 Zr=Zs+2Zp。局部事件阶次是运动学候选，不保证壳体传感器
    必然观察到峰；尤其一个行星轮坏齿可能每自转出现一次或两次啮合事件。
    """

    sun_teeth: int
    ring_teeth: int
    planet_teeth: int
    planet_count: int
    reference_axis: str
    fixed_member: str = "ring"

    def __post_init__(self) -> None:
        for name in ("sun_teeth", "ring_teeth", "planet_teeth", "planet_count"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, np.integer))
                or value < (1 if name == "planet_count" else 2)
            ):
                raise ValueError(f"{name} 必须是合法正整数")
        if self.ring_teeth != self.sun_teeth + 2 * self.planet_teeth:
            raise ValueError("简单同模数行星排必须满足 Zr=Zs+2Zp")
        if (self.sun_teeth + self.ring_teeth) % self.planet_count:
            raise ValueError("当前均布行星模型要求 (Zs+Zr)/Np 为整数")
        if (
            self.planet_count > 1
            and (self.sun_teeth + self.planet_teeth) * np.sin(np.pi / self.planet_count)
            <= self.planet_teeth
        ):
            raise ValueError("相邻行星轮节圆发生干涉")
        if self.reference_axis not in {"sun", "carrier"}:
            raise ValueError("行星分析参考轴必须明确为 sun 或 carrier")
        if self.fixed_member != "ring":
            raise ValueError("当前行星模型只支持固定齿圈")

    @property
    def carrier_to_sun_ratio(self) -> float:
        return self.sun_teeth / (self.sun_teeth + self.ring_teeth)

    def axis_order(self, axis: str) -> float:
        """轴的有符号绝对转频/分析参考轴转频；planet 为绝对自转。"""
        carrier = self.carrier_to_sun_ratio
        values = {
            "sun": 1.0,
            "carrier": carrier,
            "ring": 0.0,
            "planet": carrier - self.ring_teeth * carrier / self.planet_teeth,
        }
        if axis not in values:
            raise ValueError("未知行星轴")
        reference = 1.0 if self.reference_axis == "sun" else carrier
        return float(values[axis] / reference)

    @property
    def mesh_order(self) -> float:
        return self.ring_teeth * self.axis_order("carrier")

    @property
    def carrier_order(self) -> float:
        return self.axis_order("carrier")

    @property
    def sun_relative_order(self) -> float:
        return self.mesh_order / self.sun_teeth

    @property
    def planet_relative_order(self) -> float:
        return self.mesh_order / self.planet_teeth

    @property
    def event_orders(self) -> dict[str, float]:
        """啮合事件候选；carrier 是传递路径调制，不是故障命题。"""
        return {
            "sun_mesh_encounter": self.planet_count * self.sun_relative_order,
            "planet_single_mesh": self.planet_relative_order,
            "planet_two_mesh": 2.0 * self.planet_relative_order,
            "ring_mesh_encounter": self.planet_count * self.carrier_order,
            "carrier_transfer": self.carrier_order,
        }

    @property
    def signature(self) -> tuple:
        return (
            self.sun_teeth,
            self.ring_teeth,
            self.planet_teeth,
            self.planet_count,
            self.reference_axis,
            self.fixed_member,
        )
