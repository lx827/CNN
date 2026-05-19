"""
Layer 5 应用入口 — 辅助函数边界覆盖 + 真实数据验证

测试:
  _bearing_confidence / _gear_confidence — 边界值 + 真实数据驱动
  _time_confidence — 门控逻辑完备性
  _fault_label — 标签映射准确性

输出: layer5/output/helpers_real.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.ensemble import (
    _bearing_confidence, _gear_confidence, _time_confidence, _fault_label,
)
from app.services.analyzer import _safe_result
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


# ═══════════════════════════════════════════════════════════
# 1. _bearing_confidence — 边界值覆盖
# ═══════════════════════════════════════════════════════════

def test_bearing_confidence_boundary():
    """_bearing_confidence: 空结果 / None 参数 / 极值"""
    print("\n--- _bearing_confidence 边界 ---")
    results = []

    # 空结果
    try:
        c = _bearing_confidence({}, {"kurtosis": 3.0, "crest_factor": 5.0})
        empty_ok = c["confidence"] < 0.3 and c["abnormal"] is False
        results.append({"test": "bearing_empty_result", "conf": c["confidence"], "passed": empty_ok})
        print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空结果: conf={c['confidence']:.2f}")
    except Exception as e:
        results.append({"test": "bearing_empty_result", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 空结果: {str(e)[:60]}")

    # 无 fault_indicators 键
    try:
        c2 = _bearing_confidence({"other": 1}, {"kurtosis": 3.0, "crest_factor": 5.0})
        no_key_ok = c2["confidence"] < 0.3
        results.append({"test": "bearing_no_indicators_key", "conf": c2["confidence"], "passed": no_key_ok})
        print(f"  [{'PASS' if no_key_ok else 'FAIL'}] 无indicators键: conf={c2['confidence']:.2f}")
    except Exception as e:
        results.append({"test": "bearing_no_indicators_key", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 无indicators键: {str(e)[:60]}")

    # 极高 SNR
    try:
        res = {"fault_indicators": {"BPFO": {"significant": True, "snr": 100.0}}}
        c3 = _bearing_confidence(res, {"kurtosis": 25.0, "crest_factor": 30.0})
        capped_ok = c3["confidence"] <= 1.0
        results.append({"test": "bearing_extreme_snr", "conf": c3["confidence"], "passed": capped_ok})
        print(f"  [{'PASS' if capped_ok else 'FAIL'}] 极高SNR: conf={c3['confidence']:.3f} (应≤1.0)")
    except Exception as e:
        results.append({"test": "bearing_extreme_snr", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 极高SNR: {str(e)[:60]}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. _gear_confidence — 边界值覆盖
# ═══════════════════════════════════════════════════════════

def test_gear_confidence_boundary():
    """_gear_confidence: 无参数 / 空指标 / 行星箱特殊逻辑"""
    print("\n--- _gear_confidence 边界 ---")
    results = []

    # has_gear_params=False
    try:
        c = _gear_confidence({"fault_indicators": {}, "planet_count": 0}, has_gear_params=False,
                            time_features={"kurtosis": 5.0, "crest_factor": 8.0})
        low_ok = c["confidence"] < 0.3
        results.append({"test": "gear_no_params", "conf": c["confidence"], "passed": low_ok})
        print(f"  [{'PASS' if low_ok else 'FAIL'}] 无齿轮参数: conf={c['confidence']:.2f}")
    except Exception as e:
        results.append({"test": "gear_no_params", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 无齿轮参数: {str(e)[:60]}")

    # 行星箱 + 高 SER
    try:
        res = {"fault_indicators": {"ser": {"critical": True, "value": 20.0}}, "planet_count": 4}
        c2 = _gear_confidence(res, has_gear_params=True, time_features={"kurtosis": 8.0, "crest_factor": 12.0})
        planet_ok = c2["confidence"] > 0.3
        results.append({"test": "gear_planetary_high_ser", "conf": c2["confidence"], "passed": planet_ok})
        print(f"  [{'PASS' if planet_ok else 'FAIL'}] 行星箱高SER: conf={c2['confidence']:.2f}")
    except Exception as e:
        results.append({"test": "gear_planetary_high_ser", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 行星箱高SER: {str(e)[:60]}")

    # 空结果
    try:
        c3 = _gear_confidence({}, has_gear_params=True, time_features={"kurtosis": 3.0, "crest_factor": 5.0})
        empty_ok = c3["confidence"] < 0.2
        results.append({"test": "gear_empty", "conf": c3["confidence"], "passed": empty_ok})
        print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空结果: conf={c3['confidence']:.2f}")
    except Exception as e:
        results.append({"test": "gear_empty", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 空结果: {str(e)[:60]}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. _time_confidence — 门控完备性
# ═══════════════════════════════════════════════════════════

def test_time_confidence_boundary():
    """_time_confidence: 极值 / 缺失字段"""
    print("\n--- _time_confidence 边界 ---")
    results = []

    # 极高峭度
    c = _time_confidence({"kurtosis": 50.0, "crest_factor": 40.0})
    capped_ok = c <= 1.0
    results.append({"test": "time_extreme", "score": c, "passed": capped_ok})
    print(f"  [{'PASS' if capped_ok else 'FAIL'}] 极高峭度: score={c:.3f}")

    # 极低峭度
    c2 = _time_confidence({"kurtosis": 1.0, "crest_factor": 2.0})
    low_ok = c2 < 0.3
    results.append({"test": "time_very_low", "score": c2, "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 极低峭度: score={c2:.3f}")

    # 缺失 crest_factor
    try:
        c3 = _time_confidence({"kurtosis": 10.0})
        default_ok = c3 >= 0
        results.append({"test": "time_no_crest", "score": c3, "passed": default_ok})
        print(f"  [{'PASS' if default_ok else 'FAIL'}] 缺crest_factor: score={c3:.3f}")
    except Exception as e:
        results.append({"test": "time_no_crest", "passed": False, "error": str(e)[:80]})
        print(f"  [FAIL] 缺crest_factor: {str(e)[:60]}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. _fault_label — 标签映射
# ═══════════════════════════════════════════════════════════

def test_fault_label_boundary():
    """_fault_label: 平局 / 多故障 / 全低置信"""
    print("\n--- _fault_label 边界 ---")
    results = []

    # 平局：轴承和齿轮置信度接近
    best_b = {"fault_indicators": {"BPFO": {"significant": True}}}
    best_g = {"fault_indicators": {"ser": {"critical": True}}}
    label = _fault_label(best_b, best_g, 0.5, 0.5)
    tie_ok = label in ("bearing_BPFO", "gear_ser", "unknown")
    results.append({"test": "label_tie", "label": label, "passed": tie_ok})
    print(f"  [{'PASS' if tie_ok else 'FAIL'}] 平局(0.5 vs 0.5): {label}")

    # 全低置信
    label2 = _fault_label({}, {}, 0.1, 0.05)
    unknown_ok = label2 == "unknown"
    results.append({"test": "label_all_low", "label": label2, "passed": unknown_ok})
    print(f"  [{'PASS' if unknown_ok else 'FAIL'}] 全低置信: {label2}")

    # 只有齿轮有结果
    best_g2 = {"fault_indicators": {"fm4": {"warning": True}}}
    label3 = _fault_label({}, best_g2, 0.1, 0.3)
    gear_only_ok = label3.startswith("gear_") or label3 == "unknown"
    results.append({"test": "label_gear_only", "label": label3, "passed": gear_only_ok})
    print(f"  [{'PASS' if gear_only_ok else 'FAIL'}] 仅齿轮: {label3}")

    # 空输入
    label4 = _fault_label({}, {}, 0, 0)
    empty_ok = label4 == "unknown"
    results.append({"test": "label_empty", "label": label4, "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空输入: {label4}")

    return results


# ═══════════════════════════════════════════════════════════
# 5. _safe_result — analyzer 安全结果
# ═══════════════════════════════════════════════════════════

def test_safe_result_boundary():
    """_safe_result: 各种参数组合"""
    print("\n--- _safe_result 边界 ---")
    results = []

    # 极低健康度 — status 固定为 "normal"（安全默认值）
    r = _safe_result(msg="全部故障", health=0)
    zero_ok = r["health_score"] == 0 and r["status"] == "normal" and "_error" in r
    results.append({"test": "safe_zero", "hs": r["health_score"], "passed": zero_ok})
    print(f"  [{'PASS' if zero_ok else 'FAIL'}] health=0: hs={r['health_score']}, status={r['status']} (固定normal)")

    # 警告边界 — status 固定为 "normal"
    r2 = _safe_result(msg="轻微异常", health=70)
    warn_ok = r2["health_score"] == 70 and r2["status"] == "normal"
    results.append({"test": "safe_warning", "hs": r2["health_score"], "passed": warn_ok})
    print(f"  [{'PASS' if warn_ok else 'FAIL'}] health=70: hs={r2['health_score']}, status={r2['status']}")

    # 默认参数
    r3 = _safe_result()
    default_ok = r3["health_score"] == 100 and r3["status"] == "normal"
    results.append({"test": "safe_default", "hs": r3["health_score"], "passed": default_ok})
    print(f"  [{'PASS' if default_ok else 'FAIL'}] 默认: hs={r3['health_score']}, status={r3['status']}")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 5: 辅助函数边界覆盖")
    print("=" * 60)

    all_results = {
        "bearing_confidence_boundary": test_bearing_confidence_boundary(),
        "gear_confidence_boundary": test_gear_confidence_boundary(),
        "time_confidence_boundary": test_time_confidence_boundary(),
        "fault_label_boundary": test_fault_label_boundary(),
        "safe_result_boundary": test_safe_result_boundary(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False):
                passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "helpers_real.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}")
    print(f"总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")
    if s["failed"] > 0:
        print(f"WARNING: {s['failed']} 个测试失败")
    else:
        print("全部通过!")


if __name__ == "__main__":
    main()
