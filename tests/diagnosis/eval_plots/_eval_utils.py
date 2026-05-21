"""
评估脚本公共工具 — 被所有 run_4x_*.py 引用
"""
import sys, json, time
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

OUTPUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FS = 8192
MAX_S = 5
MAX_PTS = FS * MAX_S

HUST_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
WTG_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")

BP = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GP = {"sun": 28, "ring": 100, "planet": 36, "n_planets": 4}

# ─── 数据加载 ───
def load_sig(fpath):
    sig = np.load(str(fpath)).astype(np.float64)
    return sig[:FS * MAX_S] if len(sig) > FS * MAX_S else sig

def save_json(data, name):
    p = OUTPUT_DIR / name
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {name}")

# ─── 标签 ───
def fault_hust(fname):
    stem = fname.replace(".npy", "").rsplit("-", 1)[0]
    parts = stem.split("_")
    for p in parts:
        if p in ("H", "N"): return "H"
        if p == "B": return "B"
        if p in ("I", "IR"): return "I"
        if p in ("O", "OR"): return "O"
        if p == "C": return "C"
    return None

def fault_cw(fname):
    stem = fname.replace(".npy", "")
    if stem.startswith("H-"): return "H"
    if stem.startswith("I-"): return "I"
    if stem.startswith("O-"): return "O"
    return None

def fault_wtg(fname):
    stem = fname.replace(".npy", "").split("-")[0]
    for k in ("He","Br","Mi","Rc","We"):
        if stem.startswith(k): return k
    return None

# ─── 判定逻辑 ───
def bearing_detect(result, is_healthy):
    inds = result.get("fault_indicators", {})
    has_fault = any(v.get("significant") for k, v in inds.items()
                    if isinstance(v, dict) and not k.endswith("_stat"))
    return has_fault != is_healthy

def ensemble_detect(result, is_healthy):
    """两步判定：health_score + 子方法指标兜底 (Bug #15 修复)"""
    hs = result.get("health_score", 100)
    st = result.get("status", "normal")
    if st != "normal" or hs < 70:
        return not is_healthy
    bearing = result.get("bearing", {}) or {}
    gear = result.get("gear", {}) or {}
    has_b = any(v.get("significant") for k, v in bearing.get("fault_indicators", {}).items()
                if isinstance(v, dict) and not k.endswith("_stat"))
    has_g = any(v.get("warning") or v.get("critical") for v in gear.get("fault_indicators", {}).values()
                if isinstance(v, dict))
    pred_healthy = not (has_b or has_g)
    return pred_healthy == is_healthy

def gear_detect(result, is_healthy):
    inds = result.get("fault_indicators", {})
    has_warn = any(v.get("warning") or v.get("critical") for v in inds.values() if isinstance(v, dict))
    return has_warn != is_healthy

# ─── 故障标签映射 （兼容英文 bearing_xxx / 中文 D-S 标签）───
def map_fault_label_bearing(fl) -> str:
    """ensemble fault_label → 轴承五分类标准名"""
    fl_str = str(fl).lower()
    if "bsf" in fl_str or "ball" in fl_str or "滚动体" in fl_str or "球故障" in fl_str:
        return "球故障"
    if "bpfi" in fl_str or "inner" in fl_str or "内圈" in fl_str:
        return "内圈"
    if "bpfo" in fl_str or "outer" in fl_str or "外圈" in fl_str:
        return "外圈"
    if "复合" in fl_str or "compound" in fl_str:
        return "复合"
    if "abnormal" in fl_str or "bearing_" in fl_str:
        return "外圈"
    return "健康"

def map_fault_label_cw(fl) -> str:
    """CW三分类映射"""
    fl_str = str(fl).lower()
    if "内圈" in fl_str or "bpfi" in fl_str:
        return "内圈"
    if "外圈" in fl_str or "bpfo" in fl_str:
        return "外圈"
    if "abnormal" in fl_str:
        return "外圈"
    return "健康"

def map_fault_label_gear(fl) -> str:
    """WTG五分类映射"""
    fl_str = str(fl).lower()
    if "断齿" in fl_str or "break" in fl_str:
        return "断齿"
    if "缺齿" in fl_str or "missing" in fl_str:
        return "缺齿"
    if "裂纹" in fl_str or "crack" in fl_str:
        return "裂纹"
    if "磨损" in fl_str or "wear" in fl_str:
        return "磨损"
    if "abnormal" in fl_str:
        return "磨损"
    return "健康"

# ─── 指标计算 ───
def compute_metrics(y_true, y_pred, classes=None):
    n = len(y_true)
    if n == 0: return {}
    if classes is None:
        classes = sorted(set(y_true))
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    acc = correct / n
    # Per-class metrics
    per_class = {}
    for cls in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-12)
        per_class[cls] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}
    bal_acc = sum(per_class[c]["recall"] for c in classes) / len(classes)
    macro_f1 = sum(per_class[c]["f1"] for c in classes) / len(classes)
    return {
        "accuracy": round(acc, 4), "balanced_accuracy": round(bal_acc, 4),
        "macro_f1": round(macro_f1, 4), "total": n,
        "per_class": per_class,
    }

def compute_cm(y_true, y_pred, classes):
    n = len(classes)
    cm = [[0] * n for _ in range(n)]
    idx = {c: i for i, c in enumerate(classes)}
    for t, p in zip(y_true, y_pred):
        cm[idx[t]][idx[p]] += 1
    return cm
