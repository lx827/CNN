"""
全局阈值配置

集中管理所有告警和诊断阈值，避免分散在多个文件中导致不一致。
"""

# 振动特征阈值（与 rule_based.py 的 _FEATURE_BASELINES 保持一致）
FEATURE_THRESHOLDS = {
    "rms":       {"baseline": 0.008, "warning": 0.015, "critical": 0.030},
    "peak":      {"baseline": 0.060, "warning": 0.100, "critical": 0.150},
    "kurtosis":  {"baseline": 4.00,  "warning": 5.50,  "critical": 7.00},
    "crest_factor": {"baseline": 7.50, "warning": 9.00, "critical": 10.50},
    "skewness":  {"baseline": 0.00,  "warning": 0.20,  "critical": 0.50},
    "impulse_factor": {"baseline": 9.50, "warning": 11.00, "critical": 13.00},
}

# 告警阈值（alarm_service.py 使用）
ALARM_THRESHOLDS = {
    **{k: {"warning": v["warning"], "critical": v["critical"]} for k, v in FEATURE_THRESHOLDS.items()},
    "ser": {"warning": 1.5, "critical": 3.0},
    "fm0": {"warning": 5.0, "critical": 10.0},
    "car": {"warning": 1.2, "critical": 2.0},
    "sideband_count": {"warning": 2, "critical": 4},
}

# 设备默认告警阈值（devices.py 使用）
DEVICE_DEFAULT_THRESHOLDS = {
    "rms": {"warning": 5.0, "critical": 10.0},
    "peak": {"warning": 15.0, "critical": 30.0},
    "kurtosis": {"warning": 4.0, "critical": 6.0},
    "crest_factor": {"warning": 6.0, "critical": 10.0},
}
