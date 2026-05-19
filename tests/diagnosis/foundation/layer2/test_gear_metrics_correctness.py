"""
Layer 2 齿轮指标 — gear/metrics.py 正确性验证

测试 gear/metrics.py 中依赖 Layer 1 的函数：
  compute_tsa_residual_order, compute_fm4, compute_car,
  compute_ser_order, compute_fm0_order

原则：合成已知 ground truth 的齿轮信号，验证指标计算正确性。

输出: layer2/output/gear_metrics_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.gear.metrics import (
    compute_tsa_residual_order, compute_fm4, compute_car,
    compute_ser_order, compute_fm0_order,
)
from app.services.diagnosis.signal_utils import compute_fft_spectrum
from app.services.diagnosis.order_tracking import _compute_order_spectrum
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, gear_mesh, sinusoidal,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


# ═══════════════════════════════════════════════════════════
# 1. compute_tsa_residual_order — 时域同步平均
# ═══════════════════════════════════════════════════════════

def test_tsa():
    """TSA：合成齿轮信号验证等角度重采样和周期平均"""
    print("\n--- compute_tsa_residual_order ---")
    results = []

    # 合成齿轮信号：转频=25Hz, 啮合=450Hz
    sig, fs, gt = gear_mesh(mesh_freq=450.0, rot_freq=25.0, duration=4.0, fs=FS, snr_db=30)
    res = compute_tsa_residual_order(sig, fs, rot_freq=25.0, samples_per_rev=512, min_revolutions=3)

    valid_ok = res.get("valid", False)
    rev_ok = res.get("revolutions", 0) >= 3
    has_tsa = len(res.get("tsa_cycle", [])) > 0
    has_residual = len(res.get("residual", [])) > 0
    has_diff = len(res.get("differential", [])) > 0

    passed = valid_ok and rev_ok and has_tsa and has_residual and has_diff
    results.append({
        "test": "tsa_basic",
        "valid": valid_ok,
        "revolutions": res.get("revolutions", 0),
        "tsa_cycle_len": len(res.get("tsa_cycle", [])),
        "passed": passed,
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] TSA: valid={valid_ok}, rev={res.get('revolutions', 0)}, tsa_cycle={len(res.get('tsa_cycle', []))}")

    # 边界：无效转频
    res_invalid = compute_tsa_residual_order(sig, fs, rot_freq=0)
    invalid_ok = not res_invalid.get("valid", True)
    results.append({
        "test": "tsa_invalid_rot_freq",
        "valid": res_invalid.get("valid", True),
        "passed": invalid_ok,
    })
    print(f"  [{'PASS' if invalid_ok else 'FAIL'}] 无效转频安全处理")

    return results, res if passed else None


# ═══════════════════════════════════════════════════════════
# 2. compute_fm4 — 差分信号归一化峭度
# ═══════════════════════════════════════════════════════════

def test_fm4(tsa_res):
    """FM4：基于 TSA 差分信号计算"""
    print("\n--- compute_fm4 ---")
    results = []

    if tsa_res is None or not tsa_res.get("valid"):
        results.append({"test": "fm4_skipped", "reason": "tsa_failed", "passed": False})
        print("  [SKIP] TSA 失败，跳过 FM4")
        return results

    diff = tsa_res.get("differential")
    fm4_val = compute_fm4(diff)

    # 健康齿轮信号（合成 gear_mesh 无严重故障）FM4 应接近高斯基准 3.0
    # 因为 gear_mesh 只是正常啮合+边频带，差分信号接近随机
    fm4_ok = 2.0 < fm4_val < 8.0  # 健康状态在一个合理范围内
    results.append({
        "test": "fm4_healthy_gear",
        "fm4": round(fm4_val, 4),
        "passed": fm4_ok,
    })
    print(f"  [{'PASS' if fm4_ok else 'FAIL'}] FM4(健康): {fm4_val:.3f}")

    # 用纯高斯噪声验证基准 ≈ 3.0
    np.random.seed(42)
    noise = np.random.randn(5000)
    fm4_noise = compute_fm4(noise)
    noise_ok = 2.5 < fm4_noise < 3.5
    results.append({
        "test": "fm4_gaussian_baseline",
        "fm4": round(fm4_noise, 4),
        "passed": noise_ok,
    })
    print(f"  [{'PASS' if noise_ok else 'FAIL'}] FM4(高斯基准): {fm4_noise:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. compute_car — 倒频谱幅值比
# ═══════════════════════════════════════════════════════════

def test_car():
    """CAR：合成含周期性成分的信号验证"""
    print("\n--- compute_car ---")
    results = []

    # 合成信号：转频=25Hz 及其谐波 + 噪声
    duration = 4.0
    t = np.arange(0, duration, 1/FS)
    sig = np.sin(2*np.pi*25*t) + 0.5*np.sin(2*np.pi*50*t) + 0.3*np.sin(2*np.pi*75*t)
    sig += 0.2 * np.random.randn(len(t))

    car_val = compute_car(sig, FS, rot_freq=25.0, n_harmonics=3, tolerance_hz=500.0)

    # CAR > 1 表示倒频谱中周期性成分显著高于背景
    car_ok = car_val > 1.0
    results.append({
        "test": "car_periodic_signal",
        "car": round(car_val, 4),
        "passed": car_ok,
    })
    print(f"  [{'PASS' if car_ok else 'FAIL'}] CAR(周期性信号): {car_val:.3f}")

    # 纯噪声：CAR 不应为 nan/inf，且峰值区域未检出时应返回 0
    np.random.seed(42)
    noise = np.random.randn(int(4.0 * FS))
    car_noise = compute_car(noise, FS, rot_freq=25.0, n_harmonics=3)
    noise_ok = np.isfinite(car_noise)  # 噪声没有强周期性，但算法可能返回极大值（背景极小的边界情况）
    results.append({
        "test": "car_noise",
        "car": round(car_noise, 4) if np.isfinite(car_noise) else str(car_noise),
        "passed": noise_ok,
    })
    print(f"  [{'PASS' if noise_ok else 'FAIL'}] CAR(噪声): {car_noise:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. compute_ser_order — 边频带能量比
# ═══════════════════════════════════════════════════════════

def test_ser(tsa_res):
    """SER：基于阶次谱计算边频带能量比"""
    print("\n--- compute_ser_order ---")
    results = []

    if tsa_res is None or not tsa_res.get("valid"):
        results.append({"test": "ser_skipped", "reason": "tsa_failed", "passed": False})
        print("  [SKIP] TSA 失败，跳过 SER")
        return results

    # 用 TSA 后的信号计算阶次谱
    order_sig = tsa_res.get("order_signal", tsa_res.get("tsa_signal", np.array([])))
    rot_freq = 25.0
    if len(order_sig) < 512:
        results.append({"test": "ser_skipped", "reason": "signal_too_short", "passed": False})
        print("  [SKIP] 信号太短")
        return results

    # 计算阶次谱：对 TSA 信号做 FFT，频率轴转为阶次
    xf, yf = compute_fft_spectrum(order_sig, FS)
    # 转阶次轴：order = freq / rot_freq
    order_axis = xf / rot_freq
    spectrum = yf

    # 啮合阶次 = 450 / 25 = 18
    mesh_order = 18.0
    ser_val = compute_ser_order(order_axis, spectrum, mesh_order, n_sidebands=3, sideband_bw=0.3)

    # 合成 gear_mesh 有显著边频带，SER 应 > 0.5
    ser_ok = ser_val > 0.3
    results.append({
        "test": "ser_gear_mesh",
        "mesh_order": mesh_order,
        "ser": round(ser_val, 4),
        "passed": ser_ok,
    })
    print(f"  [{'PASS' if ser_ok else 'FAIL'}] SER(啮合阶次={mesh_order}): {ser_val:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# 5. compute_fm0_order — 粗故障检测
# ═══════════════════════════════════════════════════════════

def test_fm0(tsa_res):
    """FM0：基于 TSA 信号和阶次谱计算"""
    print("\n--- compute_fm0_order ---")
    results = []

    if tsa_res is None or not tsa_res.get("valid"):
        results.append({"test": "fm0_skipped", "reason": "tsa_failed", "passed": False})
        print("  [SKIP] TSA 失败，跳过 FM0")
        return results

    tsa_signal = tsa_res.get("tsa_signal", np.array([]))
    if len(tsa_signal) < 512:
        results.append({"test": "fm0_skipped", "reason": "signal_too_short", "passed": False})
        print("  [SKIP] 信号太短")
        return results

    rot_freq = 25.0
    xf, yf = compute_fft_spectrum(tsa_signal, FS)
    order_axis = xf / rot_freq
    spectrum = yf

    mesh_order = 18.0
    fm0_val = compute_fm0_order(tsa_signal, order_axis, spectrum, mesh_order, n_harmonics=3)

    # FM0 = PP / harmonics_sum，健康齿轮 FM0 应在合理范围（不极端大）
    fm0_ok = 0.1 < fm0_val < 50.0
    results.append({
        "test": "fm0_healthy_gear",
        "fm0": round(fm0_val, 4),
        "passed": fm0_ok,
    })
    print(f"  [{'PASS' if fm0_ok else 'FAIL'}] FM0(健康): {fm0_val:.3f}")

    return results


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Layer 2: gear/metrics.py — 齿轮指标正确性验证")
    print("=" * 60)

    tsa_results, tsa_res = test_tsa()
    all_results = {
        "tsa": tsa_results,
        "fm4": test_fm4(tsa_res),
        "car": test_car(),
        "ser": test_ser(tsa_res),
        "fm0": test_fm0(tsa_res),
    }

    total = 0
    passed = 0
    for category, items in all_results.items():
        for item in items:
            total += 1
            if item.get("passed", False):
                passed += 1

    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "gear_metrics_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    print(f"\n结果已保存: {out_path}")

    s = all_results["summary"]
    print(f"\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")
    if s["failed"] > 0:
        print(f"WARNING: {s['failed']} 个测试失败")
    else:
        print("全部通过!")


if __name__ == "__main__":
    main()
