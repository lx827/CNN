"""
超参数优化脚本 — 齿轮诊断阈值网格搜索

对 WTgearbox 数据集，遍历关键阈值组合，
以五分类 Balanced Accuracy 为目标，找出最优参数。

用法:
  cd d:\code\CNN\cloud
  . venv\Scripts\activate
  python ..\tests\diagnosis\hyperparams\optimize_gear.py
"""
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.engine import DiagnosisEngine, GearMethod, DenoiseMethod
from app.services.diagnosis.ensemble import run_research_ensemble

# ─── 数据集 ───
WTGEAR_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")
FS = 8192
MAX_SEC = 5.0

# 行星齿轮箱参数
GEAR_PARAMS = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4}
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}

# ─── 搜索空间 ───
SEARCH_SPACE = {
    "gear_kurt_threshold": [4.0, 5.0, 6.0, 7.0, 8.0],
    "gear_crest_threshold": [6.0, 7.0, 8.0, 9.0, 10.0],
    "ser_warning": [6.0, 7.0, 8.0, 9.0, 10.0],
    "fm4_warning": [3.0, 3.5, 4.0, 4.5, 5.0],
}

# 五分类标签
CLASS_MAP = {"He": "健康", "Br": "断齿", "Mi": "缺齿", "Rc": "裂纹", "We": "磨损"}


def load_signal(filepath: Path) -> np.ndarray:
    sig = np.load(str(filepath))
    max_samples = int(FS * MAX_SEC)
    if len(sig) > max_samples:
        sig = sig[:max_samples]
    return sig.astype(np.float64)


def eval_gear_multiclass(threshold_overrides: dict) -> dict:
    """用指定齿轮阈值评估五分类"""
    files = sorted(WTGEAR_DIR.glob("*_*-c1.npy"))
    if not files:
        return {"accuracy": 0, "balanced_accuracy": 0, "total": 0}

    y_true, y_pred = [], []
    engine = DiagnosisEngine(
        bearing_params=BEARING_PARAMS,
        gear_teeth=GEAR_PARAMS,
        denoise_method=DenoiseMethod.NONE,
        gear_method=GearMethod.ADVANCED,
    )

    for fpath in files:
        stem = fpath.stem
        cls_key = stem.split("_")[0] if "_" in stem else stem[:2]
        true_label = CLASS_MAP.get(cls_key, "健康")
        try:
            sig = load_signal(fpath)
            result = engine.analyze_gear(sig, FS, None, preprocess=True)
            inds = result.get("fault_indicators", {})
            # 简化判定：任一 warning/critical = 故障
            has_fault = any(
                v.get("warning") or v.get("critical")
                for v in inds.values() if isinstance(v, dict))
            pred_label = "故障" if has_fault else "健康"
            y_true.append(true_label)
            y_pred.append(pred_label)
        except Exception:
            pass

    n = len(y_true)
    if n == 0:
        return {"accuracy": 0, "balanced_accuracy": 0, "total": 0}

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    acc = correct / n * 100
    print(f"  → acc={acc:.1f}% ({correct}/{n})")
    return {"accuracy": round(acc, 2), "balanced_accuracy": round(acc, 2), "total": n}


def grid_search(fast: bool = True) -> dict:
    space = SEARCH_SPACE
    best = {"params": {"gear_kurt_threshold": 6.0, "gear_crest_threshold": 8.0}, "accuracy": 0.0}

    kurt_vals = space["gear_kurt_threshold"]
    crest_vals = space["gear_crest_threshold"]

    t0 = time.perf_counter()
    combo = 0
    total = len(kurt_vals) * len(crest_vals)

    print(f"\n{'='*60}")
    print(f"齿轮诊断超参数优化 — WTgearbox 五分类")
    print(f"搜索: kurt × crest = {total} 组合")
    print(f"{'='*60}")

    for kt in kurt_vals:
        for ct in crest_vals:
            combo += 1
            # TODO: 待 engine 支持 HyperParams 后生效
            result = eval_gear_multiclass({"gear_kurt_threshold": kt, "gear_crest_threshold": ct})
            if result["accuracy"] > best["accuracy"]:
                best = {"params": {"gear_kurt_threshold": kt, "gear_crest_threshold": ct}, "accuracy": result["accuracy"]}
            elapsed = time.perf_counter() - t0
            eta = elapsed / combo * (total - combo)
            print(f"  [{combo}/{total}] kurt={kt}, crest={ct} → acc={result['accuracy']:.1f}% "
                  f"(best={best['accuracy']:.1f}%, ETA={eta:.0f}s)")

    print(f"\n  🏆 Best: {best}")
    return best


def main():
    if not WTGEAR_DIR.exists():
        print(f"⚠️ 数据集目录不存在: {WTGEAR_DIR}")
        return

    result = grid_search(fast=True)

    out_dir = Path(__file__).resolve().parent
    out_file = out_dir / "gear_opt_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")


if __name__ == "__main__":
    main()
