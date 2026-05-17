"""
高级分类量化指标核心模块

统一计算混淆矩阵、ROC/PR 曲线、Kappa、MCC、Macro-F1、Balanced Accuracy、FDR/MDR/FIA，
供所有诊断模块调用。
"""
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from .config import OUTPUT_DIR
from .utils import (
    compute_confusion_matrix,
    compute_balanced_accuracy,
    compute_cohen_kappa,
    compute_mcc,
    compute_macro_f1,
    compute_weighted_f1,
    compute_fdr_far_mdr_fia,
    compute_multiclass_roc_pr,
    plot_confusion_matrix,
    plot_roc_curves,
    plot_pr_curves,
    save_cache,
)


def evaluate_classification_performance(
    y_true: List[str],
    y_pred: List[str],
    scores: List[float],
    labels: List[str],
    output_subdir: str = "classification",
    title_prefix: str = "",
) -> Dict[str, Any]:
    """
    统一计算所有高级分类指标，并保存图表。

    Parameters
    ----------
    y_true : 真实标签列表
    y_pred : 预测标签列表
    scores : 连续分数（如 health_score，用于 ROC）
    labels : 所有类别标签
    output_subdir : 输出图表子目录
    title_prefix : 图表标题前缀（如 "轴承" / "齿轮"）

    Returns
    -------
    字典包含：
    - confusion_matrix: np.ndarray
    - accuracy, balanced_accuracy
    - macro_f1, weighted_f1
    - cohen_kappa, mcc
    - fdr, far, mdr, fia, detection_score
    - roc_curves: Dict[label, (fpr, tpr, auc)]
    - pr_curves: Dict[label, (recall, precision, auc)]
    - macro_auc_roc, macro_auc_pr
    """
    print(f"  [分类指标] 计算 {title_prefix} 分类性能 ({len(y_true)} 样本, {len(labels)} 类)...")

    # 混淆矩阵
    cm = compute_confusion_matrix(y_true, y_pred, labels)

    # 基础分类指标
    total = len(y_true)
    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    accuracy = correct / total if total > 0 else 0.0

    # 高级指标
    balanced_acc = compute_balanced_accuracy(y_true, y_pred, labels)
    kappa = compute_cohen_kappa(y_true, y_pred, labels)
    mcc = compute_mcc(y_true, y_pred, labels)
    macro_f1 = compute_macro_f1(y_true, y_pred, labels)
    weighted_f1 = compute_weighted_f1(y_true, y_pred, labels)

    # FDD 专用指标
    fdd_metrics = compute_fdr_far_mdr_fia(y_true, y_pred, labels)

    # ROC / PR 曲线
    roc_pr = compute_multiclass_roc_pr(y_true, scores, labels)

    # 绘制图表
    title = title_prefix if title_prefix else "分类"
    out_dir = Path(output_subdir) if output_subdir else Path("classification")

    plot_confusion_matrix(cm, labels, f"{title} 淰淆矩阵", str(out_dir), normalize=True)
    plot_confusion_matrix(cm, labels, f"{title} 混淆矩阵(原始)", str(out_dir), normalize=False)
    plot_roc_curves(roc_pr["roc"], f"{title} ROC曲线", str(out_dir))
    plot_pr_curves(roc_pr["pr"], f"{title} PR曲线", str(out_dir))

    result = {
        "confusion_matrix": cm.tolist(),
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced_acc, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "cohen_kappa": round(kappa, 4),
        "mcc": round(mcc, 4),
        **fdd_metrics,
        "roc_curves": roc_pr["roc"],
        "pr_curves": roc_pr["pr"],
        "macro_auc_roc": roc_pr["macro_auc_roc"],
        "macro_auc_pr": roc_pr["macro_auc_pr"],
    }

    cache_name = f"classification_metrics_{title_prefix.lower().replace(' ', '_')}" if title_prefix else "classification_metrics"
    save_cache(cache_name, result)

    return result


def generate_classification_metrics_table(metrics: Dict[str, Any], title: str = "") -> str:
    """生成分类指标汇总 Markdown 表格"""
    lines = [
        f"## {title} 分类量化指标汇总",
        "",
        "### 核心分类指标",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| Accuracy | {metrics['accuracy']} |",
        f"| Balanced Accuracy | {metrics['balanced_accuracy']} |",
        f"| Macro-F1 | {metrics['macro_f1']} |",
        f"| Weighted-F1 | {metrics['weighted_f1']} |",
        f"| Cohen's Kappa | {metrics['cohen_kappa']} |",
        f"| MCC | {metrics['mcc']} |",
        "",
        "### FDD 专用指标",
        "",
        "| 指标 | 值 | 说明 |",
        "|------|-----|------|",
        f"| FDR (故障检出率) | {metrics['fdr']} | TP/(TP+FN) |",
        f"| FAR (虚警率) | {metrics['far']} | FP/(FP+TN) |",
        f"| MDR (漏检率) | {metrics['mdr']} | FN/(TP+FN) |",
        f"| FIA (故障隔离准确率) | {metrics['fia']} | 正确隔离/总故障 |",
        f"| Detection Score | {metrics['detection_score']} | FDR - FAR |",
        "",
        "### ROC / PR 汇总",
        "",
        f"| Macro-AUC-ROC | {metrics['macro_auc_roc']} |",
        f"| Macro-AUC-PR | {metrics['macro_auc_pr']} |",
        "",
    ]

    # 混淆矩阵表格
    cm = np.array(metrics["confusion_matrix"])
    labels = list(metrics.get("roc_curves", {}).keys())
    if len(labels) == 0 and cm.shape[0] > 0:
        labels = [f"类{i}" for i in range(cm.shape[0])]

    if cm.shape[0] > 0 and len(labels) == cm.shape[0]:
        lines.append("### 混淆矩阵")
        lines.append("")
        header = "| 真实\\预测 | " + " | ".join(labels) + " |"
        sep = "|-----------| " + " | ".join(["---"] * len(labels)) + " |"
        lines.append(header)
        lines.append(sep)
        for i, lbl in enumerate(labels):
            row = f"| {lbl} | " + " | ".join(str(cm[i, j]) for j in range(len(labels))) + " |"
            lines.append(row)
        lines.append("")

    # 各类 ROC-AUC
    if metrics.get("roc_curves"):
        lines.append("### 各类 ROC-AUC")
        lines.append("")
        lines.append("| 类别 | AUC-ROC | AUC-PR |")
        lines.append("|------|---------|--------|")
        for lbl, roc in metrics["roc_curves"].items():
            pr = metrics.get("pr_curves", {}).get(lbl, {})
            roc_auc = roc.get("auc", 0.0)
            pr_auc = pr.get("auc", 0.0)
            lines.append(f"| {lbl} | {roc_auc} | {pr_auc} |")
        lines.append("")

    return "\n".join(lines)