"""
测试 CPW 包络分析在各种边界参数下的鲁棒性
覆盖修复：rot_freq 为 None 时不会传入 cepstrum_pre_whitening 导致崩溃

运行方式:
    cd d:/code/CNN
    python tests/diagnosis/test_cpw_robustness.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud'))

import numpy as np
from app.services.diagnosis import DiagnosisEngine, BearingMethod


def test_cpw_with_none_rot_freq():
    """CPW: rot_freq 为 None 时不应崩溃（会被内部过滤掉）"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.CPW,
        gear_teeth={"input": 18},
    )
    sig = np.random.randn(4096)
    # 直接传入 rot_freq=None，内部会尝试估计，如果估计失败不应崩溃
    result = engine.analyze_bearing(sig, fs=25600, rot_freq=None)
    assert "envelope_freq" in result
    print("  [PASS] CPW with rot_freq=None 未崩溃")


def test_cpw_with_negative_rot_freq():
    """CPW: rot_freq 为负数时不应崩溃"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.CPW,
        gear_teeth={"input": 18},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_bearing(sig, fs=25600, rot_freq=-5.0)
    assert "envelope_freq" in result
    print("  [PASS] CPW with rot_freq=-5 未崩溃")


def test_cpw_with_zero_rot_freq():
    """CPW: rot_freq 为 0 时不应崩溃"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.CPW,
        gear_teeth={"input": 18},
    )
    sig = np.random.randn(4096)
    result = engine.analyze_bearing(sig, fs=25600, rot_freq=0.0)
    assert "envelope_freq" in result
    print("  [PASS] CPW with rot_freq=0 未崩溃")


def test_cpw_empty_comb_freqs():
    """CPW: 没有 comb_frequencies 时 cepstrum_pre_whitening 应原样返回信号"""
    from app.services.diagnosis.preprocessing import cepstrum_pre_whitening
    sig = np.random.randn(1024)
    out = cepstrum_pre_whitening(sig, fs=8192, comb_frequencies=[])
    assert len(out) == len(sig)
    print("  [PASS] CPW empty comb_frequencies 未崩溃")


def test_cpw_none_in_comb_freqs():
    """CPW: comb_frequencies 包含 None 时预处理应跳过"""
    from app.services.diagnosis.preprocessing import cepstrum_pre_whitening
    sig = np.random.randn(1024)
    out = cepstrum_pre_whitening(sig, fs=8192, comb_frequencies=[None, 25.0, None])
    assert len(out) == len(sig)
    print("  [PASS] CPW comb_frequencies with None 未崩溃")


def run_all_tests():
    print("=" * 60)
    print("CPW 鲁棒性测试")
    print("=" * 60)

    test_cpw_with_none_rot_freq()
    test_cpw_with_negative_rot_freq()
    test_cpw_with_zero_rot_freq()
    test_cpw_empty_comb_freqs()
    test_cpw_none_in_comb_freqs()

    print("\n" + "=" * 60)
    print("全部测试通过 [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
