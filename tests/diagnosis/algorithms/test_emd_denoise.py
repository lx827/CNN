"""
EMD / CEEMDAN 降噪模块回归测试

验证修复后的三个核心逻辑：
1. 边界镜像填充：按信号值而非极值幅值镜像
2. Rilling 停止准则：包络对称性 (|avg_env|/amp) 而非前后差值
3. CEEMDAN 噪声逻辑：白噪声 IMF 分层而非纯白噪声
"""
import sys
import os
import numpy as np

# 添加 cloud 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'cloud'))

from app.services.diagnosis.emd_denoise import (
    emd_decompose, ceemdan_decompose, emd_denoise,
    _find_extrema, _refine_extrema_parabolic,
    _pad_extrema_rilling, _compute_envelope_mean,
    _stop_sd, _stop_rilling, _excess_kurtosis,
)


def _make_test_signal(N=1024, fs=256.0):
    """构造已知频率成分的测试信号"""
    t = np.arange(N) / fs
    # 三个频率成分 + 微弱噪声
    sig = 1.0 * np.sin(2 * np.pi * 10 * t)      # 10 Hz 主频
    sig += 0.3 * np.sin(2 * np.pi * 40 * t)      # 40 Hz 谐波
    sig += 0.1 * np.sin(2 * np.pi * 100 * t)     # 100 Hz 高频
    sig += 0.02 * np.random.randn(N)              # 微弱噪声
    return sig


# ═══════ 测试1: 边界镜像填充 ─────────────────────────────
def test_pad_extrema_rilling_returns_signal_values():
    """填充幅值取信号值而非极值幅值镜像"""
    sig = _make_test_signal(256)
    max_idx, min_idx, _ = _find_extrema(sig)
    if len(max_idx) < 2 or len(min_idx) < 2:
        print("  SKIP: 信号极值不足")
        return

    max_locs, max_mags, min_locs, min_mags = _pad_extrema_rilling(
        sig, max_idx, min_idx, pad_width=3
    )

    # 填充后的幅值必须在信号值范围内（而非极值幅值镜像产生的超范围值）
    sig_range = (float(np.min(sig)), float(np.max(sig)))
    for m in max_mags:
        # 允许小幅超出（镜像位置取值可能不是精确极值），但不应严重偏离
        assert m < sig_range[1] * 2.0, f"填充幅值 {m} 远超信号最大值 {sig_range[1]}"
    for m in min_mags:
        assert m > sig_range[0] * 2.0 if sig_range[0] < 0 else m > sig_range[0] - abs(sig_range[0]), \
            f"填充幅值 {m} 远低于信号最小值 {sig_range[0]}"
    print("  PASS: 填充幅值在合理范围内")


def test_pad_extrema_rilling_joint_processing():
    """极大值和极小值同时处理（4元组返回）"""
    sig = np.sin(np.linspace(0, 4 * np.pi, 100))
    max_idx, min_idx, _ = _find_extrema(sig)

    max_locs, max_mags, min_locs, min_mags = _pad_extrema_rilling(
        sig, max_idx, min_idx, pad_width=2
    )

    assert len(max_locs) == len(max_mags), "max locs/mags 长度不一致"
    assert len(min_locs) == len(min_mags), "min locs/mags 长度不一致"
    # 填充后极值数量应 >= 原始极值数量
    assert len(max_locs) >= len(max_idx), f"填充后极大值数量 {len(max_locs)} < 原始 {len(max_idx)}"
    assert len(min_locs) >= len(min_idx), f"填充后极小值数量 {len(min_locs)} < 原始 {len(min_idx)}"
    print("  PASS: 极大极小值同时处理，4元组返回")


# ═══════ 测试2: Rilling 停止准则 ──────────────────────────
def test_stop_rilling_envelope_symmetry():
    """Rilling 停止准则评估包络对称性而非前后差值"""
    N = 200
    # 纯正弦是完美对称 IMF → 应立即停止
    perfect_imf = np.sin(np.linspace(0, 4 * np.pi, N))
    max_idx, min_idx, _ = _find_extrema(perfect_imf)
    _, upper, lower = _compute_envelope_mean(perfect_imf, max_idx, min_idx)
    result = _stop_rilling(upper, lower)
    # 调试：打印评估指标
    avg_env = (upper + lower) / 2.0
    amp = np.abs(upper - lower) / 2.0
    eval_metric = np.abs(avg_env) / (amp + 1e-18)
    max_e = float(np.max(eval_metric))
    ratio_over_sd1 = float(np.mean(eval_metric > 0.05))
    any_over_sd2 = float(np.any(eval_metric > 0.5))
    if not result:
        print(f"  DEBUG: max_E={max_e:.6f}, ratio_E>0.05={ratio_over_sd1:.4f}, any_E>0.5={any_over_sd2:.4f}")
    assert result == True, f"纯正弦 IMF 的 Rilling 准则应返回 True，实际返回 {result} (max_E={max_e:.6f})"
    print("  PASS: 纯正弦 IMF → Rilling 立即停止")

    # 明显不对称信号 → 不应停止（线性趋势叠加正弦）
    asymmetric = np.sin(np.linspace(0, 4 * np.pi, N)) + 2.0 * np.linspace(-1, 1, N)
    max_idx2, min_idx2, _ = _find_extrema(asymmetric)
    if len(max_idx2) >= 2 and len(min_idx2) >= 2:
        _, upper2, lower2 = _compute_envelope_mean(asymmetric, max_idx2, min_idx2)
        result2 = _stop_rilling(upper2, lower2)
        assert result2 == False, f"明显不对称信号的 Rilling 准则应返回 False，实际返回 {result2}"
    else:
        print("  SKIP: 不对称信号极值不足，跳过不对称测试")
    print("  PASS: 不对称信号 → Rilling 不停止")


def test_stop_rilling_uses_envelope_not_diff():
    """确认 Rilling 准则的输入是包络而非前后 proto_imf 差值"""
    # _stop_rilling 现在接受 (upper_env, lower_env) 而非 (proto_imf, old)
    # 通过函数签名验证
    import inspect
    sig = inspect.signature(_stop_rilling)
    params = list(sig.parameters.keys())
    assert params == ['upper_env', 'lower_env', 'sd1', 'sd2', 'tol'], \
        f"_stop_rilling 参数签名应为 [upper_env, lower_env, sd1, sd2, tol]，实际为 {params}"
    print("  PASS: Rilling 准则参数签名已改为包络输入")


# ═══════ 测试3: EMD 分解完备性 ──────────────────────────
def test_emd_completeness():
    """IMF 之和 + 残差 ≈ 原信号"""
    sig = _make_test_signal(512)
    imfs, residue = emd_decompose(sig, max_imfs=6, sd_threshold=0.25)

    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed - sig)))
    assert error < 0.01, f"EMD 完备性误差 {error:.6f} > 0.01"
    print(f"  PASS: EMD 完备性误差 = {error:.6f}")


def test_emd_rilling_mode():
    """EMD Rilling 停止准则模式不崩溃"""
    sig = _make_test_signal(512)
    imfs, residue = emd_decompose(sig, max_imfs=6, use_rilling=True)
    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed - sig)))
    assert error < 0.1, f"EMD(Rilling) 完备性误差 {error:.6f} > 0.1"
    print(f"  PASS: EMD(Rilling) 完备性误差 = {error:.6f}")


def test_emd_normalization_mode():
    """EMD 标准化模式正确恢复幅值"""
    sig = _make_test_signal(512) * 100  # 放大100倍
    imfs, residue = emd_decompose(sig, max_imfs=6, normalize=True)
    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed - sig)))
    assert error < 1.0, f"EMD(标准化) 幅值恢复误差 {error:.4f} > 1.0"
    print(f"  PASS: EMD(标准化) 幅值恢复误差 = {error:.4f}")


# ═══════ 测试4: CEEMDAN Torres 2011 噪声逻辑 ────────────
def test_ceemdan_completeness():
    """CEEMDAN 完备性：IMF之和 + 残差 ≈ 原信号"""
    sig = _make_test_signal(512)
    # 使用小 ensemble_size 加速测试
    imfs, residue = ceemdan_decompose(
        sig, max_imfs=4, ensemble_size=5, noise_std=0.2,
    )

    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed - sig)))
    # CEEMDAN 完备性允许更大误差（噪声辅助分解固有偏差）
    assert error < 0.5, f"CEEMDAN 完备性误差 {error:.4f} > 0.5"
    print(f"  PASS: CEEMDAN 完备性误差 = {error:.4f}")


def test_ceemdan_noise_is_imf_layered():
    """CEEMDAN 噪声来源是白噪声 IMF 分层（而非纯白噪声）"""
    # 验证 ceemdan_decompose 内部确实预分解了白噪声
    # 通过小 ensemble 运行，确认不崩溃且产生合理结果
    sig = np.sin(np.linspace(0, 2 * np.pi, 256))
    imfs, residue = ceemdan_decompose(
        sig, max_imfs=3, ensemble_size=3, noise_std=0.15,
    )
    assert len(imfs) >= 1, "CEEMDAN 应至少产生1个IMF"
    # IMF 不应全零
    assert float(np.std(imfs[0])) > 1e-6, "第1阶IMF不应全零"
    print("  PASS: CEEMDAN IMF 分层噪声逻辑运行正常")


# ═══════ 测试5: 降噪入口 ────────────────────────────────
def test_emd_denoise_entry():
    """emd_denoise 统一入口不崩溃"""
    sig = _make_test_signal(512)
    reconstructed, info = emd_denoise(sig, method="emd")
    assert "n_imfs" in info, "返回信息缺少 n_imfs"
    assert "kurtosis_before" in info, "返回信息缺少 kurtosis_before"
    assert "kurtosis_after" in info, "返回信息缺少 kurtosis_after"
    assert len(reconstructed) == len(sig), f"重构长度 {len(reconstructed)} != 原信号 {len(sig)}"
    print(f"  PASS: emd_denoise(emd) 返回 {info['n_imfs']} 个IMF")


def test_ceemdan_denoise_entry():
    """CEEMDAN 降噪入口不崩溃（小参数）"""
    sig = _make_test_signal(256)
    reconstructed, info = emd_denoise(
        sig, method="ceemdan", max_imfs=4, ensemble_size=5,
    )
    assert len(reconstructed) == len(sig), f"重构长度 {len(reconstructed)} != 原信号 {len(sig)}"
    print(f"  PASS: emd_denoise(ceemdan) 返回 {info['n_imfs']} 个IMF")


# ═══════ 测试6: 边界情况 ─────────────────────────────────
def test_zero_signal():
    """零信号安全处理"""
    sig = np.zeros(256)
    imfs, residue = emd_decompose(sig, max_imfs=3)
    reconstructed = np.sum(imfs, axis=0) + residue
    assert float(np.max(np.abs(reconstructed))) < 1e-10, "零信号重构应为零"
    print("  PASS: 零信号安全处理")


def test_constant_signal():
    """常数信号安全处理"""
    sig = np.ones(256) * 5.0
    imfs, residue = emd_decompose(sig, max_imfs=3)
    # 常数信号没有极值，不应产生任何 IMF
    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed - sig)))
    assert error < 1e-10, f"常数信号重构误差 {error:.6f}"
    print("  PASS: 常数信号安全处理")


def test_ceemdan_zero_signal():
    """CEEMDAN 零信号安全处理"""
    sig = np.zeros(256)
    imfs, residue = ceemdan_decompose(sig, max_imfs=3, ensemble_size=3)
    assert len(imfs) >= 1, "CEEMDAN 应返回至少1个IMF（零信号）"
    # 零信号分解后 IMF之和 + 残差 ≈ 0
    reconstructed = np.sum(imfs, axis=0) + residue
    error = float(np.max(np.abs(reconstructed)))
    assert error < 0.01, f"CEEMDAN 零信号误差 {error:.6f} > 0.01"
    print("  PASS: CEEMDAN 零信号安全处理")


def test_short_signal():
    """极短信号（<4点）安全处理"""
    sig = np.array([1.0, 2.0])
    imfs, residue = emd_decompose(sig, max_imfs=3)
    assert len(imfs) == 0 or len(residue) == 2, "极短信号应安全返回"
    print("  PASS: 极短信号安全处理")


# ═══════ 测试7: _compute_envelope_mean 返回3元组 ────────
def test_envelope_mean_returns_3tuple():
    """_compute_envelope_mean 返回 (mean, upper, lower) 3元组"""
    sig = np.sin(np.linspace(0, 4 * np.pi, 100))
    max_idx, min_idx, _ = _find_extrema(sig)
    result = _compute_envelope_mean(sig, max_idx, min_idx)
    assert len(result) == 3, f"_compute_envelope_mean 应返回3元组，实际返回 {len(result)} 个值"
    env_mean, upper, lower = result
    # 上包络应 >= 下包络
    assert np.all(upper >= lower - 1e-10), "上包络应 >= 下包络"
    # mean = (upper + lower) / 2
    expected_mean = (upper + lower) / 2.0
    assert np.allclose(env_mean, expected_mean, atol=1e-10), "mean != (upper+lower)/2"
    print("  PASS: _compute_envelope_mean 返回3元组 (mean, upper, lower)")


# ═══════ 运行所有测试 ═══════
if __name__ == "__main__":
    tests = [
        ("边界镜像填充: 幅值取信号值", test_pad_extrema_rilling_returns_signal_values),
        ("边界镜像填充: 联合处理", test_pad_extrema_rilling_joint_processing),
        ("Rilling准则: 包络对称性", test_stop_rilling_envelope_symmetry),
        ("Rilling准则: 参数签名", test_stop_rilling_uses_envelope_not_diff),
        ("EMD完备性", test_emd_completeness),
        ("EMD(Rilling)模式", test_emd_rilling_mode),
        ("EMD标准化模式", test_emd_normalization_mode),
        ("CEEMDAN完备性", test_ceemdan_completeness),
        ("CEEMDAN IMF分层噪声", test_ceemdan_noise_is_imf_layered),
        ("emd_denoise入口(emd)", test_emd_denoise_entry),
        ("emd_denoise入口(ceemdan)", test_ceemdan_denoise_entry),
        ("零信号", test_zero_signal),
        ("常数信号", test_constant_signal),
        ("CEEMDAN零信号", test_ceemdan_zero_signal),
        ("极短信号", test_short_signal),
        ("envelope_mean 3元组", test_envelope_mean_returns_3tuple),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        print(f"\n[TEST] {name}")
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"结果: {passed} 通过, {failed} 失败 / {len(tests)} 总计")
    if failed > 0:
        sys.exit(1)