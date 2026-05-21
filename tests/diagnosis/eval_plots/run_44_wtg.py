"""
4.4 齿轮诊断评估 (WTgearbox) — 独立可并行
输出: 44_wtg_binary.json, 44_wtg_multiclass.json
"""
import sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _eval_utils import *

# ═══ 4.4.1 二分类 ═══
def run_binary():
    print(f"\n{'='*60}\n4.4.1 WTgearbox 齿轮二分类\n{'='*60}")
    files_h = sorted(f.name for f in WTG_DIR.glob("He_*-c1.npy"))
    files_f = sorted(f.name for f in WTG_DIR.glob("*.npy") if "-c1.npy" in f.name and not f.name.startswith("He"))
    files = [(WTG_DIR / f, True) for f in files_h] + [(WTG_DIR / f, False) for f in files_f]
    print(f"  健康:{len(files_h)} 故障:{len(files_f)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(files_h), "fault": len(files_f), "methods": {}}
    for name_cn, method in [("标准边频分析", GearMethod.STANDARD), ("高级综合", GearMethod.ADVANCED)]:
        t0 = time.perf_counter()
        correct, total_t, times = 0, 0, []
        for fpath, is_h in files:
            sig = load_sig(fpath)
            if sig is None: continue
            try:
                rf = float(fpath.name.split("_")[-1].replace("-c1.npy", ""))
            except ValueError:
                rf = 30.0
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(gear_method=method, gear_teeth=GP, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_gear(sig, FS, rot_freq=rf)
                times.append((time.perf_counter() - t1) * 1000)
                if gear_detect(res, is_h): correct += 1
                total_t += 1
            except Exception: pass
        acc = correct / max(total_t, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) {avg_ms}ms")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct, "total": total_t, "avg_time_ms": avg_ms}

    # Ensemble gear
    t0 = time.perf_counter()
    correct, total_t, times = 0, 0, []
    for fpath, is_h in files:
        sig = load_sig(fpath)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, gear_teeth=GP, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            if ensemble_detect(res, is_h): correct += 1
            total_t += 1
        except Exception: pass
    acc = correct / max(total_t, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.2f}% ({correct}/{total_t}) {avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct, "total": total_t, "avg_time_ms": avg_ms}
    save_json(results, "44_wtg_binary.json")
    return results

# ═══ 4.4.3 五分类 ═══
def run_multiclass():
    print(f"\n{'='*60}\n4.4.3 WTgearbox 五分类 (Ensemble)\n{'='*60}")
    class_map = {"He": "健康", "Br": "断齿", "Mi": "缺齿", "Rc": "裂纹", "We": "磨损"}
    files = [(f, class_map[fault_wtg(f.name)]) for f in sorted(WTG_DIR.glob("*_*-c1.npy")) if fault_wtg(f.name) in class_map]

    y_true, y_pred, times = [], [], []
    for fpath, label in files:
        sig = load_sig(fpath)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BP, gear_teeth=GP, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            fl = res.get("fault_label", "unknown")
            pred = map_fault_label_gear(fl)
            y_true.append(label); y_pred.append(pred)
        except Exception: pass

    classes = list(class_map.values())
    metrics = compute_metrics(y_true, y_pred, classes)
    cm = compute_cm(y_true, y_pred, classes)
    print(f"  Acc={metrics['accuracy']:.2%} BalAcc={metrics['balanced_accuracy']:.2%} F1={metrics['macro_f1']:.3f} ({len(y_true)} samples)")

    result = {"dataset": "WTgearbox", "type": "5-class", **metrics,
              "confusion_matrix": cm, "classes": classes, "avg_time_ms": round(np.mean(times)) if times else 0}
    save_json(result, "44_wtg_multiclass.json")
    return result

if __name__ == "__main__":
    run_binary()
    run_multiclass()
