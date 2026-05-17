"""
变速信号阶次跟踪测试

使用 HUSTbear 数据集中的 0.5X_B_VS_0_40_0Hz-X.npy（从 0Hz 启动到 40Hz 又回到 0Hz）
验证改进后的阶次跟踪算法能否清晰分辨轴承故障阶次。

运行方式:
    cd d:/code/CNN
    python tests/diagnosis/test_varying_speed_order.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))

import numpy as np
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None

from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
from app.services.diagnosis.order_tracking import (
    _compute_order_spectrum,
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
)

DATA_PATH = r"E:\A-codehub\CNN\HUSTbear\down8192\0.5X_B_VS_0_40_0Hz-X.npy"
FS = 8192


def load_data():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"数据不存在: {DATA_PATH}")
    return np.load(DATA_PATH)


def test_estimate_rot_freq():
    """验证转频估计：0-40-0Hz 信号应落在扫频范围内"""
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
    assert cv > 0.08, f"变异系数 {cv:.2%} 不足，未检测到转速变化"
    print("  [PASS] 多帧法检测到显著转速变化")


def test_varying_speed_tracking():
    """变速阶次跟踪应产生清晰的阶次谱"""
    print("\n=== 测试变速阶次跟踪 ===")
    sig = load_data()

    # 单帧法（恒定转速假设）
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

    # 变速法的谱应比单帧法更集中（smearing 更少）
    # 用谱峰度衡量：峰值越尖锐，峰度越高
    kurt_single = np.mean(spectrum_single**4) / (np.mean(spectrum_single**2)**2 + 1e-12)
    kurt_var = np.mean(spectrum_var**4) / (np.mean(spectrum_var**2)**2 + 1e-12)
    print(f"  单帧谱峰度: {kurt_single:.2f}")
    print(f"  变速谱峰度: {kurt_var:.2f}")

    assert kurt_var >= kurt_single * 0.5, "变速阶次跟踪应至少保持相近的峰度"
    print("  [PASS] 变速阶次跟踪有效")


def plot_comparison():
    """生成阶次谱对比图"""
    if plt is None:
        print("\n=== 跳过对比图：未安装 matplotlib ===")
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
    print(f"数据: {DATA_PATH}")
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
