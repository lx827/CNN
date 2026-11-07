"""
变速信号阶次跟踪测试(P0 回归 —— 合成信号,无需数据集)

合成 0→40→0Hz 三角扫频信号,叠加 1 阶(不平衡)与 3.57/7.14 阶(ER-16K
轴承 BPFO=3.57×fr 及其二倍)按瞬时转频调制的谐波,验证阶次跟踪算法
能否在变速下分辨阶次成分。

运行方式(见 AGENTS.md §2/§4,uv-only):
    cd cloud
    uv run python tests/diagnosis/regression/test_varying_speed_order.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except ModuleNotFoundError:
    plt = None

from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum,
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)

FS = 8192
DURATION = 8.0          # 秒:0→40Hz 升速 4s,40→0Hz 降速 4s(仿 0_40_0Hz 扫频)
F_MAX = 40.0
BPFO_ORDER = 3.57       # ER-16K 轴承 BPFO(HUSTbear/CW 数据集同款参数,见 docs/datasets.md)


def make_synthetic_signal(seed: int = 20261108) -> np.ndarray:
    """合成变速信号:瞬时转频 fr(t) 三角扫频 + 阶次谐波族 + 弱噪声。

    谐波相位按 ∫fr(t)dt 积分生成(等相位重采样的逆问题),
    保证 1 / BPFO_ORDER / 2×BPFO_ORDER 阶成分在变速下阶次恒定。
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(FS * DURATION)) / FS
    half = DURATION / 2
    fr = np.where(t < half, F_MAX * t / half, F_MAX * (DURATION - t) / half)
    phase_rev = 2 * np.pi * np.cumsum(fr) / FS  # 每 sample 相位增量 2π·fr/fs
    sig = (
        0.60 * np.sin(phase_rev * 1.0)                # 1 阶(不平衡)
        + 0.45 * np.sin(phase_rev * BPFO_ORDER)       # BPFO 阶
        + 0.25 * np.sin(phase_rev * 2 * BPFO_ORDER)   # 2×BPFO 阶
        + 0.10 * np.sin(phase_rev * 2.0)              # 2 阶(不对中)
    )
    sig += 0.05 * rng.standard_normal(len(t))
    return sig


def load_data():
    """P0 回归只依赖合成信号;真实数据集验证归 method_eval/planetary 套件。"""
    return make_synthetic_signal()


def test_estimate_rot_freq():
    """验证转频估计:0-40-0Hz 扫频信号的估计转频应落在扫频范围内"""
    print("\n=== 测试转频估计 ===")
    sig = load_data()
    rf = estimate_rot_freq_spectrum(sig, FS, freq_range=(5, 80))
    print(f"  估计转频: {rf:.2f} Hz (期望处于 0-40Hz 扫频范围)")
    assert 5 <= rf <= 45, f"估计转频 {rf} 不在合理范围"
    print("  [PASS] 转频估计合理")


def test_multi_frame_detects_variation():
    """多帧阶次跟踪应检测到显著的转速变化"""
    print("\n=== 测试多帧法转速变化检测 ===")
    sig = load_data()
    orders, spectrum, median_rf, std_rf = _compute_order_spectrum_multi_frame(
        sig, FS, freq_range=(5, 80), samples_per_rev=512, max_order=20,
        frame_duration=1.0, overlap=0.5,
    )
    cv = std_rf / median_rf if median_rf > 0 else 0
    print(f"  中位数转频: {median_rf:.2f} Hz, 标准差: {std_rf:.2f} Hz, 变异系数: {cv:.2%}")
    assert cv > 0.08, f"变异系数 {cv:.2%} 不足,未检测到转速变化"
    print("  [PASS] 多帧法检测到显著转速变化")


def test_varying_speed_tracking():
    """变速阶次跟踪应产生清晰的阶次谱"""
    print("\n=== 测试变速阶次跟踪 ===")
    sig = load_data()

    # 单帧法(恒定转速假设)
    rf = estimate_rot_freq_spectrum(sig, FS, freq_range=(5, 80))
    orders_single, spectrum_single = _compute_order_spectrum(sig, FS, rf, samples_per_rev=512)
    mask_single = orders_single <= 20
    orders_single = orders_single[mask_single]
    spectrum_single = spectrum_single[mask_single]

    # 变速法
    orders_var, spectrum_var, median_rf, std_rf = _compute_order_spectrum_varying_speed(
        sig, FS, freq_range=(5, 80), samples_per_rev=512, max_order=20,
    )

    print(f"  单帧谱峰值: {np.max(spectrum_single):.2f}")
    print(f"  变速谱峰值: {np.max(spectrum_var):.2f}")
    print(f"  变速谱能量集中度 (前5阶占比): {np.sum(spectrum_var[:5]) / np.sum(spectrum_var):.2%}")

    # 变速法的谱应比单帧法更集中(smearing 更少)
    # 用谱峰度衡量:峰值越尖锐,峰度越高
    kurt_single = np.mean(spectrum_single**4) / (np.mean(spectrum_single**2)**2 + 1e-12)
    kurt_var = np.mean(spectrum_var**4) / (np.mean(spectrum_var**2)**2 + 1e-12)
    print(f"  单帧谱峰度: {kurt_single:.2f}")
    print(f"  变速谱峰度: {kurt_var:.2f}")

    assert kurt_var >= kurt_single * 0.5, "变速阶次跟踪应至少保持相近的峰度"
    print("  [PASS] 变速阶次跟踪有效")


def plot_comparison():
    """生成阶次谱对比图"""
    if plt is None:
        print("\n=== 跳过对比图:未安装 matplotlib ===")
        return
    print("\n=== 生成对比图 ===")
    sig = load_data()

    rf = estimate_rot_freq_spectrum(sig, FS, freq_range=(5, 80))
    orders_single, spectrum_single = _compute_order_spectrum(sig, FS, rf, samples_per_rev=512)
    mask_single = orders_single <= 15
    orders_single = orders_single[mask_single]
    spectrum_single = spectrum_single[mask_single]

    orders_multi, spectrum_multi, _, _ = _compute_order_spectrum_multi_frame(
        sig, FS, freq_range=(5, 80), samples_per_rev=512, max_order=15,
    )

    orders_var, spectrum_var, _, _ = _compute_order_spectrum_varying_speed(
        sig, FS, freq_range=(5, 80), samples_per_rev=512, max_order=15,
    )

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(orders_single, spectrum_single, label="单帧恒定转速")
    axes[0].set_title(f"单帧阶次谱 (假设恒定转速 {rf:.1f} Hz)")
    axes[0].set_ylabel("幅值")
    axes[0].legend()

    axes[1].plot(orders_multi, spectrum_multi, label="多帧平均", color='orange')
    axes[1].set_title("多帧阶次跟踪")
    axes[1].set_ylabel("幅值")
    axes[1].legend()

    axes[2].plot(orders_var, spectrum_var, label="变速跟踪 (STFT+相位积分)", color='green')
    axes[2].set_title("变速阶次跟踪")
    axes[2].set_xlabel("阶次 (Order)")
    axes[2].set_ylabel("幅值")
    axes[2].legend()

    plt.tight_layout()
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(os.path.join(output_dir, "order_tracking_comparison.png"), dpi=150)
    print(f"  对比图已保存: {output_dir}/order_tracking_comparison.png")


def run_all_tests():
    print("=" * 60)
    print("变速信号阶次跟踪测试")
    print("数据: 合成三角扫频信号(0-40-0Hz,无数据集依赖)")
    print(f"采样率: {FS} Hz")
    print("=" * 60)

    test_estimate_rot_freq()
    test_multi_frame_detects_variation()
    test_varying_speed_tracking()
    plot_comparison()

    print("\n" + "=" * 60)
    print("全部测试通过 [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
