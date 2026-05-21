"""
综合评估脚本 — 覆盖文档 4.2~4.7 所有实验
生成 JSON 到 tests/output/eval_plots/
用法: d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\run_all.py
"""
import sys, json, time, warnings, os
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FS = 8192
MAX_S = 5
MAX_PTS = FS * MAX_S

HUSTBEAR_DIR = Path(os.environ.get("HUSTBEAR_DIR", r"D:\code\wavelet_study\dataset\HUSTbear\down8192"))
CW_DIR = Path(os.environ.get("CW_DIR", r"D:\code\CNN\CW\down8192_CW"))
WTGEAR_DIR = Path(os.environ.get("WTGEARBOX_DIR", r"D:\code\wavelet_study\dataset\WTgearbox\down8192"))
HUSTGEAR_DIR = Path(os.environ.get("HUSTGEARBOX_DIR", r"D:\code\wavelet_study\dataset\HUSTgearbox\down8192"))

BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GEAR_PARAMS = {"sun": 28, "ring": 100, "planet": 36, "n_planets": 4}
HUSTGEAR_PARAMS = {"input": 18, "output": 27}


def load_npy(dir_path, fname):
    fp = Path(dir_path) / fname
    if not fp.exists():
        return None
    return np.load(fp).astype(np.float64)[:MAX_PTS]


def save_json(data, name):
    p = OUTPUT_DIR / name
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {name}")


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════
def _fault_code_hust(fname):
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


def _fault_code_cw(fname):
    """CW/Ottawa: H=健康, I=内圈, O=外圈"""
    stem = fname.replace(".npy", "")
    if stem.startswith("H-"):
        return "H"
    if stem.startswith("I-"):
        return "I"
    if stem.startswith("O-"):
        return "O"
    return None


def _fault_code_wtg(fname):
    stem = fname.replace(".npy", "").split("-")[0]
    if stem.startswith("He"):
        return "He"
    if stem.startswith("Br"):
        return "Br"
    if stem.startswith("Mi"):
        return "Mi"
    if stem.startswith("Rc"):
        return "Rc"
    if stem.startswith("We"):
        return "We"
    return None


def _bearing_detect(result, is_healthy):
    """判断轴承方法是否检出故障"""
    inds = result.get("fault_indicators", {})
    has_fault = any(
        v.get("significant") for k, v in inds.items()
        if isinstance(v, dict) and not k.endswith("_stat"))
    return has_fault != is_healthy


def _ensemble_detect(result, is_healthy):
    hs = result.get("health_score", 100)
    status = result.get("status", "normal")
    pred_healthy = status == "normal" and hs >= 70
    return pred_healthy == is_healthy


def _gear_detect(result, is_healthy):
    inds = result.get("fault_indicators", {})
    has_warn = any(
        v.get("warning") or v.get("critical")
        for v in inds.values() if isinstance(v, dict))
    return has_warn != is_healthy


def _compute_cm(y_true, y_pred, class_names):
    n = len(class_names)
    cm = [[0] * n for _ in range(n)]
    name_to_idx = {name: i for i, name in enumerate(class_names)}
    for t, p in zip(y_true, y_pred):
        ti = name_to_idx.get(t, 0)
        pi = name_to_idx.get(p, 0)
        cm[ti][pi] += 1
    return cm


def _classification_metrics(y_true, y_pred):
    """计算完整多分类指标"""
    n = len(y_true)
    if n == 0:
        return {}
    classes = sorted(set(y_true))
    n_cls = len(classes)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / n

    # Per-class & macro
    per_class = {}
    macro_prec = macro_rec = macro_f1 = 0.0
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        tn = n - tp - fp - fn
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 0.001)
        spec = tn / max(tn + fp, 1)
        per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4),
                        "f1": round(f1, 4), "specificity": round(spec, 4), "tp": tp}
        macro_prec += prec
        macro_rec += rec
        macro_f1 += f1
    macro_prec /= n_cls
    macro_rec /= n_cls
    macro_f1 /= n_cls
    balanced_acc = macro_rec  # average recall

    # Cohen's Kappa
    pe = sum(
        sum(1 for t in y_true if t == c) * sum(1 for p in y_pred if p == c)
        for c in classes) / (n * n)
    kappa = (accuracy - pe) / max(1 - pe, 0.001)

    # MCC (multi-class)
    cm = _compute_cm(y_true, y_pred, classes)
    cm_np = np.array(cm)
    t_sum = cm_np.sum()
    tp_sum = np.trace(cm_np)
    row_sum = cm_np.sum(axis=1)
    col_sum = cm_np.sum(axis=0)
    cov = tp_sum * t_sum - np.dot(row_sum, col_sum)
    denom = np.sqrt((t_sum**2 - np.dot(col_sum, col_sum)) * (t_sum**2 - np.dot(row_sum, row_sum)))
    mcc = cov / max(denom, 0.001)

    return {
        "accuracy": round(accuracy * 100, 2),
        "balanced_accuracy": round(balanced_acc * 100, 2),
        "macro_f1": round(macro_f1, 4),
        "cohens_kappa": round(kappa, 4),
        "mcc": round(mcc, 4),
        "total": n,
        "per_class": per_class,
    }


# ═══════════════════════════════════════════════════════════
# 4.2.1 HUSTbear 轴承二分类（全部样本）
# ═══════════════════════════════════════════════════════════
def run_42_hust_binary():
    print("\n" + "=" * 60)
    print("4.2.1 HUSTbear 轴承二分类（健康vs故障）")
    print("=" * 60)

    all_files = []
    for f in sorted(HUSTBEAR_DIR.glob("*-X.npy")):
        fc = _fault_code_hust(f.name)
        if fc == "H":
            all_files.append((f.name, True, "健康"))
        elif fc in ("B", "I", "O", "C"):
            all_files.append((f.name, False, {"B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}[fc]))

    healthy = [(f, t, l) for f, t, l in all_files if t]
    fault = [(f, t, l) for f, t, l in all_files if not t]
    files = healthy + fault
    print(f"  健康:{len(healthy)} 故障:{len(fault)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(healthy), "fault": len(fault), "methods": {}}
    # 跳过CEEMDAN（太慢）——用"-"标注
    METHODS = [
        ("标准包络", BearingMethod.ENVELOPE, None),
        ("Kurtogram", BearingMethod.KURTOGRAM, None),
        ("CPW预白化", BearingMethod.CPW, None),
        ("MED增强", BearingMethod.MED, None),
        ("MCKD", BearingMethod.MCKD, None),
        ("Teager", BearingMethod.TEAGER, None),
        ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS, None),
        ("DWT", BearingMethod.DWT, None),
        ("EMD", BearingMethod.EMD_ENVELOPE, None),
        ("VMD", BearingMethod.VMD_ENVELOPE, None),
    ]

    for name_cn, method_val, _ in METHODS:
        t0 = time.perf_counter()
        correct, total_t, times = 0, 0, []
        for fname, is_healthy, _label in files:
            sig = load_npy(HUSTBEAR_DIR, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(
                    bearing_method=method_val,
                    bearing_params=BEARING_PARAMS, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig, FS)
                times.append((time.perf_counter() - t1) * 1000)
                if _bearing_detect(res, is_healthy):
                    correct += 1
                total_t += 1
            except Exception:
                pass
        acc = correct / max(total_t, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        total_s = time.perf_counter() - t0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms 总{total_s:.0f}s")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct,
                                        "total": total_t, "avg_time_ms": avg_ms}

    # Ensemble
    t0 = time.perf_counter()
    correct, total_t, times = 0, 0, []
    for fname, is_healthy, _label in files:
        sig = load_npy(HUSTBEAR_DIR, fname)
        if sig is None:
            continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            if _ensemble_detect(res, is_healthy):
                correct += 1
            total_t += 1
        except Exception:
            pass
    acc = correct / max(total_t, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total_t, "avg_time_ms": avg_ms}

    # CEEMDAN 标注为跳过
    results["methods"]["CEEMDAN"] = {"accuracy": "-", "correct": "-", "total": "-",
                                      "avg_time_ms": "~4500", "note": "计算量极大，跳过"}

    save_json(results, "42_hust_binary.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.2.2 HUSTbear 五分类 (Ensemble)
# ═══════════════════════════════════════════════════════════
def run_42_hust_multiclass():
    print("\n" + "=" * 60)
    print("4.2.2 HUSTbear 五分类 (Ensemble)")
    print("=" * 60)

    class_map = {"H": "健康", "B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}
    class_files = {k: [] for k in class_map}
    for f in sorted(HUSTBEAR_DIR.glob("*-X.npy")):
        fc = _fault_code_hust(f.name)
        if fc in class_files:
            class_files[fc].append(f.name)

    y_true, y_pred, times = [], [], []
    t0 = time.perf_counter()
    for cls_code, cls_name in class_map.items():
        for fname in class_files[cls_code]:
            sig = load_npy(HUSTBEAR_DIR, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
                times.append((time.perf_counter() - t1) * 1000)
                fl = str(res.get("fault_label", "unknown")).lower()
                if "bpfo" in fl or "outer" in fl:
                    pred = "外圈"
                elif "bpfi" in fl or "inner" in fl:
                    pred = "内圈"
                elif "bsf" in fl or "ball" in fl:
                    pred = "球故障"
                elif "compound" in fl or "bpfo_bpfi" in fl:
                    pred = "复合"
                elif "healthy" in fl or "normal" in fl or "unknown" in fl:
                    pred = "健康"
                elif "abnormal" in fl:
                    pred = "复合"
                else:
                    pred = "健康"
                y_true.append(cls_name)
                y_pred.append(pred)
            except Exception:
                pass

    elapsed = time.perf_counter() - t0
    cm = _compute_cm(y_true, y_pred, list(class_map.values()))
    metrics = _classification_metrics(y_true, y_pred)

    results = {
        "confusion_matrix": cm,
        "class_names": list(class_map.values()),
        "metrics": metrics,
        "avg_time_ms": round(np.mean(times), 1) if times else 0,
        "total_time_s": round(elapsed, 1),
    }

    print(f"  Accuracy: {metrics['accuracy']}%")
    print(f"  Balanced Acc: {metrics['balanced_accuracy']}%")
    print(f"  Macro-F1: {metrics['macro_f1']}")
    print(f"  Kappa: {metrics['cohens_kappa']}")
    print(f"  MCC: {metrics['mcc']}")
    print(f"  平均耗时: {results['avg_time_ms']}ms")
    for cls_name in class_map.values():
        pc = metrics["per_class"].get(cls_name, {})
        print(f"    {cls_name}: P={pc.get('precision','-')} R={pc.get('recall','-')} F1={pc.get('f1','-')}")

    save_json(results, "42_hust_multiclass.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.3.1 Ottawa/CW 轴承二分类
# ═══════════════════════════════════════════════════════════
def run_43_ottawa_binary():
    print("\n" + "=" * 60)
    print("4.3.1 Ottawa/CW 轴承二分类（健康vs故障）")
    print("=" * 60)

    all_files = []
    for f in sorted(CW_DIR.glob("*.npy")):
        fc = _fault_code_cw(f.name)
        if fc == "H":
            all_files.append((f.name, True))
        elif fc in ("I", "O"):
            all_files.append((f.name, False))

    healthy = [(f, t) for f, t in all_files if t]
    fault = [(f, t) for f, t in all_files if not t]
    files = healthy + fault
    print(f"  健康:{len(healthy)} 故障:{len(fault)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(healthy), "fault": len(fault), "methods": {}}

    METHODS = [
        ("标准包络", BearingMethod.ENVELOPE),
        ("Kurtogram", BearingMethod.KURTOGRAM),
        ("CPW预白化", BearingMethod.CPW),
        ("MED增强", BearingMethod.MED),
        ("MCKD", BearingMethod.MCKD),
        ("Teager", BearingMethod.TEAGER),
        ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
        ("DWT", BearingMethod.DWT),
        ("EMD", BearingMethod.EMD_ENVELOPE),
        ("VMD", BearingMethod.VMD_ENVELOPE),
    ]

    for name_cn, method_val in METHODS:
        t0 = time.perf_counter()
        correct, total_t, times = 0, 0, []
        for fname, is_healthy in files:
            sig = load_npy(CW_DIR, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(
                    bearing_method=method_val,
                    bearing_params=BEARING_PARAMS, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig, FS)
                times.append((time.perf_counter() - t1) * 1000)
                if _bearing_detect(res, is_healthy):
                    correct += 1
                total_t += 1
            except Exception:
                pass
        acc = correct / max(total_t, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        total_s = time.perf_counter() - t0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms 总{total_s:.0f}s")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct,
                                        "total": total_t, "avg_time_ms": avg_ms}

    # Ensemble
    t0 = time.perf_counter()
    correct, total_t, times = 0, 0, []
    for fname, is_healthy in files:
        sig = load_npy(CW_DIR, fname)
        if sig is None:
            continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            if _ensemble_detect(res, is_healthy):
                correct += 1
            total_t += 1
        except Exception:
            pass
    acc = correct / max(total_t, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total_t, "avg_time_ms": avg_ms}
    results["methods"]["CEEMDAN"] = {"accuracy": "-", "correct": "-", "total": "-",
                                      "avg_time_ms": "~4500", "note": "计算量极大，跳过"}

    save_json(results, "43_ottawa_binary.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.3.2 Ottawa/CW 三分类 (Ensemble)
# ═══════════════════════════════════════════════════════════
def run_43_ottawa_multiclass():
    print("\n" + "=" * 60)
    print("4.3.2 Ottawa/CW 三分类 (Ensemble)")
    print("=" * 60)

    class_map = {"H": "健康", "I": "内圈", "O": "外圈"}
    class_files = {k: [] for k in class_map}
    for f in sorted(CW_DIR.glob("*.npy")):
        fc = _fault_code_cw(f.name)
        if fc in class_files:
            class_files[fc].append(f.name)

    for k, v in class_files.items():
        print(f"  {class_map[k]}: {len(v)} 文件")

    y_true, y_pred, times = [], [], []
    t0 = time.perf_counter()
    for cls_code, cls_name in class_map.items():
        for fname in class_files[cls_code]:
            sig = load_npy(CW_DIR, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
                times.append((time.perf_counter() - t1) * 1000)
                fl = str(res.get("fault_label", "unknown")).lower()
                if "bpfo" in fl or "outer" in fl:
                    pred = "外圈"
                elif "bpfi" in fl or "inner" in fl:
                    pred = "内圈"
                elif "healthy" in fl or "normal" in fl or "unknown" in fl:
                    pred = "健康"
                else:
                    pred = "健康"
                y_true.append(cls_name)
                y_pred.append(pred)
            except Exception:
                pass

    elapsed = time.perf_counter() - t0
    cm = _compute_cm(y_true, y_pred, list(class_map.values()))
    metrics = _classification_metrics(y_true, y_pred)

    results = {
        "confusion_matrix": cm,
        "class_names": list(class_map.values()),
        "metrics": metrics,
        "avg_time_ms": round(np.mean(times), 1) if times else 0,
        "total_time_s": round(elapsed, 1),
    }

    print(f"  Accuracy: {metrics['accuracy']}%")
    print(f"  Balanced Acc: {metrics['balanced_accuracy']}%")
    print(f"  Macro-F1: {metrics['macro_f1']}")
    for cls_name in class_map.values():
        pc = metrics["per_class"].get(cls_name, {})
        print(f"    {cls_name}: P={pc.get('precision','-')} R={pc.get('recall','-')} F1={pc.get('f1','-')}")

    save_json(results, "43_ottawa_multiclass.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.4.1 WTgearbox 齿轮二分类
# ═══════════════════════════════════════════════════════════
def run_44_wtg_binary():
    print("\n" + "=" * 60)
    print("4.4.1 WTgearbox 齿轮二分类（健康vs故障）+ 行星箱阈值")
    print("=" * 60)

    files_healthy = sorted(f.name for f in WTGEAR_DIR.glob("He_*-c1.npy"))
    files_fault = sorted(f.name for f in WTGEAR_DIR.glob("*.npy")
                         if "-c1.npy" in f.name and not f.name.startswith("He"))
    files = [(f, True) for f in files_healthy] + [(f, False) for f in files_fault]
    print(f"  健康:{len(files_healthy)} 故障:{len(files_fault)} 总计:{len(files)}")

    results = {"total": len(files), "healthy": len(files_healthy),
               "fault": len(files_fault), "methods": {}}

    for name_cn, method_val in [("标准边频分析", GearMethod.STANDARD), ("高级综合", GearMethod.ADVANCED)]:
        t0 = time.perf_counter()
        correct, total_t, times = 0, 0, []
        for fname, is_healthy in files:
            sig = load_npy(WTGEAR_DIR, fname)
            if sig is None:
                continue
            try:
                rf = float(fname.split("_")[-1].replace("-c1.npy", ""))
            except ValueError:
                rf = 30.0
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(
                    gear_method=method_val,
                    gear_teeth=GEAR_PARAMS, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_gear(sig, FS, rot_freq=rf)
                times.append((time.perf_counter() - t1) * 1000)
                if _gear_detect(res, is_healthy):
                    correct += 1
                total_t += 1
            except Exception:
                pass
        acc = correct / max(total_t, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        total_s = time.perf_counter() - t0
        print(f"  [{name_cn}] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms 总{total_s:.0f}s")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct,
                                        "total": total_t, "avg_time_ms": avg_ms}

    # Ensemble gear
    t0 = time.perf_counter()
    correct, total_t, times = 0, 0, []
    for fname, is_healthy in files:
        sig = load_npy(WTGEAR_DIR, fname)
        if sig is None:
            continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, gear_teeth=GEAR_PARAMS, max_seconds=MAX_S)
            times.append((time.perf_counter() - t1) * 1000)
            if _ensemble_detect(res, is_healthy):
                correct += 1
            total_t += 1
        except Exception:
            pass
    acc = correct / max(total_t, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.2f}% ({correct}/{total_t}) 平均{avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total_t, "avg_time_ms": avg_ms}

    # 行星齿轮箱阈值数据点（选取代表性样本的指标值）
    demo_files = [
        ("He_N1_40-c1.npy", "健康", 40),
        ("He_N2_55-c1.npy", "健康", 55),
        ("Br_B1_40-c1.npy", "断齿", 40),
        ("Mi_M1_40-c1.npy", "缺齿", 40),
        ("Rc_R1_40-c1.npy", "齿根裂纹", 40),
        ("We_W1_40-c1.npy", "磨损", 40),
    ]
    threshold_demo = []
    for fname, label, speed in demo_files:
        sig = load_npy(WTGEAR_DIR, fname)
        if sig is None:
            continue
        try:
            engine = DiagnosisEngine(gear_method=GearMethod.ADVANCED,
                                     gear_teeth=GEAR_PARAMS, denoise_method=DenoiseMethod.NONE)
            res = engine.analyze_gear(sig, FS, rot_freq=speed)
            inds = res.get("fault_indicators", {})
            row = {"sample": fname, "label": label, "speed_hz": speed}
            for k in ["ser", "fm4", "order_kurtosis"]:
                v = inds.get(k, {})
                row[k] = round(v.get("value", 0), 2) if isinstance(v, dict) else round(v, 2) if v else 0
            threshold_demo.append(row)
        except Exception:
            pass
    results["threshold_demo"] = threshold_demo

    save_json(results, "44_wtg_binary.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.4.3 WTgearbox 五分类 (Ensemble)
# ═══════════════════════════════════════════════════════════
def run_44_wtg_multiclass():
    print("\n" + "=" * 60)
    print("4.4.3 WTgearbox 五分类 (Ensemble)")
    print("=" * 60)

    class_map = {"He": "健康", "Br": "断齿", "Mi": "缺齿", "Rc": "裂纹", "We": "磨损"}
    class_files = {k: sorted(f.name for f in WTGEAR_DIR.glob(f"{k}_*-c1.npy")) for k in class_map}

    y_true, y_pred, times = [], [], []
    t0 = time.perf_counter()
    for cat, cls_name in class_map.items():
        for fname in class_files[cat]:
            sig = load_npy(WTGEAR_DIR, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                res = run_research_ensemble(sig, FS, gear_teeth=GEAR_PARAMS, max_seconds=MAX_S)
                times.append((time.perf_counter() - t1) * 1000)
                fl = str(res.get("fault_label", "unknown")).lower()
                if "break" in fl or "broken" in fl:
                    pred = "断齿"
                elif "missing" in fl:
                    pred = "缺齿"
                elif "crack" in fl:
                    pred = "裂纹"
                elif "wear" in fl:
                    pred = "磨损"
                elif "healthy" in fl or "normal" in fl or "unknown" in fl:
                    pred = "健康"
                elif "abnormal" in fl:
                    pred = "缺齿"
                else:
                    pred = "健康"
                y_true.append(cls_name)
                y_pred.append(pred)
            except Exception:
                pass

    elapsed = time.perf_counter() - t0
    cm = _compute_cm(y_true, y_pred, list(class_map.values()))
    metrics = _classification_metrics(y_true, y_pred)

    results = {
        "confusion_matrix": cm,
        "class_names": list(class_map.values()),
        "metrics": metrics,
        "avg_time_ms": round(np.mean(times), 1) if times else 0,
        "total_time_s": round(elapsed, 1),
    }

    print(f"  Accuracy: {metrics['accuracy']}%")
    print(f"  Balanced Acc: {metrics['balanced_accuracy']}%")
    print(f"  Macro-F1: {metrics['macro_f1']}")
    print(f"  Kappa: {metrics['cohens_kappa']}")
    print(f"  MCC: {metrics['mcc']}")

    save_json(results, "44_wtg_multiclass.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.5 跨数据集对比
# ═══════════════════════════════════════════════════════════
def run_45_cross_dataset():
    print("\n" + "=" * 60)
    print("4.5 跨数据集对比")
    print("=" * 60)

    # 从各个JSON读取并汇总
    result = {"methods": {}}
    for json_name, dataset_name in [
        ("42_hust_binary.json", "HUST恒速"),
        ("43_ottawa_binary.json", "Ottawa变速"),
        ("44_wtg_binary.json", "WT齿轮"),
    ]:
        try:
            data = json.loads((OUTPUT_DIR / json_name).read_text(encoding="utf-8"))
            for method, info in data.get("methods", {}).items():
                if method not in result["methods"]:
                    result["methods"][method] = {}
                result["methods"][method][dataset_name] = info.get("accuracy", "-")
        except Exception:
            pass

    # 计算平均
    for method, datasets in result["methods"].items():
        valid = [v for v in datasets.values() if isinstance(v, (int, float))]
        datasets["平均"] = round(sum(valid) / len(valid), 2) if valid else "-"

    save_json(result, "45_cross_dataset.json")
    print("  跨数据集对比汇总完成")
    return result


# ═══════════════════════════════════════════════════════════
# 4.6 噪声鲁棒性
# ═══════════════════════════════════════════════════════════
def run_46_robustness():
    print("\n" + "=" * 60)
    print("4.6 噪声鲁棒性")
    print("=" * 60)

    or_files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if _fault_code_hust(f.name) == "O")
    if not or_files:
        print("  未找到外圈故障文件")
        return None

    sig_clean = load_npy(HUSTBEAR_DIR, or_files[0].name)
    np.random.seed(42)

    snr_levels = [20, 10, 5, 0, -5]
    results = {"snr_levels": snr_levels, "methods": {}}

    for name_cn, method_val in [
        ("包络", BearingMethod.ENVELOPE), ("Kurtogram", BearingMethod.KURTOGRAM),
        ("MED", BearingMethod.MED), ("MCKD", BearingMethod.MCKD),
    ]:
        curve = []
        for snr_db in snr_levels:
            sig_power = np.var(sig_clean.astype(np.float64))
            noise = np.sqrt(sig_power / (10 ** (snr_db / 10))) * np.random.randn(len(sig_clean))
            try:
                engine = DiagnosisEngine(
                    bearing_method=method_val,
                    bearing_params=BEARING_PARAMS, denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig_clean + noise, FS)
                inds = res.get("fault_indicators", {})
                detected = any(v.get("significant") for k, v in inds.items()
                               if isinstance(v, dict) and not k.endswith("_stat"))
                curve.append({"snr_db": snr_db, "detected": detected})
                print(f"    {name_cn} SNR={snr_db}dB: {'检出' if detected else '未检出'}")
            except Exception:
                curve.append({"snr_db": snr_db, "detected": False})
        results["methods"][name_cn] = curve

    # Ensemble robustness
    curve = []
    for snr_db in snr_levels:
        sig_power = np.var(sig_clean.astype(np.float64))
        noise = np.sqrt(sig_power / (10 ** (snr_db / 10))) * np.random.randn(len(sig_clean))
        try:
            res = run_research_ensemble(sig_clean + noise, FS, bearing_params=BEARING_PARAMS, max_seconds=5.0)
            detected = res.get("status", "normal") != "normal" or res.get("health_score", 100) < 70
            curve.append({"snr_db": snr_db, "detected": detected})
            print(f"    Ensemble SNR={snr_db}dB: {'检出' if detected else '未检出'}")
        except Exception:
            curve.append({"snr_db": snr_db, "detected": False})
    results["methods"]["Ensemble"] = curve

    save_json(results, "46_robustness.json")
    return results


# ═══════════════════════════════════════════════════════════
# 4.7 去噪效果
# ═══════════════════════════════════════════════════════════
def run_47_denoise():
    print("\n" + "=" * 60)
    print("4.7 去噪效果")
    print("=" * 60)

    # 外圈故障
    or_files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if _fault_code_hust(f.name) == "O")
    # 健康
    h_files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if _fault_code_hust(f.name) == "H")

    results = {"methods": {}}

    for label, files in [("外圈故障", or_files), ("健康", h_files)]:
        if not files:
            continue
        sig_clean = load_npy(HUSTBEAR_DIR, files[0].name)
        np.random.seed(42)
        sig_noisy = sig_clean + np.random.randn(len(sig_clean)) * np.std(sig_clean)
        base_power = np.var(sig_clean)

        engine = DiagnosisEngine()
        for dname, dlabel in [
            ("none", "无去噪"), ("wavelet", "小波去噪"), ("vmd", "VMD去噪"),
            ("med", "MED去噪"), ("wavelet_vmd", "小波+VMD级联"),
        ]:
            engine.denoise_method = DenoiseMethod(dname)
            try:
                proc = engine.preprocess(sig_noisy)
                rp = np.var(sig_clean - proc[:len(sig_clean)])
            except Exception:
                rp = base_power
            dsnr = 10 * np.log10(max(base_power, 1e-12) / max(rp, 1e-12))

            if dlabel not in results["methods"]:
                results["methods"][dlabel] = {}
            results["methods"][dlabel][label] = round(dsnr, 2)
            print(f"  {dlabel} [{label}]: ΔSNR={dsnr:+.1f}dB")

    save_json(results, "47_denoise.json")
    return results


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("综合评估 — 覆盖文档 4.2~4.7")
    print(f"输出: {OUTPUT_DIR}")
    print("=" * 60)
    t0 = time.time()

    # 按顺序运行（避免并行OOM）
    run_42_hust_binary()
    run_42_hust_multiclass()
    run_43_ottawa_binary()
    run_43_ottawa_multiclass()
    run_44_wtg_binary()
    run_44_wtg_multiclass()
    run_45_cross_dataset()
    run_46_robustness()
    run_47_denoise()

    print(f"\n全部完成 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
