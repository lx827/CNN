"""
实验B：齿轮故障分类对比

大创答辩实验，生成：
1. 齿轮指标箱线图（5种故障类型的 SER / FM4 / TSA残差峭度分布）
2. 混淆矩阵（综合诊断方法的5类分类）
3. 分离度柱状图（各指标的 healthy vs fault 分离度对比）
4. 指标汇总 Markdown 表格

使用方式:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.contest.experiment_b_gear
"""
import sys
import warnings
from pathlib import Path
from typing import Dict, List

import numpy as np

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

# ── 答辩风格 ──────────────────────────────────────────────
from .style import (
    apply_contest_style,
    COLORS,
    FIGURE_DPI,
    FIGURE_SIZE,
    FIGURE_SIZE_GRID,
    FIGURE_SIZE_TALL,
)
apply_contest_style()

# ── 答辩配置 ──────────────────────────────────────────────
from .config import (
    OUTPUT_DIR,
    EXP_DIRS,
    WTGEARBOX_DIR,
    WTGEARBOX_GEAR,
    SAMPLE_RATE,
    MAX_SAMPLES,
    MAX_PER_CLASS_WTGEARBOX,
    GEAR_LABELS,
    LABEL_CN,
    MESH_FREQ_COEFF,
)

# ── 诊断引擎 ──────────────────────────────────────────────
from app.services.diagnosis import DiagnosisEngine, GearMethod, DiagnosisStrategy, DenoiseMethod
from app.services.diagnosis.gear.metrics import compute_tsa_residual_order

# ── 评价框架（复用分类指标计算） ──────────────────────────────
# evaluation 包需从 tests/diagnosis 父路径导入（包内使用相对导入）
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))
from evaluation.classification_metrics_eval import evaluate_classification_performance, generate_classification_metrics_table
from evaluation.utils import load_npy, compute_excess_kurtosis
from evaluation.datasets import classify_wtgearbox

# ── 输出目录 ──────────────────────────────────────────────
OUT_DIR = EXP_DIRS["b_gear"]
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 齿轮指标名列表 ────────────────────────────────────────
GEAR_METRICS = ["ser", "fm4", "fm0", "car", "m6a", "m8a"]
GEAR_METRICS_CN = {
    "ser":      "SER 边频带能量比",
    "fm4":      "FM4 局部故障",
    "fm0":      "FM0 粗故障",
    "car":      "CAR 倒频谱幅值比",
    "m6a":      "M6A 高阶矩",
    "m8a":      "M8A 高阶矩",
    "tsa_kurt": "TSA残差峭度",
}

# ── 5类标签 → 箱线图颜色 ──────────────────────────────────
BOX_COLORS = {
    "healthy": COLORS["healthy"],       # #2ECC71 绿色
    "break":   COLORS["fault"],         # #E74C3C 红色
    "missing": "#E74C3C",
    "crack":   COLORS["critical"],      # #C0392B 深红
    "wear":    "#C0392B",
}


# ═══════════════════════════════════════════════════════════
# 1. 数据加载与诊断
# ═══════════════════════════════════════════════════════════

def load_wtgearbox_c1_files() -> List[Dict]:
    """加载 WTgearbox 数据集（仅 c1 通道，每类最多 MAX_PER_CLASS_WTGEARBOX 个）"""
    if not WTGEARBOX_DIR.exists():
        print(f"[SKIP] WTgearbox 数据集不存在: {WTGEARBOX_DIR}")
        return []

    from collections import defaultdict
    class_files = defaultdict(list)
    for f in sorted(WTGEARBOX_DIR.glob("*.npy")):
        if not f.name.endswith("-c1.npy"):
            continue
        info = classify_wtgearbox(f.name)
        if info["label"] == "unknown":
            continue
        class_files[info["label"]].append((f, info))

    files = []
    for lbl in GEAR_LABELS:
        files.extend(class_files[lbl][:MAX_PER_CLASS_WTGEARBOX])

    return files


def run_diagnosis(files: List[Dict]) -> List[Dict]:
    """对每个文件运行综合诊断，提取齿轮指标"""
    results = []
    engine = DiagnosisEngine(
        strategy=DiagnosisStrategy.ADVANCED,
        gear_method=GearMethod.ADVANCED,
        denoise_method=DenoiseMethod.NONE,
        gear_teeth=WTGEARBOX_GEAR,
    )

    for filepath, info in files:
        signal = load_npy(filepath, MAX_SAMPLES)
        # 从文件名提取转速
        name = filepath.name.replace(".npy", "")
        parts = name.split("-")
        main_parts = parts[0].split("_")
        try:
            rot_freq = float(main_parts[-1])
        except ValueError:
            rot_freq = 30.0  # 默认转速

        gear_result = {}
        health_score = 100
        status = "normal"
        try:
            comp = engine.analyze_comprehensive(signal, SAMPLE_RATE, rot_freq=rot_freq)
            health_score = int(comp.get("health_score", 100))
            status = comp.get("status", "normal")
            gear_result = comp.get("gear_results", {})
        except Exception as e:
            print(f"  [WARN] 诊断失败 {filepath.name}: {e}")

        # 提取标准齿轮指标
        row = {
            "file": filepath.name,
            "fault_label": info["label"],
            "rot_freq": rot_freq,
            "health_score": health_score,
            "status": status,
        }
        for key in GEAR_METRICS:
            row[key] = gear_result.get(key, 0.0)

        # TSA 残差峭度（需单独调用）
        tsa_kurt = 0.0
        try:
            tsa_result = compute_tsa_residual_order(signal, SAMPLE_RATE, rot_freq)
            if bool(tsa_result.get("valid", False)):
                diff = tsa_result.get("differential", np.array([]))
                if len(diff) > 0:
                    tsa_kurt = compute_excess_kurtosis(diff)
        except Exception:
            pass
        row["tsa_kurt"] = tsa_kurt

        results.append(row)

    return results


# ═══════════════════════════════════════════════════════════
# 2. 箱线图（5种故障类型 × 3个核心指标）
# ═══════════════════════════════════════════════════════════

def plot_boxplot(results: List[Dict]):
    """绘制齿轮指标箱线图（5种故障类型 × 3个核心指标）"""
    core_metrics = ["ser", "fm4", "tsa_kurt"]
    core_titles = [GEAR_METRICS_CN[k] for k in core_metrics]

    # 每类指标值
    data_by_label = {}
    for lbl in GEAR_LABELS:
        data_by_label[lbl] = {
            key: [r[key] for r in results if r["fault_label"] == lbl]
            for key in core_metrics
        }

    fig, axes = plt.subplots(1, 3, figsize=FIGURE_SIZE_GRID)

    for col, (metric_key, metric_title) in enumerate(core_metrics):
        ax = axes[col]
        box_data = []
        labels_cn = []
        colors = []
        for lbl in GEAR_LABELS:
            vals = data_by_label[lbl][metric_key]
            if vals:
                box_data.append(vals)
                labels_cn.append(LABEL_CN[lbl])
                colors.append(BOX_COLORS[lbl])

        if not box_data:
            ax.text(0.5, 0.5, "无数据", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(metric_title)
            continue

        bp = ax.boxplot(box_data, patch_artist=True, widths=0.6)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.85)
        for median in bp["medians"]:
            median.set_color("black")
            median.set_linewidth(2)

        ax.set_xticklabels(labels_cn, rotation=15)
        ax.set_title(metric_title)
        ax.set_ylabel(metric_title)

    fig.suptitle("齿轮指标箱线图：5种故障类型对比", fontsize=16, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "boxplot_gear_metrics.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [保存] 箱线图: {OUT_DIR / 'boxplot_gear_metrics.png'}")


# ═══════════════════════════════════════════════════════════
# 3. 混淆矩阵（5类分类）
# ═══════════════════════════════════════════════════════════

def predict_label(row: Dict) -> str:
    """从诊断结果推断预测标签

    策略：
    - status == "normal" → "healthy"
    - status != "normal" → 根据齿轮指标最大异常推断故障类型
      - SER 高 → break / wear（边频带强 → 断齿/磨损）
      - FM4 高 → crack / missing（局部缺陷 → 裂纹/缺齿）
      - FM0 高 → break（粗故障 → 断齿）
    """
    if row["status"] == "normal":
        return "healthy"

    # 故障时：综合判断
    # 用 health_score 量化严重程度
    ser = float(row.get("ser", 0.0))
    fm4 = float(row.get("fm4", 0.0))
    fm0 = float(row.get("fm0", 0.0))
    tsa_kurt = float(row.get("tsa_kurt", 0.0))

    # 基于指标特征推断（简化规则）
    if fm0 > 1.0 and tsa_kurt > 3.0:
        return "break"       # 粗故障 + 高峭度 → 断齿
    elif fm4 > 3.0 and tsa_kurt > 3.0:
        return "crack"       # 局部缺陷 + 高峭度 → 齿根裂纹
    elif ser > 0.5:
        return "wear"        # 边频带强 → 磨损/缺齿
    elif fm4 > 3.0:
        return "missing"     # 局部缺陷中等 → 缺齿
    else:
        return "wear"        # 默认归为磨损


def plot_confusion_matrix(results: List[Dict]):
    """计算并绘制5类混淆矩阵"""
    y_true = [r["fault_label"] for r in results]
    y_pred = [predict_label(r) for r in results]
    scores = [100 - r["health_score"] for r in results]  # 反转：故障→高分

    # 使用评价框架的分类指标计算（含混淆矩阵绘制）
    cls_metrics = evaluate_classification_performance(
        y_true=y_true,
        y_pred=y_pred,
        scores=scores,
        labels=GEAR_LABELS,
        output_subdir=str(OUT_DIR),
        title_prefix="齿轮",
    )

    # 答辩风格：自定义混淆矩阵（使用 COLORS 配色）
    cm = np.array(cls_metrics["confusion_matrix"])
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
    cm_norm = np.nan_to_num(cm_norm)

    labels_cn = [LABEL_CN[l] for l in GEAR_LABELS]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_TALL)
    im = ax.imshow(cm_norm, cmap="Blues", interpolation="nearest", vmin=0, vmax=1)

    ax.set_xticks(range(len(GEAR_LABELS)))
    ax.set_yticks(range(len(GEAR_LABELS)))
    ax.set_xticklabels(labels_cn, rotation=30, ha="right")
    ax.set_yticklabels(labels_cn)
    ax.set_title("齿轮故障5类分类混淆矩阵", fontsize=16)
    ax.set_xlabel("预测标签")
    ax.set_ylabel("真实标签")

    # 在格子中显示数值
    for i in range(len(GEAR_LABELS)):
        for j in range(len(GEAR_LABELS)):
            val_norm = cm_norm[i, j]
            val_raw = cm[i, j]
            text_color = "white" if float(val_norm) > 0.5 else "black"
            ax.text(j, i, f"{val_norm:.2f}\n({val_raw})",
                    ha="center", va="center", color=text_color, fontsize=11)

    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "confusion_matrix_gear.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [保存] 混淆矩阵: {OUT_DIR / 'confusion_matrix_gear.png'}")

    # 保存分类指标 Markdown
    table = generate_classification_metrics_table(cls_metrics, title="齿轮故障5类分类")
    with open(OUT_DIR / "classification_metrics.md", "w", encoding="utf-8") as f:
        f.write(table)
    print(f"  [保存] 分类指标: {OUT_DIR / 'classification_metrics.md'}")

    return cls_metrics


# ═══════════════════════════════════════════════════════════
# 4. 分离度柱状图
# ═══════════════════════════════════════════════════════════

def compute_separability(results: List[Dict]) -> Dict[str, float]:
    """计算各指标的 healthy vs fault 分离度 = |mean_fault - mean_healthy|"""
    healthy_vals = {key: [] for key in GEAR_METRICS}
    healthy_vals["tsa_kurt"] = []
    fault_vals = {key: [] for key in GEAR_METRICS}
    fault_vals["tsa_kurt"] = []

    for r in results:
        target = healthy_vals if r["fault_label"] == "healthy" else fault_vals
        for key in GEAR_METRICS:
            target[key].append(r[key])
        target["tsa_kurt"].append(r["tsa_kurt"])

    sep = {}
    all_keys = GEAR_METRICS + ["tsa_kurt"]
    for key in all_keys:
        h_mean = np.mean(healthy_vals[key]) if healthy_vals[key] else 0.0
        f_mean = np.mean(fault_vals[key]) if fault_vals[key] else 0.0
        sep[key] = abs(f_mean - h_mean)

    return sep


def plot_separability(sep: Dict[str, float]):
    """绘制分离度柱状图（综合方法用红色高亮）"""
    all_keys = GEAR_METRICS + ["tsa_kurt"]
    # 排序：按分离度从大到小
    sorted_keys = sorted(all_keys, key=lambda k: sep[k], reverse=True)
    sorted_vals = [sep[k] for k in sorted_keys]
    labels_cn = [GEAR_METRICS_CN[k] for k in sorted_keys]

    # 颜色：TSA残差峭度（综合方法核心指标）用红色高亮，其他灰色
    bar_colors = []
    for k in sorted_keys:
        if k == "tsa_kurt":
            bar_colors.append(COLORS["our_method"])   # 红色 — 我们的方法
        elif k in ("fm4", "ser"):
            bar_colors.append(COLORS["best_baseline"])  # 蓝色 — 较好 baseline
        else:
            bar_colors.append(COLORS["baseline"])       # 灰色 — baseline

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    bars = ax.barh(labels_cn, sorted_vals, color=bar_colors, edgecolor="white", height=0.6)

    # 数值标注
    for bar, val in zip(bars, sorted_vals):
        ax.text(bar.get_width() + 0.01 * max(sorted_vals, default=1),
                bar.get_y() + bar.get_height() / 2,
                f"{val:.4f}", va="center", fontsize=12)

    ax.set_xlabel("分离度 |mean_fault - mean_healthy|")
    ax.set_title("齿轮指标分离度对比（TSA残差峭度为综合方法核心指标）", fontsize=14)
    ax.invert_yaxis()  # 最大值在最上面
    ax.grid(axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "separability_gear.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [保存] 分离度柱状图: {OUT_DIR / 'separability_gear.png'}")


# ═══════════════════════════════════════════════════════════
# 5. 指标汇总 Markdown 表格
# ═══════════════════════════════════════════════════════════

def generate_summary_table(results: List[Dict], sep: Dict[str, float]) -> str:
    """生成指标汇总 Markdown 表格"""
    lines = [
        "# 实验B：齿轮故障分类对比 — 指标汇总",
        "",
        "> 数据集: WTgearbox 行星齿轮箱 (恒速 20~55Hz, c1通道)",
        "> 每类最多 {} 个样本".format(MAX_PER_CLASS_WTGEARBOX),
        "> 诊断引擎: DiagnosisEngine(ADVANCED, GearMethod=ADVANCED, DenoiseMethod=NONE)",
        "",
        "## 1. 各指标统计（按故障类型）",
        "",
    ]

    # 各类均值表
    all_keys = GEAR_METRICS + ["tsa_kurt"]
    header = "| 故障类型 | " + " | ".join(GEAR_METRICS_CN[k] for k in all_keys) + " |"
    sep_line = "|----------| " + " | ".join(["---"] * len(all_keys)) + " |"
    lines.append(header)
    lines.append(sep_line)

    for lbl in GEAR_LABELS:
        rows_lbl = [r for r in results if r["fault_label"] == lbl]
        if not rows_lbl:
            lines.append(f"| {LABEL_CN[lbl]} | " + " | ".join(["N/A"] * len(all_keys)) + " |")
            continue
        vals = []
        for key in all_keys:
            mean_val = np.mean([r[key] for r in rows_lbl])
            vals.append(f"{mean_val:.4f}")
        lines.append(f"| {LABEL_CN[lbl]} | " + " | ".join(vals) + " |")

    # 分离度表
    lines.extend([
        "",
        "## 2. 分离度（healthy vs fault）",
        "",
        "| 指标 | 健康均值 | 故障均值 | 分离度 |",
        "|------|----------|----------|--------|",
    ])

    healthy_rows = [r for r in results if r["fault_label"] == "healthy"]
    fault_rows = [r for r in results if r["fault_label"] != "healthy"]

    for key in all_keys:
        h_mean = np.mean([r[key] for r in healthy_rows]) if healthy_rows else 0.0
        f_mean = np.mean([r[key] for r in fault_rows]) if fault_rows else 0.0
        lines.append(f"| {GEAR_METRICS_CN[key]} | {h_mean:.4f} | {f_mean:.4f} | {sep[key]:.4f} |")

    # 分离度排序
    lines.extend([
        "",
        "## 3. 分离度排序（从高到低）",
        "",
    ])
    sorted_sep = sorted(sep.items(), key=lambda x: x[1], reverse=True)
    for i, (key, val) in enumerate(sorted_sep, 1):
        marker = " **" if key == "tsa_kurt" else ""
        lines.append(f"{i}. {marker}{GEAR_METRICS_CN[key]}: {val:.4f}{marker}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════

def run_experiment_b():
    """实验B：齿轮故障分类对比"""
    print("\n" + "=" * 60)
    print("【实验B】齿轮故障分类对比")
    print("=" * 60)

    # 1. 加载 WTgearbox 数据
    files = load_wtgearbox_c1_files()
    if not files:
        print("[ABORT] 无可用数据，实验终止")
        return

    print(f"  加载 WTgearbox 数据: {len(files)} 个文件")
    for lbl in GEAR_LABELS:
        n = sum(1 for _, info in files if info["label"] == lbl)
        print(f"    {LABEL_CN[lbl]}: {n} 个")

    # 2. 运行综合诊断，提取齿轮指标
    print("  运行综合诊断引擎...")
    results = run_diagnosis(files)
    print(f"  完成: {len(results)} 条诊断结果")

    # 3. 绘制箱线图
    print("  绘制齿轮指标箱线图...")
    plot_boxplot(results)

    # 4. 计算分离度
    sep = compute_separability(results)
    print("  分离度:")
    for key, val in sorted(sep.items(), key=lambda x: x[1], reverse=True):
        print(f"    {GEAR_METRICS_CN[key]}: {val:.4f}")

    # 5. 绘制分离度柱状图
    print("  绘制分离度柱状图...")
    plot_separability(sep)

    # 6. 绘制混淆矩阵
    print("  绘制混淆矩阵...")
    cls_metrics = plot_confusion_matrix(results)
    print(f"  Accuracy: {cls_metrics['accuracy']}, Macro-F1: {cls_metrics['macro_f1']}")

    # 7. 生成汇总 Markdown
    table = generate_summary_table(results, sep)
    with open(OUT_DIR / "summary_gear.md", "w", encoding="utf-8") as f:
        f.write(table)
    print(f"  [保存] 指标汇总: {OUT_DIR / 'summary_gear.md'}")

    print("\n实验B完成！输出目录: {}".format(OUT_DIR))


if __name__ == "__main__":
    run_experiment_b()