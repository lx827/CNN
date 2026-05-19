"""
Layer 1 信号基元 — savgol_denoise 正确性验证

测试 sg_denoise / sg_trend_residual

输出: layer1/output/savgol_denoise.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.savgol_denoise import sg_denoise, sg_trend_residual
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"
FS = 8192


def test_sg_denoise_smooth():
    """sg_denoise: 对含噪正弦信号的平滑效果"""
    print("\n--- sg_denoise 平滑 ---")
    results = []

    t = np.arange(0, 1.0, 1.0 / FS)
    clean = np.sin(2 * np.pi * 50 * t)
    noise = np.random.randn(len(t)) * 0.3
    sig = clean + noise

    smoothed, info = sg_denoise(sig, window_length=51, polyorder=3)
    # 平滑后应更接近 clean
    mse_before = np.mean((sig - clean) ** 2)
    mse_after = np.mean((smoothed - clean) ** 2)
    improved = mse_after < mse_before * 0.8
    results.append({
        "test": "sg_smooth_noise",
        "mse_before": round(float(mse_before), 6),
        "mse_after": round(float(mse_after), 6),
        "snr_imp": info.get("snr_improvement", 0),
        "passed": improved,
    })
    print(f"  [{'PASS' if improved else 'FAIL'}] 平滑降噪: MSE {mse_before:.4f} -> {mse_after:.4f}, SNR_imp={info.get('snr_improvement', 0):.2f}")

    # 元信息完整性
    meta_ok = info.get("method") == "savgol" and info.get("window_length", 0) > 0
    results.append({"test": "sg_meta", "method": info.get("method"), "passed": meta_ok})
    print(f"  [{'PASS' if meta_ok else 'FAIL'}] 元信息: method={info.get('method')}")

    return results


def test_sg_denoise_short_signal():
    """sg_denoise: 短信号安全处理"""
    print("\n--- sg_denoise 边界 ---")
    results = []

    sig = np.array([1.0, 2.0, 3.0])
    out, info = sg_denoise(sig, window_length=51)
    # 极短信号应原样返回或安全处理
    safe_ok = len(out) == len(sig)
    results.append({"test": "sg_short_signal", "len_out": len(out), "passed": safe_ok})
    print(f"  [{'PASS' if safe_ok else 'FAIL'}] 短信号: len={len(out)}")

    return results


def test_sg_trend_residual():
    """sg_trend_residual: 趋势提取 + 残余"""
    print("\n--- sg_trend_residual ---")
    results = []

    t = np.arange(0, 2.0, 1.0 / FS)
    trend_true = 0.5 * t ** 2  # 二次趋势
    oscillation = 0.1 * np.sin(2 * np.pi * 100 * t)
    sig = trend_true + oscillation

    trend, residual, info = sg_trend_residual(sig, window_length=501, polyorder=2)
    # 趋势应近似 trend_true
    trend_corr = np.corrcoef(trend, trend_true)[0, 1] if len(trend) == len(trend_true) else 0
    trend_ok = trend_corr > 0.8
    results.append({
        "test": "sg_trend_residual",
        "trend_corr": round(float(trend_corr), 4),
        "passed": trend_ok,
    })
    print(f"  [{'PASS' if trend_ok else 'FAIL'}] 趋势提取: corr={trend_corr:.3f}")

    # 残余应主要含高频
    residual_std = float(np.std(residual))
    has_residual = residual_std > 0.01
    results.append({"test": "sg_residual_exists", "std": round(residual_std, 4), "passed": has_residual})
    print(f"  [{'PASS' if has_residual else 'FAIL'}] 残余存在: std={residual_std:.4f}")

    return results


def main():
    print("=" * 60)
    print("Layer 1: savgol_denoise — S-G 平滑正确性")
    print("=" * 60)

    all_results = {
        "denoise": test_sg_denoise_smooth(),
        "boundary": test_sg_denoise_short_signal(),
        "trend_residual": test_sg_trend_residual(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "savgol_denoise.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
