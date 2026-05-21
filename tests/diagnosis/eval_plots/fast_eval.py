"""
快速综合评估 — 每类取少量样本，重点覆盖所有方法×数据集
用法: & d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\fast_eval.py
"""
import sys, json, time, warnings, os
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FS = 8192
MAX_PTS = FS * 5  # 5 seconds

HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
WTGEAR_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GEAR_PARAMS = {"sun": 28, "ring": 100, "planet": 36, "n_planets": 4}


def load_sig(d, f):
    fp = Path(d) / f
    return np.load(fp).astype(np.float64)[:MAX_PTS] if fp.exists() else None


def save_json(data, name):
    (OUTPUT_DIR / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fault_hust(fname):
    s = fname.replace(".npy", "").rsplit("-", 1)[0]
    for p in s.split("_"):
        if p in "HNBIOCh":
            return {"H": "H", "N": "H", "B": "B", "I": "I", "O": "O", "C": "C"}.get(p)
    return None


def fault_cw(fname):
    return fname[0] if fname[0] in "HIO" else None


# ═══ 轴承二分类 ═══
def eval_bearing_binary(dataset_name, data_dir, file_glob, fault_func, class_names):
    print(f"\n{'='*60}\n{dataset_name} 轴承二分类\n{'='*60}")
    files = []
    for f in sorted(Path(data_dir).glob(file_glob)):
        fc = fault_func(f.name)
        if fc in class_names:
            files.append((f.name, fc == "H", class_names.get(fc, "?")))
    h = [(f, t, l) for f, t, l in files if t]
    f_ = [(f, t, l) for f, t, l in files if not t]
    files = h + f_
    print(f"  健康:{len(h)} 故障:{len(f_)}")

    METHODS = [
        ("标准包络", BearingMethod.ENVELOPE), ("Kurtogram", BearingMethod.KURTOGRAM),
        ("CPW预白化", BearingMethod.CPW), ("MED增强", BearingMethod.MED),
        ("MCKD", BearingMethod.MCKD), ("Teager", BearingMethod.TEAGER),
        ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS), ("DWT", BearingMethod.DWT),
        ("EMD", BearingMethod.EMD_ENVELOPE), ("VMD", BearingMethod.VMD_ENVELOPE),
    ]

    results = {"total": len(files), "healthy": len(h), "fault": len(f_), "methods": {}}
    for name, method in METHODS:
        t0 = time.perf_counter()
        correct, total, times = 0, 0, []
        for fname, is_h, _ in files:
            sig = load_sig(data_dir, fname)
            if sig is None:
                continue
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(bearing_method=method, bearing_params=BEARING_PARAMS,
                                         denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig, FS)
                times.append((time.perf_counter() - t1) * 1000)
                inds = res.get("fault_indicators", {})
                has_f = any(v.get("significant") for k, v in inds.items()
                            if isinstance(v, dict) and not k.endswith("_stat"))
                if has_f != is_h:
                    correct += 1
                total += 1
            except Exception:
                pass
        acc = correct / max(total, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        print(f"  [{name}] {acc:.1f}% ({correct}/{total}) {avg_ms}ms")
        results["methods"][name] = {"accuracy": round(acc, 2), "correct": correct,
                                     "total": total, "avg_time_ms": avg_ms}

    # Ensemble
    t0 = time.perf_counter()
    correct, total, times = 0, 0, []
    for fname, is_h, _ in files:
        sig = load_sig(data_dir, fname)
        if sig is None:
            continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BEARING_PARAMS, max_seconds=5.0)
            times.append((time.perf_counter() - t1) * 1000)
            hs = res.get("health_score", 100)
            st = res.get("status", "normal")
            pred_h = st == "normal" and hs >= 70
            if pred_h == is_h:
                correct += 1
            total += 1
        except Exception:
            pass
    acc = correct / max(total, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.1f}% ({correct}/{total}) {avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total, "avg_time_ms": avg_ms}
    return results


# ═══ 齿轮二分类 ═══
def eval_gear_binary():
    print(f"\n{'='*60}\nWTgearbox 齿轮二分类\n{'='*60}")
    files_h = sorted(f.name for f in WTGEAR_DIR.glob("He_*-c1.npy"))
    files_f = sorted(f.name for f in WTGEAR_DIR.glob("*.npy")
                     if "-c1.npy" in f.name and not f.name.startswith("He"))
    files = [(f, True) for f in files_h] + [(f, False) for f in files_f]
    print(f"  健康:{len(files_h)} 故障:{len(files_f)}")

    results = {"total": len(files), "healthy": len(files_h), "fault": len(files_f), "methods": {}}
    for name, method in [("标准边频分析", GearMethod.STANDARD), ("高级综合", GearMethod.ADVANCED)]:
        t0 = time.perf_counter()
        correct, total, times = 0, 0, []
        for fname, is_h in files:
            sig = load_sig(WTGEAR_DIR, fname)
            if sig is None:
                continue
            try:
                rf = float(fname.split("_")[-1].replace("-c1.npy", ""))
            except ValueError:
                rf = 30.0
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(gear_method=method, gear_teeth=GEAR_PARAMS,
                                         denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_gear(sig, FS, rot_freq=rf)
                times.append((time.perf_counter() - t1) * 1000)
                inds = res.get("fault_indicators", {})
                has_w = any(v.get("warning") or v.get("critical")
                            for v in inds.values() if isinstance(v, dict))
                if has_w != is_h:
                    correct += 1
                total += 1
            except Exception:
                pass
        acc = correct / max(total, 1) * 100
        avg_ms = round(np.mean(times), 1) if times else 0
        print(f"  [{name}] {acc:.1f}% ({correct}/{total}) {avg_ms}ms")
        results["methods"][name] = {"accuracy": round(acc, 2), "correct": correct,
                                     "total": total, "avg_time_ms": avg_ms}

    # Ensemble
    t0 = time.perf_counter()
    correct, total, times = 0, 0, []
    for fname, is_h in files:
        sig = load_sig(WTGEAR_DIR, fname)
        if sig is None:
            continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, gear_teeth=GEAR_PARAMS, max_seconds=5.0)
            times.append((time.perf_counter() - t1) * 1000)
            hs = res.get("health_score", 100)
            st = res.get("status", "normal")
            if (st == "normal" and hs >= 70) == is_h:
                correct += 1
            total += 1
        except Exception:
            pass
    acc = correct / max(total, 1) * 100
    avg_ms = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.1f}% ({correct}/{total}) {avg_ms}ms")
    results["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                       "total": total, "avg_time_ms": avg_ms}
    return results


# ═══ 去噪效果 ═══
def eval_denoise():
    print(f"\n{'='*60}\n去噪效果\n{'='*60}")
    results = {"methods": {}}
    for label, fault_code in [("外圈故障", "O"), ("健康", "H")]:
        files = sorted(f for f in HUSTBEAR_DIR.glob("*-X.npy") if fault_hust(f.name) == fault_code)
        if not files:
            continue
        sig_c = load_sig(HUSTBEAR_DIR, files[0].name)
        np.random.seed(42)
        sig_n = sig_c + np.random.randn(len(sig_c)) * np.std(sig_c)
        bp = np.var(sig_c)

        engine = DiagnosisEngine()
        for dn, dl in [("none", "无去噪"), ("wavelet", "小波去噪"), ("vmd", "VMD去噪"),
                        ("med", "MED去噪"), ("wavelet_vmd", "小波+VMD级联")]:
            engine.denoise_method = DenoiseMethod(dn)
            try:
                proc = engine.preprocess(sig_n)
                rp = np.var(sig_c - proc[:len(sig_c)])
            except Exception:
                rp = bp
            dsnr = 10 * np.log10(max(bp, 1e-12) / max(rp, 1e-12))
            results["methods"].setdefault(dl, {})[label] = round(dsnr, 2)
            print(f"  {dl} [{label}]: DSNR={dsnr:+.1f}dB")
    return results


# ═══ MAIN ═══
def main():
    print("快速综合评估")
    t0 = time.time()

    # 轴承二分类 HUST
    r1 = eval_bearing_binary("4.2.1 HUSTbear", HUSTBEAR_DIR, "*-X.npy", fault_hust,
                             {"H": "健康", "B": "球故障", "I": "内圈", "O": "外圈", "C": "复合"})
    save_json(r1, "fast_hust_binary.json")

    # 轴承二分类 Ottawa
    r2 = eval_bearing_binary("4.3.1 Ottawa/CW", CW_DIR, "*.npy", fault_cw,
                             {"H": "健康", "I": "内圈", "O": "外圈"})
    save_json(r2, "fast_ottawa_binary.json")

    # 齿轮二分类
    r3 = eval_gear_binary()
    save_json(r3, "fast_wtg_binary.json")

    # 去噪
    r4 = eval_denoise()
    save_json(r4, "fast_denoise.json")

    print(f"\n完成 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
