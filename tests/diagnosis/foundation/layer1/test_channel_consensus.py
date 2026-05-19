"""
Layer 1 信号基元 — channel_consensus 正确性验证

测试 cross_channel_consensus — 多通道一致性投票

输出: layer1/output/channel_consensus.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.channel_consensus import cross_channel_consensus
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def _make_ch_result(faults=None):
    """构造单个通道的诊断结果"""
    r = {"bearing": {"fault_indicators": {}}, "gear": {"fault_indicators": {}},
         "ensemble": {"has_gear_params": False}, "time_features": {"kurtosis": 3.0}}
    if faults:
        for name in faults:
            r["bearing"]["fault_indicators"][name] = {"significant": True}
    return r


def test_consensus():
    """跨通道一致性投票"""
    print("\n--- cross_channel_consensus ---")
    results = []

    # 3通道全部检出BPFO → 应形成一致
    chs = [_make_ch_result(["BPFO"]), _make_ch_result(["BPFO"]), _make_ch_result(["BPFO"])]
    c = cross_channel_consensus(chs, min_channels_for_consensus=2)
    has_consensus = c["consensus_fault_label"] == "轴承外圈故障"
    boost_ok = c["consensus_boost"] > 1.0
    results.append({
        "test": "3ch_all_BPFO", "label": c["consensus_fault_label"],
        "boost": round(c["consensus_boost"], 3), "passed": has_consensus and boost_ok,
    })
    print(f"  [{'PASS' if has_consensus and boost_ok else 'FAIL'}] 3通道全BPFO: label={c['consensus_fault_label']}, boost={c['consensus_boost']:.2f}")

    # 仅1通道检出 → 无一致性
    chs = [_make_ch_result(["BPFO"]), _make_ch_result([]), _make_ch_result([])]
    c = cross_channel_consensus(chs, min_channels_for_consensus=2)
    no_consensus = c["consensus_fault_label"] == "unknown"
    has_single = len(c["single_channel_faults"]) > 0
    results.append({
        "test": "1ch_only_BPFO", "label": c["consensus_fault_label"],
        "single_channels": len(c["single_channel_faults"]), "passed": no_consensus and has_single,
    })
    print(f"  [{'PASS' if no_consensus and has_single else 'FAIL'}] 仅1通道BPFO: label={c['consensus_fault_label']}")

    # 空输入
    c = cross_channel_consensus([])
    empty_ok = c["consensus_fault_label"] == "unknown"
    results.append({"test": "empty_input", "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空输入: {c['consensus_fault_label']}")

    # 混合故障类型
    chs = [_make_ch_result(["BPFO"]), _make_ch_result(["BPFI"]), _make_ch_result(["BSF"])]
    c = cross_channel_consensus(chs, min_channels_for_consensus=2)
    mixed_ok = c["consensus_fault_label"] == "unknown"
    results.append({
        "test": "mixed_fault_types", "label": c["consensus_fault_label"],
        "single_count": len(c["single_channel_faults"]), "passed": mixed_ok,
    })
    print(f"  [{'PASS' if mixed_ok else 'FAIL'}] 混合故障: label={c['consensus_fault_label']}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: channel_consensus — 通道一致性投票")
    print("=" * 60)

    all_results = {"consensus": test_consensus()}
    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "channel_consensus.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
