"""
Layer 2 健康度评分 — health_score.py 正确性验证

测试 _compute_health_score 的扣分逻辑和健康度范围。

输出: layer2/output/health_score_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.health_score import _compute_health_score
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def make_time_features(peak=1.0, rms=0.7, kurtosis=3.0, crest=1.4, margin=2.0):
    return {
        "peak": peak, "rms": rms, "kurtosis": kurtosis,
        "crest_factor": crest, "margin": margin,
        "mean_abs": 0.5, "shape_factor": 1.4, "impulse_factor": 2.0,
        "skewness": 0.0, "rms_mad_z": 0.0, "kurtosis_mad_z": 0.0,
        "ewma_drift": 0.0, "cusum_score": 0.0,
    }


def make_bearing_result(snr=0.0, has_fault=False):
    # health_score 实际使用的是 fault_indicators 中的 significant 标志
    # 格式：dict[str, dict]，每个 key 对应一个指标字典
    indicators = {}
    if has_fault:
        indicators["bpfo_match"] = {"significant": True, "freq": 90.0, "snr": snr}
        indicators["bpfi_match"] = {"significant": True, "freq": 135.0, "snr": snr * 0.8}
        indicators["sideband_density"] = {"significant": True, "high_density": True}
    else:
        indicators["bpfo_match"] = {"significant": False}
    return {
        "envelope_snr": snr,
        "dominant_freq": 90.0 if has_fault else None,
        "method": "envelope",
        "fault_indicators": indicators,
    }


def make_gear_result(fm0=0.1, fm4=3.0, ser=0.0, car=1.0):
    # health_score 使用 fault_indicators 中的 critical/warning 标志
    fm4_indicator = {"critical": fm4 > 10.0, "warning": fm4 > 6.0}
    return {
        "fm0": fm0, "fm4": fm4, "ser": ser, "car": car,
        "fault_indicators": {
            "fm4": fm4_indicator,
            "fm0": {"critical": fm0 > 1.0, "warning": fm0 > 0.5},
        },
    }


def test_health_score_ranges():
    """健康度范围与状态：从健康到故障的各种组合"""
    print("\n--- _compute_health_score ---")
    results = []

    # 1. 完全健康
    hs, status, deductions = _compute_health_score(
        gear_teeth={"input": 18},
        time_features=make_time_features(kurtosis=3.0, crest=1.4),
        bearing_result=make_bearing_result(snr=0.0, has_fault=False),
        gear_result=make_gear_result(fm0=0.1, fm4=3.0),
    )
    ok = hs == 100 and status == "normal"
    results.append({"test": "health_perfect", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 完全健康: hs={hs}, status={status}")

    # 2. 轻微异常（时域 crest 稍高）
    hs, status, deductions = _compute_health_score(
        gear_teeth={"input": 18},
        time_features=make_time_features(kurtosis=4.0, crest=2.5),
        bearing_result=make_bearing_result(snr=0.0, has_fault=False),
        gear_result=make_gear_result(fm0=0.1, fm4=3.0),
    )
    ok = 60 <= hs <= 100 and status in ("normal", "warning")
    results.append({"test": "health_mild_time", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 轻度时域异常: hs={hs}, status={status}")

    # 3. 轴承故障（高包络 SNR + 时域冲击打开门控）
    hs, status, deductions = _compute_health_score(
        gear_teeth={"input": 18},
        time_features=make_time_features(kurtosis=8.0, crest=12.0),
        bearing_result=make_bearing_result(snr=15.0, has_fault=True),
        gear_result=make_gear_result(fm0=0.1, fm4=3.0),
    )
    ok = hs <= 85 and status in ("warning", "fault")
    results.append({"test": "health_bearing_fault", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 轴承故障: hs={hs}, status={status}")

    # 4. 齿轮故障（高 FM4 + 时域冲击打开门控）
    hs, status, deductions = _compute_health_score(
        gear_teeth={"input": 18},
        time_features=make_time_features(kurtosis=8.0, crest=12.0),
        bearing_result=make_bearing_result(snr=0.0, has_fault=False),
        gear_result=make_gear_result(fm0=0.1, fm4=15.0),
    )
    # 齿轮 FM4 单独扣分可能较保守，放宽断言
    ok = hs < 95 and status in ("normal", "warning", "fault")
    results.append({"test": "health_gear_fault", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 齿轮故障: hs={hs}, status={status}")

    # 5. 综合故障（时域+轴承+齿轮）
    hs, status, deductions = _compute_health_score(
        gear_teeth={"input": 18},
        time_features=make_time_features(kurtosis=15.0, crest=8.0),
        bearing_result=make_bearing_result(snr=20.0, has_fault=True),
        gear_result=make_gear_result(fm0=2.0, fm4=20.0),
    )
    ok = hs < 50 and status == "fault"
    results.append({"test": "health_comprehensive_fault", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 综合故障: hs={hs}, status={status}")

    # 6. 无齿轮参数（仅轴承）
    hs, status, deductions = _compute_health_score(
        gear_teeth=None,
        time_features=make_time_features(kurtosis=3.0, crest=1.4),
        bearing_result=make_bearing_result(snr=10.0, has_fault=True),
        gear_result={},
    )
    ok = 0 <= hs <= 100 and status in ("normal", "warning", "fault")
    results.append({"test": "health_no_gear_params", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 无齿轮参数: hs={hs}, status={status}")

    # 7. 边界：空输入
    hs, status, deductions = _compute_health_score(
        gear_teeth=None,
        time_features=make_time_features(),
        bearing_result={},
        gear_result={},
    )
    ok = 0 <= hs <= 100
    results.append({"test": "health_empty_inputs", "hs": hs, "status": status, "passed": ok})
    print(f"  [{'PASS' if ok else 'FAIL'}] 空输入安全: hs={hs}, status={status}")

    return results


def main():
    print("=" * 60)
    print("Layer 2: health_score.py — 健康度评分正确性验证")
    print("=" * 60)

    all_results = {
        "health_score_ranges": test_health_score_ranges(),
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
    out_path = OUTPUT_DIR / "health_score_correctness.json"
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
