"""
综合评估编排器 — 并行运行所有独立脚本
生成 JSON 到 tests/output/eval_plots/

用法:
  # 并行跑全部 (推荐)
  d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\run_all.py

  # 单独跑某节
  d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\run_42_hust.py

  # 顺序跑 (调试用)
  d:\code\CNN\cloud\venv\Scripts\python.exe d:\code\CNN\tests\diagnosis\eval_plots\run_all.py --seq

数据解释见: docs/EVALUATION_REPORT_20260521.md
"""
import subprocess, sys, time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PYTHON = Path(r"d:\code\CNN\cloud\venv\Scripts\python.exe")

SCRIPTS = [
    ("4.2 恒速轴承", "run_42_hust.py"),
    ("4.3 变速轴承", "run_43_cw.py"),
    ("4.4 齿轮诊断", "run_44_wtg.py"),
    ("4.6 鲁棒性",   "run_46_robustness.py"),
    ("4.7 去噪效果", "run_47_denoise.py"),
]


def run_parallel():
    print("=" * 60)
    print("CNN 综合评估 — 并行执行")
    print("=" * 60)

    t0 = time.perf_counter()
    procs = []
    for section, script in SCRIPTS:
        sp = SCRIPTS_DIR / script
        if not sp.exists():
            print(f"  ⚠️ {script} 不存在，跳过")
            continue
        print(f"  启动: {section} ({script})")
        procs.append(subprocess.Popen([str(PYTHON), str(sp)],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT))

    for i, (section, _) in enumerate(SCRIPTS):
        if i < len(procs):
            out, _ = procs[i].communicate()
            print(f"\n--- {section} ---")
            if out:
                lines = out.decode("utf-8", errors="replace").strip().splitlines()
                for line in lines[-8:]:
                    print(f"  {line}")
            print(f"  完成 (exit={procs[i].returncode})")

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"全部完成，耗时 {elapsed:.0f}s (并行模式下为最慢脚本耗时)")
    print(f"JSON 输出: tests/output/eval_plots/")
    print(f"查看报告: docs/EVALUATION_REPORT_20260521.md")
    print(f"{'='*60}")


def run_sequential():
    print("=" * 60)
    print("CNN 综合评估 — 顺序执行")
    print("=" * 60)
    t0 = time.perf_counter()
    for section, script in SCRIPTS:
        sp = SCRIPTS_DIR / script
        if not sp.exists():
            print(f"  ⚠️ {script} 不存在")
            continue
        print(f"\n{'='*40}\n  {section}\n{'='*40}")
        result = subprocess.run([str(PYTHON), str(sp)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[:500])
    elapsed = time.perf_counter() - t0
    print(f"\n{'='*60}")
    print(f"全部完成，耗时 {elapsed:.0f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--seq" in sys.argv:
        run_sequential()
    else:
        run_parallel()
