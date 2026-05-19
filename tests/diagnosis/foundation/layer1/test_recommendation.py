"""
Layer 1 信号基元 — recommendation 正确性验证

测试 _generate_recommendation / _match_suggestion

输出: layer1/output/recommendation.json
"""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.recommendation import _generate_recommendation, _match_suggestion, SUGGESTION_MAP
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_match_suggestion():
    """精确建议匹配"""
    print("\n--- _match_suggestion ---")
    results = []

    # 已知组合的匹配验证（注意：SUGGESTION_MAP 的键未按字母序排列，
    # 而 _match_suggestion 内部会 sorted，导致部分键无法匹配 — 已知限制）
    # 使用与 map 中字母序一致的键来验证
    ded = [("bearing_sc_scoh_evidence", 10)]  # 单键，不受排序影响
    s = _match_suggestion(ded)
    scoh_ok = s is not None and "周期" in s
    results.append({"test": "match_scoh_evidence", "matched": s is not None, "passed": scoh_ok})
    print(f"  [{'PASS' if scoh_ok else 'FAIL'}] scoh evidence: {'matched' if s else 'no match'}")

    # 验证修复后的双键匹配（键已按字母序排列，_match_suggestion 的 sorted() 能正确匹配）
    ded2 = [("kurtosis_high", 20), ("bearing_multi_freq", 15)]
    s = _match_suggestion(ded2)
    combo_ok = s is not None and "复合故障" in s
    results.append({"test": "match_bearing_combo", "matched": s is not None,
                    "passed": combo_ok})
    print(f"  [{'PASS' if combo_ok else 'FAIL'}] bearing combo: {'matched' if s else 'no match'}")

    # 不存在的组合
    s = _match_suggestion([("nonexistent", 0)])
    no_match_ok = s is None
    results.append({"test": "no_match_unknown", "matched": s is not None, "passed": no_match_ok})
    print(f"  [{'PASS' if no_match_ok else 'FAIL'}] unknown combo: {'matched' if s else 'no match (correct)'}")

    return results


def test_generate_recommendation():
    """生成诊断建议"""
    print("\n--- _generate_recommendation ---")
    results = []

    # 正常状态
    r = _generate_recommendation({}, {}, "normal")
    normal_ok = "正常" in r
    results.append({"test": "normal_status", "suggestion": r[:40], "passed": normal_ok})
    print(f"  [{'PASS' if normal_ok else 'FAIL'}] normal: {r[:50]}...")

    # 精确匹配（使用单键避免排序问题 + D-S 冲突）
    bearing = {"fault_indicators": {}}
    gear = {"fault_indicators": {}}
    r = _generate_recommendation(bearing, gear, "warning", ds_conflict_high=True,
                                  deductions=[("ds_conflict_penalty", 10)])
    conflict_ok = "冲突" in r or "不一致" in r
    results.append({"test": "precise_ds_conflict", "suggestion": r[:50], "passed": conflict_ok})
    print(f"  [{'PASS' if conflict_ok else 'FAIL'}] DS conflict: {r[:60]}...")

    # 传统分支：齿轮 SER critical
    gear = {"fault_indicators": {"ser": {"critical": True}}}
    r = _generate_recommendation({}, gear, "critical")
    gear_ok = "齿轮" in r and "边频" in r
    results.append({"test": "gear_ser_critical", "suggestion": r[:50], "passed": gear_ok})
    print(f"  [{'PASS' if gear_ok else 'FAIL'}] gear SER critical: {r[:60]}...")

    return results


def test_suggestion_map():
    """SUGGESTION_MAP 完整性检查"""
    print("\n--- SUGGESTION_MAP ---")
    results = []

    n_entries = len(SUGGESTION_MAP)
    map_ok = n_entries >= 5
    results.append({"test": "suggestion_map_size", "n_entries": n_entries, "passed": map_ok})
    print(f"  [{'PASS' if map_ok else 'FAIL'}] 映射表条目: {n_entries}")

    # 所有键都是元组
    all_tuples = all(isinstance(k, tuple) for k in SUGGESTION_MAP)
    results.append({"test": "all_keys_are_tuples", "passed": all_tuples})
    print(f"  [{'PASS' if all_tuples else 'FAIL'}] 键均为元组: {all_tuples}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: recommendation — 诊断建议生成")
    print("=" * 60)

    all_results = {
        "match_suggestion": test_match_suggestion(),
        "generate_recommendation": test_generate_recommendation(),
        "suggestion_map": test_suggestion_map(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "recommendation.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
