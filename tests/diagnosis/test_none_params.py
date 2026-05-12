"""
测试设备参数中包含 None 值时的鲁棒性

覆盖修复：
- bearing_params 中 alpha/d/D/n 为 None 时 np.radians / 比较不崩溃
- gear_teeth 中 input/output 为 None 时比较运算不崩溃

运行方式:
    cd d:/code/CNN
    python tests/diagnosis/test_none_params.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))

import numpy as np
from app.services.diagnosis.features import _compute_bearing_fault_freqs
from app.services.diagnosis.rule_based import (
    _extract_spectrum_features,
    _extract_order_features,
)
from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod


def test_bearing_fault_freqs_with_none_alpha():
    """_compute_bearing_fault_freqs: alpha=None 不应崩溃"""
    params = {"n": 9, "d": 7.94, "D": 39.04, "alpha": None}
    freqs = _compute_bearing_fault_freqs(rot_freq=25.0, bearing_params=params)
    assert isinstance(freqs, dict)
    # alpha 被当作 0 处理，应正常返回频率
    assert "BPFO" in freqs
    print("  [PASS] bearing_params alpha=None 未崩溃")


def test_bearing_fault_freqs_with_all_none():
    """_compute_bearing_fault_freqs: 全部参数为 None 应返回空 dict"""
    params = {"n": None, "d": None, "D": None, "alpha": None}
    freqs = _compute_bearing_fault_freqs(rot_freq=25.0, bearing_params=params)
    assert freqs == {}
    print("  [PASS] bearing_params 全 None 返回空 dict")


def test_extract_spectrum_features_with_none_gear_teeth():
    """_extract_spectrum_features: gear_teeth 含 None 值不应崩溃"""
    xf = np.linspace(0, 1000, 1000)
    yf = np.random.rand(1000)
    gear_teeth = {"input": None, "output": None}
    features = _extract_spectrum_features(
        xf, yf, rot_freq=25.0, gear_teeth=gear_teeth, bearing_params=None
    )
    assert isinstance(features, dict)
    # 齿轮特征不应生成
    assert "mesh_freq_hz" not in features
    print("  [PASS] spectrum_features gear_teeth=None 未崩溃")


def test_extract_order_features_with_none_gear_teeth():
    """_extract_order_features: gear_teeth 含 None 值不应崩溃"""
    orders = np.linspace(0, 50, 500)
    spectrum = np.random.rand(500)
    gear_teeth = {"input": None, "output": None}
    features = _extract_order_features(
        orders, spectrum, rot_freq=25.0, gear_teeth=gear_teeth, bearing_params=None
    )
    assert isinstance(features, dict)
    assert "mesh_order" not in features
    print("  [PASS] order_features gear_teeth=None 未崩溃")


def test_diagnosis_engine_bearing_with_none_params():
    """DiagnosisEngine.analyze_bearing: bearing_params 含 None 不崩溃"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.ENVELOPE,
        bearing_params={"n": 9, "d": 7.94, "D": 39.04, "alpha": None},
        gear_teeth={"input": None, "output": None},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_bearing(sig, fs=25600, rot_freq=25.0)
    assert "fault_indicators" in result
    print("  [PASS] DiagnosisEngine bearing alpha=None 未崩溃")


def test_diagnosis_engine_gear_with_none_teeth():
    """DiagnosisEngine.analyze_gear: gear_teeth 含 None 不崩溃"""
    engine = DiagnosisEngine(
        gear_method=GearMethod.STANDARD,
        gear_teeth={"input": None, "output": None},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_gear(sig, fs=25600, rot_freq=25.0)
    assert "sidebands" in result
    assert result.get("mesh_freq_hz") is None
    print("  [PASS] DiagnosisEngine gear input=None 未崩溃")


def test_diagnosis_engine_advanced_gear_with_none_teeth():
    """DiagnosisEngine.analyze_gear (ADVANCED): gear_teeth 含 None 不崩溃"""
    engine = DiagnosisEngine(
        gear_method=GearMethod.ADVANCED,
        gear_teeth={"input": None, "output": 80},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_gear(sig, fs=25600, rot_freq=25.0)
    assert "sidebands" in result
    print("  [PASS] DiagnosisEngine ADVANCED gear input=None 未崩溃")


def run_all_tests():
    print("=" * 60)
    print("设备参数 None 值鲁棒性测试")
    print("=" * 60)

    test_bearing_fault_freqs_with_none_alpha()
    test_bearing_fault_freqs_with_all_none()
    test_extract_spectrum_features_with_none_gear_teeth()
    test_extract_order_features_with_none_gear_teeth()
    test_diagnosis_engine_bearing_with_none_params()
    test_diagnosis_engine_gear_with_none_teeth()
    test_diagnosis_engine_advanced_gear_with_none_teeth()

    print("\n" + "=" * 60)
    print("全部测试通过 [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
