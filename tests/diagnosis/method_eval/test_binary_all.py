"""
测试 4：二分类全数据集汇总

在所有三个数据集上运行二分类评估（健康 vs 故障），生成：
- 跨数据集对比柱状图
- 雷达图（Top 5 方法）
- 汇总 Markdown 报告

运行方式：
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\test_binary_all.py
"""
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════
# 路径设置
# ═══════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CLOUD_PATH = PROJECT_ROOT / "cloud"
sys.path.insert(0, str(CLOUD_PATH))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

# ═══════════════════════════════════════════════════════════
# 导入配置
# ═══════════════════════════════════════════════════════════
from method_eval.config import (
    HUSTBEAR_DIR, CW_DIR, WTGEARBOX_DIR,
    SAMPLE_RATE, MAX_SAMPLES,
    BEARING_PARAMS, GEAR_PARAMS,
    HEALTH_THRESHOLD, ENSEMBLE_PROFILE, ENSEMBLE_MAX_SECONDS,
    EXP_DIRS,
)
from method_eval.label_mapper import infer_binary_label
from method_eval.visualizer import (
    apply_style, plot_method_comparison_bar, plot_radar_chart,
)

apply_style()

# ═══════════════════════════════════════════════════════════
# 导入诊断引擎
# ═══════════════════════════════════════════════════════════
from app.services.diagnosis.engine import (
    DiagnosisEngine, BearingMethod, GearMethod, DiagnosisStrategy, DenoiseMethod,
)
from app.services.diagnosis.ensemble import run_research_ensemble
from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum

# ═══════════════════════════════════════════════════════════
# 导入评价工具
# ═══════════════════════════════════════════════════════════
from evaluation.datasets import classify_hustbear, classify_cw, classify_wtgearbox
from evaluation.utils import load_npy

# ═══════════════════════════════════════════════════════════
# 输出目录
# ═══════════════════════════════════════════════════════════
OUTPUT_DIR = EXP_DIRS["binary_all"]

# 快速模式：5 个代表性方法
METHODS_ACTIVE = [
    ("标准包络", "envelope"), ("MCKD", "mckd"), ("DWT", "dwt"),
    ("EMD", "emd_envelope"), ("谱峭度重加权", "spectral_kurtosis"),
]
# 全量模式：取消注释下面一行
# METHODS_ACTIVE = [(n, v) for n, v in [
#     ("标准包络", "envelope"), ("Kurtogram", "kurtogram"),
#     ("CPW预白化", "cpw"), ("MED增强", "med"), ("MCKD", "mckd"),
#     ("Teager", "teager"), ("谱峭度重加权", "spectral_kurtosis"),
#     ("DWT", "dwt"), ("EMD", "emd_envelope"), ("CEEMDAN", "ceemdan_envelope"),
#     ("VMD", "vmd_envelope"),
# ] if v not in SKIP_METHODS]


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def _get_binary_files():
    """获取所有数据集的二分类文件"""
    datasets = {
        "HUSTbear": [],
        "CW": [],
        "WTgearbox": [],
    }

    # HUSTbear (X 通道)
    if HUSTBEAR_DIR.exists():
        for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
            if not f.name.endswith("-X.npy"):
                continue
            info = classify_hustbear(f.name)
            if info["label"] != "unknown":
                datasets["HUSTbear"].append((f, info))

    # CW
    if CW_DIR.exists():
        for f in sorted(CW_DIR.glob("*.npy")):
            info = classify_cw(f.name)
            if info["label"] != "unknown":
                datasets["CW"].append((f, info))

    # WTgearbox (c1 通道)
    if WTGEARBOX_DIR.exists():
        for f in sorted(WTGEARBOX_DIR.glob("*.npy")):
            if not f.name.endswith("-c1.npy"):
                continue
            info = classify_wtgearbox(f.name)
            if info["label"] != "unknown":
                datasets["WTgearbox"].append((f, info))

    return datasets


def _run_bearing_method(files, bm_value):
    """在轴承数据集上运行单一方法"""
    y_true = []
    y_pred = []
    exec_times = []
    bm_enum = BearingMethod(bm_value)

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            rf = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

            t0 = time.perf_counter()
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.ADVANCED,
                bearing_method=bm_enum,
                denoise_method=DenoiseMethod.NONE,
                bearing_params=BEARING_PARAMS,
            )
            result = engine.analyze_bearing(signal, SAMPLE_RATE, rot_freq=rf)
            elapsed = (time.perf_counter() - t0) * 1000

            indicators = result.get("fault_indicators", {}) or {}
            has_fault = any(
                isinstance(v, dict) and v.get("significant") and not k.endswith("_stat")
                for k, v in indicators.items()
            )

            y_true.append("fault" if info["label"] != "healthy" else "healthy")
            y_pred.append("fault" if has_fault else "healthy")
            exec_times.append(elapsed)

        except Exception as e:
            true = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true)
            y_pred.append("healthy")
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    return acc, exec_times


def _run_gear_method(files, gm_value):
    """在齿轮数据集上运行单一方法"""
    y_true = []
    y_pred = []
    exec_times = []
    gm_enum = GearMethod(gm_value)

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            name = filepath.name.replace(".npy", "")
            parts = name.split("-")
            main_parts = parts[0].split("_")
            try:
                rot_freq = float(main_parts[-1])
            except ValueError:
                rot_freq = 30.0

            t0 = time.perf_counter()
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.ADVANCED,
                gear_method=gm_enum,
                denoise_method=DenoiseMethod.NONE,
                gear_teeth=GEAR_PARAMS,
            )
            result = engine.analyze_gear(signal, SAMPLE_RATE, rot_freq=rot_freq)
            elapsed = (time.perf_counter() - t0) * 1000

            indicators = result.get("fault_indicators", {}) or {}
            has_fault = any(
                isinstance(v, dict) and (v.get("warning") or v.get("critical"))
                for v in indicators.values()
            )

            y_true.append("fault" if info["label"] != "healthy" else "healthy")
            y_pred.append("fault" if has_fault else "healthy")
            exec_times.append(elapsed)

        except Exception as e:
            true = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true)
            y_pred.append("healthy")
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    return acc, exec_times


def _run_ensemble(files, bearing_params, gear_teeth):
    """运行 Ensemble"""
    y_true = []
    y_pred = []
    exec_times = []

    for filepath, info in files:
        try:
            signal = load_npy(filepath, MAX_SAMPLES)
            rf = estimate_rot_freq_spectrum(signal, SAMPLE_RATE)

            t0 = time.perf_counter()
            result = run_research_ensemble(
                signal, SAMPLE_RATE,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
                denoise_method="none",
                rot_freq=rf,
                profile=ENSEMBLE_PROFILE,
                max_seconds=ENSEMBLE_MAX_SECONDS,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            hs = int(result.get("health_score", 100))

            true = "fault" if info["label"] != "healthy" else "healthy"
            pred = infer_binary_label(hs)

            y_true.append(true)
            y_pred.append(pred)
            exec_times.append(elapsed)

        except Exception as e:
            true = "fault" if info["label"] != "healthy" else "healthy"
            y_true.append(true)
            y_pred.append("healthy")
            exec_times.append(0.0)

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    return acc, exec_times


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def test_binary_all() -> Dict[str, Any]:
    print("\n" + "=" * 70)
    print("  测试 4：二分类全数据集汇总")
    print(f"  输出:   {OUTPUT_DIR}")
    print("=" * 70)

    # ── 1. 加载数据 ──
    datasets = _get_binary_files()
    for name, files in datasets.items():
        n = len(files)
        n_fault = sum(1 for _, i in files if i["label"] != "healthy")
        n_healthy = n - n_fault
        print(f"  {name}: {n} 个 (健康={n_healthy}, 故障={n_fault})")

    # ── 2. 运行轴承方法 ──
    hustbear_files = datasets["HUSTbear"]
    cw_files = datasets["CW"]
    wtgearbox_files = datasets["WTgearbox"]

    all_results = {}  # {method_name: {"HUSTbear": acc, "CW": acc, "WTgearbox": acc}}

    for display_name, bm_value in METHODS_ACTIVE:
        print(f"\n  ▶ {display_name}")

        if hustbear_files:
            acc_h, _ = _run_bearing_method(hustbear_files, bm_value)
            print(f"    HUSTbear: {acc_h:.2%}")
        else:
            acc_h = 0.0

        if cw_files:
            acc_c, _ = _run_bearing_method(cw_files, bm_value)
            print(f"    CW:       {acc_c:.2%}")
        else:
            acc_c = 0.0

        if wtgearbox_files:
            acc_w, _ = _run_gear_method(wtgearbox_files, "standard")  # 齿轮方法
            print(f"    WTgear:   {acc_w:.2%}")
        else:
            acc_w = 0.0

        all_results[display_name] = {
            "HUSTbear": acc_h, "CW": acc_c, "WTgearbox": acc_w,
            "avg": (acc_h + acc_c + acc_w) / 3,
        }

    # ── 3. 运行 Ensemble ──
    print(f"\n  ▶ Ensemble")
    if hustbear_files:
        acc_h_e, _ = _run_ensemble(hustbear_files, BEARING_PARAMS, None)
        print(f"    HUSTbear: {acc_h_e:.2%}")
    else:
        acc_h_e = 0.0

    if cw_files:
        acc_c_e, _ = _run_ensemble(cw_files, BEARING_PARAMS, None)
        print(f"    CW:       {acc_c_e:.2%}")
    else:
        acc_c_e = 0.0

    if wtgearbox_files:
        acc_w_e, _ = _run_ensemble(wtgearbox_files, None, GEAR_PARAMS)
        print(f"    WTgear:   {acc_w_e:.2%}")
    else:
        acc_w_e = 0.0

    all_results["Ensemble"] = {
        "HUSTbear": acc_h_e, "CW": acc_c_e, "WTgearbox": acc_w_e,
        "avg": (acc_h_e + acc_c_e + acc_w_e) / 3,
    }

    # ═══════════════════════════════════════════════════════
    # 4. 生成图表
    # ═══════════════════════════════════════════════════════
    print("\n  ── 生成图表 ──")

    method_names = list(all_results.keys())
    ensemble_idx = len(method_names) - 1

    # 柱状图 — HUSTbear
    acc_list_h = [all_results[m]["HUSTbear"] for m in method_names]
    plot_method_comparison_bar(
        method_names=method_names, metrics={"accuracy": acc_list_h},
        metric_label="accuracy", title="HUSTbear 恒速轴承二分类准确率",
        output_path=str(OUTPUT_DIR / "bar_hustbear.svg"),
        highlight_indices=[ensemble_idx], ylim=(0.5, 1.05),
    )

    # 柱状图 — CW
    acc_list_c = [all_results[m]["CW"] for m in method_names]
    plot_method_comparison_bar(
        method_names=method_names, metrics={"accuracy": acc_list_c},
        metric_label="accuracy", title="CW 变速轴承二分类准确率",
        output_path=str(OUTPUT_DIR / "bar_cw.svg"),
        highlight_indices=[ensemble_idx], ylim=(0.5, 1.05),
    )

    # 柱状图 — WTgearbox
    acc_list_w = [all_results[m]["WTgearbox"] for m in method_names]
    plot_method_comparison_bar(
        method_names=method_names, metrics={"accuracy": acc_list_w},
        metric_label="accuracy", title="WTgearbox 齿轮二分类准确率",
        output_path=str(OUTPUT_DIR / "bar_wtgearbox.svg"),
        highlight_indices=[ensemble_idx], ylim=(0.5, 1.05),
    )

    # 雷达图 — Top 5
    sorted_methods = sorted(all_results.items(), key=lambda x: x[1]["avg"], reverse=True)[:5]
    top_names = [m[0] for m in sorted_methods]
    dimensions = ["HUSTbear", "CW", "WTgearbox"]
    data = np.array([[m[1]["HUSTbear"], m[1]["CW"], m[1]["WTgearbox"]] for m in sorted_methods])

    plot_radar_chart(
        method_names=top_names, dimensions=dimensions,
        data=data, output_path=str(OUTPUT_DIR / "radar_top5.svg"),
        highlight_indices=[i for i, m in enumerate(sorted_methods) if m[0] == "Ensemble"],
        title="Top 5 方法跨数据集二分类准确率雷达图",
    )

    # ═══════════════════════════════════════════════════════
    # 5. Markdown 报告
    # ═══════════════════════════════════════════════════════
    lines = [
        "# 二分类全数据集汇总报告",
        "",
        f"> 数据集: HUSTbear ({len(hustbear_files)}), CW ({len(cw_files)}), WTgearbox ({len(wtgearbox_files)})",
        f"> 方法: {len(METHODS_ACTIVE)} 种 + Ensemble",
        "",
        "| 方法 | HUSTbear | CW 变速 | WTgearbox | 平均 |",
        "|------|---------|---------|-----------|------|",
    ]
    for name in method_names:
        r = all_results[name]
        marker = " **" if name == "Ensemble" else ""
        lines.append(
            f"| {name}{marker} | {r['HUSTbear']:.2%} | {r['CW']:.2%} | {r['WTgearbox']:.2%} | {r['avg']:.2%} |"
        )

    with open(OUTPUT_DIR / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ═══════════════════════════════════════════════════════
    # 6. 打印摘要
    # ═══════════════════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("  测试 4 完成！")
    print(f"{'=' * 70}")
    print("\n  跨数据集平均准确率 (Top 5):")
    for name in top_names:
        print(f"    {name}: {all_results[name]['avg']:.2%}")
    print(f"\n  图表目录: {OUTPUT_DIR}")

    return all_results


if __name__ == "__main__":
    test_binary_all()
