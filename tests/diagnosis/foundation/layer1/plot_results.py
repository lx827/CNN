"""
Layer 1 信号基元 — 独立绘图脚本

读取 layer1/output/*.json 生成对比图，无需重跑分析。

用法:
    python tests/diagnosis/foundation/layer1/plot_results.py
"""
import json
from pathlib import Path
import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

OUTPUT_DIR = Path(__file__).parent / "output"
PLOT_DIR = OUTPUT_DIR / "plots"


def load_json(name):
    p = OUTPUT_DIR / name
    if not p.exists():
        print(f"  [SKIP] {name} 不存在，请先运行对应的 test_*.py")
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(p.read_bytes())


def plot_signal_utils():
    """signal_utils：按类别展示通过率"""
    data = load_json("signal_utils_correctness.json")
    if not data:
        return

    categories = [k for k in data.keys() if k != "summary"]
    cat_passed = []
    cat_total = []
    for cat in categories:
        items = data[cat]
        cat_passed.append(sum(1 for it in items if it.get("passed", False)))
        cat_total.append(len(items))

    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(categories))
    failed = [t - p for t, p in zip(cat_total, cat_passed)]
    ax.bar(x, cat_passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=cat_passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace('_', '\n') for c in categories], fontsize=8)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 1: signal_utils — 信号基元正确性")
    ax.legend()
    for i, (t, p) in enumerate(zip(cat_total, cat_passed)):
        ax.text(i, t + 0.2, f"{p}/{t}", ha='center', fontsize=9)
    ax.set_ylim(0, max(cat_total) * 1.3)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "signal_utils_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] signal_utils_correctness.png")


def plot_vmd():
    """VMD：降噪 SNR 改善 + 冲击模态峭度"""
    data = load_json("vmd_denoise_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 降噪 SNR
    denoise_items = data.get("vmd_denoise", [])
    if denoise_items:
        for item in denoise_items:
            if "snr_before_db" in item:
                axes[0].barh(["降噪前", "降噪后"],
                             [item["snr_before_db"], item["snr_after_db"]],
                             color=['#FF4D4F', '#52C41A'])
                axes[0].set_xlabel("SNR (dB)")
                axes[0].set_title("VMD 降噪 — SNR 改善")
                for i, v in enumerate([item["snr_before_db"], item["snr_after_db"]]):
                    axes[0].text(v + 0.3, i, f"{v:.1f}dB", va='center')

    # 冲击模态峭度
    impact_items = data.get("vmd_select_impact", [])
    if impact_items:
        for item in impact_items:
            modes = item.get("mode_kurtoses", [])
            if modes:
                best_idx = item.get("best_index", 0)
                axes[1].bar(range(len(modes)), modes,
                            color=['#165DFF' if i == best_idx else '#D9D9D9' for i in range(len(modes))])
                axes[1].set_xlabel("IMF 序号")
                axes[1].set_ylabel("峭度")
                axes[1].set_title("VMD 冲击模态选择 (蓝色=最佳)")
                orig_kurt = item.get("original_kurtosis", 0)
                axes[1].axhline(y=orig_kurt, color='orange', linestyle='--',
                                label=f'原始信号峭度={orig_kurt:.1f}')
                axes[1].legend()

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "vmd_denoise_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] vmd_denoise_correctness.png")


def plot_summary():
    """汇总 Layer 1 所有测试的通过率"""
    summary_data = {}
    for json_name in ["signal_utils_correctness", "vmd_denoise_correctness"]:
        data = load_json(f"{json_name}.json")
        if data and "summary" in data:
            summary_data[json_name.replace("_correctness", "").replace("_", "\n")] = data["summary"]

    if not summary_data:
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    labels = list(summary_data.keys())
    totals = [v.get("total", 0) for v in summary_data.values()]
    passed = [v.get("passed", 0) for v in summary_data.values()]
    failed = [v.get("failed", v.get("total", 0) - v.get("passed", 0)) for v in summary_data.values()]

    x = range(len(labels))
    ax.bar(x, passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 1: 信号基元 — 测试通过率")
    ax.set_ylim(0, max(totals) * 1.5)
    ax.legend()

    for i, (t, p) in enumerate(zip(totals, passed)):
        ax.text(i, t + 0.3, f"{p}/{t}", ha='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "layer1_summary.png", dpi=150)
    plt.close(fig)
    print("  [OK] layer1_summary.png")


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer 1: 信号基元 — 生成对比图")
    print("=" * 50)

    plot_signal_utils()
    plot_vmd()
    plot_summary()

    print(f"\n图表保存在: {PLOT_DIR}")


if __name__ == "__main__":
    main()
