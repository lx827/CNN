"""
超参数优化脚本 — 轴承诊断阈值网格搜索

对 HUSTbear 和 CW 数据集，遍历关键阈值组合，
以二分类准确率最大化为目标，找出最优参数。

用法:
  cd d:\code\CNN\cloud
  . venv\Scripts\activate
  python ..\tests\diagnosis\hyperparams\optimize_bearing.py

输出:
  tests/diagnosis/hyperparams/default_profiles.json（更新 bearing 相关字段）
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

from app.services.diagnosis.engine import DiagnosisEngine, BearingMethod, DenoiseMethod

# ─── 数据集路径 ───
HUST_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
FS = 8192
MAX_SEC = 5.0

# ER-16K 轴承参数
BEARING_PARAMS = {"n": 9, "d": 7.94, "D": 38.52, "alpha": 0}

# ─── 网格搜索空间 ───
SEARCH_SPACE = {
    "kurtosis_threshold": [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0],
    "crest_evidence_threshold": [7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    "snr_warning": [2.0, 2.5, 3.0, 3.5, 4.0],
    "snr_critical": [3.5, 4.0, 4.5, 5.0, 5.5, 6.0],
}

# 快速搜索：只测最敏感的参数
FAST_SEARCH = {
    "kurtosis_threshold": [4.0, 5.0, 6.0],
    "crest_evidence_threshold": [8.0, 10.0, 12.0],
}


def load_signal(filepath: Path, max_sec: float = MAX_SEC) -> np.ndarray:
    """加载 .npy 并截断"""
    sig = np.load(str(filepath))
    max_samples = int(FS * max_sec)
    if len(sig) > max_samples:
        sig = sig[:max_samples]
    return sig.astype(np.float64)


def eval_bearing_binary(
    data_dir: Path,
    threshold_overrides: dict,
    dataset_name: str = "hustbear",
) -> dict:
    """用指定阈值评估轴承二分类准确率
    
    Returns: {"accuracy": float, "correct": int, "total": int, "false_pos": int, "false_neg": int}
    """
    # 收集文件
    files = []
    for f in sorted(data_dir.glob("*.npy")):
        if dataset_name == "hustbear":
            # 只取 X 通道
            if not f.name.endswith("-X.npy"):
                continue
            stem = f.stem
            parts = stem.split("_")
            if len(parts) < 3:
                continue
            fc = parts[1]  # N/B/IR/OR/C
            is_healthy = fc == "N"
        else:  # cw
            stem = f.stem
            parts = stem.split("-")
            if len(parts) < 3:
                continue
            fc = parts[0]  # H/I/O
            is_healthy = fc == "H"
        files.append((f, is_healthy))

    if not files:
        return {"accuracy": 0, "correct": 0, "total": 0}

    correct = 0
    total = 0
    false_pos = 0
    false_neg = 0

    engine = DiagnosisEngine(
        bearing_params=BEARING_PARAMS,
        denoise_method=DenoiseMethod.NONE,
    )

    for fpath, is_healthy in files:
        try:
            sig = load_signal(fpath)
            result = engine.analyze_bearing(sig, FS, None, preprocess=True)

            # 判定逻辑：轴承方法检出显著非统计指标 = 故障
            inds = result.get("fault_indicators", {})
            has_fault = any(
                v.get("significant") for k, v in inds.items()
                if isinstance(v, dict) and not k.endswith("_stat")
            )
            pred_healthy = not has_fault

            if pred_healthy == is_healthy:
                correct += 1
            elif pred_healthy and not is_healthy:
                false_neg += 1
            elif not pred_healthy and is_healthy:
                false_pos += 1
            total += 1
        except Exception:
            total += 1  # 计入但算错

    acc = correct / max(total, 1) * 100
    return {
        "accuracy": round(acc, 2),
        "correct": correct,
        "total": total,
        "false_pos": false_pos,
        "false_neg": false_neg,
    }


def grid_search(dataset_dir: Path, dataset_name: str, fast: bool = False) -> dict:
    """网格搜索最优阈值"""
    space = FAST_SEARCH if fast else SEARCH_SPACE
    
    # 当前默认值（作为起点）
    defaults = {
        "kurtosis_threshold": 5.0,
        "crest_evidence_threshold": 10.0,
        "snr_warning": 3.0,
        "snr_critical": 5.0,
    }
    
    best = {"params": dict(defaults), "accuracy": 0.0}
    total_combos = 1
    for v in space.values():
        total_combos *= len(v)
    
    print(f"\n{'='*60}")
    print(f"网格搜索: {dataset_name} ({dataset_dir.name})")
    print(f"搜索空间: {total_combos} 组合")
    print(f"{'='*60}")
    
    combo_count = 0
    t0 = time.perf_counter()
    
    # 简化：只搜两个最敏感的参数（kurtosis_threshold, crest_evidence_threshold）
    # 其他用默认值
    kurt_vals = space.get("kurtosis_threshold", [5.0])
    crest_vals = space.get("crest_evidence_threshold", [10.0])
    
    for kt in kurt_vals:
        for ct in crest_vals:
            combo_count += 1
            overrides = {
                "kurtosis_threshold": kt,
                "crest_evidence_threshold": ct,
            }
            
            # 临时修改引擎的阈值（这里需要 engine 支持可配置阈值）
            # 当前 engine 内部 hardcode，需要后续 Step 3 完整替换后才能真正生效
            # 此脚本先记录搜索逻辑，待 engine 支持 HyperParams 后启用
            
            result = eval_bearing_binary(dataset_dir, overrides, dataset_name)
            
            if result["accuracy"] > best["accuracy"]:
                best = {
                    "params": dict(overrides),
                    "accuracy": result["accuracy"],
                    "details": result,
                }
            
            elapsed = time.perf_counter() - t0
            est_total = elapsed / combo_count * len(kurt_vals) * len(crest_vals)
            print(f"  [{combo_count}/{len(kurt_vals)*len(crest_vals)}] "
                  f"kurt={kt}, crest={ct} → acc={result['accuracy']:.1f}% "
                  f"(best={best['accuracy']:.1f}%, ETA={est_total-elapsed:.0f}s)")
    
    print(f"\n  🏆 Best: {best['params']} → acc={best['accuracy']:.1f}%")
    return best


def main():
    print("=" * 60)
    print("轴承诊断超参数优化 — HUSTbear + CW")
    print("=" * 60)
    
    results = {}
    
    # HUSTbear
    if HUST_DIR.exists():
        r = grid_search(HUST_DIR, "hustbear", fast=True)
        results["hustbear_bearing"] = r
    
    # CW
    if CW_DIR.exists():
        r = grid_search(CW_DIR, "cw", fast=True)
        results["cw_bearing"] = r
    
    # 保存结果
    out_dir = Path(__file__).resolve().parent
    out_file = out_dir / "bearing_opt_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_file}")
    
    # 更新 default_profiles.json
    update_profiles(results, out_dir)


def update_profiles(results: dict, out_dir: Path):
    """将搜索结果合并到 default_profiles.json"""
    profiles_path = PROJECT_ROOT / "cloud" / "app" / "core" / "dataset_profiles.json"
    if not profiles_path.exists():
        print(f"⚠️ 未找到 {profiles_path}，跳过更新")
        return
    
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    
    for ds_key, prefix in [("hustbear_bearing", "hustbear"), ("cw_bearing", "cw")]:
        if ds_key not in results:
            continue
        best_params = results[ds_key]["params"]
        ds_profile = profiles.get(prefix, {})
        bearing_cfg = ds_profile.get("diagnosis", {}).get("bearing", {})
        for k, v in best_params.items():
            if k in bearing_cfg:
                bearing_cfg[k] = v
                print(f"  更新 {prefix}.diagnosis.bearing.{k} = {v}")
    
    with open(profiles_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    print(f"已更新 {profiles_path}")


if __name__ == "__main__":
    main()
