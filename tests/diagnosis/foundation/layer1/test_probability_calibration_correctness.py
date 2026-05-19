"""
Layer 1 信号基元 — probability_calibration 正确性验证

测试 calibrate_fault_probabilities / _sigmoid_prob / calibrate_snr_to_prob

输出: layer1/output/probability_calibration.json
"""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.probability_calibration import (
    calibrate_fault_probabilities, calibrate_snr_to_prob, _sigmoid_prob,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_sigmoid_prob():
    """_sigmoid_prob: 映射范围与单调性"""
    print("\n--- _sigmoid_prob ---")
    results = []

    # 远低于阈值 → ≈0
    p = _sigmoid_prob(0.0, threshold=5.0, max_prob=0.85, slope=1.5)
    low_ok = p < 0.05
    results.append({"test": "sigmoid_far_below", "prob": round(p, 4), "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 远低于阈值: {p:.4f}")

    # 远高于阈值 → ≈max_prob
    p2 = _sigmoid_prob(20.0, threshold=5.0, max_prob=0.85, slope=1.5)
    high_ok = p2 > 0.8
    results.append({"test": "sigmoid_far_above", "prob": round(p2, 4), "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] 远高于阈值: {p2:.4f}")

    # 单调性
    p3 = _sigmoid_prob(4.0, threshold=5.0, max_prob=0.85, slope=1.5)
    p4 = _sigmoid_prob(6.0, threshold=5.0, max_prob=0.85, slope=1.5)
    mono_ok = p4 > p3
    results.append({"test": "sigmoid_monotonic", "passed": mono_ok})
    print(f"  [{'PASS' if mono_ok else 'FAIL'}] 单调性: {p3:.4f} < {p4:.4f}")

    return results


def test_calibrate_probabilities():
    """calibrate_fault_probabilities: 归一化与正常运行概率"""
    print("\n--- calibrate_fault_probabilities ---")
    results = []

    raw = {"轴承外圈故障": 0.8, "齿轮磨损": 0.6}
    cal = calibrate_fault_probabilities(raw)
    total = sum(v for k, v in cal.items() if k != "正常运行")
    sum_ok = total <= 1.01
    has_normal = "正常运行" in cal and cal["正常运行"] >= 0
    results.append({
        "test": "calibrate_normalize",
        "total_fault": round(total, 4), "normal": round(cal.get("正常运行", 0), 4),
        "passed": sum_ok and has_normal,
    })
    print(f"  [{'PASS' if sum_ok and has_normal else 'FAIL'}] 归一化: total={total:.3f}, normal={cal.get('正常运行', 0):.3f}")

    # 空输入
    cal2 = calibrate_fault_probabilities({})
    empty_ok = cal2.get("正常运行") == 1.0
    results.append({"test": "calibrate_empty", "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空输入: normal={cal2.get('正常运行', 0):.3f}")

    return results


def test_calibrate_snr():
    """calibrate_snr_to_prob: SNR→概率映射"""
    print("\n--- calibrate_snr_to_prob ---")
    results = []

    # 健康 SNR
    p_low = calibrate_snr_to_prob(2.0)
    low_ok = p_low < 0.2
    results.append({"test": "snr_healthy", "prob": round(p_low, 4), "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] SNR=2(健康): {p_low:.3f}")

    # 故障 SNR
    p_high = calibrate_snr_to_prob(10.0)
    high_ok = p_high > 0.6
    results.append({"test": "snr_fault", "prob": round(p_high, 4), "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] SNR=10(故障): {p_high:.3f}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: probability_calibration — 概率校准正确性")
    print("=" * 60)

    all_results = {
        "sigmoid": test_sigmoid_prob(),
        "calibrate": test_calibrate_probabilities(),
        "snr": test_calibrate_snr(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "probability_calibration.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
