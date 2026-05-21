"""
4.2 恒速轴承评估 (HUSTbear) — 独立可并行
输出: 42_hust_binary.json, 42_hust_multiclass.json

用法:
  d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\run_42_hust.py
"""
import sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _eval_utils import *

# ═══ 4.2.1 二分类 ═══
def run_binary():
    print(f"\n{'='*60}\n4.2.1 HUSTbear 轴承二分类（健康vs故障）\n{'='*60}")
    files = []
    healthy = []
    for f in sorted(HUST_DIR.glob("*-X.npy")):
        fc = fault_hust(f.name)
        if fc == "H":
            files.append((f, True, "健康"))
            healthy.append(f)
        elif fc in ("B", "I", "O", "C"):
            files.append((f, False, {"B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}[fc]))
    print(f"  健康:{len(healthy)} 故障:{len(files)-len(healthy)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(healthy), "fault": len(files) - len(healthy),
               "methods": {}}
    methods = [
        ("VMD", BearingMethod.VMD_ENVELOPE), ("DWT", BearingMethod.DWT),
        ("标准包络", BearingMethod.ENVELOPE), ("EMD", BearingMethod.EMD_ENVELOPE),
        ("MED增强", BearingMethod.MED), ("MCKD", BearingMethod.MCKD),
        ("Teager", BearingMethod.TEAGER), ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
        ("Kurtogram", BearingMethod.KURTOGRAM), ("CPW预白化", BearingMethod.CPW),
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
        total_s = time.perf_counter() - t0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) {avg_ms}ms ({total_s:.0f}s)")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct,
                                        "total": total_t, "avg_time_ms": avg_ms}

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
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total_t, "avg_time_ms": avg_ms}
    save_json(results, "42_hust_binary.json")
    return results

# ═══ 4.2.2 五分类 ═══
def run_multiclass():
    print(f"\n{'='*60}\n4.2.2 HUSTbear 五分类 (Ensemble)\n{'='*60}")
    class_map = {"H": "健康", "B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}
    files = []
    for f in sorted(HUST_DIR.glob("*-X.npy")):
        fc = fault_hust(f.name)
        if fc and fc in class_map:
            files.append((f, class_map[fc]))

    y_true, y_pred = [], []
    times = []
    for fpath, label in files:
        sig = load_sig(fpath)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BP, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            fl = res.get("fault_label", "unknown")
            pred = map_fault_label_bearing(fl)
            y_true.append(label); y_pred.append(pred)
        except Exception: pass

    classes = list(class_map.values())
    metrics = compute_metrics(y_true, y_pred, classes)
    cm = compute_cm(y_true, y_pred, classes)
    print(f"  Acc={metrics['accuracy']:.2%} BalAcc={metrics['balanced_accuracy']:.2%} F1={metrics['macro_f1']:.3f} ({len(y_true)} samples)")

    result = {"dataset": "HUSTbear", "type": "5-class", **metrics,
              "confusion_matrix": cm, "classes": classes, "avg_time_ms": round(np.mean(times)) if times else 0}
    save_json(result, "42_hust_multiclass.json")
    return result

if __name__ == "__main__":
    run_binary()
    run_multiclass()
