"""
大创答辩图表一键生成 - 主入口

用法:
    cd /d/code/CNN/cloud
    . venv/Scripts/activate
    python -m tests.diagnosis.contest.main

或:
    cd /d/code/CNN
    python tests/diagnosis/contest/main.py
"""
import sys
import time
from pathlib import Path

# 确保项目路径正确
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

from contest.style import apply_contest_style
from contest.config import OUTPUT_DIR, EXP_DIRS


def main():
    apply_contest_style()  # 全局应用统一风格

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      大创答辩专用图表生成框架                                 ║")
    print('║      以「图」服人、以「数」服人、以「对比」服人                    ║')
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    experiments = [
        ("A", "轴承故障分类对比",   "experiment_a_bearing",  "run_experiment_a"),
        ("B", "齿轮故障分类对比",   "experiment_b_gear",     "run_experiment_b"),
        ("C", "去噪效果对比",       "experiment_c_denoise",  "run_experiment_c"),
        ("D", "噪声鲁棒性衰减曲线", "experiment_d_robustness", "run_experiment_d"),
        ("E", "D-S融合增益分析",   "experiment_e_fusion",    "run_experiment_e"),
        ("F", "健康度退化轨迹",     "experiment_f_health",    "run_experiment_f"),
    ]

    results_summary = {}

    for code, desc, module_name, func_name in experiments:
        print(f"\n{'=' * 60}")
        print(f"  【实验{code}】 {desc}")
        print(f"{'=' * 60}")

        try:
            mod = __import__(f"contest.{module_name}", fromlist=[func_name])
            func = getattr(mod, func_name)
            result = func()
            results_summary[code] = {"desc": desc, "status": "OK", "result": result}
            print(f"  ✓ 实验{code}完成")
        except Exception as e:
            results_summary[code] = {"desc": desc, "status": "FAIL", "error": str(e)}
            print(f"  ✗ 实验{code}失败: {e}")

    # ── 打印汇总 ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  大创答辩图表生成汇总")
    print(f"{'=' * 60}")

    for code, info in results_summary.items():
        status_mark = "✓" if info["status"] == "OK" else "✗"
        print(f"  {status_mark} 实验{code} — {info['desc']}: {info['status']}")

    print(f"\n  输出目录: {OUTPUT_DIR}")
    print(f"  生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    ok_count = sum(1 for v in results_summary.values() if v["status"] == "OK")
    print(f"\n  成功: {ok_count}/{len(experiments)}")
    print("=" * 60)


if __name__ == "__main__":
    main()