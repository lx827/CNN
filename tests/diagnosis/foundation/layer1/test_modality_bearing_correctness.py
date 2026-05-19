"""
Layer 1 信号基元 — modality_bearing 正确性验证

测试 emd_bearing_analysis / ceemdan_bearing_analysis / vmd_bearing_analysis

输出: layer1/output/modality_bearing.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.modality_bearing import (
    emd_bearing_analysis, ceemdan_bearing_analysis, vmd_bearing_analysis,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def _make_bearing_signal(rot_f=25.0, bpfo=90.0, duration=1.0):
    """构造含 BPFO 冲击的合成轴承信号"""
    t = np.arange(0, duration, 1.0 / FS)
    sig = np.zeros_like(t)
    n_impulses = int(duration * bpfo)
    for i in range(n_impulses):
        idx = int(i / bpfo * FS)
        if idx < len(sig) - 5:
            sig[idx:idx+3] += [1.0, 0.5, 0.3]
    # 加共振载波
    sig += 0.3 * np.sin(2 * np.pi * 3000 * t) * (sig > 0.1)
    sig += np.random.randn(len(t)) * 0.1
    return sig


def test_emd_bearing():
    """emd_bearing_analysis: 返回结构与包络谱"""
    print("\n--- emd_bearing_analysis ---")
    results = []

    sig = _make_bearing_signal(duration=0.5)
    res = emd_bearing_analysis(sig, FS, max_imfs=5, max_sifts=20, top_n=1)

    has_env = len(res.get("envelope_freq", [])) > 0 and len(res.get("envelope_amp", [])) > 0
    has_method = res.get("method") == "EMD Sensitive IMF Envelope"
    n_imfs = res.get("n_imfs", 0)
    results.append({
        "test": "emd_bearing_structure",
        "has_env": has_env, "method": res.get("method"), "n_imfs": n_imfs,
        "passed": has_env and has_method and n_imfs > 0,
    })
    print(f"  [{'PASS' if has_env and has_method and n_imfs > 0 else 'FAIL'}] EMD结构: env={has_env}, n_imfs={n_imfs}")

    return results


def test_ceemdan_bearing():
    """ceemdan_bearing_analysis: CEEMDAN 版本"""
    print("\n--- ceemdan_bearing_analysis ---")
    results = []

    sig = _make_bearing_signal(duration=0.5)
    res = ceemdan_bearing_analysis(sig, FS, max_imfs=5, ensemble_size=10, top_n=1)

    has_env = len(res.get("envelope_freq", [])) > 0
    has_method = res.get("method") == "CEEMDAN Sensitive IMF Envelope"
    results.append({
        "test": "ceemdan_bearing_structure",
        "has_env": has_env, "method": res.get("method"),
        "passed": has_env and has_method,
    })
    print(f"  [{'PASS' if has_env and has_method else 'FAIL'}] CEEMDAN结构: env={has_env}")

    return results


def test_vmd_bearing():
    """vmd_bearing_analysis: VMD 版本"""
    print("\n--- vmd_bearing_analysis ---")
    results = []

    sig = _make_bearing_signal(duration=0.5)
    res = vmd_bearing_analysis(sig, FS, K=3, alpha=2000, top_n=1)

    has_env = len(res.get("envelope_freq", [])) > 0
    has_method = res.get("method") == "VMD Sensitive Mode Envelope"
    has_modes = len(res.get("mode_center_freqs", [])) > 0
    results.append({
        "test": "vmd_bearing_structure",
        "has_env": has_env, "has_modes": has_modes, "method": res.get("method"),
        "passed": has_env and has_method and has_modes,
    })
    print(f"  [{'PASS' if has_env and has_method and has_modes else 'FAIL'}] VMD结构: env={has_env}, modes={has_modes}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: modality_bearing — 模态分解轴承诊断正确性")
    print("=" * 60)

    all_results = {
        "emd": test_emd_bearing(),
        "ceemdan": test_ceemdan_bearing(),
        "vmd": test_vmd_bearing(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "modality_bearing.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
