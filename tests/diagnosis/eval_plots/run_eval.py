"""
评估实验 — 数据采集（存 JSON, joblib 多进程加速）

用法:
    cd d:/code/CNN/cloud
    . venv/Scripts/activate
    python ../tests/diagnosis/eval_plots/run_eval.py
"""
import sys, json, time, warnings, os, traceback
from pathlib import Path
import numpy as np
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

# ── 配置 ──────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FS = 8192
MAX_S = 5
MAX_PTS = FS * MAX_S
N_JOBS = min(4, os.cpu_count() or 4)

HUSTBEAR_DIR = Path(os.environ.get("HUSTBEAR_DIR", r"D:\code\wavelet_study\dataset\HUSTbear\down8192"))
CW_DIR = Path(os.environ.get("CW_DIR", r"D:\code\CNN\CW\down8192_CW"))
WTGEAR_DIR = Path(os.environ.get("WTGEARBOX_DIR", r"D:\code\wavelet_study\dataset\WTgearbox\down8192"))

BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GEAR_PARAMS = {"sun": 28, "ring": 100, "planet": 36, "n_planets": 4}


def load_npy(dir_path, fname):
    fp = Path(dir_path) / fname
    if not fp.exists():
        return None
    return np.load(fp).astype(np.float64)[:MAX_PTS]


def save_json(data, name):
    with open(str(OUTPUT_DIR / name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> saved: {name}")


def _fault_code(fname):
    """从 HUSTbear 文件名提取故障码: H/B/I/O/C 或 None"""
    stem = fname.replace(".npy", "").rsplit("-", 1)[0]
    parts = stem.split("_")
    if parts[0] in ("H", "B", "I", "O", "C"):
        return parts[0]
    if len(parts) >= 2 and parts[1] in ("B", "I", "O", "C"):
        return parts[1]
    return None


# ── 模块级 worker 函数（供 joblib 并行使用）──────────────

def _worker_bearing(fname, is_healthy, method_str):
    """单轴承方法评估一个文件"""
    sig = load_npy(HUSTBEAR_DIR, fname)
    if sig is None:
        return None
    try:
        engine = DiagnosisEngine(
            bearing_method=BearingMethod(method_str),
            bearing_params=BEARING_PARAMS, denoise_method=DenoiseMethod.NONE)
        res = engine.analyze_bearing(sig, FS)  # rot_freq=None: 引擎自估计
        inds = res.get("fault_indicators", {})
        has_fault = any(
            v.get("significant") for k, v in inds.items()
            if isinstance(v, dict) and not k.endswith("_stat"))
        return {"correct": has_fault != is_healthy}
    except Exception:
        return None


def _worker_ensemble_bearing(fname, is_healthy):
    """Ensemble 评估一个文件"""
    sig = load_npy(HUSTBEAR_DIR, fname)
    if sig is None:
        return None
    try:
        res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
        hs = res.get("health_score", 100)
        status = res.get("status", "normal")
        pred_healthy = status == "normal" and hs >= 70
        return {"correct": pred_healthy == is_healthy or (not is_healthy and not pred_healthy)}
    except Exception:
        return None


def _worker_gear(fname, is_healthy, method_str):
    """单齿轮方法评估一个文件"""
    sig = load_npy(WTGEAR_DIR, fname)
    if sig is None:
        return None
    try:
        engine = DiagnosisEngine(
            gear_method=GearMethod(method_str),
            gear_teeth=GEAR_PARAMS, denoise_method=DenoiseMethod.NONE)
        rf = float(fname.split("_")[-1].replace("-c1.npy", ""))
        res = engine.analyze_gear(sig, FS, rot_freq=rf)
        inds = res.get("fault_indicators", {})
        has_warn = any(
            v.get("warning") or v.get("critical")
            for v in inds.values() if isinstance(v, dict))
        return {"correct": has_warn != is_healthy}
    except Exception:
        return None


def _worker_ensemble_gear(fname, is_healthy):
    """Ensemble 齿轮评估"""
    sig = load_npy(WTGEAR_DIR, fname)
    if sig is None:
        return None
    try:
        res = run_research_ensemble(sig, FS, gear_teeth=GEAR_PARAMS, max_seconds=MAX_S)
        hs = res.get("health_score", 100)
        status = res.get("status", "normal")
        pred_healthy = status == "normal" and hs >= 70
        return {"correct": pred_healthy == is_healthy or (not is_healthy and not pred_healthy)}
    except Exception:
        return None


def _worker_snr(method_str, snr_db, sig_clean):
    """单方法 SNR 鲁棒性测试"""
    sig_power = np.var(sig_clean.astype(np.float64))
    np.random.seed(abs(42 + (snr_db + 10) * 100) % (2**31))
    noise = np.sqrt(sig_power / (10 ** (snr_db / 10))) * np.random.randn(len(sig_clean))
    try:
        engine = DiagnosisEngine(
            bearing_method=BearingMethod(method_str),
            bearing_params=BEARING_PARAMS, denoise_method=DenoiseMethod.NONE)
        res = engine.analyze_bearing(sig_clean + noise, FS)  # rot_freq=None: 引擎自估计
        inds = res.get("fault_indicators", {})
        return any(v.get("significant") for k, v in inds.items()
                   if isinstance(v, dict) and not k.endswith("_stat"))
    except Exception:
        return False


def _worker_ens_snr(snr_db, sig_clean):
    """Ensemble SNR 鲁棒性测试"""
    sig_power = np.var(sig_clean.astype(np.float64))
    np.random.seed(abs(42 + (snr_db + 10) * 100) % (2**31))
    noise = np.sqrt(sig_power / (10 ** (snr_db / 10))) * np.random.randn(len(sig_clean))
    try:
        res = run_research_ensemble(sig_clean + noise, FS, bearing_params=BEARING_PARAMS, max_seconds=5.0)
        return res.get("status", "normal") != "normal" or res.get("health_score", 100) < 70
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# 实验A: 轴承二分类 (HUSTbear)
# ═══════════════════════════════════════════════════════════
def run_expA_bearing():
    print("\n" + "=" * 60)
    print("实验A: 轴承诊断 HUSTbear 二分类 (joblib x%d)" % N_JOBS)
    print("=" * 60)

    all_files = []
    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if "-X.npy" not in f.name:
            continue
        fc = _fault_code(f.name)
        if fc == "H":
            all_files.append((f.name, True))
        elif fc in ("B", "I", "O", "C"):
            all_files.append((f.name, False))

    healthy = [(f, t) for f, t in all_files if t][:10]
    fault = [(f, t) for f, t in all_files if not t][:10]
    files_to_test = healthy + fault
    print(f"  健康:{len(healthy)} 故障:{len(fault)}")

    results = {"methods": {}}

    METHODS = [
        ("包络分析", "envelope"), ("Kurtogram", "kurtogram"), ("CPW预白化", "cpw"),
        ("MED增强", "med"), ("MCKD", "mckd"), ("Teager", "teager"),
        ("谱峭度重加权", "spectral_kurtosis"), ("DWT", "dwt"),
        ("EMD", "emd_envelope"), ("CEEMDAN", "ceemdan_envelope"), ("VMD", "vmd_envelope"),
    ]

    for name_cn, method_val in METHODS:
        t0 = time.time()
        correct, total = 0, 0
        for fname, is_healthy in files_to_test:
            r = _worker_bearing(fname, is_healthy, method_val)
            if r is not None:
                correct += r["correct"]
                total += 1
        acc = correct / max(total, 1) * 100
        print(f"  [{name_cn}] {acc:.1f}% ({correct}/{total}) {time.time()-t0:.1f}s")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct, "total": total}

    t0 = time.time()
    correct, total = 0, 0
    for fname, is_healthy in files_to_test:
        r = _worker_ensemble_bearing(fname, is_healthy)
        if r is not None:
            correct += r["correct"]
            total += 1
    acc = correct / max(total, 1) * 100
    print(f"  [Ensemble集成] {acc:.1f}% ({correct}/{total}) {time.time()-t0:.1f}s")
    results["methods"]["Ensemble集成"] = {"accuracy": round(acc, 2), "correct": correct, "total": total}

    save_json(results, "expA_bearing.json")
    return results


# ═══════════════════════════════════════════════════════════
# 实验B: 齿轮诊断 (WTgearbox)
# ═══════════════════════════════════════════════════════════
def run_expB_gear():
    print("\n" + "=" * 60)
    print("实验B: 齿轮诊断 WTgearbox 二分类 (joblib x%d)" % N_JOBS)
    print("=" * 60)

    files_healthy = sorted(f.name for f in WTGEAR_DIR.glob("He_*-c1.npy"))
    files_fault = sorted(f.name for f in WTGEAR_DIR.glob("*.npy")
                         if "-c1.npy" in f.name and not f.name.startswith("He"))
    files_to_test = [(f, True) for f in files_healthy] + [(f, False) for f in files_fault]
    print(f"  健康:{len(files_healthy)} 故障:{len(files_fault)}")

    results = {"methods": {}}

    for name_cn, method_val in [("标准边频分析", "standard"), ("高级综合", "advanced")]:
        t0 = time.time()
        jobs = [delayed(_worker_gear)(f, h, method_val) for f, h in files_to_test]
        rlist = [r for r in Parallel(n_jobs=N_JOBS, backend="loky")(jobs) if r is not None]
        correct = sum(1 for r in rlist if r["correct"])
        acc = correct / max(len(rlist), 1) * 100
        print(f"  [{name_cn}] {acc:.1f}% ({correct}/{len(rlist)}) {time.time()-t0:.1f}s")
        results["methods"][name_cn] = {"accuracy": round(acc, 2), "correct": correct, "total": len(rlist)}

    t0 = time.time()
    jobs = [delayed(_worker_ensemble_gear)(f, h) for f, h in files_to_test]
    rlist = [r for r in Parallel(n_jobs=N_JOBS, backend="loky")(jobs) if r is not None]
    correct = sum(1 for r in rlist if r["correct"])
    acc = correct / max(len(rlist), 1) * 100
    print(f"  [Ensemble集成] {acc:.1f}% ({correct}/{len(rlist)}) {time.time()-t0:.1f}s")
    results["methods"]["Ensemble集成"] = {"accuracy": round(acc, 2), "correct": correct, "total": len(rlist)}

    save_json(results, "expB_gear.json")
    return results


# ═══════════════════════════════════════════════════════════
# 实验C: 去噪效果
# ═══════════════════════════════════════════════════════════
def run_expC_denoise():
    print("\n" + "=" * 60)
    print("实验C: 去噪效果 HUSTbear 外圈故障")
    print("=" * 60)

    or_files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if _fault_code(f.name) == "O")
    if not or_files:
        print("  未找到外圈故障文件")
        return None

    sig_or = load_npy(HUSTBEAR_DIR, or_files[0].name)
    np.random.seed(42)
    sig_noisy = sig_or + np.random.randn(len(sig_or)) * np.std(sig_or)

    results = {"sample": or_files[0].name, "methods": {}}
    base_power = np.var(sig_or)
    engine = DiagnosisEngine()

    for dname, dlabel in [
        ("none", "无去噪"), ("wavelet", "小波去噪"), ("vmd", "VMD去噪"),
        ("savgol", "Savitzky-Golay"), ("wavelet_vmd", "小波+VMD级联"),
    ]:
        engine.denoise_method = DenoiseMethod(dname)
        t0 = time.time()
        try:
            proc = engine.preprocess(sig_noisy)
            rp = np.var(sig_or - proc[:len(sig_or)])
        except Exception:
            rp = base_power
        dt = time.time() - t0
        dsnr = 10 * np.log10(max(base_power, 1e-12) / max(rp, 1e-12))
        results["methods"][dlabel] = {"delta_snr_db": round(dsnr, 2), "time_s": round(dt, 2)}
        print(f"  {dlabel}: DSNR={dsnr:+.1f}dB {dt:.2f}s")

    save_json(results, "expC_denoise.json")
    return results


# ═══════════════════════════════════════════════════════════
# 实验D: 噪声鲁棒性
# ═══════════════════════════════════════════════════════════
def run_expD_robustness():
    print("\n" + "=" * 60)
    print("实验D: 噪声鲁棒性 HUSTbear 外圈故障 (joblib x%d)" % N_JOBS)
    print("=" * 60)

    or_files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if _fault_code(f.name) == "O")
    if not or_files:
        print("  未找到外圈故障文件")
        return None

    sig_clean = load_npy(HUSTBEAR_DIR, or_files[0].name)
    snr_levels = [20, 10, 5, 0, -5]
    results = {"snr_levels": snr_levels, "methods": {}}

    for name_cn, method_val in [
        ("包络分析", "envelope"), ("Kurtogram", "kurtogram"),
        ("MED增强", "med"), ("MCKD", "mckd"),
    ]:
        jobs = [delayed(_worker_snr)(method_val, s, sig_clean) for s in snr_levels]
        raw = Parallel(n_jobs=N_JOBS, backend="loky")(jobs)
        curve = [{"snr_db": s, "detected": bool(d)} for s, d in zip(snr_levels, raw)]
        marks = " ".join("V" if c["detected"] else "X" for c in curve)
        avg = sum(1 for c in curve if c["detected"]) / len(curve) * 100
        print(f"  {name_cn}: [{marks}] {avg:.0f}%")
        results["methods"][name_cn] = curve

    jobs = [delayed(_worker_ens_snr)(s, sig_clean) for s in snr_levels]
    raw = Parallel(n_jobs=N_JOBS, backend="loky")(jobs)
    curve = [{"snr_db": s, "detected": bool(d)} for s, d in zip(snr_levels, raw)]
    marks = " ".join("V" if c["detected"] else "X" for c in curve)
    avg = sum(1 for c in curve if c["detected"]) / len(curve) * 100
    print(f"  Ensemble集成: [{marks}] {avg:.0f}%")
    results["methods"]["Ensemble集成"] = curve

    save_json(results, "expD_robustness.json")
    return results


# ═══════════════════════════════════════════════════════════
# 实验A2: 轴承五分类 (HUSTbear + Ensemble)
# ═══════════════════════════════════════════════════════════
def run_expA2_bearing_multiclass():
    print("\n" + "=" * 60)
    print("实验A2: 轴承五分类 HUSTbear (Ensemble)")
    print("=" * 60)

    # 收集文件按类别分组
    classes = {"H": "健康", "B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"}
    class_files = {k: [] for k in classes}
    for f in sorted(HUSTBEAR_DIR.glob("*-X.npy")):
        fc = _fault_code(f.name)
        if fc in class_files:
            class_files[fc].append(f.name)

    for k, v in class_files.items():
        class_files[k] = v[:6]  # 每类最多6个
        print(f"  {classes[k]}: {len(class_files[k])} 文件")

    y_true, y_pred = [], []
    all_files = [(f, c) for c in classes for f in class_files[c]]
    t0 = time.time()

    for fname, true_cls in all_files:
        sig = load_npy(HUSTBEAR_DIR, fname)
        if sig is None:
            continue
        try:
            res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=MAX_S)
            fl = res.get("fault_label", "unknown")
            # 映射 fault_label 到标准类别
            pred = _map_bearing_label(fl)
            y_true.append(classes[true_cls])
            y_pred.append(pred)
        except Exception:
            pass

    elapsed = time.time() - t0
    cm = _compute_cm(y_true, y_pred, list(classes.values()))
    metrics = _classification_metrics(y_true, y_pred)

    results = {
        "confusion_matrix": cm,
        "class_names": list(classes.values()),
        "metrics": metrics,
        "time_s": round(elapsed, 1),
    }
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"  耗时: {elapsed:.1f}s")

    save_json(results, "expA2_multiclass.json")
    return results


def _map_bearing_label(fl):
    """映射 ensemble fault_label → 标准中文类别（精确匹配，避免子串误判）"""
    fl_lower = str(fl).lower()
    if fl_lower == "bearing_bpfo" or "outer" in fl_lower:
        return "外圈"
    if fl_lower == "bearing_bpfi" or "inner" in fl_lower:
        return "内圈"
    if fl_lower == "bearing_bsf" or "ball" in fl_lower:
        return "球故障"
    if "compound" in fl_lower or fl_lower == "bearing_bpfo_bpfi" or fl_lower == "bearing_bpfo_bsf" or fl_lower == "bearing_bpfi_bsf":
        return "复合"
    if "healthy" in fl_lower or "normal" in fl_lower or "unknown" in fl_lower:
        return "健康"
    if "abnormal" in fl_lower:
        return "复合"  # 兜底
    return "健康"


def _compute_cm(y_true, y_pred, class_names):
    """计算混淆矩阵"""
    n = len(class_names)
    cm = [[0] * n for _ in range(n)]
    name_to_idx = {name: i for i, name in enumerate(class_names)}
    for t, p in zip(y_true, y_pred):
        ti = name_to_idx.get(t, 0)
        pi = name_to_idx.get(p, 0)
        cm[ti][pi] += 1
    return cm


def _classification_metrics(y_true, y_pred):
    """计算多分类指标"""
    n = len(y_true)
    if n == 0:
        return {}
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    classes = sorted(set(y_true))
    per_class = {}
    macro_f1 = 0.0
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 0.001)
        per_class[c] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "tp": tp}
        macro_f1 += f1
    macro_f1 /= max(len(classes), 1)
    return {
        "accuracy": round(correct / n * 100, 1),
        "macro_f1": round(macro_f1, 3),
        "total": n,
        "per_class": per_class,
    }


# ═══════════════════════════════════════════════════════════
# 实验B2: 齿轮五分类 (WTgearbox + Ensemble)
# ═══════════════════════════════════════════════════════════
def run_expB2_gear_multiclass():
    print("\n" + "=" * 60)
    print("实验B2: 齿轮五分类 WTgearbox (Ensemble)")
    print("=" * 60)

    class_map = {"He": "健康", "Br": "断齿", "Mi": "缺齿", "Rc": "裂纹", "We": "磨损"}
    class_files = {k: sorted(f.name for f in WTGEAR_DIR.glob(f"{k}_*-c1.npy"))[:6] for k in class_map}
    for k, v in class_files.items():
        print(f"  {class_map[k]}: {len(v)}")

    y_true, y_pred = [], []
    t0 = time.time()
    for cat, files in class_files.items():
        for fname in files:
            sig = load_npy(WTGEAR_DIR, fname)
            if sig is None:
                continue
            try:
                res = run_research_ensemble(sig, FS, gear_teeth=GEAR_PARAMS, max_seconds=MAX_S)
                fl = res.get("fault_label", "unknown")
                pred = _map_gear_label(fl)
                y_true.append(class_map[cat])
                y_pred.append(pred)
            except Exception:
                pass

    elapsed = time.time() - t0
    cm = _compute_cm(y_true, y_pred, list(class_map.values()))
    metrics = _classification_metrics(y_true, y_pred)
    results = {
        "confusion_matrix": cm,
        "class_names": list(class_map.values()),
        "metrics": metrics,
        "time_s": round(elapsed, 1),
    }
    for k, v in metrics.items():
        if k == "per_class":
            for cls, m in v.items():
                print(f"  {cls}: P={m['precision']} R={m['recall']} F1={m['f1']}")
        else:
            print(f"  {k}: {v}")
    print(f"  耗时: {elapsed:.1f}s")

    save_json(results, "expB2_multiclass.json")
    return results


def _map_gear_label(fl):
    """映射 ensemble gear fault_label → 标准中文类别"""
    fl_l = str(fl).lower()
    if "break" in fl_l or "broken" in fl_l:
        return "断齿"
    if "missing" in fl_l:
        return "缺齿"
    if "crack" in fl_l:
        return "裂纹"
    if "wear" in fl_l:
        return "磨损"
    if "healthy" in fl_l or "normal" in fl_l or "unknown" in fl_l:
        return "健康"
    if "abnormal" in fl_l:
        return "缺齿"
    return "健康"


def main():
    print("=" * 60)
    print("评估数据采集 joblib x%d" % N_JOBS)
    print(f"输出: {OUTPUT_DIR}")
    print("=" * 60)
    t0 = time.time()
    for name, func in [
        ("A-轴承二分类", run_expA_bearing),
        ("B-齿轮二分类", run_expB_gear),
        ("C-去噪效果", run_expC_denoise),
        ("D-噪声鲁棒性", run_expD_robustness),
        ("A2-轴承五分类", run_expA2_bearing_multiclass),
        ("B2-齿轮五分类", run_expB2_gear_multiclass),
    ]:
        try:
            func()
        except Exception as e:
            print(f"\n  [ERROR] {name}: {e}")
            traceback.print_exc()
    print(f"\n全部完成 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
