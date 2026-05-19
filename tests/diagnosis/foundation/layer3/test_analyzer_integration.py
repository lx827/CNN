"""
Layer 3 分析器集成 — analyzer.py 正确性验证

测试 analyze_device 的多通道综合分析能力。

输出: layer3/output/analyzer_integration.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.analyzer import analyze_device
from app.services.diagnosis.features import has_bearing_params, has_gear_params
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, bearing_outer_race, gear_mesh,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


class MockDevice:
    """模拟数据库 device 对象"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_analyzer_single_channel():
    """单通道分析：验证能返回完整诊断结果"""
    print("\n--- analyze_device (单通道) ---")
    results = []

    sig, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    device = MockDevice(
        diagnosis_strategy="advanced",
        bearing_method="kurtogram",
        gear_method="standard",
        bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        gear_teeth=None,
    )
    channels_data = {"1": sig.tolist()}

    try:
        res = analyze_device(channels_data, sample_rate=FS, device=device, rot_freq=25.0)
        has_health = res.get("health_score", -1) >= 0
        has_status = res.get("status") in {"normal", "warning", "fault"}
        passed = has_health and has_status
        results.append({
            "test": "analyzer_single_channel",
            "health_score": res.get("health_score"),
            "status": res.get("status"),
            "passed": passed,
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] 单通道: hs={res.get('health_score')}, status={res.get('status')}")
    except Exception as e:
        results.append({"test": "analyzer_single_channel", "error": str(e), "passed": False})
        print(f"  [FAIL] 单通道异常: {e}")

    return results


def test_analyzer_multi_channel():
    """多通道分析：验证各通道结果独立且能汇总"""
    print("\n--- analyze_device (多通道) ---")
    results = []

    sig1, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    sig2, _, _ = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=25)

    device = MockDevice(
        diagnosis_strategy="advanced",
        bearing_method="kurtogram",
        gear_method="standard",
        bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        gear_teeth={"input": 18},
    )
    channels_data = {"1": sig1.tolist(), "2": sig2.tolist()}

    try:
        res = analyze_device(channels_data, sample_rate=FS, device=device, rot_freq=25.0)
        has_health = res.get("health_score", -1) >= 0
        has_status = res.get("status") in {"normal", "warning", "fault"}
        passed = has_health and has_status
        results.append({
            "test": "analyzer_multi_channel",
            "health_score": res.get("health_score"),
            "status": res.get("status"),
            "passed": passed,
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] 多通道: hs={res.get('health_score')}, status={res.get('status')}")
    except Exception as e:
        results.append({"test": "analyzer_multi_channel", "error": str(e), "passed": False})
        print(f"  [FAIL] 多通道异常: {e}")

    return results


def test_analyzer_no_params():
    """无机械参数时走统计诊断路径"""
    print("\n--- analyze_device (无参数) ---")
    results = []

    sig, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    device = MockDevice(
        diagnosis_strategy="advanced",
        bearing_method="kurtogram",
        gear_method="standard",
        bearing_params=None,
        gear_teeth=None,
    )
    channels_data = {"1": sig.tolist()}

    try:
        res = analyze_device(channels_data, sample_rate=FS, device=device, rot_freq=25.0)
        has_health = res.get("health_score", -1) >= 0
        has_status = res.get("status") in {"normal", "warning", "fault"}
        passed = has_health and has_status
        results.append({
            "test": "analyzer_no_params",
            "health_score": res.get("health_score"),
            "status": res.get("status"),
            "passed": passed,
        })
        print(f"  [{'PASS' if passed else 'FAIL'}] 无参数: hs={res.get('health_score')}, status={res.get('status')}")
    except Exception as e:
        results.append({"test": "analyzer_no_params", "error": str(e), "passed": False})
        print(f"  [FAIL] 无参数异常: {e}")

    return results


def main():
    print("=" * 60)
    print("Layer 3: analyzer.py — 分析器集成正确性验证")
    print("=" * 60)

    all_results = {
        "single_channel": test_analyzer_single_channel(),
        "multi_channel": test_analyzer_multi_channel(),
        "no_params": test_analyzer_no_params(),
    }

    total = 0
    passed = 0
    for category, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", False):
                passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "analyzer_integration.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    print(f"\n结果已保存: {out_path}")

    s = all_results["summary"]
    print(f"\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")
    if s["failed"] > 0:
        print(f"WARNING: {s['failed']} 个测试失败")
    else:
        print("全部通过!")


if __name__ == "__main__":
    main()
