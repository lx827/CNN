"""边端诊断 POC 的参照/边端 JSON 对比脚本。

用法: uv run python scripts/edge_diag_compare.py <ref.json> <edge.json>

逐字段比较 metrics 五个标量、speed_hz 标量与 spectrum/envelope_spectrum 数组,
以及二期新增的六个标量(wavelet.residual_rms/denoised_rms、kurtogram 三项、
vmd.n_input)与四个数组(cepstrum、vmd.mode_energy_ratio、order_spectrum、tsa),
容差 rtol=1e-6、atol=1e-8(元素判据 |ref-edge| <= atol + rtol*|ref|);
输出每字段 max 绝对/相对偏差与总结 PASS/FAIL,任一字段 FAIL 时退出码 1。

- 双方均为 null 的字段跳过(某一侧无对应入口时按 null 对齐,参照脚本 docstring
  记录差异);单侧 null 判 FAIL。
- 数组长度不一致直接 FAIL 并报两侧长度,不做逐元素比较。
- input 块与双方额外字段(边端 timings_ms/peak_rss_kb)不参与比较。
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

RTOL = 1e-6  # 与 edge-diag POC 验收一致
ATOL = 1e-8

SCALAR_FIELDS = (
    "metrics.rms",
    "metrics.peak",
    "metrics.crest",
    "metrics.kurtosis",
    "metrics.skewness",
    "speed_hz",
    "wavelet.residual_rms",
    "wavelet.denoised_rms",
    "kurtogram.best_low_hz",
    "kurtogram.best_high_hz",
    "kurtogram.max_kurtosis",
    "vmd.n_input",
)
ARRAY_FIELDS = (
    "spectrum",
    "envelope_spectrum",
    "cepstrum",
    "vmd.mode_energy_ratio",
    "order_spectrum",
    "tsa",
)


def load_field(document: dict, name: str):
    """按 'a.b' 或 'a' 取字段;缺失视为 null。"""
    if "." in name:
        section, key = name.split(".", 1)
        return document.get(section, {}).get(key)
    return document.get(name)


def compare_scalar(name: str, ref, edge):
    """返回 (max_abs, max_rel, 通过, 说明);双方 null 返回 None 表示跳过。"""
    if ref is None and edge is None:
        return None
    if ref is None or edge is None:
        return (None, None, False, "单侧为 null")
    diff = abs(ref - edge)
    rel = diff / abs(ref) if ref else (0.0 if diff == 0 else math.inf)
    return (diff, rel, diff <= ATOL + RTOL * abs(ref), "")


def compare_array(name: str, ref, edge):
    """返回 (max_abs, max_rel, 通过, 说明);双方 null 返回 None 表示跳过。"""
    if ref is None and edge is None:
        return None
    if ref is None or edge is None:
        return (None, None, False, "单侧为 null")
    if len(ref) != len(edge):
        return (None, None, False, f"长度不一致 ref={len(ref)} edge={len(edge)}")
    a = np.asarray(ref, dtype=np.float64)
    b = np.asarray(edge, dtype=np.float64)
    diff = np.abs(a - b)
    denominator = np.where(np.abs(a) > 0, np.abs(a), np.inf)
    return (
        float(diff.max()),
        float((diff / denominator).max()),
        bool(np.all(diff <= ATOL + RTOL * np.abs(a))),
        "",
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("用法: uv run python scripts/edge_diag_compare.py <ref.json> <edge.json>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as stream:
        ref = json.load(stream)
    with open(argv[2], encoding="utf-8") as stream:
        edge = json.load(stream)

    rows = []
    for name in SCALAR_FIELDS:
        rows.append((name, compare_scalar(name, load_field(ref, name), load_field(edge, name))))
    for name in ARRAY_FIELDS:
        rows.append((name, compare_array(name, load_field(ref, name), load_field(edge, name))))

    failed = False
    for name, result in rows:
        if result is None:
            print(f"{name:20s} SKIP  双方均为 null")
            continue
        max_abs, max_rel, ok, note = result
        verdict = "PASS" if ok else "FAIL"
        failed |= not ok
        detail = f"max_abs={max_abs:.3e} max_rel={max_rel:.3e}" if note == "" else note
        print(f"{name:20s} {verdict}  {detail}")
    print(f"总结: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
