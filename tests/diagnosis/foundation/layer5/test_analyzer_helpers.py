"""
Layer 5 应用入口 — analyzer.py 辅助函数测试

测试 calibrate_fault_probabilities / _safe_result

输出: layer5/output/analyzer_helpers.json
"""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.probability_calibration import calibrate_fault_probabilities
from app.services.analyzer import _safe_result
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_calibrate_probabilities():
    """calibrate_fault_probabilities: 概率校准"""
    print("\n--- calibrate_fault_probabilities ---")
    results = []

    # 单一故障高概率
    raw = {"轴承外圈故障": 0.8, "正常运行": 0.2}
    cal = calibrate_fault_probabilities(raw)
    has_normal = "正常运行" in cal
    sum_le_1 = sum(v for k, v in cal.items() if k != "正常运行") <= 1.0
    bearing_high = cal.get("轴承外圈故障", 0) > 0.5
    results.append({"test": "calibrate_single_high", "calibrated": cal, "passed": has_normal and sum_le_1 and bearing_high})
    print(f"  [{'PASS' if has_normal and sum_le_1 and bearing_high else 'FAIL'}] 单故障高概率: {cal}")

    # 多故障概率归一化
    raw2 = {"轴承外圈故障": 0.9, "齿轮磨损": 0.8, "正常运行": 0.3}
    cal2 = calibrate_fault_probabilities(raw2)
    total_fault = sum(v for k, v in cal2.items() if k != "正常运行")
    normalized_ok = total_fault <= 1.01  # 允许浮点误差
    normal_present = "正常运行" in cal2 and cal2["正常运行"] >= 0
    results.append({"test": "calibrate_multi_normalize", "total_fault": round(total_fault, 4),
                    "passed": normalized_ok and normal_present})
    print(f"  [{'PASS' if normalized_ok and normal_present else 'FAIL'}] 多故障归一化: total={total_fault:.3f}, normal={cal2.get('正常运行', 0):.3f}")

    # 低概率（健康）— raw_prob=0.1 经 sigmoid(th=0.2, slope=6) 校准后约 0.3
    raw3 = {"轴承外圈故障": 0.1, "正常运行": 0.9}
    cal3 = calibrate_fault_probabilities(raw3)
    low_ok = cal3.get("轴承外圈故障", 1) < 0.4  # 校准后仍低于 0.4
    results.append({"test": "calibrate_low_prob", "bearing_prob": cal3.get("轴承外圈故障"), "passed": low_ok})
    print(f"  [{'PASS' if low_ok else 'FAIL'}] 低概率: bearing={cal3.get('轴承外圈故障', 0):.3f}")

    # 空输入
    cal4 = calibrate_fault_probabilities({})
    empty_ok = "正常运行" in cal4 and cal4["正常运行"] == 1.0
    results.append({"test": "calibrate_empty", "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空输入: normal={cal4.get('正常运行', 0):.3f}")

    return results


def test_safe_result():
    """_safe_result: 崩溃安全默认结果"""
    print("\n--- _safe_result ---")
    results = []

    r = _safe_result()
    keys_ok = all(k in r for k in ["health_score", "status", "fault_probabilities", "imf_energy", "order_analysis", "rot_freq", "_error"])
    health_ok = r["health_score"] == 100 and r["status"] == "normal"
    results.append({"test": "safe_result_default", "keys_present": keys_ok, "passed": keys_ok and health_ok})
    print(f"  [{'PASS' if keys_ok and health_ok else 'FAIL'}] 默认安全结果: hs={r['health_score']}, status={r['status']}")

    r2 = _safe_result(msg="测试错误", health=80)
    custom_ok = r2["health_score"] == 80 and r2["_error"] == "测试错误"
    results.append({"test": "safe_result_custom", "passed": custom_ok})
    print(f"  [{'PASS' if custom_ok else 'FAIL'}] 自定义安全结果: hs={r2['health_score']}, msg={r2['_error']}")

    return results


def main():
    print("=" * 60)
    print("Layer 5: analyzer.py — 辅助函数测试")
    print("=" * 60)

    all_results = {
        "calibrate": test_calibrate_probabilities(),
        "safe_result": test_safe_result(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "analyzer_helpers.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
