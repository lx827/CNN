"""
轴承故障特征频率计算 — 正确性验证

使用已知轴承参数计算 BPFO/BPFI/BSF/FTF，
与手动计算的理论值对比。

输出: output/bearing_fault_freqs.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from app.services.diagnosis.features import _compute_bearing_fault_freqs
from tests.diagnosis.foundation.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"

# ── ER-16K (HUSTbear / CW) ──
ER16K = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}

# ── NSK 6202 (HUSTgearbox 主动轮轴承) ──
# Bore=15mm, Outer=35mm → pitch ≈ (15+35)/2 = 25mm, 8 balls, ball dia ≈ 7.94mm
NSK6202 = {"n": 8, "d": 7.94, "D": 25.0, "alpha": 0}

# ── 手动计算的理论值（公式来自文献） ──
def theoretical_freqs(params, rot_freq):
    n, d, D = params["n"], params["d"], params["D"]
    alpha = np.radians(params.get("alpha", 0))
    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a
    return {
        "BPFO": round((n / 2.0) * rot_freq * (1 - dd), 6),
        "BPFI": round((n / 2.0) * rot_freq * (1 + dd), 6),
        "BSF":  round((D / (2.0 * d)) * rot_freq * (1 - dd**2), 6),
        "FTF":  round(0.5 * rot_freq * (1 - dd), 6),
    }


def test_bearing_fault_freqs():
    results = {"test_cases": [], "summary": {}}

    test_cases = [
        ("ER-16K @ 25Hz", ER16K, 25.0),
        ("ER-16K @ 50Hz", ER16K, 50.0),
        ("ER-16K @ 10Hz", ER16K, 10.0),
        ("NSK 6202 @ 25Hz", NSK6202, 25.0),
    ]

    all_errors = []
    for name, params, rot_freq in test_cases:
        computed = _compute_bearing_fault_freqs(rot_freq, params)
        expected = theoretical_freqs(params, rot_freq)

        errors = {}
        for key in ["BPFO", "BPFI", "BSF", "FTF"]:
            c = computed.get(key, 0)
            e = expected.get(key, 0)
            err_abs = abs(c - e)
            err_rel = err_abs / e if e > 0 else 0
            errors[key] = {"computed": round(c, 6), "expected": e, "abs_error": round(err_abs, 8), "rel_error": round(err_rel, 8)}
            all_errors.append(err_rel)

        results["test_cases"].append({
            "name": name,
            "params": params,
            "rot_freq": rot_freq,
            "errors": errors,
            "passed": all(v["rel_error"] < 0.001 for v in errors.values()),
        })
        status = "PASS" if results["test_cases"][-1]["passed"] else "FAIL"
        print(f"  [{status}] {name}: max rel error = {max(v['rel_error'] for v in errors.values()):.2e}")

    results["summary"] = {
        "total": len(test_cases),
        "passed": sum(1 for tc in results["test_cases"] if tc["passed"]),
        "max_rel_error": max(all_errors),
        "mean_rel_error": np.mean(all_errors),
    }
    return results


def main():
    print("=" * 60)
    print("轴承故障特征频率计算 — 正确性验证")
    print("=" * 60)

    results = test_bearing_fault_freqs()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "bearing_fault_freqs.json"
    out_path.write_text(json.dumps(results, indent=2, cls=NumpyEncoder))
    print(f"\n结果已保存: {out_path}")

    s = results["summary"]
    print(f"\n总计: {s['total']}, 通过: {s['passed']}, 最大相对误差: {s['max_rel_error']:.2e}")
    assert s["passed"] == s["total"], f"{s['total']-s['passed']} 个测试失败"
    print("全部通过!")


if __name__ == "__main__":
    main()
