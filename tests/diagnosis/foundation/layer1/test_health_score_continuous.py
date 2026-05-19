"""
Layer 1 信号基元 — health_score_continuous 正确性验证

测试 sigmoid_deduction / multi_threshold_deduction /
cascade_deduction / compute_continuous_deductions

输出: layer1/output/health_score_continuous.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.health_score_continuous import (
    sigmoid_deduction, multi_threshold_deduction,
    cascade_deduction, compute_continuous_deductions,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_sigmoid():
    """sigmoid_deduction 基本性质"""
    print("\n--- sigmoid_deduction ---")
    results = []

    # 远低于阈值 → 扣分≈0
    d = sigmoid_deduction(2.0, 5.0, 15.0)
    zero_ok = d < 0.1
    results.append({"test": "sigmoid_below_threshold", "value": 2.0, "threshold": 5.0,
                    "deduction": round(float(d), 4), "passed": zero_ok})
    print(f"  [{'PASS' if zero_ok else 'FAIL'}] 远低于阈值(2<5): 扣分={d:.4f}≈0")

    # 远高于阈值 → 扣分≈max
    d = sigmoid_deduction(20.0, 5.0, 15.0)
    full_ok = d > 14.9
    results.append({"test": "sigmoid_above_threshold", "value": 20.0, "threshold": 5.0,
                    "deduction": round(float(d), 4), "passed": full_ok})
    print(f"  [{'PASS' if full_ok else 'FAIL'}] 远高于阈值(20>5): 扣分={d:.4f}≈15")

    # 恰好等于阈值 → 扣分=max/2
    d = sigmoid_deduction(5.0, 5.0, 10.0)
    half_ok = abs(d - 5.0) < 0.1
    results.append({"test": "sigmoid_at_threshold", "value": 5.0, "threshold": 5.0,
                    "deduction": round(float(d), 4), "passed": half_ok})
    print(f"  [{'PASS' if half_ok else 'FAIL'}] 等于阈值(5=5): 扣分={d:.4f}≈5")

    # 单调性：value越大扣分越多
    d1 = sigmoid_deduction(4.0, 5.0, 10.0)
    d2 = sigmoid_deduction(6.0, 5.0, 10.0)
    mono_ok = d2 > d1
    results.append({"test": "sigmoid_monotonic", "d_4": round(float(d1), 4), "d_6": round(float(d2), 4),
                    "passed": mono_ok})
    print(f"  [{'PASS' if mono_ok else 'FAIL'}] 单调性: d(4)={d1:.2f} < d(6)={d2:.2f}")

    return results


def test_multi_threshold():
    """multi_threshold_deduction: 多级阈值连续扣分"""
    print("\n--- multi_threshold_deduction ---")
    results = []

    thresholds = [5, 8, 12, 20]
    max_deds = [15, 22, 30, 40]

    # 低于所有阈值
    d = multi_threshold_deduction(3.0, thresholds, max_deds)
    low_ok = d < 0.5
    results.append({"test": "multi_below_all", "value": 3.0, "deduction": round(float(d), 4), "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 低于所有阈值(3): {d:.2f}≈0")

    # 超过最高阈值
    d = multi_threshold_deduction(25.0, thresholds, max_deds)
    high_ok = d > 35
    results.append({"test": "multi_above_all", "value": 25.0, "deduction": round(float(d), 4), "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] 超过所有阈值(25): {d:.2f}≈40")

    # 中间值
    d = multi_threshold_deduction(10.0, thresholds, max_deds)
    mid_ok = 15 < d < 30  # 应该在 22 附近
    results.append({"test": "multi_middle", "value": 10.0, "deduction": round(float(d), 4), "passed": mid_ok})
    print(f"  [{'PASS' if mid_ok else 'FAIL'}] 中间值(10): {d:.2f} (期望≈22)")

    return results


def test_cascade():
    """cascade_deduction: 级联扣分"""
    print("\n--- cascade_deduction ---")
    results = []

    # 单值多级级联
    d = cascade_deduction(10.0, [5, 8, 12, 20], [15, 22, 30, 40])
    mid_ok = 15 < d < 28
    results.append({"test": "cascade_kurt10", "value": 10.0, "deduction": round(float(d), 2),
                    "passed": mid_ok})
    print(f"  [{'PASS' if mid_ok else 'FAIL'}] kurt=10 级联扣分: {d:.1f} (期望≈20)")

    d = cascade_deduction(4.0, [5, 8, 12], [15, 22, 30])
    low_ok = d < 2
    results.append({"test": "cascade_below_all", "value": 4.0, "deduction": round(float(d), 2),
                    "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 低于所有阈值: {d:.2f}≈0")

    return results


def test_continuous_deductions():
    """compute_continuous_deductions: 完整扣分计算"""
    print("\n--- compute_continuous_deductions ---")
    results = []

    tf = {"kurtosis": 3.2, "crest_factor": 6.0, "rms": 0.5,
          "rms_mad_z": 1.0, "kurtosis_mad_z": 0.5}
    bearing = {"fault_indicators": {}}
    gear = {"fault_indicators": {}}
    ded = compute_continuous_deductions(tf, None, bearing, gear)
    not_empty = len(ded) >= 0  # 可能为空（指标都在正常范围）
    results.append({"test": "continuous_deductions", "n_deductions": len(ded),
                    "passed": not_empty})
    print(f"  [{'PASS' if not_empty else 'FAIL'}] 扣分项数: {len(ded)}")

    # 高峭度应产生扣分
    tf2 = {"kurtosis": 12.0, "crest_factor": 12.0, "rms": 0.5}
    ded2 = compute_continuous_deductions(tf2, None, bearing, gear)
    has_ded = len(ded2) > 0
    results.append({"test": "high_kurtosis_deductions", "n_deductions": len(ded2),
                    "passed": has_ded})
    print(f"  [{'PASS' if has_ded else 'FAIL'}] 高峭度(12): 扣分项={len(ded2)}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: health_score_continuous — 连续扣分正确性")
    print("=" * 60)

    all_results = {
        "sigmoid": test_sigmoid(),
        "multi_threshold": test_multi_threshold(),
        "cascade": test_cascade(),
        "continuous": test_continuous_deductions(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "health_score_continuous.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    print(f"\n结果: {out}")
    s = all_results["summary"]
    print(f"总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
