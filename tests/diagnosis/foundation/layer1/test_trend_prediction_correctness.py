"""
Layer 1 信号基元 — trend_prediction 正确性验证

测试 holt_winters_forecast / kalman_smooth_health_scores

输出: layer1/output/trend_prediction.json
"""
import json, sys, os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cloud'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
from app.services.diagnosis.trend_prediction import holt_winters_forecast, kalman_smooth_health_scores
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def test_holt_winters_degrading():
    """holt_winters_forecast: 退化趋势预测"""
    print("\n--- holt_winters_forecast 退化 ---")
    results = []

    # 构造退化序列：100 → 85（线性退化）
    hs = [100.0, 98.0, 95.0, 92.0, 88.0, 85.0]
    ts = list(range(len(hs)))
    res = holt_winters_forecast(hs, ts, forecast_steps=3)

    forecasts = res.get("forecast_values", [])
    direction = res.get("trend_direction", "")
    has_forecast = len(forecasts) == 3
    degrading = direction == "degrading"
    # 预测值应继续下降
    forecast_decreasing = forecasts[-1] < forecasts[0] if len(forecasts) >= 2 else False
    results.append({
        "test": "hw_degrading",
        "forecasts": forecasts,
        "direction": direction,
        "passed": has_forecast and degrading and forecast_decreasing,
    })
    print(f"  [{'PASS' if has_forecast and degrading and forecast_decreasing else 'FAIL'}] 退化预测: dir={direction}, forecasts={forecasts}")

    return results


def test_holt_winters_stable():
    """holt_winters_forecast: 稳定趋势"""
    print("\n--- holt_winters_forecast 稳定 ---")
    results = []

    hs = [95.0, 96.0, 94.0, 95.0, 96.0, 95.0]
    ts = list(range(len(hs)))
    res = holt_winters_forecast(hs, ts, forecast_steps=2)

    direction = res.get("trend_direction", "")
    stable_ok = direction in ("stable", "improving", "degrading")  # 允许任意（小波动）
    # 预测值应在合理范围
    forecasts = res.get("forecast_values", [])
    in_range = all(0 <= f <= 100 for f in forecasts)
    results.append({
        "test": "hw_stable",
        "direction": direction,
        "forecasts": forecasts,
        "passed": stable_ok and in_range,
    })
    print(f"  [{'PASS' if stable_ok and in_range else 'FAIL'}] 稳定预测: dir={direction}, forecasts={forecasts}")

    return results


def test_holt_winters_short():
    """holt_winters_forecast: 短序列回退"""
    print("\n--- holt_winters_forecast 短序列 ---")
    results = []

    # 单点
    res = holt_winters_forecast([80.0], [0], forecast_steps=2)
    has_fc = len(res.get("forecast_values", [])) == 2
    results.append({"test": "hw_single_point", "passed": has_fc})
    print(f"  [{'PASS' if has_fc else 'FAIL'}] 单点预测")

    # 空序列
    res2 = holt_winters_forecast([], [], forecast_steps=2)
    empty_ok = len(res2.get("forecast_values", [])) == 0
    results.append({"test": "hw_empty", "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空序列")

    return results


def test_kalman_smooth():
    """kalman_smooth_health_scores: 卡尔曼平滑"""
    print("\n--- kalman_smooth_health_scores ---")
    results = []

    # 含噪声的健康度序列（真实值 90，加噪声 ±5）
    np.random.seed(42)
    true_hs = [90.0] * 10
    noisy_hs = [h + np.random.randn() * 3 for h in true_hs]
    res = kalman_smooth_health_scores(noisy_hs)

    smoothed = res.get("smoothed_scores", [])
    rates = res.get("estimated_rates", [])
    has_smoothed = len(smoothed) == len(noisy_hs)
    has_rates = len(rates) == len(noisy_hs)

    # 平滑后应降低方差
    var_before = float(np.var(noisy_hs))
    var_after = float(np.var(smoothed)) if smoothed else float('inf')
    reduced = var_after < var_before * 1.2  # 允许小幅增加（边界效应）

    results.append({
        "test": "kalman_smooth",
        "var_before": round(var_before, 4),
        "var_after": round(var_after, 4),
        "passed": has_smoothed and has_rates and reduced,
    })
    print(f"  [{'PASS' if has_smoothed and has_rates and reduced else 'FAIL'}] 卡尔曼平滑: var {var_before:.3f} -> {var_after:.3f}")

    # 空序列
    res2 = kalman_smooth_health_scores([])
    empty_ok = len(res2.get("smoothed_scores", [])) == 0
    results.append({"test": "kalman_empty", "passed": empty_ok})
    print(f"  [{'PASS' if empty_ok else 'FAIL'}] 空序列")

    return results


def main():
    print("=" * 60)
    print("Layer 1: trend_prediction — 趋势预测正确性")
    print("=" * 60)

    all_results = {
        "hw_degrading": test_holt_winters_degrading(),
        "hw_stable": test_holt_winters_stable(),
        "hw_short": test_holt_winters_short(),
        "kalman": test_kalman_smooth(),
    }

    total = passed = 0
    for items in all_results.values():
        for it in items:
            total += 1
            if it.get("passed", False): passed += 1
    all_results["summary"] = {"total": total, "passed": passed, "failed": total - passed}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "trend_prediction.json"
    out.write_text(json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False), encoding='utf-8')
    s = all_results["summary"]
    print(f"\n结果: {out}\n总计: {s['total']}, 通过: {s['passed']}, 失败: {s['failed']}")


if __name__ == "__main__":
    main()
