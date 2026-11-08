"""统计表示与分析函数公共接口。"""
from .time_domain import (
    SegmentedRMS,
    SignalStatistics,
    TimeDomainAnalysis,
    WindowedStatistics,
    analyze_time_domain,
    centered_rms,
    segmented_rms,
)

__all__ = [
    "SegmentedRMS",
    "SignalStatistics",
    "TimeDomainAnalysis",
    "WindowedStatistics",
    "analyze_time_domain",
    "centered_rms",
    "segmented_rms",
]
