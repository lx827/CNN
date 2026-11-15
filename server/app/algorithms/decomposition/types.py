"""分解结果的公共有效区间；索引均相对未截断的输入信号。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidInterval:
    """半开有效区间 ``[start_index, stop_index)``，不代表补零区域。"""

    start_index: int
    stop_index: int

    def __post_init__(self) -> None:
        if isinstance(self.start_index, bool) or isinstance(self.stop_index, bool):
            raise ValueError("有效区间索引必须是整数")
        if not isinstance(self.start_index, int) or not isinstance(
            self.stop_index, int
        ):
            raise ValueError("有效区间索引必须是整数")
        if self.start_index < 0 or self.stop_index <= self.start_index:
            raise ValueError("有效区间必须满足 0 <= start < stop")

    @property
    def length(self) -> int:
        return self.stop_index - self.start_index
