"""
Layer 5 应用入口 — ensemble.py 辅助函数测试

测试 _bearing_confidence / _gear_confidence / _time_confidence / _fault_label

输出: layer5/output/ensemble_helpers.json
"""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.ensemble import (
    _bearing_confidence, _gear_confidence, _time_confidence, _fault_label,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_bearing_confidence():
    """_bearing_confidence: 轴承置信度计算"""
    print("\n--- _bearing_confidence ---")
    results = []

    # 高置信：2+ param hits + 冲击背景
    res = {
        "fault_indicators": {
            "BPFO": {"significant": True, "snr": 12.0},
            "BPFI": {"significant": True, "snr": 8.0},
        }
    }
    tf = {"kurtosis": 12.0, "crest_factor": 15.0}
    c = _bearing_confidence(res, tf)
    high_ok = c["confidence"] >= 0.8 and c["abnormal"] is True
    results.append({"test": "bearing_high_conf", "conf": c["confidence"], "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] 高置信: conf={c['confidence']:.2f}, abnormal={c['abnormal']}")

    # 低置信：无显著指标
    res2 = {"fault_indicators": {}}
    c2 = _bearing_confidence(res2, {"kurtosis": 3.0, "crest_factor": 5.0})
    low_ok = c2["confidence"] < 0.3 and c2["abnormal"] is False
    results.append({"test": "bearing_low_conf", "conf": c2["confidence"], "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 低置信: conf={c2['confidence']:.2f}")

    # 统计路径：单统计指标 + 高 SNR + 冲击
    res3 = {
        "fault_indicators": {
            "envelope_peak_snr": {"significant": True, "snr": 15.0},
        }
    }
    c3 = _bearing_confidence(res3, {"kurtosis": 8.0, "crest_factor": 12.0})
    stat_ok = c3["confidence"] > 0.3
    results.append({"test": "bearing_stat_path", "conf": c3["confidence"], "passed": stat_ok})
    print(f"  [{'PASS' if stat_ok else 'FAIL'}] 统计路径: conf={c3['confidence']:.2f}")

    return results


def test_gear_confidence():
    """_gear_confidence: 齿轮置信度计算"""
    print("\n--- _gear_confidence ---")
    results = []

    # 高置信：有齿轮参数 + critical + warning + 冲击背景
    res = {
        "fault_indicators": {
            "ser": {"critical": True, "value": 15.0},
            "fm4": {"warning": True, "value": 8.0},
        },
        "planet_count": 0,
    }
    tf = {"kurtosis": 15.0, "crest_factor": 16.0}
    c = _gear_confidence(res, has_gear_params=True, time_features=tf)
    high_ok = c["confidence"] >= 0.5 and c["abnormal"] is True
    results.append({"test": "gear_high_conf", "conf": c["confidence"], "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] 高置信: conf={c['confidence']:.2f}, abnormal={c['abnormal']}")

    # 低置信：无齿轮参数 + 无指标
    res2 = {"fault_indicators": {}, "planet_count": 0}
    c2 = _gear_confidence(res2, has_gear_params=False, time_features={"kurtosis": 3.0, "crest_factor": 5.0})
    low_ok = c2["confidence"] < 0.2 and c2["abnormal"] is False
    results.append({"test": "gear_low_conf", "conf": c2["confidence"], "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 低置信: conf={c2['confidence']:.2f}")

    # 行星箱：低 kurt (<5.5) 也应打开门控
    res3 = {
        "fault_indicators": {
            "ser": {"warning": True, "value": 9.0},
        },
        "planet_count": 4,
    }
    c3 = _gear_confidence(res3, has_gear_params=True, time_features={"kurtosis": 4.0, "crest_factor": 8.0})
    planetary_ok = c3["confidence"] > 0.1  # 行星箱在低 kurt 下也应有一定置信度
    results.append({"test": "gear_planetary_low_kurt", "conf": c3["confidence"], "passed": planetary_ok})
    print(f"  [{'PASS' if planetary_ok else 'FAIL'}] 行星箱低kurt: conf={c3['confidence']:.2f}")

    return results


def test_time_confidence():
    """_time_confidence: 时域置信度"""
    print("\n--- _time_confidence ---")
    results = []

    # 高峭度
    c = _time_confidence({"kurtosis": 25.0, "crest_factor": 20.0})
    high_ok = c >= 0.8
    results.append({"test": "time_high_kurt", "score": c, "passed": high_ok})
    print(f"  [{'PASS' if high_ok else 'FAIL'}] kurt=25: score={c:.2f}")

    # 中等
    c2 = _time_confidence({"kurtosis": 10.0, "crest_factor": 12.0})
    mid_ok = 0.5 < c2 < 0.8
    results.append({"test": "time_mid_kurt", "score": c2, "passed": mid_ok})
    print(f"  [{'PASS' if mid_ok else 'FAIL'}] kurt=10: score={c2:.2f}")

    # 正常
    c3 = _time_confidence({"kurtosis": 3.0, "crest_factor": 5.0})
    low_ok = c3 < 0.3
    results.append({"test": "time_normal", "score": c3, "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] kurt=3: score={c3:.2f}")

    return results


def test_fault_label():
    """_fault_label: 故障标签推断"""
    print("\n--- _fault_label ---")
    results = []

    # 齿轮占优
    best_gear = {"fault_indicators": {"ser": {"critical": True}}}
    label = _fault_label({}, best_gear, 0.3, 0.7)
    gear_ok = label.startswith("gear_")
    results.append({"test": "label_gear_dominant", "label": label, "passed": gear_ok})
    print(f"  [{'PASS' if gear_ok else 'FAIL'}] 齿轮占优: {label}")

    # 轴承占优
    best_bearing = {"fault_indicators": {"BPFO": {"significant": True}}}
    label2 = _fault_label(best_bearing, {}, 0.7, 0.2)
    bearing_ok = "bearing_" in label2
    results.append({"test": "label_bearing_dominant", "label": label2, "passed": bearing_ok})
    print(f"  [{'PASS' if bearing_ok else 'FAIL'}] 轴承占优: {label2}")

    # 无明确故障
    label3 = _fault_label({}, {}, 0.2, 0.1)
    unknown_ok = label3 == "unknown"
    results.append({"test": "label_unknown", "label": label3, "passed": unknown_ok})
    print(f"  [{'PASS' if unknown_ok else 'FAIL'}] 无故障: {label3}")

    return results


def main():
    print("=" * 60)
    print("Layer 5: ensemble.py — 辅助函数测试")
    print("=" * 60)

    all_results = {
        "bearing_confidence": test_bearing_confidence(),
        "gear_confidence": test_gear_confidence(),
        "time_confidence": test_time_confidence(),
        "fault_label": test_fault_label(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "ensemble_helpers.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
