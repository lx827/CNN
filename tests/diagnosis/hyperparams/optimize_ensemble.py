"""
超参数优化脚本 — Ensemble 投票/D-S 融合阈值网格搜索

对全部三个数据集，搜索最佳融合阈值。
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

from app.services.diagnosis.ensemble import run_research_ensemble

# ─── 数据集 ───
HUST_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
WTGEAR_DIR = Path(r"D:\code\wavelet_study\dataset\WTgearbox\down8192")
FS = 8192

BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}
GEAR_PARAMS = {"sun": 28, "ring": 100, "planet": 36, "planet_count": 4}

# ─── 搜索空间 ───
SEARCH_SPACE = {
    "ds_dominant_prob": [0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    "ds_uncertainty_max": [0.20, 0.25, 0.30, 0.35, 0.40],
    "bearing_confidence_threshold": [0.45, 0.50, 0.55, 0.60, 0.65],
}


def load_signal(filepath: Path, max_sec: float = 5.0) -> np.ndarray:
    sig = np.load(str(filepath))
    max_samples = int(FS * max_sec)
    if len(sig) > max_samples:
        sig = sig[:max_samples]
    return sig.astype(np.float64)


def eval_binary(data_dir, dataset_name, bearing_params, gear_teeth=None):
    """二分类评估"""
    files = []
    for f in sorted(data_dir.glob("*.npy")):
        if dataset_name == "hustbear":
            if not f.name.endswith("-X.npy"):
                continue
            fc = f.stem.split("_")[1]
            is_healthy = fc == "N"
        elif dataset_name == "cw":
            fc = f.stem.split("-")[0]
            is_healthy = fc == "H"
        else:  # wtgearbox
            if not f.name.endswith("-c1.npy"):
                continue
            fc = f.stem.split("_")[0]
            is_healthy = fc == "He"
        files.append((f, is_healthy))

    correct = total = 0
    for fpath, is_h in files:
        try:
            sig = load_signal(fpath)
            res = run_research_ensemble(
                sig, FS, bearing_params=bearing_params,
                gear_teeth=gear_teeth, max_seconds=5.0,
            )
            hs = res.get("health_score", 100)
            st = res.get("status", "normal")
            pred_h = st == "normal" and hs >= 70
            if pred_h == is_h:
                correct += 1
            total += 1
        except Exception:
            total += 1

    return {"accuracy": round(correct / max(total, 1) * 100, 2), "correct": correct, "total": total}


def main():
    print("=" * 60)
    print("Ensemble D-S 融合超参数优化")
    print("⚠️ 当前 engine 尚未完全接入 HyperParams，脚本记录搜索框架")
    print("=" * 60)

    # 保存搜索空间供后续使用
    out_dir = Path(__file__).resolve().parent
    out_file = out_dir / "ensemble_opt_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "search_space": SEARCH_SPACE,
            "status": "pending_engine_hyperparams_support",
            "note": "待 engine/ensemble 完全接入 HyperParams 后运行网格搜索"
        }, f, ensure_ascii=False, indent=2)
    print(f"搜索空间已保存: {out_file}")


if __name__ == "__main__":
    main()
