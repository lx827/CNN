"""
评估结果数据保存工具

将数据分析与绘图流程分离：
1. 测试运行时保存结果到 JSON
2. 修改绘图代码后，从 JSON 重新生成图表，无需重跑数据
"""
import json
import numpy as np
from pathlib import Path
from typing import Any, Dict, List


def _convert_for_json(obj):
    """将 numpy 类型转换为 Python 原生类型"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def save_confusion_matrix_results(cm, labels, method_name, accuracy, output_path, highlight=False):
    """保存混淆矩阵数据到 JSON"""
    data = {
        "type": "confusion_matrix",
        "confusion_matrix": _convert_for_json(cm),
        "labels": labels,
        "method_name": method_name,
        "accuracy": float(accuracy),
        "highlight": highlight,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 数据已保存: {output_path}")


def save_accuracy_bar_results(method_names, accuracies, title, output_path, highlight_indices=None, ylim=None):
    """保存准确率柱状图数据到 JSON"""
    data = {
        "type": "accuracy_bar",
        "method_names": method_names,
        "method_accuracies": [float(x) for x in accuracies],
        "title": title,
        "highlight_indices": highlight_indices,
        "ylim": ylim,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 数据已保存: {output_path}")


def save_roc_pr_results(roc_data, pr_data, macro_auc_roc, macro_auc_pr, output_path):
    """保存 ROC/PR 曲线数据到 JSON"""
    data = {
        "type": "roc_pr_curves",
        "roc_curves": roc_data,
        "pr_curves": pr_data,
        "macro_auc_roc": float(macro_auc_roc),
        "macro_auc_pr": float(macro_auc_pr),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 数据已保存: {output_path}")
