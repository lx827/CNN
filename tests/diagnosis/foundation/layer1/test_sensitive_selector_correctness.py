"""
Layer 1 信号基元 — sensitive_selector 正确性验证

测试 score_components / select_top_components /
     select_emd_sensitive_imfs / select_vmd_sensitive_modes

输出: layer1/output/sensitive_selector.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.sensitive_selector import (
    score_components, select_top_components,
    select_emd_sensitive_imfs, select_vmd_sensitive_modes,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_score_components():
    """score_components: 综合评分排序"""
    print("\n--- score_components ---")
    results = []

    t = np.arange(0, 1.0, 1.0 / FS)
    original = np.sin(2 * np.pi * 100 * t) + np.random.randn(len(t)) * 0.1

    np.random.seed(7)
    # 构造 3 个分量：一个含强冲击（高峭度），一个纯噪声，一个低频趋势
    comp1 = np.sin(2 * np.pi * 100 * t)
    # 给 comp1 添加周期性冲击以提高峭度
    for i in range(int(0.5 * 80)):
        idx = int(i / 80 * len(t))
        if idx < len(t) - 3:
            comp1[idx:idx+3] += [2.0, 1.0, 0.5]
    comp2 = np.random.randn(len(t)) * 0.5  # 噪声
    comp3 = np.sin(2 * np.pi * 5 * t) * 0.1  # 低频趋势

    scored = score_components([comp1, comp2, comp3], original, FS, mode="bearing")
    scores = [s["score"] for s in scored]
    highest_idx = scored[np.argmax(scores)]["index"]

    # comp1 与 original 最相关，应得分最高
    best_is_comp1 = highest_idx == 0
    results.append({
        "test": "score_ranking",
        "scores": scores,
        "best_index": highest_idx,
        "passed": best_is_comp1,
    })
    print(f"  [{'PASS' if best_is_comp1 else 'FAIL'}] 评分排序: best_idx={highest_idx}, scores={[round(s, 3) for s in scores]}")

    # 结果包含完整字段
    fields_ok = all("score" in s and "corr" in s and "kurt" in s for s in scored)
    results.append({"test": "score_fields", "passed": fields_ok})
    print(f"  [{'PASS' if fields_ok else 'FAIL'}] 字段完整")

    return results


def test_select_top_components():
    """select_top_components: 选择最高评分分量"""
    print("\n--- select_top_components ---")
    results = []

    scored = [
        {"index": 0, "score": 0.9},
        {"index": 1, "score": 0.5},
        {"index": 2, "score": 0.7},
    ]
    top = select_top_components(scored, top_n=2)
    top_ok = top == [0, 2]
    results.append({"test": "select_top2", "top": top, "passed": top_ok})
    print(f"  [{'PASS' if top_ok else 'FAIL'}] top2: {top}")

    # 低于 min_score 回退
    scored2 = [
        {"index": 0, "score": 0.1},
        {"index": 1, "score": 0.05},
    ]
    top2 = select_top_components(scored2, top_n=1, min_score=0.2)
    fallback_ok = len(top2) == 1  # 回退选最高
    results.append({"test": "select_fallback", "top": top2, "passed": fallback_ok})
    print(f"  [{'PASS' if fallback_ok else 'FAIL'}] 回退: {top2}")

    return results


def test_select_emd_sensitive_imfs():
    """select_emd_sensitive_imfs: EMD IMF 选择"""
    print("\n--- select_emd_sensitive_imfs ---")
    results = []

    # 构造 5 个模拟 IMF
    t = np.arange(0, 0.5, 1.0 / FS)
    imfs = [
        np.random.randn(len(t)) * 0.5,  # IMF0: 高频噪声
        np.sin(2 * np.pi * 500 * t),     # IMF1: 目标频段
        np.sin(2 * np.pi * 200 * t),     # IMF2
        np.sin(2 * np.pi * 50 * t),      # IMF3
        np.sin(2 * np.pi * 5 * t) * 0.1, # IMF4: 低频趋势
    ]
    original = np.sum(imfs, axis=0)

    indices, scored = select_emd_sensitive_imfs(imfs, original, FS, mode="bearing", top_n=2)
    selected_ok = len(indices) > 0 and all(isinstance(i, int) for i in indices)
    results.append({"test": "emd_select", "indices": indices, "passed": selected_ok})
    print(f"  [{'PASS' if selected_ok else 'FAIL'}] EMD选择: indices={indices}")

    return results


def test_select_vmd_sensitive_modes():
    """select_vmd_sensitive_modes: VMD 模态选择"""
    print("\n--- select_vmd_sensitive_modes ---")
    results = []

    t = np.arange(0, 0.5, 1.0 / FS)
    modes = [
        np.sin(2 * np.pi * 300 * t),
        np.sin(2 * np.pi * 150 * t),
        np.sin(2 * np.pi * 50 * t),
    ]
    center_freqs = [300.0, 150.0, 50.0]
    original = np.sum(modes, axis=0)

    indices, scored = select_vmd_sensitive_modes(modes, center_freqs, original, FS, mode="bearing", top_n=2)
    selected_ok = len(indices) > 0 and all(isinstance(i, int) for i in indices)
    results.append({"test": "vmd_select", "indices": indices, "passed": selected_ok})
    print(f"  [{'PASS' if selected_ok else 'FAIL'}] VMD选择: indices={indices}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: sensitive_selector — 敏感分量选择正确性")
    print("=" * 60)

    all_results = {
        "score": test_score_components(),
        "select_top": test_select_top_components(),
        "emd_select": test_select_emd_sensitive_imfs(),
        "vmd_select": test_select_vmd_sensitive_modes(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "sensitive_selector.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
