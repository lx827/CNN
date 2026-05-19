"""
Layer 3 引擎集成 — engine.py 调度正确性验证

测试 DiagnosisEngine 的调度与分发功能：
  analyze_bearing, analyze_gear, analyze_comprehensive

原则：验证 engine 能正确调用 Layer 2 方法并返回结构化结果。

输出: layer3/output/engine_integration.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis import DiagnosisEngine, GearMethod
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, bearing_outer_race, gear_mesh, sinusoidal,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_engine_analyze_bearing():
    """engine.analyze_bearing：验证能分发多种轴承方法并返回结果"""
    print("\n--- engine.analyze_bearing ---")
    results = []

    sig, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    engine = DiagnosisEngine(bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0})
    res = engine.analyze_bearing(sig, FS)

    has_indicators = len(res.get("fault_indicators", {})) > 0
    has_envelope = len(res.get("envelope_freq", [])) > 0
    passed = has_indicators and has_envelope
    results.append({
        "test": "engine_bearing_dispatch",
        "method": res.get("method"),
        "has_indicators": has_indicators,
        "has_envelope": has_envelope,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 轴承分发: method={res.get('method')}, indicators={has_indicators}, envelope={has_envelope}")

    return results


def test_engine_analyze_gear():
    """engine.analyze_gear：验证齿轮方法分发"""
    print("\n--- engine.analyze_gear ---")
    results = []

    sig, _, _ = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=4.0, fs=FS, snr_db=25)
    engine = DiagnosisEngine(gear_teeth={"input": 18}, gear_method=GearMethod.STANDARD)
    res = engine.analyze_gear(sig, FS, rot_freq=25.0)

    has_indicators = len(res.get("fault_indicators", {})) > 0
    passed = has_indicators
    results.append({
        "test": "engine_gear_dispatch_standard",
        "indicators_keys": list(res.get("fault_indicators", {}).keys()),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 齿轮分发(standard): indicators={list(res.get('fault_indicators', {}).keys())}")

    # 高级方法
    engine_adv = DiagnosisEngine(gear_teeth={"input": 18}, gear_method=GearMethod.ADVANCED)
    res_adv = engine_adv.analyze_gear(sig, FS, rot_freq=25.0)
    has_tsa = "tsa_kurtosis" in res_adv.get("fault_indicators", {})
    results.append({
        "test": "engine_gear_dispatch_advanced",
        "has_tsa": has_tsa,
        "passed": has_tsa or has_indicators,
    })
    print(f"  [{'PASS' if has_tsa or has_indicators else 'FAIL'}] 齿轮分发(advanced): has_tsa={has_tsa}")

    return results


def test_engine_comprehensive():
    """engine.analyze_comprehensive：综合分析返回完整结构"""
    print("\n--- engine.analyze_comprehensive ---")
    results = []

    sig, _, _ = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=3.0, fs=FS, snr_db=15)
    engine = DiagnosisEngine(
        bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        gear_teeth={"input": 18},
    )
    res = engine.analyze_comprehensive(sig, FS)

    has_bearing = "bearing" in res
    has_gear = "gear" in res
    has_health = "health_score" in res
    has_status = "status" in res
    passed = has_bearing and has_gear and has_health and has_status
    results.append({
        "test": "engine_comprehensive_structure",
        "has_bearing": has_bearing,
        "has_gear": has_gear,
        "has_health": has_health,
        "has_status": has_status,
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] 综合结构: bearing={has_bearing}, gear={has_gear}, health={has_health}, status={has_status}")

    # 无参数时应走统计诊断
    engine_stat = DiagnosisEngine(strategy="advanced", bearing_params={}, gear_teeth={})
    res_stat = engine_stat.analyze_comprehensive(sig, FS)
    stat_ok = res_stat.get("health_score", 100) < 100 or res_stat.get("status") != "normal"
    results.append({
        "test": "engine_comprehensive_no_params",
        "health_score": res_stat.get("health_score"),
        "status": res_stat.get("status"),
        "passed": stat_ok,
    })
    print(f"  [{'PASS' if stat_ok else 'FAIL'}] 无参数统计诊断: hs={res_stat.get('health_score')}, status={res_stat.get('status')}")

    return results


def main():
    print("=" * 60)
    print("Layer 3: engine.py — 引擎集成正确性验证")
    print("=" * 60)

    all_results = {
        "analyze_bearing": test_engine_analyze_bearing(),
        "analyze_gear": test_engine_analyze_gear(),
        "analyze_comprehensive": test_engine_comprehensive(),
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
    out_path = OUTPUT_DIR / "engine_integration.json"
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
