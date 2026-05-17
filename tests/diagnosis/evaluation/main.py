"""
故障诊断算法多维度评价框架 - 主入口

用法:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.evaluation.main

或:
    cd /d/code/CNN
    python tests/diagnosis/evaluation/main.py
"""
import sys
from pathlib import Path

# 确保项目路径正确
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

from evaluation.denoise_eval import evaluate_denoise_methods
from evaluation.bearing_eval import evaluate_bearing_methods
from evaluation.gear_eval import evaluate_gear_methods
from evaluation.comprehensive_eval import evaluate_comprehensive_diagnosis
from evaluation.robustness_eval import evaluate_noise_robustness
from evaluation.ds_fusion_eval import evaluate_ds_fusion
from evaluation.health_trend_eval import evaluate_health_trend
from evaluation.channel_consensus_eval import evaluate_channel_consensus
from evaluation.report_generator import generate_final_report


def _limit_files(files, max_per_class=5):
    """限制每个类别的文件数量，加快评价速度"""
    from collections import defaultdict
    class_files = defaultdict(list)
    for f, info in files:
        lbl = info.get("label", "unknown")
        class_files[lbl].append((f, info))
    result = []
    for lbl in sorted(class_files.keys()):
        result.extend(class_files[lbl][:max_per_class])
    return result


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      故障诊断算法多维度评价框架                                ║")
    print("║      HUSTbear + CW + WTgearbox 三数据集全面评估              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Phase 1-2: 基础评价模块
    denoise_results = evaluate_denoise_methods()
    bearing_results = evaluate_bearing_methods()
    gear_results = evaluate_gear_methods()
    comprehensive_results = evaluate_comprehensive_diagnosis()
    robustness_results = evaluate_noise_robustness()

    # Phase 3: 高级评价模块
    ds_fusion_results = evaluate_ds_fusion()
    health_trend_results = evaluate_health_trend()
    channel_consensus_results = evaluate_channel_consensus()

    # Phase 4: 生成最终报告
    generate_final_report(
        denoise_results,
        bearing_results,
        gear_results,
        comprehensive_results,
        robustness_results,
        ds_fusion_results,
        health_trend_results,
        channel_consensus_results,
    )

    from evaluation.config import OUTPUT_DIR
    print("\n" + "=" * 60)
    print("  全部评价完成！")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
