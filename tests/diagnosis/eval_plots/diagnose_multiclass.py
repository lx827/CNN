"""
Ensemble 五分类偏向 BPFO 问题诊断脚本

用法:
    cd d:/code/CNN/cloud
    . venv/Scripts/activate
    python ../tests/diagnosis/eval_plots/diagnose_multiclass.py

输出: 每个样本的 fault_label / param_hits / BPFO/BPFI/BSF SNR / 预测类别
"""
import sys, json, warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.ensemble import run_research_ensemble

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FS = 8192
MAX_S = 5
MAX_PTS = FS * MAX_S

HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}


def load_npy(dir_path, fname):
    fp = Path(dir_path) / fname
    if not fp.exists():
        return None
    return np.load(fp).astype(np.float64)[:MAX_PTS]


def _fault_code(fname):
    stem = fname.replace(".npy", "").rsplit("-", 1)[0]
    parts = stem.split("_")
    for p in parts:
        if p in ("H", "N"):
            return "H"
        if p == "B":
            return "B"
        if p in ("I", "IR"):
            return "I"
        if p in ("O", "OR"):
            return "O"
        if p == "C":
            return "C"
    return None


def _map_label_buggy(fl):
    """run_all.py 中的原始映射逻辑（含 bug）"""
    fl = str(fl).lower()
    if "bpfo" in fl or "outer" in fl:
        return "外圈(映射)"
    elif "bpfi" in fl or "inner" in fl:
        return "内圈(映射)"
    elif "bsf" in fl or "ball" in fl:
        return "球故障(映射)"
    elif "compound" in fl or "bpfo_bpfi" in fl:
        return "复合(映射)"
    elif "healthy" in fl or "normal" in fl or "unknown" in fl:
        return "健康(映射)"
    elif "abnormal" in fl:
        return "复合(映射)"
    return "健康(映射)"


def _map_label_fixed(fl):
    """修复后的映射逻辑：精确匹配，避免子串误判"""
    fl = str(fl).lower()
    if fl == "bearing_bpfo" or "outer" in fl:
        return "外圈(修复)"
    if fl == "bearing_bpfi" or "inner" in fl:
        return "内圈(修复)"
    if fl == "bearing_bsf" or "ball" in fl:
        return "球故障(修复)"
    if "bpfo_bpfi" in fl or "compound" in fl or fl == "bearing_bpfo_bsf" or fl == "bearing_bpfi_bsf":
        return "复合(修复)"
    if "healthy" in fl or "normal" in fl or "unknown" in fl:
        return "健康(修复)"
    if "abnormal" in fl:
        return "复合(修复)"
    return "健康(修复)"


def diagnose():
    classes = {"H": "健康", "B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}
    class_files = {k: [] for k in classes}
    for f in sorted(HUSTBEAR_DIR.glob("*-X.npy")):
        fc = _fault_code(f.name)
        if fc in class_files:
            class_files[fc].append(f.name)

    # 每类最多取 6 个（与 run_all.py 保持一致）
    for k in class_files:
        class_files[k] = class_files[k][:6]

    records = []
    total = sum(len(v) for v in class_files.values())
    processed = 0

    for cls_code, cls_name in classes.items():
        for fname in class_files[cls_code]:
            sig = load_npy(HUSTBEAR_DIR, fname)
            if sig is None:
                continue
            try:
                res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
            except Exception as e:
                records.append({
                    "file": fname, "true": cls_name, "error": str(e)
                })
                continue

            fl = res.get("fault_label", "unknown")
            pred_buggy = _map_label_buggy(fl)
            pred_fixed = _map_label_fixed(fl)

            # 提取 best_bearing 的 indicators
            best_bearing = res.get("bearing", {})
            indicators = best_bearing.get("fault_indicators", {})
            param_hits = [
                name for name, item in indicators.items()
                if isinstance(item, dict) and item.get("significant") and not name.endswith("_stat")
            ]

            # 提取 BPFO/BPFI/BSF 的 SNR
            snrs = {}
            for k in ("BPFO", "BPFI", "BSF"):
                v = indicators.get(k, {})
                if isinstance(v, dict):
                    snrs[k] = {
                        "snr": v.get("snr"),
                        "significant": v.get("significant"),
                        "theory_hz": v.get("theory_hz"),
                        "detected_hz": v.get("detected_hz"),
                    }

            record = {
                "file": fname,
                "true": cls_name,
                "fault_label_raw": fl,
                "param_hits": param_hits,
                "pred_buggy": pred_buggy,
                "pred_fixed": pred_fixed,
                "snrs": snrs,
                "health_score": res.get("health_score"),
                "status": res.get("status"),
            }
            records.append(record)
            processed += 1
            if processed % 5 == 0:
                print(f"  已处理 {processed}/{total}")

    # ── 汇总分析 ──
    print("\n" + "=" * 70)
    print("【诊断结果汇总】")
    print("=" * 70)

    # 1. 标签映射子串匹配 bug 统计
    buggy_mismatch = [r for r in records if r.get("true") and r.get("pred_buggy") and r["true"] not in r["pred_buggy"]]
    fixed_mismatch = [r for r in records if r.get("true") and r.get("pred_fixed") and r["true"] not in r["pred_fixed"]]

    print(f"\n1. 原始映射(buggy) 误判数: {len(buggy_mismatch)} / {len(records)}")
    print(f"   修复映射(fixed) 误判数: {len(fixed_mismatch)} / {len(records)}")

    # 2. 分析标签映射 bug 的贡献
    print("\n2. 【标签映射子串匹配 Bug】")
    print("   问题: 'bpfo' in 'bearing_bpfo_bpfi' → True，复合故障被误判为外圈")
    bpfo_in_multi = [r for r in records
                     if "bpfo" in r.get("fault_label_raw", "").lower()
                     and "bpfi" in r.get("fault_label_raw", "").lower()]
    for r in bpfo_in_multi:
        print(f"   {r['file']}: true={r['true']} label={r['fault_label_raw']} → buggy={r['pred_buggy']} fixed={r['pred_fixed']}")

    # 3. 各类别 param_hits 分布
    print("\n3. 【param_hits 分布（各类别）】")
    for cls_code in ("H", "B", "I", "O", "C"):
        cls_name = classes[cls_code]
        subset = [r for r in records if r.get("true") == cls_name]
        if not subset:
            continue
        hits_list = [tuple(r.get("param_hits", [])) for r in subset]
        from collections import Counter
        cnt = Counter(hits_list)
        print(f"   {cls_name} (n={len(subset)}):")
        for hits, c in cnt.most_common():
            print(f"      {hits}: {c} 次")

    # 4. BPFO/BPFI/BSF SNR 统计
    print("\n4. 【物理参数路径 SNR 统计】")
    for cls_code in ("H", "B", "I", "O", "C"):
        cls_name = classes[cls_code]
        subset = [r for r in records if r.get("true") == cls_name]
        if not subset:
            continue
        print(f"   {cls_name} (n={len(subset)}):")
        for param in ("BPFO", "BPFI", "BSF"):
            vals = [r["snrs"][param]["snr"] for r in subset if param in r.get("snrs", {}) and r["snrs"][param]["snr"] is not None]
            sigs = [r["snrs"][param]["significant"] for r in subset if param in r.get("snrs", {}) and r["snrs"][param]["significant"] is not None]
            if vals:
                print(f"      {param}: SNR={np.mean(vals):.1f}±{np.std(vals):.1f} (max={np.max(vals):.1f}) significant={sum(sigs)}/{len(sigs)}")

    # 5. D-S 融合标签覆盖
    print("\n5. 【D-S 融合标签覆盖】")
    ds_overrides = [r for r in records if r.get("fault_label_raw") and "ds_" in str(r["fault_label_raw"]).lower()]
    print(f"   D-S 融合覆盖样本数: {len(ds_overrides)}")

    # 保存完整记录
    out_path = OUTPUT_DIR / "diagnose_multiclass.json"
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细记录已保存: {out_path}")


if __name__ == "__main__":
    diagnose()
