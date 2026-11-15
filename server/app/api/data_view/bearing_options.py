"""研究和包络入口共用高级轴承方法的显式参数校验。"""

from typing import Literal, Optional

from fastapi import Query


def get_bearing_options(
    target_fault: Optional[Literal["BPFO", "BPFI", "BSF", "FTF"]] = Query(default=None),
    target_frequency_hz: Optional[float] = Query(default=None, gt=0),
    period_samples: Optional[int] = Query(default=None, ge=1),
    comb_frequencies_hz: list[float] = Query(default=[]),
    comb_is_stable: bool = Query(default=False),
) -> dict:
    """空 MCKD 目标明确转 MED；CPW 稳定性由调用方确认，不由齿数推断。"""
    return {
        "target_fault": target_fault,
        "target_frequency_hz": target_frequency_hz,
        "period_samples": period_samples,
        "comb_frequencies_hz": comb_frequencies_hz,
        "comb_is_stable": comb_is_stable,
    }
