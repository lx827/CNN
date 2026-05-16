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
from evaluation.report_generator import generate_final_report


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      故障诊断算法多维度评价框架                                ║")
    print("║      HUSTbear + CW + WTgearbox 三数据集全面评估              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # 运行各评价模块
    denoise_results = evaluate_denoise_methods()
    bearing_results = evaluate_bearing_methods()
    gear_results = evaluate_gear_methods()
    comprehensive_results = evaluate_comprehensive_diagnosis()
    robustness_results = evaluate_noise_robustness()

    # 生成最终报告
    generate_final_report(
        denoise_results,
        bearing_results,
        gear_results,
        comprehensive_results,
        robustness_results,
    )

    from evaluation.config import OUTPUT_DIR
    print("\n" + "=" * 60)
    print("  全部评价完成！")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
