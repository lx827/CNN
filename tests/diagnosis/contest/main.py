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


def _generate_master_report(results_summary: dict):
    """在所有实验完成后，生成总报告，汇总各实验结果和图表清单"""
    lines = [
        "# 大创答辩实验总报告",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 输出目录：{OUTPUT_DIR}",
        "",
        "## 实验总览",
        "",
        "| 实验 | 描述 | 状态 |",
        "|------|------|------|",
    ]
    for code, info in results_summary.items():
        desc = info["desc"]
        status = info["status"]
        mark = "✅" if status == "OK" else "❌"
        lines.append(f"| {code} | {desc} | {mark} {status} |")

    ok_count = sum(1 for v in results_summary.values() if v["status"] == "OK")
    lines.append(f"| **合计** | **6 个实验** | **{ok_count}/6 成功** |")
    lines.append("")

    # ── 各实验图表清单 ──────────────────────────────────────
    lines.append("## 图表清单")
    lines.append("")

    exp_chart_map = {
        "A": {
            "dir": EXP_DIRS["a_bearing"],
            "charts": [
                ("fig1_confusion_matrix_comparison.svg", "混淆矩阵对比图"),
                ("fig2_accuracy_bar.svg", "准确率柱状图"),
                ("fig3_roc_comparison.svg", "ROC曲线对比图"),
            ],
            "tables": [("metrics_summary.md", "分类指标汇总表")],
        },
        "B": {
            "dir": EXP_DIRS["b_gear"],
            "charts": [
                ("boxplot_gear_metrics.svg", "齿轮指标箱线图"),
                ("confusion_matrix_gear.svg", "混淆矩阵"),
                ("separability_gear.svg", "分离度柱状图"),
            ],
            "tables": [("classification_metrics.md", "分类指标"), ("summary_gear.md", "指标汇总")],
        },
        "C": {
            "dir": EXP_DIRS["c_denoise"],
            "charts": [
                ("fig1_waveform_comparison.svg", "波形对比图"),
                ("fig2_delta_snr.svg", "ΔSNR柱状图"),
                ("fig3_multi_metrics.svg", "多指标对比图"),
            ],
            "tables": [("experiment_c_denoise.md", "去噪指标汇总表")],
        },
        "D": {
            "dir": EXP_DIRS["d_robustness"],
            "charts": [
                ("snr_accuracy_decay.svg", "SNR-准确率衰减曲线"),
                ("robustness_index_bar.svg", "鲁棒性指数柱状图"),
            ],
            "tables": [("critical_snr_table.txt", "Critical SNR汇总表")],
        },
        "E": {
            "dir": EXP_DIRS["e_fusion"],
            "charts": [
                ("far_reduction.svg", "FAR降低柱状图"),
                ("confidence_dist.svg", "置信度分布对比图"),
            ],
            "tables": [("fusion_gain.md", "融合增益汇总")],
        },
        "F": {
            "dir": EXP_DIRS["f_health"],
            "charts": [
                ("health_degradation_trajectory.svg", "健康度退化轨迹图"),
            ],
            "tables": [
                ("health_degradation_report.md", "退化趋势报告"),
                ("phm_metrics_table.md", "PHM指标汇总表"),
            ],
        },
    }

    for code, info in exp_chart_map.items():
        desc = results_summary.get(code, {}).get("desc", "")
        lines.append(f"### 实验{code}：{desc}")
        lines.append("")
        lines.append("| 文件 | 说明 | 路径 |")
        lines.append("|------|------|------|")
        d = info["dir"]
        for fname, note in info["charts"]:
            p = d / fname
            exists = "✅" if p.exists() else "❌"
            lines.append(f"| {exists} {fname} | {note} | `{p}` |")
        for fname, note in info["tables"]:
            p = d / fname
            exists = "✅" if p.exists() else "❌"
            lines.append(f"| {exists} {fname} | {note} | `{p}` |")
        lines.append("")

    # ── 嵌入各实验分报告 ──────────────────────────────────────
    lines.append("## 各实验详细报告")
    lines.append("")
    lines.append("> 以下内容自动从各实验输出目录的 Markdown 文件中嵌入。")
    lines.append("")

    report_files = {
        "A": EXP_DIRS["a_bearing"] / "metrics_summary.md",
        "B": EXP_DIRS["b_gear"] / "summary_gear.md",
        "C": EXP_DIRS["c_denoise"] / "experiment_c_denoise.md",
        "D": None,  # 实验D只有 txt/json，无 md
        "E": EXP_DIRS["e_fusion"] / "fusion_gain.md",
        "F": EXP_DIRS["f_health"] / "health_degradation_report.md",
    }

    for code, md_path in report_files.items():
        desc = results_summary.get(code, {}).get("desc", "")
        lines.append(f"### 实验{code}：{desc}")
        lines.append("")
        if md_path and md_path.exists():
            try:
                content = md_path.read_text(encoding="utf-8")
                lines.append(content)
                lines.append("")
            except Exception:
                lines.append(f"*（读取 {md_path} 失败）*")
                lines.append("")
        elif code == "D":
            txt_path = EXP_DIRS["d_robustness"] / "critical_snr_table.txt"
            if txt_path.exists():
                try:
                    content = txt_path.read_text(encoding="utf-8")
                    lines.append("```")
                    lines.append(content)
                    lines.append("```")
                    lines.append("")
                except Exception:
                    lines.append("*（读取汇总表失败）*")
                    lines.append("")
            else:
                lines.append("*（实验D汇总表尚未生成）*")
                lines.append("")
        else:
            lines.append("*（该实验未生成 Markdown 报告）*")
            lines.append("")

    # ── 写入总报告 ──────────────────────────────────────────
    report_path = OUTPUT_DIR / "contest_master_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  总报告已保存: {report_path}")
    return report_path


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

    # ── 生成总报告 ──────────────────────────────────────────
    _generate_master_report(results_summary)

    print("=" * 60)


if __name__ == "__main__":
    main()