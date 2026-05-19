"""
Layer 1 信号基元 — bearing_cyclostationary 正确性验证

测试 _compute_sc_scoh_bearing / bearing_sc_scoh_analysis

输出: layer1/output/bearing_cyclostationary.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.bearing_cyclostationary import (
    _compute_sc_scoh_bearing, bearing_sc_scoh_analysis,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_sc_scoh_structure():
    """_compute_sc_scoh_bearing: 返回结构"""
    print("\n--- _compute_sc_scoh_bearing ---")
    results = []

    # 构造含循环平稳特征的信号（周期冲击）
    t = np.arange(0, 2.0, 1.0 / FS)
    bpfo = 90.0
    rot_f = 25.0
    sig = np.zeros_like(t)
    for i in range(int(2.0 * bpfo)):
        idx = int(i / bpfo * FS)
        if idx < len(sig) - 10:
            sig[idx:idx+5] += 1.0
    sig += np.random.randn(len(t)) * 0.2

    f_axis, alpha_axis, scoh = _compute_sc_scoh_bearing(sig, FS, seg_len=1024)

    shape_ok = len(f_axis) > 0 and len(alpha_axis) > 0 and scoh.shape[0] == len(alpha_axis)
    results.append({
        "test": "sc_scoh_shape",
        "f_len": len(f_axis), "alpha_len": len(alpha_axis), "scoh_shape": list(scoh.shape),
        "passed": shape_ok,
    })
    print(f"  [{'PASS' if shape_ok else 'FAIL'}] 形状: f={len(f_axis)}, alpha={len(alpha_axis)}, scoh={scoh.shape}")

    # SCoh 值应在 [0, 1] 范围
    val_ok = np.min(scoh) >= 0 and np.max(scoh) <= 1.0 + 1e-6
    results.append({
        "test": "sc_scoh_range",
        "min": round(float(np.min(scoh)), 4), "max": round(float(np.max(scoh)), 4),
        "passed": val_ok,
    })
    print(f"  [{'PASS' if val_ok else 'FAIL'}] 值域: [{np.min(scoh):.3f}, {np.max(scoh):.3f}]")

    return results


def test_bearing_sc_scoh_analysis():
    """bearing_sc_scoh_analysis: 轴承故障循环频率搜索"""
    print("\n--- bearing_sc_scoh_analysis ---")
    results = []

    t = np.arange(0, 2.0, 1.0 / FS)
    rot_f = 25.0
    bpfo = 3.57 * rot_f  # ~89.25 Hz
    sig = np.zeros_like(t)
    for i in range(int(2.0 * bpfo)):
        idx = int(i / bpfo * FS)
        if idx < len(sig) - 10:
            sig[idx:idx+5] += 1.0
    sig += np.random.randn(len(t)) * 0.3

    bearing_params = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
    res = bearing_sc_scoh_analysis(sig, FS, bearing_params=bearing_params, rot_freq=rot_f, seg_len=1024)

    has_method = res.get("method") == "bearing_sc_scoh"
    has_indicators = len(res.get("fault_indicators", {})) > 0
    results.append({
        "test": "sc_scoh_analysis_structure",
        "method": res.get("method"),
        "n_indicators": len(res.get("fault_indicators", {})),
        "passed": has_method and has_indicators,
    })
    print(f"  [{'PASS' if has_method and has_indicators else 'FAIL'}] 结构: method={res.get('method')}, indicators={len(res.get('fault_indicators', {}))}")

    # 最大 SCoh 值应在合理范围
    sc_max = res.get("sc_max_value", 0)
    sc_ok = 0 <= sc_max <= 1.0
    results.append({"test": "sc_max_value", "sc_max": round(sc_max, 4), "passed": sc_ok})
    print(f"  [{'PASS' if sc_ok else 'FAIL'}] SC最大值: {sc_max:.4f}")

    return results


def test_sc_scoh_empty():
    """空输入安全处理"""
    print("\n--- SC/SCoh 边界 ---")
    results = []

    f_axis, alpha_axis, scoh = _compute_sc_scoh_bearing(np.array([]), FS)
    # 空信号时仍返回基于 seg_len 的轴，但 scoh 应全为 0
    empty_ok = len(f_axis) > 0 and np.all(scoh == 0)
    results.append({"test": "sc_scoh_empty", "scoh_all_zero": bool(np.all(scoh == 0)), "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空信号: scoh全零={np.all(scoh == 0)}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: bearing_cyclostationary — 循环平稳正确性")
    print("=" * 60)

    all_results = {
        "structure": test_sc_scoh_structure(),
        "analysis": test_bearing_sc_scoh_analysis(),
        "empty": test_sc_scoh_empty(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "bearing_cyclostationary.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
