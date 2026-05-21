"""
4.3 变速轴承评估 (CW/Ottawa) — 独立可并行
输出: 43_cw_binary.json, 43_cw_multiclass.json
"""
import sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _eval_utils import *

# ═══ 4.3.1 二分类 ═══
def run_binary():
    print(f"\n{'='*60}\n4.3.1 CW/Ottawa 轴承二分类\n{'='*60}")
    files = []
    healthy = []
    for f in sorted(CW_DIR.glob("*.npy")):
        fc = fault_cw(f.name)
        if fc == "H":
            files.append((f, True, "健康")); healthy.append(f)
        elif fc in ("I", "O"):
            files.append((f, False, "内圈" if fc == "I" else "外圈"))
    print(f"  健康:{len(healthy)} 故障:{len(files)-len(healthy)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(healthy), "fault": len(files) - len(healthy), "methods": {}}
    methods = [
        ("MCKD", BearingMethod.MCKD), ("Teager", BearingMethod.TEAGER),
        ("DWT", BearingMethod.DWT), ("MED增强", BearingMethod.MED),
        ("标准包络", BearingMethod.ENVELOPE), ("VMD", BearingMethod.VMD_ENVELOPE),
        ("Kurtogram", BearingMethod.KURTOGRAM), ("CPW预白化", BearingMethod.CPW),
        ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
        ("EMD", BearingMethod.EMD_ENVELOPE),
    ]

    for name_cn, method_val in methods:
        t0 = time.perf_counter()
        correct, total_t, times = 0, 0, []
        for fpath, is_healthy, _label in files:
            sig = load_sig(fpath)
            if sig is None: continue
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(bearing_method=method_val, bearing_params=BP, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig, FS)
                times.append((time.perf_counter() - t1) * 1000)
                if bearing_detect(res, is_healthy): correct += 1
                total_t += 1
            except Exception: pass
        acc = correct / max(total_t, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) {avg_ms}ms")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct, "total": total_t, "avg_time_ms": avg_ms}

    # Ensemble
    t0 = time.perf_counter()
    correct, total_t, times = 0, 0, []
    for fpath, is_healthy, _label in files:
        sig = load_sig(fpath)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BP, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            if ensemble_detect(res, is_healthy): correct += 1
            total_t += 1
        except Exception: pass
    acc = correct / max(total_t, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.2f}% ({correct}/{total_t}) {avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct, "total": total_t, "avg_time_ms": avg_ms}
    save_json(results, "43_cw_binary.json")
    return results

# ═══ 4.3.2 三分类 ═══
def run_multiclass():
    print(f"\n{'='*60}\n4.3.2 CW/Ottawa 三分类 (Ensemble)\n{'='*60}")
    class_map = {"H": "健康", "I": "内圈", "O": "外圈"}
    files = [(f, class_map[fault_cw(f.name)]) for f in sorted(CW_DIR.glob("*.npy")) if fault_cw(f.name) in class_map]

    y_true, y_pred, times = [], [], []
    for fpath, label in files:
        sig = load_sig(fpath)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BP, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            fl = res.get("fault_label", "unknown")
            pred = map_fault_label_cw(fl)
            y_true.append(label); y_pred.append(pred)
        except Exception: pass

    classes = list(class_map.values())
    metrics = compute_metrics(y_true, y_pred, classes)
    cm = compute_cm(y_true, y_pred, classes)
    print(f"  Acc={metrics['accuracy']:.2%} BalAcc={metrics['balanced_accuracy']:.2%} F1={metrics['macro_f1']:.3f}")

    result = {"dataset": "CW", "type": "3-class", **metrics,
              "confusion_matrix": cm, "classes": classes, "avg_time_ms": round(np.mean(times)) if times else 0}
    save_json(result, "43_cw_multiclass.json")
    return result

if __name__ == "__main__":
    run_binary()
    run_multiclass()
