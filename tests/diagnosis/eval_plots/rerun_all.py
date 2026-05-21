# -*- coding: utf-8 -*-
"""全面重跑评估 - 带中间保存，异常中断不丢数据"""
import sys, json, time, os
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

OUT = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUT.mkdir(parents=True, exist_ok=True)
FS = 8192
MAX_PTS = FS * 5
BP = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GP = {"sun": 28, "ring": 100, "planet": 36, "n_planets": 4}

HUST = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW   = Path(r"D:\code\CNN\CW\down8192_CW")
WTG  = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {name}")


def load_sig(d, f):
    p = d / f
    return np.load(p).astype(np.float64)[:MAX_PTS] if p.exists() else None


# ═════════════════════════════════════════════════
# 文件收集
# ═════════════════════════════════════════════════
def collect_hust():
    def fc(f):
        s = f.replace(".npy", "").rsplit("-", 1)[0]
        for p in s.split("_"):
            if p in "HNBIOCh": return {"H": "H", "N": "H", "B": "B", "I": "I", "O": "O", "C": "C"}.get(p)
        return None
    fs = [(f.name, fc(f.name) == "H") for f in sorted(HUST.glob("*-X.npy")) if fc(f.name)]
    h = [(f, t) for f, t in fs if t]
    f_ = [(f, t) for f, t in fs if not t]
    return h + f_


def collect_cw():
    def fc(f):
        return f[0] if f[0] in "HIO" else None
    fs = [(f.name, fc(f.name) == "H") for f in sorted(CW.glob("*.npy")) if fc(f.name)]
    h = [(f, t) for f, t in fs if t]
    f_ = [(f, t) for f, t in fs if not t]
    return h + f_


def collect_wtg():
    hf = sorted(f.name for f in WTG.glob("He_*-c1.npy"))
    ff = sorted(f.name for f in WTG.glob("*.npy") if "-c1.npy" in f.name and not f.name.startswith("He"))
    return [(f, True) for f in hf] + [(f, False) for f in ff]


# ═════════════════════════════════════════════════
# 轴承二分类评估
# ═════════════════════════════════════════════════
def eval_bearing(label, files, methods):
    print(f"\n{'='*60}\n{label} ({len(files)} 样本)\n{'='*60}")
    result = {"total": len(files), "methods": {}}
    for name, method in methods:
        t0 = time.perf_counter()
        correct = total = 0
        times = []
        for fname, is_h in files:
            sig = load_sig(HUST if "HUST" in label else CW, fname)
            if sig is None: continue
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(bearing_method=method, bearing_params=BP,
                                         denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig, FS)
                times.append((time.perf_counter() - t1) * 1000)
                inds = res.get("fault_indicators", {})
                has_f = any(v.get("significant") for k, v in inds.items()
                            if isinstance(v, dict) and not k.endswith("_stat"))
                if has_f != is_h: correct += 1
                total += 1
            except Exception as e:
                pass
        acc = correct / max(total, 1) * 100
        avg = round(np.mean(times), 1) if times else 0
        print(f"  [{name}] {acc:.1f}% ({correct}/{total}) {avg}ms")
        result["methods"][name] = {"accuracy": round(acc, 2), "correct": correct,
                                    "total": total, "avg_time_ms": avg}

    # Ensemble
    t0 = time.perf_counter()
    correct = total = 0
    times = []
    for fname, is_h in files:
        sig = load_sig(HUST if "HUST" in label else CW, fname)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, bearing_params=BP, max_seconds=5.0)
            times.append((time.perf_counter() - t1) * 1000)
            hs = res.get("health_score", 100)
            st = res.get("status", "normal")
            if (st == "normal" and hs >= 70) == is_h: correct += 1
            total += 1
        except: pass
    acc = correct / max(total, 1) * 100
    avg = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.1f}% ({correct}/{total}) {avg}ms")
    result["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                      "total": total, "avg_time_ms": avg}
    return result


# ═════════════════════════════════════════════════
# 齿轮二分类
# ═════════════════════════════════════════════════
def eval_gear_binary(files):
    print(f"\n{'='*60}\nWTgearbox 齿轮二分类 ({len(files)} 样本)\n{'='*60}")
    result = {"total": len(files), "methods": {}}
    for name, method in [("标准边频分析", GearMethod.STANDARD), ("高级综合", GearMethod.ADVANCED)]:
        t0 = time.perf_counter()
        correct = total = 0
        times = []
        for fname, is_h in files:
            sig = load_sig(WTG, fname)
            if sig is None: continue
            try:
                rf = float(fname.split("_")[-1].replace("-c1.npy", ""))
            except: rf = 30.0
            try:
                t1 = time.perf_counter()
                engine = DiagnosisEngine(gear_method=method, gear_teeth=GP,
                                         denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_gear(sig, FS, rot_freq=rf)
                times.append((time.perf_counter() - t1) * 1000)
                inds = res.get("fault_indicators", {})
                has_w = any(v.get("warning") or v.get("critical")
                            for v in inds.values() if isinstance(v, dict))
                if has_w != is_h: correct += 1
                total += 1
            except: pass
        acc = correct / max(total, 1) * 100
        avg = round(np.mean(times), 1) if times else 0
        print(f"  [{name}] {acc:.1f}% ({correct}/{total}) {avg}ms")
        result["methods"][name] = {"accuracy": round(acc, 2), "correct": correct,
                                    "total": total, "avg_time_ms": avg}

    # Ensemble
    t0 = time.perf_counter()
    correct = total = 0
    times = []
    for fname, is_h in files:
        sig = load_sig(WTG, fname)
        if sig is None: continue
        try:
            t1 = time.perf_counter()
            res = run_research_ensemble(sig, FS, gear_teeth=GP, max_seconds=5.0)
            times.append((time.perf_counter() - t1) * 1000)
            hs = res.get("health_score", 100)
            st = res.get("status", "normal")
            if (st == "normal" and hs >= 70) == is_h: correct += 1
            total += 1
        except: pass
    acc = correct / max(total, 1) * 100
    avg = round(np.mean(times), 1) if times else 0
    print(f"  [Ensemble] {acc:.1f}% ({correct}/{total}) {avg}ms")
    result["methods"]["Ensemble"] = {"accuracy": round(acc, 2), "correct": correct,
                                      "total": total, "avg_time_ms": avg}
    return result


# ═════════════════════════════════════════════════
# 去噪效果
# ═════════════════════════════════════════════════
def eval_denoise():
    print(f"\n{'='*60}\n去噪效果对比\n{'='*60}")
    result = {"methods": {}}

    def fc(f):
        s = f.replace(".npy", "").rsplit("-", 1)[0]
        for p in s.split("_"):
            if p in "HNBIOCh":
                return {"H": "H", "N": "H", "B": "B", "I": "I", "O": "O", "C": "C"}.get(p)
        return None

    for label, fcode in [("外圈故障", "O"), ("健康", "H")]:
        files = sorted(f for f in HUST.glob("*-X.npy") if fc(f.name) == fcode)
        if not files:
            print(f"  [{label}] 未找到文件")
            continue
        print(f"  [{label}] 使用: {files[0].name}")
        sig_c = load_sig(HUST, files[0].name)
        np.random.seed(42)
        sig_n = sig_c + np.random.randn(len(sig_c)) * np.std(sig_c)
        bp = np.var(sig_c)

        for dn, dl in [("none", "无去噪"), ("wavelet", "小波去噪"), ("vmd", "VMD去噪"),
                        ("med", "MED去噪"), ("wavelet_vmd", "小波+VMD级联")]:
            engine = DiagnosisEngine()
            engine.denoise_method = DenoiseMethod(dn)
            try:
                proc = engine.preprocess(sig_n)
                rp = np.var(sig_c - proc[:len(sig_c)])
            except Exception:
                rp = bp
            dsnr = 10 * np.log10(max(bp, 1e-12) / max(rp, 1e-12))
            result["methods"].setdefault(dl, {})[label] = round(dsnr, 2)
            print(f"    {dl}: DSNR={dsnr:+.1f}dB")

    return result


# ═════════════════════════════════════════════════
# 噪声鲁棒性
# ═════════════════════════════════════════════════
def eval_robustness():
    print(f"\n{'='*60}\n噪声鲁棒性\n{'='*60}")
    def fc(f): 
        s=f.replace(".npy","").rsplit("-",1)[0]
        for p in s.split("_"):
            if p in "HNBIOCh": return {"H":"H","N":"H","B":"B","I":"I","O":"O","C":"C"}.get(p)
    or_files = sorted(f for f in HUST.glob("*-X.npy") if fc(f.name) == "O")
    if not or_files: return None
    sig_c = load_sig(HUST, or_files[0].name)
    np.random.seed(42)
    snrs = [20, 10, 5, 0, -5]
    result = {"snr_levels": snrs, "methods": {}}

    for name, method in [("包络", BearingMethod.ENVELOPE), ("Kurtogram", BearingMethod.KURTOGRAM),
                          ("MED", BearingMethod.MED), ("MCKD", BearingMethod.MCKD)]:
        curve = []
        for s_db in snrs:
            sp = np.var(sig_c.astype(np.float64))
            noise = np.sqrt(sp / (10 ** (s_db / 10))) * np.random.randn(len(sig_c))
            try:
                engine = DiagnosisEngine(bearing_method=method, bearing_params=BP,
                                         denoise_method=DenoiseMethod.NONE)
                res = engine.analyze_bearing(sig_c + noise, FS)
                inds = res.get("fault_indicators", {})
                det = any(v.get("significant") for k, v in inds.items()
                          if isinstance(v, dict) and not k.endswith("_stat"))
                curve.append({"snr_db": s_db, "detected": det})
                print(f"    {name} SNR={s_db}dB: {'V' if det else 'X'}")
            except:
                curve.append({"snr_db": s_db, "detected": False})
        result["methods"][name] = curve

    # Ensemble robustness
    curve = []
    for s_db in snrs:
        sp = np.var(sig_c.astype(np.float64))
        noise = np.sqrt(sp / (10 ** (s_db / 10))) * np.random.randn(len(sig_c))
        try:
            res = run_research_ensemble(sig_c + noise, FS, bearing_params=BP, max_seconds=5.0)
            det = res.get("status", "normal") != "normal" or res.get("health_score", 100) < 70
            curve.append({"snr_db": s_db, "detected": det})
            print(f"    Ensemble SNR={s_db}dB: {'V' if det else 'X'}")
        except:
            curve.append({"snr_db": s_db, "detected": False})
    result["methods"]["Ensemble"] = curve
    return result


# ═════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("全面重跑评估")
    print(f"输出: {OUT}")
    print("=" * 60)

    # 1) HUST 轴承二分类 (99样本)
    hust_files = collect_hust()
    r = eval_bearing("4.2.1 HUSTbear 轴承二分类", hust_files,
                     [("标准包络", BearingMethod.ENVELOPE),
                      ("Kurtogram", BearingMethod.KURTOGRAM),
                      ("CPW预白化", BearingMethod.CPW),
                      ("MED增强", BearingMethod.MED),
                      ("MCKD", BearingMethod.MCKD),
                      ("Teager", BearingMethod.TEAGER),
                      ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
                      ("DWT", BearingMethod.DWT),
                      ("EMD", BearingMethod.EMD_ENVELOPE),
                      ("VMD", BearingMethod.VMD_ENVELOPE)])
    save("42_hust_binary.json", r)

    # 2) Ottawa 轴承二分类 (36样本)
    cw_files = collect_cw()
    r2 = eval_bearing("4.3.1 Ottawa/CW 轴承二分类", cw_files,
                      [("标准包络", BearingMethod.ENVELOPE),
                       ("Kurtogram", BearingMethod.KURTOGRAM),
                       ("CPW预白化", BearingMethod.CPW),
                       ("MED增强", BearingMethod.MED),
                       ("MCKD", BearingMethod.MCKD),
                       ("Teager", BearingMethod.TEAGER),
                       ("谱峭度重加权", BearingMethod.SPECTRAL_KURTOSIS),
                       ("DWT", BearingMethod.DWT),
                       ("EMD", BearingMethod.EMD_ENVELOPE),
                       ("VMD", BearingMethod.VMD_ENVELOPE)])
    save("43_ottawa_binary.json", r2)

    # 3) WTG 齿轮二分类
    wtg_files = collect_wtg()
    r3 = eval_gear_binary(wtg_files)
    save("44_wtg_binary.json", r3)

    # 4) 去噪
    r4 = eval_denoise()
    save("47_denoise.json", r4)

    # 5) 鲁棒性
    r5 = eval_robustness()
    if r5:
        save("46_robustness.json", r5)

    print(f"\n{'='*60}")
    print("全部完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
