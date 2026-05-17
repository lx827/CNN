"""
独立绘图脚本 — 从已保存的 JSON 数据重新生成图表

用法：
    # 从测试1的数据重新生成
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py bearing_hustbear

    # 从测试3的数据重新生成
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py gear_wtgearbox

    # 从所有数据重新生成
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\replot.py --all
"""
import sys
import json
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

from method_eval.config import EXP_DIRS
from method_eval.visualizer import apply_style, plot_confusion_matrix, plot_method_comparison_bar


def load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 数据"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def replot_from_dir(data_dir: Path):
    """从目录下所有 results_*.json 重新生成图表"""
    json_files = sorted(data_dir.glob("results_*.json"))
    if not json_files:
        print(f"  [SKIP] 没有找到 JSON 文件")
        print(f"  提示：运行测试时会自动保存数据到 results_*.json")
        return

    apply_style()

    for json_file in json_files:
        print(f"  📊 处理: {json_file.name}")
        data = load_json(json_file)
        data_type = data.get("type")

        # 生成输出文件名（避免重复后缀）
        stem = json_file.stem.replace("results_", "")
        # 如果 stem 已经包含类型后缀，直接使用
        if data_type == "confusion_matrix":
            if not stem.endswith("_confusion"):
                stem = stem.replace("_confusion", "") + "_confusion"
            output_name = f"{stem}.svg"
        elif data_type == "accuracy_bar":
            if not stem.endswith("_bar"):
                stem = stem.replace("_bar", "") + "_bar"
            output_name = f"{stem}.svg"
        elif data_type == "roc_pr_curves":
            if not stem.endswith("_curves"):
                stem = stem.replace("_curves", "") + "_curves"
            output_name = f"{stem}.svg"
        else:
            output_name = f"{stem}.svg"

        try:
            if data_type == "confusion_matrix":
                cm = np.array(data["confusion_matrix"])
                labels = data.get("labels", [])
                method_name = data.get("method_name", "Unknown")
                accuracy = float(data.get("accuracy", 0))

                plot_confusion_matrix(
                    cm, labels, method_name, accuracy,
                    str(data_dir / output_name),
                    highlight=data.get("highlight", False),
                )

            elif data_type == "accuracy_bar":
                method_names = data.get("method_names", [])
                acc_list = [float(x) for x in data.get("method_accuracies", [])]
                plot_method_comparison_bar(
                    method_names=method_names,
                    metrics={"accuracy": acc_list},
                    metric_label="accuracy",
                    title=data.get("title", "方法准确率对比"),
                    output_path=str(data_dir / output_name),
                    highlight_indices=data.get("highlight_indices"),
                    ylim=data.get("ylim"),
                )

            else:
                print(f"    [SKIP] 未知类型: {data_type}")

        except Exception as e:
            print(f"    [ERR] 生成失败: {e}")

    print(f"  ✅ 完成")


def main():
    test_name = sys.argv[1] if len(sys.argv) > 1 else "all"

    if test_name == "all":
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║      从已保存数据重新生成全部图表                             ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        for name, dir_path in EXP_DIRS.items():
            print(f"\n{'=' * 60}")
            print(f"  测试: {name}")
            print(f"{'=' * 60}")
            if dir_path.exists():
                replot_from_dir(dir_path)
            else:
                print(f"  [SKIP] 目录不存在")
    else:
        dir_path = EXP_DIRS.get(test_name)
        if not dir_path:
            print(f"[ERROR] 未知测试: {test_name}")
            return
        print(f"  重新生成: {test_name}")
        if dir_path.exists():
            replot_from_dir(dir_path)
        else:
            print(f"  [SKIP] 目录不存在")

    print("\n  ✅ 完成！")


if __name__ == "__main__":
    main()
