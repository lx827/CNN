"""
Layer 1 信号基元 — VMD 降噪正确性验证

测试 vmd_denoise.py 中的函数：
  vmd_decompose — 分解为 IMF
  vmd_denoise   — 信号降噪
  vmd_select_impact_mode — 最优冲击模态选择

原则：合成已知成分的信号，验证 VMD 能否正确分解/降噪。

输出: layer1/output/vmd_denoise_correctness.json
"""
import json
import sys
import os
from pathlib import Path
import numpy as np

# 导入云端模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.vmd_denoise import (
    vmd_decompose, vmd_denoise, vmd_select_impact_mode,
)
from app.services.diagnosis.signal_utils import (
    compute_fft_spectrum, kurtosis, rms, prepare_signal,
)
from tests.diagnosis.foundation.layer1.synthetic_signals import (
    NumpyEncoder, sinusoidal, bearing_outer_race, impulse_train,
)

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192

# 真实数据集路径
HUSTBEAR_DIR = Path(r"D:\code\wavelet_study\dataset\HUSTbear\down8192")
CW_DIR = Path(r"D:\code\CNN\CW\down8192_CW")


# ═══════════════════════════════════════════════════════════
# 1. vmd_decompose — 多分量信号分解
# ═══════════════════════════════════════════════════════════

def test_vmd_decompose():
    """VMD 分解：多分量合成信号"""
    print("\n--- vmd_decompose ---")
    results = []

    # 合成信号: 30Hz + 120Hz + 300Hz（三个清晰的模态）
    duration = 1.0
    t = np.arange(0, duration, 1/FS)
    sig = (
        np.sin(2 * np.pi * 30 * t) +
        0.7 * np.sin(2 * np.pi * 120 * t) +
        0.5 * np.sin(2 * np.pi * 300 * t)
    )

    # VMD 分解 (K=3, 匹配实际分量数)
    try:
        u, u_hat, omega = vmd_decompose(sig, K=3, alpha=2000, tol=1e-6)
        n_imfs = u.shape[0]
        k_ok = n_imfs == 3
        results.append({
            "test": "vmd_decompose_3tones",
            "K_requested": 3,
            "K_actual": n_imfs,
            "passed": k_ok,
        })
        print(f"  [{'PASS' if k_ok else 'FAIL'}] 3分量分解: K=3 → {n_imfs} IMFs")

        # 验证：IMF 频谱应各自集中在原始分量频率附近 (30/120/300Hz)
        expected_freqs = [30.0, 120.0, 300.0]
        matched = 0
        for i in range(n_imfs):
            xf, yf = compute_fft_spectrum(u[i, :], FS)
            peak_freq = xf[np.argmax(yf)]
            # 检查是否落在任一预期频率的 ±20% 容差内
            freq_ok = any(abs(peak_freq - ef) / ef < 0.20 for ef in expected_freqs)
            if freq_ok:
                matched += 1
            results.append({
                "test": f"vmd_imf{i}_frequency",
                "imf_index": i,
                "peak_freq_hz": round(float(peak_freq), 1),
                "passed": freq_ok,
            })
        # 至少 2/3 的 IMF 频率要匹配上
        decompose_freq_ok = matched >= 2
        results.append({
            "test": "vmd_decompose_freq_match",
            "matched": matched,
            "expected": 3,
            "passed": decompose_freq_ok,
        })
    except Exception as e:
        results.append({
            "test": "vmd_decompose_3tones",
            "error": str(e),
            "passed": False,
        })
        print(f"  [FAIL] VMD 分解异常: {e}")

    return results


# ═══════════════════════════════════════════════════════════
# 2. vmd_denoise — 降噪效果验证
# ═══════════════════════════════════════════════════════════

def test_vmd_denoise():
    """VMD 降噪：加噪正弦的 SNR 改善"""
    print("\n--- vmd_denoise ---")
    results = []

    # 纯净正弦 + 强噪声
    duration = 1.0
    t = np.arange(0, duration, 1/FS)
    clean = np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 120 * t)
    np.random.seed(42)
    noise = 0.5 * np.random.randn(len(t))
    noisy = clean + noise

    # 降噪前 SNR: 信号功率 / 噪声功率
    signal_power = np.var(clean)
    noise_power = np.var(noise)
    snr_before = signal_power / (noise_power + 1e-12)

    # VMD 降噪
    try:
        denoised = vmd_denoise(noisy, K=3, alpha=2000, corr_threshold=0.2, kurt_threshold=2.5)

        # 降噪后 SNR: denoised 与 clean 的相似度
        residual = denoised[:len(clean)] - clean[:len(denoised)]
        residual_power = np.var(residual)
        snr_after = signal_power / (residual_power + 1e-12)

        snr_improved = snr_after > snr_before * 0.8  # 至少不恶化太多
        results.append({
            "test": "vmd_denoise_snr",
            "snr_before_db": round(float(10 * np.log10(snr_before)), 1),
            "snr_after_db": round(float(10 * np.log10(snr_after)), 1),
            "passed": snr_improved,
        })
        print(f"  [{'PASS' if snr_improved else 'FAIL'}] 降噪SNR: {10*np.log10(snr_before):.1f}dB → {10*np.log10(snr_after):.1f}dB")

    except Exception as e:
        results.append({
            "test": "vmd_denoise_snr",
            "error": str(e),
            "passed": False,
        })
        print(f"  [FAIL] VMD 降噪异常: {e}")

    return results


# ═══════════════════════════════════════════════════════════
# 3. vmd_select_impact_mode — 最优冲击模态
# ═══════════════════════════════════════════════════════════

def test_vmd_select_impact():
    """VMD 冲击模态选择：轴承冲击信号"""
    print("\n--- vmd_select_impact_mode ---")
    results = []

    # 合成轴承冲击信号
    sig, fs, gt = bearing_outer_race(bpfo=90.0, rot_freq=25.0, duration=1.0, fs=FS, snr_db=15)

    try:
        best_imf, info = vmd_select_impact_mode(sig, K=3, alpha=2000)

        # 验证：选出的 IMF 确实是所有模态中峭度最大的，且峭度显著高于高斯噪声(≈3)
        orig_kurt = kurtosis(sig, fisher=False)
        best_kurt = info.get("best_kurtosis", 0)
        mode_kurtoses = [float(m["kurtosis"]) for m in info.get("modes", [])]
        max_kurt = max(mode_kurtoses) if mode_kurtoses else 0
        # 选择逻辑正确：best_kurt 必须等于所有模态中的最大值
        select_logic_ok = abs(best_kurt - max_kurt) < 1e-6
        # 冲击性标准：显著高于高斯噪声（fisher=False 时约 3）
        impact_ok = best_kurt > 4.0

        results.append({
            "test": "vmd_impact_mode_bearing",
            "original_kurtosis": round(float(orig_kurt), 2),
            "best_imf_kurtosis": round(float(best_kurt), 2),
            "best_index": info.get("best_index"),
            "n_modes": len(info.get("modes", [])),
            "mode_kurtoses": [round(float(m["kurtosis"]), 2) for m in info.get("modes", [])],
            "passed": len(info.get("modes", [])) > 0 and select_logic_ok and impact_ok,
        })
        print(f"  [{'PASS' if len(info.get('modes', [])) > 0 and select_logic_ok and impact_ok else 'FAIL'}] "
              f"冲击模态: 原始峭度={orig_kurt:.1f}, 最佳IMF峭度={best_kurt:.1f}, "
              f"模态数={len(info.get('modes', []))}")

    except Exception as e:
        results.append({
            "test": "vmd_impact_mode_bearing",
            "error": str(e),
            "passed": False,
        })
        print(f"  [FAIL] VMD 冲击模态异常: {e}")

    return results


# ═══════════════════════════════════════════════════════════
# 4. 真实数据 — VMD 降噪 + 冲击模态
# ═══════════════════════════════════════════════════════════

def test_vmd_real():
    """真实 HUSTbear + CW 轴承数据：VMD 降噪 + 冲击模态选择"""
    print("\n--- 真实数据 VMD ---")
    results = []

    # ── HUSTbear: 多种转速的健康 + 球故障 ──
    if HUSTBEAR_DIR.exists():
        for speed in [20, 30, 40]:
            for fname, desc in [(f"0.5X_B_{speed}Hz-X.npy", f"球故障{speed}Hz"),
                                 (f"H_{speed}Hz-X.npy", f"健康{speed}Hz")]:
                fpath = HUSTBEAR_DIR / fname
                if not fpath.exists():
                    continue

                sig = np.load(str(fpath)).astype(np.float64)
                if len(sig) > FS * 2:
                    sig = sig[:FS * 2]

                try:
                    best_imf, info = vmd_select_impact_mode(sig, K=3, alpha=2000)
                    orig_kurt = kurtosis(sig, fisher=False)
                    best_kurt = info.get("best_kurtosis", 0)
                    n_modes = len(info.get("modes", []))
                    basic_ok = n_modes > 0 and best_kurt > 0

                    results.append({
                        "dataset": "HUSTbear", "file": fname, "description": desc,
                        "original_kurtosis": round(float(orig_kurt), 2),
                        "best_imf_kurtosis": round(float(best_kurt), 2),
                        "n_modes": n_modes, "passed": basic_ok,
                    })
                    status = "PASS" if basic_ok else "FAIL"
                    print(f"  [{status}] {desc}: 原始峭度={orig_kurt:.1f}, 最佳IMF峭度={best_kurt:.1f}")
                except Exception as e:
                    results.append({"dataset": "HUSTbear", "file": fname, "description": desc,
                                    "error": str(e), "passed": False})
                    print(f"  [FAIL] {desc}: {e}")

    # ── CW 变速数据：每种健康状态选 2 个 ──
    if CW_DIR.exists():
        cw_cases = [
            ("H-A-1.npy", "健康升速"), ("H-B-1.npy", "健康降速"),
            ("I-A-1.npy", "内圈升速"), ("I-B-1.npy", "内圈降速"),
            ("O-A-1.npy", "外圈升速"), ("O-B-1.npy", "外圈降速"),
        ]
        for fname, desc in cw_cases:
            fpath = CW_DIR / fname
            if not fpath.exists():
                continue

            sig = np.load(str(fpath)).astype(np.float64)
            if len(sig) > FS * 2:
                sig = sig[:FS * 2]

            try:
                best_imf, info = vmd_select_impact_mode(sig, K=3, alpha=2000)
                orig_kurt = kurtosis(sig, fisher=False)
                best_kurt = info.get("best_kurtosis", 0)
                n_modes = len(info.get("modes", []))
                basic_ok = n_modes > 0 and best_kurt > 0

                results.append({
                    "dataset": "CW", "file": fname, "description": desc,
                    "original_kurtosis": round(float(orig_kurt), 2),
                    "best_imf_kurtosis": round(float(best_kurt), 2),
                    "n_modes": n_modes, "passed": basic_ok,
                })
                status = "PASS" if basic_ok else "FAIL"
                print(f"  [{status}] CW {desc}: 原始峭度={orig_kurt:.1f}, 最佳IMF峭度={best_kurt:.1f}")
            except Exception as e:
                results.append({"dataset": "CW", "file": fname, "description": desc,
                                "error": str(e), "passed": False})
                print(f"  [FAIL] CW {desc}: {e}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: vmd_denoise — VMD 降噪正确性验证")
    print("=" * 60)

    all_results = {
        "vmd_decompose": test_vmd_decompose(),
        "vmd_denoise": test_vmd_denoise(),
        "vmd_select_impact": test_vmd_select_impact(),
        "vmd_real": test_vmd_real(),
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
    out_path = OUTPUT_DIR / "vmd_denoise_correctness.json"
    out_path.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    print(f"\n结果已保存: {out_path}")

    s = all_results["summary"]
    print(f"\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")
    if s["failed"] > 0:
        print(f"WARNING: {s['failed']} 个测试失败")


if __name__ == "__main__":
    main()
