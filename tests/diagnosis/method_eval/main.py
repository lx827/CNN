"""
诊断方法评估框架 — 主入口

一键运行全部 4 个测试，生成跨数据集对比图表和总报告。

用法:
    d:\code\CNN\cloud\venv\Scripts\python.exe -m tests.diagnosis.method_eval.main

或:
    d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\method_eval\main.py
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

from method_eval.config import OUTPUT_DIR


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      诊断方法评估框架 — 全量测试                             ║")
    print("║      基于云端生产代码 + 三大数据集全面评估                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    tests = [
        ("1", "HUSTbear 恒速轴承评估",      "test_bearing_hustbear", "test_bearing_hustbear"),
        ("2", "CW 变速轴承评估",            "test_bearing_cw",       "test_bearing_cw"),
        ("3", "WTgearbox 齿轮评估",         "test_gear_wtgearbox",   "test_gear_wtgearbox"),
        ("4", "二分类全数据集汇总",         "test_binary_all",       "test_binary_all"),
    ]

    results = {}

    for code, desc, module, func in tests:
        print(f"\n{'=' * 60}")
        print(f"  【测试{code}】 {desc}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            mod = __import__(f"method_eval.{module}", fromlist=[func])
            fn = getattr(mod, func)
            result = fn()
            results[code] = {"desc": desc, "status": "OK", "result": result}
        except Exception as e:
            results[code] = {"desc": desc, "status": "FAIL", "error": str(e)}
            print(f"  ✗ 测试{code}失败: {e}")

        elapsed = time.time() - t0
        print(f"  ⏱ 耗时: {elapsed:.0f}s")

    # ── 生成总报告 ──
    _generate_master_report(results)


def _generate_master_report(results: dict):
    lines = [
        "# 诊断方法评估总报告",
        "",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 输出目录: {OUTPUT_DIR}",
        "",
        "## 测试总览",
        "",
        "| 测试 | 描述 | 状态 | 输出目录 |",
        "|------|------|------|---------|",
    ]

    exp_map = {
        "1": {"dir": "bearing_hustbear", "files": "binary_accuracy_comparison.svg, confusion_ensemble_5class.svg, report.md"},
        "2": {"dir": "bearing_cw", "files": "binary_accuracy_comparison.svg, confusion_ensemble_3class.svg, report.md"},
        "3": {"dir": "gear_wtgearbox", "files": "binary_accuracy_comparison.svg, confusion_ensemble_5class.svg, report.md"},
        "4": {"dir": "binary_all", "files": "bar_hustbear.svg, bar_cw.svg, bar_wtgearbox.svg, radar_top5.svg, report.md"},
    }

    for code, info in results.items():
        status_mark = "✅" if info["status"] == "OK" else "❌"
        exp_info = exp_map.get(code, {})
        dir_name = exp_info.get("dir", "")
        lines.append(
            f"| {status_mark} 测试{code} | {info['desc']} | {info['status']} | "
            f"`{OUTPUT_DIR / dir_name}` |"
        )

    ok_count = sum(1 for v in results.values() if v["status"] == "OK")
    lines.append(f"| **合计** | **4 个测试** | **{ok_count}/4 成功** | |")
    lines.append("")
    lines.append("## 图表清单")
    lines.append("")

    for code, info in exp_map.items():
        desc = results.get(code, {}).get("desc", "")
        lines.append(f"### 测试{code}: {desc}")
        lines.append("")
        files = info.get("files", "").split(", ")
        for fname in files:
            p = OUTPUT_DIR / info["dir"] / fname
            exists = "✅" if p.exists() else "❌"
            lines.append(f"- {exists} `{fname}`")
        lines.append("")

    report_path = OUTPUT_DIR / "master_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n  📋 总报告已保存: {report_path}")


if __name__ == "__main__":
    main()
