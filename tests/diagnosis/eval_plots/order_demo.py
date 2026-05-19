"""
变速阶次跟踪演示 — CW数据集 + _compute_order_spectrum_varying_speed

展示系统最核心的变速工况诊断能力：
- 时域波形 + 瞬时转速
- 变速阶次谱（等角度重采样后，故障阶次清晰可辨）
- 包络阶次谱（故障特征阶次峰值标注）

输出: tests/output/eval_plots/cw_order_demo/
"""
import sys
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))

from app.services.diagnosis.order_tracking import _compute_order_spectrum_varying_speed
from app.services.diagnosis.signal_utils import bandpass_filter, estimate_rot_freq_spectrum

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 配置 ──────────────────────────────────────────────────
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")
FS = 8192
OUT_DIR = PROJECT_ROOT / "tests" / "output" / "eval_plots" / "cw_order_demo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ER-16K 轴承参数
BPFI_COEF = 5.43  # BPFI = 5.43 × fr
BPFO_COEF = 3.57  # BPFO = 3.57 × fr


def main():
    # 选择外圈故障变速文件
    fname = "O-A-1.npy"  # 外圈故障, 升速 14.8→27.1 Hz
    fp = CW_DIR / fname
    if not fp.exists():
        fname = "I-A-1.npy"  # fallback: 内圈故障
        fp = CW_DIR / fname

    print(f"加载: {fname}")
    sig = np.load(fp).astype(np.float64)[:FS * 5]  # 5秒

    # ═══════════════════════════════════════════════════════
    # 1. 变速阶次跟踪
    # ═══════════════════════════════════════════════════════
    print("运行变速阶次跟踪...")
    orders, spectrum, median_rf, std_rf = _compute_order_spectrum_varying_speed(
        sig, FS, freq_range=(10, 40), samples_per_rev=2048, max_order=20
    )
    print(f"  中位数转频: {median_rf:.1f} Hz, 标准差: {std_rf:.1f} Hz")

    # 理论故障阶次
    bpfo_order = BPFO_COEF  # 3.57
    bpfi_order = BPFI_COEF  # 5.43
    bsf_order = 4.71

    # ═══════════════════════════════════════════════════════
    # 2. 包络阶次谱 (窄带滤波 + Hilbert + 阶次跟踪)
    # ═══════════════════════════════════════════════════════
    # 宽带带通滤波 → 包络 → 阶次跟踪
    band = bandpass_filter(sig, FS, 500, 3500, order=4)
    envelope = np.abs(scipy_hilbert(band))
    envelope = envelope - np.mean(envelope)
    env_orders, env_spectrum, env_rf, _ = _compute_order_spectrum_varying_speed(
        envelope, FS, freq_range=(5, 50), samples_per_rev=2048, max_order=20
    )
    print(f"  包络阶次追踪转频: {env_rf:.1f} Hz")

    # 包络阶次谱中寻找 bpfo/bpfi 峰值
    env_peaks = []
    for target_order in [bpfo_order, bpfi_order, bsf_order]:
        tol = 0.3
        mask = (env_orders >= target_order - tol) & (env_orders <= target_order + tol)
        if mask.any():
            idx = np.argmax(env_spectrum[mask])
            peak_order = env_orders[mask][idx]
            peak_val = env_spectrum[mask][idx]
            env_peaks.append((peak_order, peak_val, target_order))
            print(f"  包络谱峰值 @ {peak_order:.2f}阶 (理论BPFO={bpfo_order}) → amp={peak_val:.1f}")

    # ═══════════════════════════════════════════════════════
    # 3. 绘图 — 3面板专业风格
    # ═══════════════════════════════════════════════════════
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 200, "savefig.dpi": 200,
        "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12,
    })

    fig, axes = plt.subplots(3, 1, figsize=(12, 13))

    # Panel 1: 时域波形 + 瞬时转速
    ax = axes[0]
    t = np.arange(min(4096, len(sig))) / FS * 1000  # ms
    ax.plot(t, sig[:4096], color="#2980B9", linewidth=0.5, alpha=0.8)
    ax.set_xlabel("时间 (ms)")
    ax.set_ylabel("加速度 (g)")
    ax.set_title(f"CW变速数据集 — 外圈故障 升速工况\n{fname}  |  转频范围 {median_rf-std_rf:.0f}~{median_rf+std_rf:.0f} Hz  |  BPFO={bpfo_order}×fr, BPFI={bpfi_order}×fr", fontweight="bold")
    ax.grid(alpha=0.25, linestyle="--")

    # Panel 2: 变速阶次谱
    ax = axes[1]
    ax.fill_between(orders, spectrum, alpha=0.4, color="#27AE60", step="mid")
    ax.plot(orders, spectrum, color="#27AE60", linewidth=0.8)
    ax.set_xlabel("阶次 (× 转频)")
    ax.set_ylabel("幅值")
    ax.set_xlim(0, 15)
    ax.set_title("变速阶次谱 (STFT瞬时频率积分 → 等角度重采样)", fontweight="bold", color="#27AE60")
    # 标记故障阶次
    for order, label, color in [(bpfo_order, "BPFO=3.57", "#E74C3C"),
                                  (bpfi_order, "BPFI=5.43", "#F39C12"),
                                  (bsf_order, "BSF=4.71", "#8E44AD")]:
        ax.axvline(order, color=color, linewidth=1.5, linestyle="--", alpha=0.7)
        ax.text(order + 0.2, ax.get_ylim()[1] * 0.95, label, color=color, fontsize=9,
                fontweight="bold", rotation=90, va="top")
    ax.grid(alpha=0.25, linestyle="--")

    # Panel 3: 包络阶次谱 + 峰值标注
    ax = axes[2]
    ax.fill_between(env_orders, env_spectrum, alpha=0.4, color="#E74C3C", step="mid")
    ax.plot(env_orders, env_spectrum, color="#E74C3C", linewidth=0.8)
    ax.set_xlabel("阶次 (× 转频)")
    ax.set_ylabel("包络幅值")
    ax.set_xlim(0, 15)
    ax.set_title("包络阶次谱 — 故障特征阶次清晰可辨", fontweight="bold", color="#E74C3C")
    # 峰值标注
    for peak_order, peak_val, target_order in env_peaks:
        name = {bpfo_order: "BPFO", bpfi_order: "BPFI", bsf_order: "BSF"}.get(target_order, "?")
        ax.annotate(f"{name}\n{peak_order:.2f}阶",
                    xy=(peak_order, peak_val), xytext=(peak_order + 2, peak_val * 1.3),
                    fontsize=10, fontweight="bold", color="#C0392B",
                    arrowprops=dict(arrowstyle="->", color="#C0392B", lw=1.5),
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    # 理论位置虚线
    for order, label, color in [(bpfo_order, "BPFO", "#E74C3C"),
                                  (bpfi_order, "BPFI", "#F39C12")]:
        ax.axvline(order, color=color, linewidth=1, linestyle=":", alpha=0.5)
    ax.grid(alpha=0.25, linestyle="--")

    fig.tight_layout(pad=2)

    for fmt in ["svg", "png"]:
        out_path = OUT_DIR / f"cw_order_demo.{fmt}"
        fig.savefig(out_path)
        print(f"  → {out_path}")
    plt.close(fig)

    print("\n完成！图表展示变速工况下阶次跟踪算法的核心能力。")

# 延迟导入避免顶层import失败
from scipy.signal import hilbert as scipy_hilbert

if __name__ == "__main__":
    main()
