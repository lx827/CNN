"""
仅运行鲁棒性评估（Monte-Carlo 多样本版）
用法: cd /d/code/CNN && . cloud/venv/Scripts/activate && python tests/diagnosis/eval_plots/run_robustness_only.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from run_all import run_46_robustness, OUTPUT_DIR
from plot_comparison import plot_robustness

# 确保输出目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 运行鲁棒性评估: 3样本 × 5次 Monte-Carlo
results = run_46_robustness(n_mc=5)

# 绘图
plot_robustness()

print("\n" + "=" * 60)
print("鲁棒性评估完成!")
print(f"输出: {OUTPUT_DIR / 'comparison_robustness.png'}")
print("=" * 60)
