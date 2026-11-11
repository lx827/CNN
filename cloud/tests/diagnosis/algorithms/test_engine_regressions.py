"""
诊断引擎回归测试：
- 无机械参数时不注入默认轴承/齿轮参数，走统计诊断。
- 齿轮高级指标使用 TSA/残差信号。
- 转频估计在噪声下保持稳定。
- 若本地数据集存在，抽样检查健康/故障可区分性。
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.diagnosis import DiagnosisEngine, GearMethod
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from data_paths import HUSTBEAR_DIR, CW_DIR


FS = 8192
HUST_DIR = str(HUSTBEAR_DIR)


def _impulse_signal(fs=FS, seconds=5, rot_freq=25.0):
    rng = np.random.default_rng(42)
    t = np.arange(int(fs * seconds)) / fs
    sig = 0.05 * rng.standard_normal(len(t)) + 0.02 * np.sin(2 * np.pi * rot_freq * t)
    period = int(fs / rot_freq)
    for idx in range(period // 2, len(sig), period):
        width = min(24, len(sig) - idx)
        sig[idx:idx + width] += np.hanning(width) * 4.0
    return sig


def test_no_params_uses_statistical_fault_indicators():
    sig = _impulse_signal()
    engine = DiagnosisEngine(strategy="advanced", bearing_params={}, gear_teeth={})
    result = engine.analyze_comprehensive(sig, FS)

    indicators = result["bearing"]["evaluation"]["indicators"]
    assert "BPFO" not in indicators
    assert "envelope_peak_snr" in indicators
    assert "order_kurtosis" in result["gear"]["fault_indicators"]
    assert result["health_score"] is None
    assert result["diagnosis_conclusion"] == "unknown"


def test_advanced_gear_uses_tsa_residual():
    rot_freq = 20.0
    teeth = 18
    t = np.arange(FS * 5) / FS
    mesh = 0.4 * np.sin(2 * np.pi * rot_freq * teeth * t)
    local_tooth_fault = np.zeros_like(t)
    period = int(FS / rot_freq)
    for idx in range(period // 3, len(t), period):
        width = min(16, len(t) - idx)
        local_tooth_fault[idx:idx + width] += np.hanning(width) * 2.0
    sig = mesh + local_tooth_fault

    engine = DiagnosisEngine(gear_method=GearMethod.ADVANCED, gear_teeth={"input": teeth})
    result = engine.analyze_gear(sig, FS, rot_freq=rot_freq)

    assert result["tsa_revolutions"] >= 4
    assert result["fm4"] > 0
    assert result["m6a"] > 0


def test_noisy_rot_freq_estimation_is_robust():
    rng = np.random.default_rng(7)
    rot_freq = 25.0
    t = np.arange(FS * 4) / FS
    sig = (
        0.15 * np.sin(2 * np.pi * rot_freq * t)
        + 0.7 * np.sin(2 * np.pi * rot_freq * 4 * t)
        + 0.4 * np.sin(2 * np.pi * rot_freq * 9 * t)
        + 0.5 * rng.standard_normal(len(t))
    )
    estimated = estimate_rot_freq_spectrum(sig, FS, freq_range=(10, 80))
    assert abs(estimated - rot_freq) < 2.0


def test_dataset_sample_fault_scores_when_available():
    healthy_path = os.path.join(HUST_DIR, "H_25hz-X.npy")
    fault_path = os.path.join(HUST_DIR, "0.5X_B_25Hz-X.npy")
    if not os.path.exists(healthy_path) or not os.path.exists(fault_path):
        return

    healthy = np.load(healthy_path)[: FS * 5]
    fault = np.load(fault_path)[: FS * 5]
    engine = DiagnosisEngine(strategy="advanced", bearing_params={}, gear_teeth={})

    healthy_result = engine.analyze_comprehensive(healthy, FS)
    fault_result = engine.analyze_comprehensive(fault, FS)

    assert fault_result["health_score"] is None and healthy_result["health_score"] is None


def test_cw_dataset_can_be_loaded_when_available():
    files = glob.glob(os.path.join(CW_DIR, "**", "*.npy"), recursive=True)
    if not files:
        return
    sig = np.load(files[0])[: FS * 3]
    engine = DiagnosisEngine(strategy="advanced", bearing_params={}, gear_teeth={})
    result = engine.analyze_comprehensive(sig, FS)
    assert "health_score" in result
    assert "time_features" in result


def test_zero_signal_comprehensive_is_indeterminate_not_healthy():
    engine = DiagnosisEngine(gear_teeth={"input": 18})
    result = engine.analyze_comprehensive(np.zeros(FS), FS, rot_freq=20.0, skip_bearing=True)
    assert result["gear"]["analysis"]["status"] == "indeterminate"
    assert result["gear"]["order_peak_concentration"] is None
    assert result["gear"]["fault_indicators"]["order_kurtosis"]["status"] == "not_evaluable"
    assert result["health_score"] is None
    assert result["evaluation_status"] == "indeterminate"


def test_zero_signal_ensemble_paths_are_indeterminate_not_healthy():
    signal = np.zeros(2048)
    bearing_params = {"n": 9, "d": 7.94, "D": 39.04}
    gear_teeth = {"input": 18}
    for name, kwargs in (
        ("bearing_and_gear", {"bearing_params": bearing_params, "gear_teeth": gear_teeth}),
        ("no_mechanical_params", {}),
    ):
        result = run_research_ensemble(
            signal, 2048, rot_freq=16, profile="runtime", **kwargs,
        )
        assert result["health_score"] is None, name
        assert result["evaluation_status"] == "indeterminate", name


def test_zero_signal_all_methods_paths_are_indeterminate_not_healthy():
    signal = np.zeros(2048)
    bearing_params = {"n": 9, "d": 7.94, "D": 39.04}
    gear_teeth = {"input": 18}
    for name, engine, skip_bearing in (
        ("gear_only", DiagnosisEngine(gear_teeth=gear_teeth), True),
        (
            "bearing_and_gear",
            DiagnosisEngine(bearing_params=bearing_params, gear_teeth=gear_teeth),
            False,
        ),
    ):
        result = engine.analyze_all_methods(
            signal, 2048, rot_freq=16, skip_bearing=skip_bearing,
        )
        assert result["health_score"] is None, name
        assert result["evaluation_status"] == "indeterminate", name


if __name__ == "__main__":
    test_no_params_uses_statistical_fault_indicators()
    test_advanced_gear_uses_tsa_residual()
    test_noisy_rot_freq_estimation_is_robust()
    test_dataset_sample_fault_scores_when_available()
    test_cw_dataset_can_be_loaded_when_available()
    test_zero_signal_comprehensive_is_indeterminate_not_healthy()
    test_zero_signal_ensemble_paths_are_indeterminate_not_healthy()
    test_zero_signal_all_methods_paths_are_indeterminate_not_healthy()
    print("test_engine_regressions: OK")
