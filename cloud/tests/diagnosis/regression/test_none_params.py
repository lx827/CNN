"""
测试设备参数中包含 None 值时的鲁棒性

覆盖修复：
- bearing_params 中 alpha/d/D/n 为 None 时 np.radians / 比较不崩溃
- gear_teeth 中 input/output 为 None 时比较运算不崩溃

运行方式(uv-only,见 AGENTS.md §2/§4):
    cd cloud
    uv run python tests/diagnosis/regression/test_none_params.py
"""
import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import numpy as np
from app.services.diagnosis.features import _compute_bearing_fault_freqs
from app.algorithms.order import ScalarSpeed
from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline
from app.services.analyzer import analyze_device
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


def test_fixed_axis_pipeline_without_geometry_has_no_mesh_evidence():
    """没有几何参数时，保留通用统计，但 SER 明确不可评估而不是 0。"""
    time = np.arange(8192) / 8192
    signal = np.sin(2 * np.pi * 25.0 * time)
    diagnosis = FixedAxisGearPipeline(geometry=None).run(
        signal, 8192, speed=ScalarSpeed(25.0, "test_truth"),
    )
    assert diagnosis.analysis.mesh_order is None
    ser = diagnosis.analysis.sideband_analysis.ser
    assert ser.status == "not_evaluable" and ser.value is None
    assert ser.reason == "missing_fixed_axis_geometry"
    indicator = diagnosis.evaluation.indicators["ser"]
    assert indicator["evaluable"] is False
    assert indicator["warning"] is None and indicator["critical"] is None
    print("  [PASS] 定轴 Pipeline 缺少几何参数时不伪造啮合/SER 证据")


def test_orchestration_with_none_teeth_is_unknown():
    """已配置却缺失的齿数不能在统一编排中变成健康诊断。"""
    time = np.arange(8192) / 8192
    signal = np.sin(2 * np.pi * 25.0 * time)
    device = SimpleNamespace(gear_teeth={"input": None, "output": None}, bearing_params=None)
    result = analyze_device({"ch1": signal}, sample_rate=8192, device=device, rot_freq=25, denoise_method="none")
    assert result["evaluation_status"] in {"indeterminate", "not_evaluable"}
    assert result["diagnosis_conclusion"] == "unknown"
    assert result["health_score"] is None
    assert "status" not in result and "fault_probabilities" not in result
    print("  [PASS] 统一编排 gear_teeth=None 保留未知与空评分")


def test_diagnosis_engine_bearing_with_none_params():
    """DiagnosisEngine.analyze_bearing: bearing_params 含 None 不崩溃"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.ENVELOPE,
        bearing_params={"n": 9, "d": 7.94, "D": 39.04, "alpha": None},
        gear_teeth={"input": None, "output": None},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_bearing(sig, fs=25600, rot_freq=25.0)
    assert "evaluation" in result
    assert "indicators" in result["evaluation"]
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
    test_fixed_axis_pipeline_without_geometry_has_no_mesh_evidence()
    test_orchestration_with_none_teeth_is_unknown()
    test_diagnosis_engine_bearing_with_none_params()
    test_diagnosis_engine_gear_with_none_teeth()
    test_diagnosis_engine_advanced_gear_with_none_teeth()

    print("\n" + "=" * 60)
    print("全部测试通过 [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
