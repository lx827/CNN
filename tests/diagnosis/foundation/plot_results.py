"""
基础算法正确性 — 独立绘图脚本

读取 foundation/output/*.json 生成对比图，无需重跑分析。

用法:
    python tests/diagnosis/foundation/plot_results.py
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


def plot_bearing_fault_freqs():
    """轴承故障频率：理论值 vs 计算值 并排对比"""
    data = load_json("bearing_fault_freqs.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    # 按 (测试用例, freq_type) 排列
    groups = []
    group_labels = []
    for tc in data["test_cases"]:
        for key in ["BPFO", "BPFI", "BSF", "FTF"]:
            e = tc["errors"].get(key, {})
            if e and e["expected"] > 0:
                groups.append({
                    "label": f"{tc['name']}\n{key}",
                    "expected": e["expected"],
                    "computed": e["computed"],
                    "diff_hz": e["abs_error"],
                })
                group_labels.append(f"{tc['name']}\n{key}")

    x = np.arange(len(groups))
    width = 0.35

    expected_vals = [g["expected"] for g in groups]
    computed_vals = [g["computed"] for g in groups]
    diffs = [g["diff_hz"] for g in groups]

    bars1 = ax.bar(x - width/2, expected_vals, width, label='理论值', color='#165DFF', alpha=0.85)
    bars2 = ax.bar(x + width/2, computed_vals, width, label='计算值', color='#FAAD14', alpha=0.85)

    # 标注差异
    for i, d in enumerate(diffs):
        if d > 0.001:
            ax.annotate(f'Δ={d:.2e}Hz', (x[i], max(expected_vals[i], computed_vals[i])),
                        ha='center', fontsize=7, color='red')

    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, fontsize=8)
    ax.set_ylabel("频率 (Hz)")
    ax.set_title(f"轴承故障频率 — 理论值 vs 计算值  (最大误差={max(diffs):.2e} Hz)")
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "bearing_fault_freqs.png", dpi=150)
    plt.close(fig)
    print("  [OK] bearing_fault_freqs.png")


def plot_envelope_correctness():
    """包络谱：冲击频率检出 SNR"""
    data = load_json("envelope_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 合成信号 SNR
    impulse_data = data.get("synthetic_impulse", [])
    if impulse_data:
        freqs = [d["expected_freq"] for d in impulse_data]
        snrs = [d["detected_snr"] for d in impulse_data]
        axes[0].bar(range(len(freqs)), snrs, tick_label=[f"{f}Hz" for f in freqs],
                    color=['green' if s > 3 else 'red' for s in snrs])
        axes[0].axhline(y=3.0, color='orange', linestyle='--', label='SNR=3 阈值')
        axes[0].set_title("合成冲击信号 — 包络谱 SNR")
        axes[0].set_ylabel("SNR")
        axes[0].legend()

    # 合成轴承信号
    bearing_data = data.get("synthetic_bearing", [])
    if bearing_data:
        labels = [d["test"].replace("synthetic_", "") for d in bearing_data]
        snrs = [d["detected_snr"] for d in bearing_data]
        colors = ['green' if d.get("passed") else 'red' for d in bearing_data]
        axes[1].bar(labels, snrs, color=colors)
        axes[1].axhline(y=5.0, color='orange', linestyle='--', label='SNR=5 阈值')
        axes[1].set_title("合成轴承信号 — 故障频率检出")
        axes[1].set_ylabel("SNR")
        axes[1].legend()

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "envelope_correctness.png", dpi=150)
    plt.close(fig)
    print("  [OK] envelope_correctness.png")

    # 真实数据 SNR 对比 (HUSTbear + CW)
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    real_data = data.get("real_hustbear", []) + data.get("real_cw", [])
    if real_data:
        labels = [f"{d.get('dataset','')}-{d['description']}" for d in real_data]
        bpfo_snrs = [d.get("snr", {}).get("BPFO", 0) for d in real_data]
        bpfi_snrs = [d.get("snr", {}).get("BPFI", 0) for d in real_data]
        x = np.arange(len(labels))
        w = 0.35
        ax2.bar(x - w/2, bpfo_snrs, w, label='BPFO SNR', color='#165DFF')
        ax2.bar(x + w/2, bpfi_snrs, w, label='BPFI SNR', color='#FAAD14')
        ax2.axhline(y=3.0, color='red', linestyle='--', alpha=0.5, label='SNR=3')
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, fontsize=8)
        ax2.set_ylabel("SNR")
        ax2.set_title("真实数据 — BPFO/BPFI 检出 SNR")
        ax2.legend()
        plt.tight_layout()
        fig2.savefig(PLOT_DIR / "envelope_real_snr.png", dpi=150)
        plt.close(fig2)
        print("  [OK] envelope_real_snr.png")


def plot_order_tracking():
    """阶次跟踪：转频估计误差"""
    data = load_json("order_tracking_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    freq_data = data.get("rot_freq_estimation", [])
    if freq_data:
        actuals = [d["actual_freq"] for d in freq_data]
        estims = [d["estimated_freq"] for d in freq_data]
        errs = [d["rel_error_pct"] for d in freq_data]
        colors = ['green' if e < 5 else 'red' for e in errs]

        x = range(len(actuals))
        ax.bar(x, errs, color=colors, alpha=0.7)
        for i, (a, e_f) in enumerate(zip(actuals, estims)):
            ax.text(i, errs[i] + 0.2, f"{a}→{e_f:.1f}Hz", ha='center', fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{a}Hz" for a in actuals])
        ax.set_ylabel("相对误差 (%)")
        ax.set_title("转频估计 — 实际值 vs 估计值")
        ax.axhline(y=5.0, color='red', linestyle='--', alpha=0.5, label='5% 容差')
        ax.legend()

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "order_tracking.png", dpi=150)
    plt.close(fig)
    print("  [OK] order_tracking.png")

    # 真实数据转频估计
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    real_data = (data.get("real_hustbear", []) or []) + (data.get("real_cw", []) or [])
    if real_data:
        labels = [f"{d.get('dataset','')}-{d['file'][:10]}" for d in real_data]
        rfreqs = [d["estimated_rot_freq_Hz"] for d in real_data]
        colors = ['#165DFF' if 'health' in d.get('description','').lower() or '健康' in d.get('description','')
                  else '#F5222D' for d in real_data]
        ax2.barh(labels, rfreqs, color=colors)
        ax2.set_xlabel("估计转频 (Hz)")
        ax2.set_title("真实数据 — 转频估计")
        plt.tight_layout()
        fig2.savefig(PLOT_DIR / "order_real_rotfreq.png", dpi=150)
        plt.close(fig2)
        print("  [OK] order_real_rotfreq.png")


def plot_cepstrum():
    """倒谱：峰值检测结果"""
    data = load_json("cepstrum_correctness.json")
    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    all_tests = data.get("gear_mesh", []) + data.get("harmonic", [])
    labels = []
    values = []
    for d in all_tests:
        labels.append(d["test"])
        values.append(1 if d.get("passed") else 0)

    colors = ['green' if v else 'red' for v in values]
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("通过 (1=是, 0=否)")
    ax.set_title("倒谱分析 — 特征频率检出")
    ax.set_xlim(0, 1.5)
    for i, (l, v) in enumerate(zip(labels, values)):
        ax.text(v + 0.05, i, "PASS" if v else "FAIL", va='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "cepstrum.png", dpi=150)
    plt.close(fig)
    print("  [OK] cepstrum.png")


def plot_gear_metrics():
    """齿轮指标：SER/FM4 在各数据集上的分布"""
    data = load_json("gear_metrics_correctness.json")
    if not data:
        return

    # SER 对比
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, ds_name in [(axes[0], "wtgearbox"), (axes[1], "hustgearbox")]:
        ds_data = data.get(ds_name, [])
        if not ds_data:
            continue
        labels = [d["label"] for d in ds_data]
        ser_vals = [d["ser"] for d in ds_data]
        fm4_vals = [d["fm4"] for d in ds_data]
        kurt_vals = [d["kurtosis"] for d in ds_data]

        x = np.arange(len(labels))
        w = 0.25
        ax.bar(x - w, ser_vals, w, label='SER', color='#165DFF')
        # Normalize FM4 and kurtosis to similar scale
        fm4_norm = [v / max(fm4_vals) * max(ser_vals) * 0.8 if max(fm4_vals) > 0 else 0 for v in fm4_vals]
        kurt_norm = [v / max(kurt_vals) * max(ser_vals) * 0.8 if max(kurt_vals) > 0 else 0 for v in kurt_vals]
        ax.bar(x, fm4_norm, w, label=f'FM4 (×{max(ser_vals)*0.8/max(fm4_vals):.0f})', color='#FAAD14', alpha=0.7)
        ax.bar(x + w, kurt_norm, w, label=f'Kurt (×{max(ser_vals)*0.8/max(kurt_vals):.0f})', color='#52C41A', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(f"{ds_name} — SER / FM4 / Kurtosis")
        ax.legend(fontsize=7)

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "gear_metrics.png", dpi=150)
    plt.close(fig)
    print("  [OK] gear_metrics.png")


def plot_summary():
    """汇总所有测试的通过率"""
    summary_data = {}
    for json_name in ["bearing_fault_freqs", "envelope_correctness", "order_tracking_correctness", "cepstrum_correctness", "gear_metrics_correctness"]:
        data = load_json(f"{json_name}.json")
        if data and "summary" in data:
            summary_data[json_name] = data["summary"]

    if not summary_data:
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    labels = [k.replace("_", "\n") for k in summary_data.keys()]
    totals = [v.get("total", 0) for v in summary_data.values()]
    passed = [v.get("passed", 0) for v in summary_data.values()]
    failed = [v.get("failed", v.get("total", 0) - v.get("passed", 0)) for v in summary_data.values()]

    x = range(len(labels))
    ax.bar(x, passed, color='green', label='通过')
    ax.bar(x, failed, bottom=passed, color='red', label='失败')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("测试数")
    ax.set_title("基础算法正确性 — 测试通过率汇总")
    ax.set_ylim(0, 10)
    ax.legend()

    for i, (t, p) in enumerate(zip(totals, passed)):
        ax.text(i, t + 0.3, f"{p}/{t}", ha='center')

    plt.tight_layout()
    fig.savefig(PLOT_DIR / "summary.png", dpi=150)
    plt.close(fig)
    print("  [OK] summary.png")


def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("基础算法正确性 — 生成对比图")
    print("=" * 50)

    plot_bearing_fault_freqs()
    plot_envelope_correctness()
    plot_order_tracking()
    plot_cepstrum()
    plot_gear_metrics()
    plot_summary()

    print(f"\n图表保存在: {PLOT_DIR}")


if __name__ == "__main__":
    main()
