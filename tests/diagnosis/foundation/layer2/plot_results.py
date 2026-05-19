"""
Layer 2 特征提取 & 信号处理 — 独立绘图脚本

读取 layer2/output/*.json 生成对比图，无需重跑分析。

用法:
    python tests/diagnosis/foundation/layer2/plot_results.py
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
        print(f"  [SKIP] {name} 不存在")
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(p.read_bytes())


def plot_features():
    """features：时域特征 + 轴承频率 + FFT 特征通过率"""
    data = load_json("features_correctness.json")
    if not data:
        return

    categories = [k for k in data.keys() if k != "summary"]
    cat_passed = []
    cat_total = []
    for cat in categories:
        items = data[cat]
        cat_passed.append(sum(1 for it in items if it.get("passed", False)))
        cat_total.append(len(items))

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(categories))
    failed = [t - p for t, p in zip(cat_total, cat_passed)]
    ax.bar(x, cat_passed, color='#52C41A', label='通过')
    ax.bar(x, failed, bottom=cat_passed, color='#FF4D4F', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace('_', '\n') for c in categories], fontsize=9)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 2: features.py — 特征提取正确性")
    ax.legend()
    for i, (t, p) in enumerate(zip(cat_total, cat_passed)):
        ax.text(i, t + 0.2, f"{p}/{t}", ha='center', fontsize=9)
    ax.set_ylim(0, max(cat_total) * 1.3)
    plt.tight_layout()
    fig.savefig(PLOT_DIR / "features_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] features_correctness.png")


def plot_bearing():
    """bearing：各方法检出频率与 SNR"""
    data = load_json("bearing_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # 左图：各方法的目标频率 vs 检出峰值
    methods = []
    targets = []
    detected = []
    snrs = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "target_freq" in it:
                methods.append(f"{cat}\n{it['test']}")
                targets.append(it["target_freq"])
                detected.append(it.get("detected_peak", 0))
                snrs.append(it.get("snr", 0))
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if methods:
        x = np.arange(len(methods))
        axes[0].scatter(targets, detected, c=colors, s=80, zorder=3)
        # 理想对角线
        min_val = min(min(targets, default=0), min(detected, default=0))
        max_val = max(max(targets, default=100), max(detected, default=100))
        axes[0].plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.3, label='理想 y=x')
        axes[0].set_xlabel("目标频率 (Hz)")
        axes[0].set_ylabel("检出峰值 (Hz)")
        axes[0].set_title("轴承诊断 — 目标频率 vs 检出峰值")
        axes[0].legend()
        axes[0].grid(alpha=0.3)

        # 右图：SNR 分布
        axes[1].barh(range(len(methods)), snrs, color=colors)
        axes[1].set_yticks(range(len(methods)))
        axes[1].set_yticklabels(methods, fontsize=7)
        axes[1].axvline(x=3.0, color='orange', linestyle='--', label='SNR=3 阈值')
        axes[1].set_xlabel("SNR")
        axes[1].set_title("各方法包络谱 SNR")
        axes[1].legend()

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "bearing_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] bearing_correctness.png")


def plot_preprocessing():
    """preprocessing：降噪前后对比"""
    data = load_json("preprocessing_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 小波去噪 SNR
    wavelet_items = data.get("wavelet_denoise", [])
    for it in wavelet_items:
        if "snr_before_db" in it:
            axes[0].barh(["降噪前", "降噪后"],
                         [it["snr_before_db"], it["snr_after_db"]],
                         color=['#FF4D4F', '#52C41A'])
            axes[0].set_xlabel("SNR (dB)")
            axes[0].set_title("小波去噪 — SNR 改善")
            for i, v in enumerate([it["snr_before_db"], it["snr_after_db"]]):
                axes[0].text(v + 0.3, i, f"{v:.1f}dB", va='center')

    # MED 峭度改善
    med_items = data.get("med", [])
    for it in med_items:
        if "kurt_before" in it:
            axes[1].barh(["MED前", "MED后"],
                         [it["kurt_before"], it["kurt_after"]],
                         color=['#FF4D4F', '#52C41A'])
            axes[1].set_xlabel("峭度")
            axes[1].set_title("MED 解卷积 — 峭度改善")
            for i, v in enumerate([it["kurt_before"], it["kurt_after"]]):
                axes[1].text(v + 0.3, i, f"{v:.1f}", va='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "preprocessing_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] preprocessing_correctness.png")


def plot_gear_metrics():
    """gear_metrics：各指标值"""
    data = load_json("gear_metrics_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    labels = []
    values = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "fm4" in it:
                labels.append(f"{cat}\nFM4")
                values.append(it["fm4"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')
            elif "car" in it:
                labels.append(f"{cat}\nCAR")
                values.append(np.log10(abs(it["car"]) + 1e-12))
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')
            elif "ser" in it:
                labels.append(f"{cat}\nSER")
                values.append(it["ser"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')
            elif "fm0" in it:
                labels.append(f"{cat}\nFM0")
                values.append(it["fm0"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if labels:
        x = np.arange(len(labels))
        ax.bar(x, values, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("指标值 (CAR 取 log10)")
        ax.set_title("Layer 2: gear/metrics.py — 齿轮指标")
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "gear_metrics_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] gear_metrics_correctness.png")


def plot_order_tracking():
    """order_tracking：恒定/缓变/变速转速估计"""
    data = load_json("order_tracking_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    labels = []
    values = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "median_rot_freq" in it:
                labels.append(cat.replace("_", "\n"))
                values.append(it["median_rot_freq"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if labels:
        x = np.arange(len(labels))
        ax.bar(x, values, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("估计转频 (Hz)")
        ax.set_title("Layer 2: order_tracking.py — 转频估计")
        ax.axhline(y=25.0, color='orange', linestyle='--', label='期望中值≈25Hz')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "order_tracking_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] order_tracking_correctness.png")


def plot_health_score():
    """health_score：各场景健康度分布"""
    data = load_json("health_score_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    labels = []
    values = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "hs" in it:
                labels.append(it["test"].replace("health_", ""))
                values.append(it["hs"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if labels:
        x = np.arange(len(labels))
        ax.bar(x, values, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8, rotation=15)
        ax.set_ylabel("健康度")
        ax.set_title("Layer 2: health_score.py — 各场景健康度")
        ax.axhline(y=80, color='orange', linestyle='--', label='warning 阈值')
        ax.axhline(y=50, color='red', linestyle='--', label='fault 阈值')
        ax.legend()
        ax.set_ylim(0, 110)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "health_score_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] health_score_correctness.png")


def plot_planetary():
    """planetary_demod：各方法故障 SNR"""
    data = load_json("planetary_demod_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    labels = []
    values = []
    colors = []
    for cat, items in data.items():
        if cat == "summary":
            continue
        for it in items:
            if "sun_fault_snr" in it:
                labels.append(cat.replace("planetary_", ""))
                values.append(it["sun_fault_snr"])
                colors.append('#52C41A' if it.get("passed") else '#FF4D4F')

    if labels:
        x = np.arange(len(labels))
        ax.bar(x, values, color=colors)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("Sun Fault SNR")
        ax.set_title("Layer 2: planetary_demod.py — 太阳轮故障 SNR")
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "planetary_demod_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] planetary_demod_correctness.png")


def plot_summary():
    """汇总 Layer 2 所有测试的通过率"""
    summary_data = {}
    for json_name in ["features_correctness", "bearing_correctness", "preprocessing_correctness", "gear_metrics_correctness", "order_tracking_correctness", "bearing_advanced_correctness", "preprocessing_cascade_correctness", "health_score_correctness", "rule_based_correctness", "planetary_demod_correctness"]:
        data = load_json(f"{json_name}.json")
        if data and "summary" in data:
            summary_data[json_name.replace("_correctness", "").replace("_", "\n")] = data["summary"]

    if not summary_data:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
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
    ax.set_title("Layer 2: 特征提取 & 信号处理 — 测试通过率")
    ax.set_ylim(0, max(totals) * 1.5)
    ax.legend()

    for i, (t, p) in enumerate(zip(totals, passed)):
        ax.text(i, t + 0.3, f"{p}/{t}", ha='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "layer2_summary.png", dpi=150)
    plt.close(fig)
    print("  [OK] layer2_summary.png")


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer 2: 特征提取 & 信号处理 — 生成对比图")
    print("=" * 50)

    plot_features()
    plot_bearing()
    plot_preprocessing()
    plot_gear_metrics()
    plot_order_tracking()
    plot_health_score()
    plot_planetary()
    plot_summary()

    print(f"\n图表保存在: {PLOT_DIR}")


if __name__ == "__main__":
    main()
