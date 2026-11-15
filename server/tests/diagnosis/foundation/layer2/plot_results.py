"""
Layer 2 特征提取 & 信号处理 — 独立绘图脚本

读取 layer2/output/*.json 生成对比图，无需重跑分析。

用法:
    uv run python tests/diagnosis/foundation/layer2/plot_results.py
"""

import json
from pathlib import Path
import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ═══════════════════════════════════════════════════════════
# 全局视觉语义
# ═══════════════════════════════════════════════════════════
COLOR_PASS = "#52C41A"  # 绿 = 通过 / 正确 / 健康
COLOR_FAIL = "#FF4D4F"  # 红 = 失败 / 错误 / 故障
COLOR_GT = "#D9D9D9"  # 灰 = Ground Truth / 理论值 / 期望范围
COLOR_THRESH = "#FAAD14"  # 橙 = 阈值线 / 警告边界
COLOR_EST = "#165DFF"  # 蓝 = 算法估计值 / 实际计算结果

MARK_OK = "OK"
MARK_NG = "NG"
MARK_WARN = "WARN"

OUTPUT_DIR = Path(__file__).parent / "output"
PLOT_DIR = OUTPUT_DIR / "plots"


def load_json(name):
    p = OUTPUT_DIR / name
    if not p.exists():
        print(f"  [SKIP] {name} 不存在")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.loads(p.read_bytes())


def _save(fig, name):
    fig.savefig(PLOT_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {name}")


# ═══════════════════════════════════════════════════════════
# 01: features.py — 特征提取正确性（理论值 vs 计算值）
# ═══════════════════════════════════════════════════════════
def plot_features():
    data = load_json("features_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # ── 子图1: 时域特征 ──
    time_items = data.get("time_features", [])
    if time_items:
        ax = axes[0, 0]
        it = time_items[0]
        metrics = [
            ("峰值", it.get("peak", 0), 1.0, it.get("peak_ok", False)),
            ("RMS", it.get("rms", 0), 1 / np.sqrt(2), it.get("rms_ok", False)),
            ("峰值因子", it.get("crest", 0), np.sqrt(2), it.get("crest_ok", False)),
            ("峭度", it.get("kurtosis", 0), 1.5, it.get("kurt_ok", False)),
        ]
        x = np.arange(len(metrics))
        w = 0.35
        expecteds = [m[2] for m in metrics]
        actuals = [m[1] for m in metrics]
        colors = [COLOR_PASS if m[3] else COLOR_FAIL for m in metrics]

        ax.bar(
            x - w / 2, expecteds, w, color=COLOR_GT, edgecolor="#999", label="理论值"
        )
        ax.bar(x + w / 2, actuals, w, color=COLOR_EST, label="实际值")
        for i, (a, e, passed) in enumerate(
            zip(actuals, expecteds, [m[3] for m in metrics])
        ):
            err = abs(a - e) / (abs(e) + 1e-12) * 100
            mark = MARK_OK if passed else MARK_NG
            color = COLOR_PASS if passed else COLOR_FAIL
            ax.annotate(
                f"{mark} Δ={err:.1f}%",
                (i, max(a, e) + 0.03),
                ha="center",
                fontsize=9,
                color=color,
                fontweight="bold",
            )
        ax.set_xticks(x)
        ax.set_xticklabels([m[0] for m in metrics], fontsize=10)
        ax.set_ylabel("值")
        ax.set_title("时域特征 — 正弦信号理论值 vs 计算值\n（|相对误差|<5% 为通过）")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    # ── 子图2: 轴承故障频率 ──
    freq_items = data.get("bearing_fault_freqs", [])
    if freq_items:
        ax = axes[0, 1]
        groups = []
        for it in freq_items:
            for key in ["BPFO", "BPFI", "BSF", "FTF"]:
                exp_key = f"{key}_expected"
                if exp_key in it:
                    groups.append(
                        {
                            "label": f"{it['test'][:8]}..\n{key}",
                            "expected": it[exp_key],
                            "computed": it.get(key, 0),
                            "passed": it.get("passed", False),
                        }
                    )
        if groups:
            x = np.arange(len(groups))
            w = 0.35
            exp_vals = [g["expected"] for g in groups]
            comp_vals = [g["computed"] for g in groups]
            colors = [COLOR_PASS if g["passed"] else COLOR_FAIL for g in groups]
            ax.bar(
                x - w / 2, exp_vals, w, color=COLOR_GT, edgecolor="#999", label="理论值"
            )
            ax.bar(x + w / 2, comp_vals, w, color=COLOR_EST, label="计算值")
            for i, g in enumerate(groups):
                err = abs(g["computed"] - g["expected"])
                mark = MARK_OK if g["passed"] else MARK_NG
                color = COLOR_PASS if g["passed"] else COLOR_FAIL
                ax.annotate(
                    f"{mark} Δ={err:.2f}Hz",
                    (i, max(g["expected"], g["computed"]) + 1),
                    ha="center",
                    fontsize=7,
                    color=color,
                )
            ax.set_xticks(x)
            ax.set_xticklabels([g["label"] for g in groups], fontsize=7)
            ax.set_ylabel("频率 (Hz)")
            ax.set_title("轴承故障频率 — 理论值 vs 计算值\n（|误差|<0.1Hz 为通过）")
            ax.legend(fontsize=8)
            ax.grid(axis="y", alpha=0.3)

    # ── 子图3: 参数有效性 ──
    param_items = data.get("param_validity", [])
    if param_items:
        ax = axes[1, 0]
        labels = [
            it["test"].replace("has_", "").replace("_params", "") for it in param_items
        ]
        vals = [1 if it.get("actual") else 0 for it in param_items]
        colors = [COLOR_PASS if it.get("passed") else COLOR_FAIL for it in param_items]
        ax.bar(range(len(labels)), vals, color=colors, width=0.5)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("有效性 (1=有效, 0=无效)")
        ax.set_ylim(0, 1.5)
        ax.set_title("参数有效性 — 预期与实际布尔值对比")
        for i, it in enumerate(param_items):
            mark = MARK_OK if it.get("passed") else MARK_NG
            color = COLOR_PASS if it.get("passed") else COLOR_FAIL
            ax.text(
                i,
                1.1,
                f"{mark}\nexp={it.get('expected')}",
                ha="center",
                fontsize=8,
                color=color,
            )
        ax.grid(axis="y", alpha=0.3)

    # ── 子图4: FFT 特征 ──
    fft_items = data.get("fft_features", [])
    if fft_items:
        ax = axes[1, 1]
        it = fft_items[0]
        labels = ["啮合频率\n占比", "边带总\n占比"]
        vals = [it.get("mesh_freq_ratio", 0), it.get("sideband_total_ratio", 0)]
        passed = it.get("passed", False)
        colors = [COLOR_EST, COLOR_EST]
        x = np.arange(len(labels))
        ax.bar(x, vals, color=colors, width=0.4)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylabel("能量占比")
        ax.set_ylim(0, 1.0)
        ax.set_title(
            f"FFT 特征 — 啮合频率与边带能量分布\n啮合频率应显著 > 边带（通过={passed}）"
        )
        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            0.5,
            0.85,
            f"{mark} mesh_ratio={vals[0]:.3f}",
            ha="center",
            fontsize=11,
            color=color,
            fontweight="bold",
            transform=ax.transAxes,
        )
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle(
        "Layer 2 — features.py 特征提取正确性验证", fontsize=14, fontweight="bold"
    )
    _save(fig, "01_features_correctness.png")


# ═══════════════════════════════════════════════════════════
# 04: preprocessing.py — 降噪与预处理效果验证
# ═══════════════════════════════════════════════════════════
def plot_preprocessing():
    data = load_json("preprocessing_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # ── 子图1: 小波去噪 SNR 改善 ──
    wavelet_items = [
        it for it in data.get("wavelet_denoise", []) if "snr_before_db" in it
    ]
    if wavelet_items:
        ax = axes[0]
        it = wavelet_items[0]
        before = it["snr_before_db"]
        after = it["snr_after_db"]
        improve = after - before
        passed = it.get("passed", False)
        colors = [
            COLOR_FAIL if before < 0 else COLOR_GT,
            COLOR_PASS if passed else COLOR_FAIL,
        ]

        bars = ax.barh(["降噪前", "降噪后"], [before, after], color=colors, height=0.4)
        ax.set_xlabel("SNR (dB)")
        ax.axvline(
            x=5.0, color=COLOR_THRESH, linestyle="--", linewidth=1.5, label="SNR=5 阈值"
        )
        ax.set_title("小波去噪 — SNR 改善\n（SNR↑且>5dB 为通过）")
        ax.legend(fontsize=8)
        ax.grid(axis="x", alpha=0.3)

        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            max(before, after) + 0.5,
            0.5,
            f"{mark} 提升 {improve:.1f}dB",
            ha="left",
            va="center",
            fontsize=11,
            color=color,
            fontweight="bold",
        )
        for i, v in enumerate([before, after]):
            ax.text(v + 0.2, i, f"{v:.1f}dB", va="center", fontsize=9)

    # ── 子图2: MED 峭度与峰值改善 ──
    med_items = [it for it in data.get("med", []) if "kurt_before" in it]
    if med_items:
        ax = axes[1]
        it = med_items[0]
        metrics = [
            ("峭度", it["kurt_before"], it["kurt_after"]),
            ("峰值", it["peak_before"], it["peak_after"]),
        ]
        x = np.arange(len(metrics))
        w = 0.35
        befores = [m[1] for m in metrics]
        afters = [m[2] for m in metrics]
        passed = it.get("passed", False)

        ax.bar(x - w / 2, befores, w, color=COLOR_GT, edgecolor="#999", label="MED前")
        ax.bar(
            x + w / 2,
            afters,
            w,
            color=COLOR_PASS if passed else COLOR_FAIL,
            label="MED后",
        )
        for i, (name, b, a) in enumerate(metrics):
            improve = (a - b) / (b + 1e-12) * 100
            ax.annotate(f"{b:.2f}", (i - w / 2, b + 0.05), ha="center", fontsize=8)
            ax.annotate(
                f"{a:.2f}\n(+{improve:.0f}%)",
                (i + w / 2, a + 0.05),
                ha="center",
                fontsize=8,
            )
        ax.set_xticks(x)
        ax.set_xticklabels([m[0] for m in metrics], fontsize=10)
        ax.set_title("MED 解卷积 — 冲击特征增强\n（峭度/峰值提升为通过）")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            0.98,
            0.95,
            f"{mark} passed",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=11,
            color=color,
            fontweight="bold",
        )

    # ── 子图3: CPW 能量抑制 ──
    cpw_items = [it for it in data.get("cpw", []) if "energy_before" in it]
    if cpw_items:
        ax = axes[2]
        it = cpw_items[0]
        before = it["energy_before"]
        after = it["energy_after"]
        ratio = before / (after + 1e-12)
        passed = it.get("passed", False)
        colors = [COLOR_GT, COLOR_PASS if passed else COLOR_FAIL]

        ax.bar(["CPW前", "CPW后"], [before, after], color=colors, width=0.4)
        ax.set_ylabel("能量")
        ax.set_title("CPW 倒频谱预白化 — 谐波能量抑制\n（能量显著下降为通过）")
        ax.grid(axis="y", alpha=0.3)

        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            0.5,
            max(before, after) * 1.1,
            f"{mark} 抑制比 {ratio:.1f}:1",
            ha="center",
            fontsize=11,
            color=color,
            fontweight="bold",
        )
        for i, v in enumerate([before, after]):
            ax.text(
                i, v + max(before, after) * 0.02, f"{v:.1f}", ha="center", fontsize=9
            )

    fig.suptitle(
        "Layer 2 — preprocessing.py 降噪效果验证", fontsize=14, fontweight="bold"
    )
    _save(fig, "04_preprocessing_correctness.png")


# ═══════════════════════════════════════════════════════════
# 05: preprocessing_cascade.py — 级联降噪效果
# ═══════════════════════════════════════════════════════════
def plot_preprocessing_cascade():
    data = load_json("preprocessing_cascade_correctness.json")
    if not data:
        return

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # ── wavelet + VMD 级联 ──
    vmd_items = data.get("cascade_wavelet_vmd", [])
    if vmd_items:
        ax = axes[0]
        it = vmd_items[0]
        stages = ["原始信号", "小波去噪后", "级联 VMD 后"]
        kurt_vals = [
            it["kurt_before"],
            it["kurt_after_wavelet"],
            it["kurt_after_cascade"],
        ]
        passed = it.get("passed", False)
        colors = [COLOR_GT, COLOR_EST, COLOR_PASS if passed else COLOR_FAIL]

        bars = ax.bar(stages, kurt_vals, color=colors, width=0.5)
        ax.set_ylabel("峭度")
        ax.set_title("级联降噪：wavelet → VMD\n（峭度合理收敛为通过）")
        ax.grid(axis="y", alpha=0.3)

        for i, (stage, v) in enumerate(zip(stages, kurt_vals)):
            ax.text(i, v + max(kurt_vals) * 0.02, f"{v:.2f}", ha="center", fontsize=9)
            if i > 0:
                change = (v - kurt_vals[i - 1]) / (kurt_vals[i - 1] + 1e-12) * 100
                ax.annotate(
                    f"{change:+.1f}%",
                    (i, v + max(kurt_vals) * 0.08),
                    ha="center",
                    fontsize=8,
                    color=COLOR_THRESH,
                )

        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            0.98,
            0.95,
            f"{mark} passed",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=11,
            color=color,
            fontweight="bold",
        )

    # ── wavelet + LMS 级联 ──
    lms_items = data.get("cascade_wavelet_lms", [])
    if lms_items:
        ax = axes[1]
        it = lms_items[0]
        stages = ["原始信号", "级联 LMS 后"]
        kurt_vals = [it["kurt_before"], it["kurt_after_cascade"]]
        passed = it.get("passed", False)
        colors = [COLOR_GT, COLOR_PASS if passed else COLOR_FAIL]

        bars = ax.bar(stages, kurt_vals, color=colors, width=0.4)
        ax.set_ylabel("峭度")
        ax.set_title("级联降噪：wavelet → LMS\n（峭度提升为通过）")
        ax.grid(axis="y", alpha=0.3)

        for i, v in enumerate(kurt_vals):
            ax.text(i, v + max(kurt_vals) * 0.02, f"{v:.2f}", ha="center", fontsize=9)
        change = (kurt_vals[1] - kurt_vals[0]) / (kurt_vals[0] + 1e-12) * 100
        ax.annotate(
            f"{change:+.1f}%",
            (1, kurt_vals[1] + max(kurt_vals) * 0.08),
            ha="center",
            fontsize=9,
            color=COLOR_THRESH,
            fontweight="bold",
        )

        mark = MARK_OK if passed else MARK_NG
        color = COLOR_PASS if passed else COLOR_FAIL
        ax.text(
            0.98,
            0.95,
            f"{mark} passed",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=11,
            color=color,
            fontweight="bold",
        )

    fig.suptitle(
        "Layer 2 — preprocessing_cascade.py 级联降噪验证",
        fontsize=14,
        fontweight="bold",
    )
    _save(fig, "05_preprocessing_cascade_correctness.png")


# ═══════════════════════════════════════════════════════════
# 07: order_tracking.py — 阶次跟踪精度
# ═══════════════════════════════════════════════════════════
def plot_order_tracking():
    data = load_json("order_tracking_correctness.json")
    if not data:
        return

    items = []
    for cat, vals in data.items():
        if cat == "summary":
            continue
        for it in vals:
            if "mesh_order" in it:
                items.append((cat, it))

    if not items:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # ── 左图：理论阶次 vs 检出阶次 ──
    ax = axes[0]
    theories = [it["mesh_order"] for _, it in items]
    detected = [it.get("detected_peak_order", 0) for _, it in items]
    colors = [COLOR_PASS if it.get("passed") else COLOR_FAIL for _, it in items]

    x = np.arange(len(items))
    w = 0.35
    ax.bar(x - w / 2, theories, w, color=COLOR_GT, edgecolor="#999", label="理论阶次")
    ax.bar(x + w / 2, detected, w, color=colors, label="检出阶次")

    for i, (cat, it) in enumerate(items):
        t = it["mesh_order"]
        d = it.get("detected_peak_order", 0)
        err = abs(d - t)
        mark = MARK_OK if it.get("passed") else MARK_NG
        color = COLOR_PASS if it.get("passed") else COLOR_FAIL
        ax.annotate(
            f"{mark} Δ={err:.1f}",
            (i, max(t, d) + 0.2),
            ha="center",
            fontsize=9,
            color=color,
            fontweight="bold",
        )

    labels = [cat.replace("_", "\n") for cat, _ in items]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("阶次")
    ax.set_title("阶次跟踪 — 理论阶次 vs 检出阶次\n（误差<1 阶为通过）")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # ── 右图：转速估计误差 ──
    ax = axes[1]
    rot_freqs = [it.get("rot_freq", 0) for _, it in items]
    labels2 = [cat.replace("_", "\n") for cat, _ in items]
    colors2 = [COLOR_PASS if it.get("passed") else COLOR_FAIL for _, it in items]
    x2 = np.arange(len(items))

    ax.bar(x2, rot_freqs, color=colors2, width=0.5)
    ax.set_xticks(x2)
    ax.set_xticklabels(labels2, fontsize=8)
    ax.set_ylabel("设定转频 (Hz)")
    ax.set_title("阶次跟踪 — 各工况转频设定")
    ax.grid(axis="y", alpha=0.3)

    for i, (_, it) in enumerate(items):
        mark = MARK_OK if it.get("passed") else MARK_NG
        color = COLOR_PASS if it.get("passed") else COLOR_FAIL
        ax.text(
            i,
            rot_freqs[i] + 0.3,
            f"{mark}\n{rot_freqs[i]:.0f}Hz",
            ha="center",
            fontsize=9,
            color=color,
            fontweight="bold",
        )

    plt.tight_layout()
    _save(fig, "07_order_tracking_correctness.png")


# ═══════════════════════════════════════════════════════════
# 14: Layer 2 汇总 — 4 个合成验证模块
# ═══════════════════════════════════════════════════════════
def plot_summary():
    json_names = [
        "features_correctness",
        "preprocessing_correctness",
        "preprocessing_cascade_correctness",
        "order_tracking_correctness",
    ]

    summary_data = {}
    for name in json_names:
        data = load_json(f"{name}.json")
        if data and "summary" in data:
            label = name.replace("_correctness", "").replace("_", "\n")
            summary_data[label] = data["summary"]

    if not summary_data:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    labels = list(summary_data.keys())
    totals = [v.get("total", 0) for v in summary_data.values()]
    passed = [v.get("passed", 0) for v in summary_data.values()]
    failed = [
        v.get("failed", v.get("total", 0) - v.get("passed", 0))
        for v in summary_data.values()
    ]

    x = np.arange(len(labels))
    ax.bar(x, passed, color=COLOR_PASS, label="通过", width=0.6)
    ax.bar(x, failed, bottom=passed, color=COLOR_FAIL, label="失败", width=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("测试数")
    ax.set_title("Layer 2 汇总 — 特征提取 & 信号处理（4 个合成验证模块）")
    ax.set_ylim(0, max(totals) * 1.4)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    for i, (t, p, f) in enumerate(zip(totals, passed, failed)):
        pct = p * 100 // t if t > 0 else 0
        ax.text(
            i, t + 0.3, f"{p}/{t}\n{pct}%", ha="center", fontsize=9, fontweight="bold"
        )
        if f > 0:
            ax.text(
                i,
                p + f / 2,
                f"{f}",
                ha="center",
                va="center",
                fontsize=9,
                color="white",
                fontweight="bold",
            )

    # 总通过率标注
    total_all = sum(totals)
    passed_all = sum(passed)
    fig.text(
        0.5,
        0.01,
        f"Layer 2 总通过率: {passed_all}/{total_all} = {passed_all * 100 // total_all if total_all else 0}%",
        ha="center",
        fontsize=12,
        fontweight="bold",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])
    _save(fig, "11_layer2_summary.png")


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════
def main():
    if not HAS_MPL:
        print("matplotlib 未安装，跳过绘图")
        return

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    print("Layer 2: 特征提取 & 信号处理 — 生成对比图")
    print("=" * 55)

    plot_features()  # 01
    plot_preprocessing()  # 04
    plot_preprocessing_cascade()  # 05
    plot_order_tracking()  # 07
    plot_summary()  # 11

    print(f"\n共 5 张图表 → {PLOT_DIR}")


if __name__ == "__main__":
    main()
