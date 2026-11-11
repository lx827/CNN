"""
测试 CPW 包络分析在各种边界参数下的鲁棒性
覆盖修复：rot_freq 为 None 时不会传入 cepstrum_pre_whitening 导致崩溃

运行方式(uv-only,见 AGENTS.md §2/§4):
    cd cloud
    uv run python tests/diagnosis/regression/test_cpw_robustness.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

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
    assert "spectrum" in result
    print("  [PASS] CPW with rot_freq=None 未崩溃")


def test_cpw_with_negative_rot_freq():
    """CPW: 显式传入负转频时必须给出可控参数错误"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.CPW,
        gear_teeth={"input": 18},
    )
    sig = np.random.randn(4096)
    try:
        engine.analyze_bearing(sig, fs=25600, rot_freq=-5.0)
    except ValueError:
        pass
    else:
        raise AssertionError("负转频未触发 ValueError")
    print("  [PASS] CPW with rot_freq=-5 明确拒绝非法参数")


def test_cpw_with_zero_rot_freq():
    """CPW: 显式传入零转频时必须给出可控参数错误"""
    engine = DiagnosisEngine(
        bearing_method=BearingMethod.CPW,
        gear_teeth={"input": 18},
    )
    sig = np.random.randn(4096)
    try:
        engine.analyze_bearing(sig, fs=25600, rot_freq=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("零转频未触发 ValueError")
    print("  [PASS] CPW with rot_freq=0 明确拒绝非法参数")


def test_cpw_empty_comb_freqs():
    """CPW: 缺稳定梳状前提必须不可判定，不冒充预白化。"""
    from app.algorithms.bearing.cepstral import CPWEnvelopePipeline

    sig = np.random.randn(1024)
    out = CPWEnvelopePipeline().run(sig, 8192, comb_frequencies=[])
    assert out.status == "indeterminate" and out.representation is None
    assert out.reason == "missing_stable_comb_frequencies"
    print("  [PASS] CPW empty comb_frequencies 明确不可判定")


def test_cpw_none_in_comb_freqs():
    """CPW: 非法梳状输入不能被静默过滤后继续声称已预白化。"""
    from app.algorithms.bearing.cepstral import CPWEnvelopePipeline

    sig = np.random.randn(1024)
    try:
        CPWEnvelopePipeline().run(sig, 8192, comb_frequencies=[None, 25.0, None])
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("非法梳状频率未被拒绝")
    print("  [PASS] CPW comb_frequencies with None 明确拒绝")


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
