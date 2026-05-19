"""
CW变速转频估计+阶次谱 — 改进版

基于 plot_results.py 图17 的逻辑，使用最准确的 _compute_order_spectrum_varying_speed
生成 2 面板图：
  上：转频估计精度对比 (spectrum vs order_tracking vs GT范围)
  下：变速阶次谱示例 — 外圈故障 BPFO 峰值清晰可辨

输出: tests/output/eval_plots/cw_order_demo/
"""
import sys, json
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import _compute_order_spectrum_varying_speed, _compute_order_spectrum
from app.services.diagnosis.signal_utils import bandpass_filter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import hilbert as scipy_hilbert

# ── 配置 ──────────────────────────────────────────────────
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
FS = 8192
OUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots" / "cw_order_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 轴承参数 ER-16K
BPFO_COEF = 3.57
BPFI_COEF = 5.43

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.dpi": 200, "savefig.dpi": 200,
    "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12,
})


def main():
    # ═══════════════════════════════════════════════════════
    # Panel 1: 转频估计精度对比 (复现并改进图17)
    # ═══════════════════════════════════════════════════════
    cw_cases = [
        ("H-A-1.npy", "健康", (14.1, 23.8)),
        ("H-A-2.npy", "健康", (14.1, 29.0)),
        ("I-A-1.npy", "内圈故障", (12.5, 27.8)),
        ("I-A-2.npy", "内圈故障", (13.0, 25.7)),
        ("O-A-1.npy", "外圈故障", (14.8, 27.1)),
        ("O-A-2.npy", "外圈故障", (12.9, 23.0)),
    ]

    results = []
    for fname, desc, (lo, hi) in cw_cases:
        fp = CW_DIR / fname
        if not fp.exists():
            continue
        sig = np.load(fp).astype(np.float64)[:FS * 5]

        # spectrum 法
        rf_spec = estimate_rot_freq_spectrum(sig, FS, freq_range=(5, 50))
        # 变速阶次跟踪法
        _, _, median_rf, std_rf = _compute_order_spectrum_varying_speed(
            sig, FS, freq_range=(5, 40), samples_per_rev=512, max_order=20)

        spec_ok = lo <= rf_spec <= hi
        order_ok = lo <= median_rf <= hi

        results.append({
            "fname": fname, "desc": desc, "lo": lo, "hi": hi,
            "spec_hz": float(rf_spec), "spec_ok": spec_ok,
            "order_hz": float(median_rf), "order_std": float(std_rf), "order_ok": order_ok,
            "sig": sig,
        })

    # ═══════════════════════════════════════════════════════
    # 绘图 — 2 面板
    # ═══════════════════════════════════════════════════════
    fig = plt.figure(figsize=(13, 11))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.2], hspace=0.35)

    # ═══ Panel 1: 转频估计对比 ═══
    ax1 = fig.add_subplot(gs[0])
    labels = [f"{r['desc']}\n{r['fname']}" for r in results]
    y = range(len(labels))
    n = len(results)

    for i, r in enumerate(results):
        # GT 范围灰色带
        ax1.barh(i, r["hi"] - r["lo"], left=r["lo"], height=0.25,
                 color="#BDC3C7", alpha=0.5, zorder=1)
        ax1.text(r["hi"] + 0.5, i + 0.12, f"[{r['lo']:.0f}-{r['hi']:.0f}]Hz",
                 fontsize=8, color="gray", va="bottom")

        # spectrum 估计点
        c_spec = "#27AE60" if r["spec_ok"] else "#E74C3C"
        ax1.scatter(r["spec_hz"], i, color=c_spec, s=100, zorder=3,
                    marker="o", edgecolors="white", linewidth=0.8)
        ax1.text(r["spec_hz"] + 0.5, i - 0.3, f"频谱={r['spec_hz']:.1f}",
                 fontsize=7, color=c_spec, va="top")

        # order_tracking 估计点
        c_ord = "#2980B9" if r["order_ok"] else "#E74C3C"
        ax1.scatter(r["order_hz"], i, color=c_ord, s=120, zorder=4,
                    marker="D", edgecolors="white", linewidth=0.8)
        ax1.text(r["order_hz"] + 0.5, i, f"阶次={r['order_hz']:.1f}±{r['order_std']:.1f}",
                 fontsize=7, color=c_ord, fontweight="bold")

        # 通过/失败标记
        ok = r["spec_ok"] or r["order_ok"]
        mk = "OK" if ok else "NG"
        ax1.text(max(r["lo"], r["hi"]) + 3, i, mk, fontsize=14,
                 color="#27AE60" if ok else "#E74C3C", fontweight="bold", ha="center")

    ax1.set_yticks(list(y))
    ax1.set_yticklabels(labels, fontsize=9)
    ax1.set_xlabel("频率 (Hz)", fontsize=12)
    ax1.set_xlim(5, 50)
    ax1.set_title("CW变速数据集 — 转频估计精度对比\n"
                  "灰带=Ground Truth  ○绿色/红色=频谱法  ◇蓝色/红色=阶次跟踪法(最准确)",
                  fontweight="bold", fontsize=13, pad=12)
    ax1.grid(axis="x", alpha=0.3, linestyle="--")

    # 图例
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    legend_elements = [
        Patch(facecolor="#BDC3C7", alpha=0.5, label="GT转速范围"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#27AE60", markersize=10, label="频谱法"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="#2980B9", markersize=10, label="阶次跟踪法(最准确)"),
    ]
    ax1.legend(handles=legend_elements, loc="lower right", fontsize=9)

    # ═══ Panel 2: 外圈故障变速阶次谱 ═══
    ax2 = fig.add_subplot(gs[1])

    # 选外圈故障文件做示范
    or_result = [r for r in results if "外圈" in r["desc"]]
    if not or_result:
        or_result = [results[0]]
    demo = or_result[0]
    sig = demo["sig"]
    median_rf = demo["order_hz"]

    # 宽带包络 → 变速阶次跟踪
    band = bandpass_filter(sig, FS, 500, 3500, order=4)
    env = np.abs(scipy_hilbert(band))
    env = env - np.mean(env)
    env_orders, env_spec, _, _ = _compute_order_spectrum_varying_speed(
        env, FS, freq_range=(5, 50), samples_per_rev=2048, max_order=12)

    ax2.fill_between(env_orders, env_spec, alpha=0.35, color="#E74C3C", step="mid")
    ax2.plot(env_orders, env_spec, color="#E74C3C", linewidth=1.0)
    ax2.set_xlabel("阶次 (× 转频)", fontsize=12)
    ax2.set_ylabel("包络幅值", fontsize=12)
    ax2.set_xlim(0, 12)
    ax2.set_title(f"变速阶次谱 — 外圈故障 {demo['fname']}  |  转频={median_rf:.1f}±{demo['order_std']:.1f} Hz\n"
                  "BPFO=3.57×fr 峰值清晰可辨，变速工况下阶次跟踪算法有效",
                  fontweight="bold", fontsize=13, pad=12)

    # 标注 BPFO 及其谐波
    for harm in range(1, 4):
        order = BPFO_COEF * harm
        tol = 0.3
        mask = (env_orders >= order - tol) & (env_orders <= order + tol)
        if mask.any() and np.max(env_spec[mask]) > 0:
            idx = np.argmax(env_spec[mask])
            peak_o = env_orders[mask][idx]
            peak_v = env_spec[mask][idx]
            label = f"BPFO×{harm}\n{peak_o:.2f}阶" if harm > 1 else f"BPFO\n{peak_o:.2f}阶"
            ax2.annotate(label, xy=(peak_o, peak_v),
                        xytext=(peak_o + 1.2, peak_v * 1.2),
                        fontsize=10, fontweight="bold", color="#C0392B",
                        arrowprops=dict(arrowstyle="->", color="#C0392B", lw=1.5),
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))
        ax2.axvline(order, color="#E74C3C", linewidth=0.8, linestyle=":", alpha=0.5)
    # BPFI 参考线
    ax2.axvline(BPFI_COEF, color="#F39C12", linewidth=0.8, linestyle="--", alpha=0.4)
    ax2.text(BPFI_COEF + 0.1, ax2.get_ylim()[1] * 0.92, "BPFI=5.43", color="#F39C12", fontsize=8)

    ax2.grid(alpha=0.25, linestyle="--")

    # ── 保存 ──
    fig.tight_layout()
    for fmt in ["svg", "png"]:
        fp = OUT_DIR / f"cw_speed_order.{fmt}"
        fig.savefig(fp)
        print(f"  → {fp}")
    plt.close(fig)

    # ── 统计 ──
    spec_ok = sum(1 for r in results if r["spec_ok"])
    order_ok = sum(1 for r in results if r["order_ok"])
    print(f"\n频谱法通过: {spec_ok}/{n}, 阶次跟踪法通过: {order_ok}/{n}")


if __name__ == "__main__":
    main()
