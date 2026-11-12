"""
健康度趋势预测模块

提供 Holt-Winters 三阶指数平滑和 Kalman 滤波两种趋势预测算法，
用于预测设备健康度变化趋势和退化速率。

仅依赖 numpy，无第三方库依赖。

典型用法：
    from app.services.diagnosis.trend_prediction import holt_winters_forecast, kalman_smooth_health_scores

    # Holt-Winters 预测
    result = holt_winters_forecast(health_scores, timestamps, forecast_steps=3)

    # Kalman 滤波平滑
    result = kalman_smooth_health_scores(health_scores)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from cnn_compute import sequence as native

import numpy as np


# ═══════════════════════════════════════════════════════════════
# Holt-Winters 三阶指数平滑
# ═══════════════════════════════════════════════════════════════


def holt_winters_forecast(
    health_scores: List[float],
    timestamps: List[float],
    forecast_steps: int = 3,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.05,
    season_length: int = None,
) -> Dict[str, Any]:
    """
    Holt-Winters 三阶指数平滑预测健康度趋势。

    加法模型公式：
        level:   l(t) = α·y(t) + (1-α)·(l(t-1) + b(t-1))
        trend:   b(t) = β·(l(t) - l(t-1)) + (1-β)·b(t-1)
        season:  s(t) = γ·(y(t) - l(t)) + (1-γ)·s(t-m)
        forecast: y(t+h) = l(t) + h·b(t) + s(t+h-m)

    当 season_length=None 时退化为 Holt 双指数平滑（线性趋势预测）。

    参数:
        health_scores: 历史健康度序列（0-100）
        timestamps: 对应的时间戳序列（秒或 Unix 时间戳）
        forecast_steps: 预测步数，默认 3
        alpha: 水平平滑系数，默认 0.3
        beta: 趋势平滑系数，默认 0.1
        gamma: 季节平滑系数，默认 0.05（仅在 season_length 非 None 时生效）
        season_length: 季节周期长度，None 表示无季节性

    返回:
        {
            "forecast_values":    List[float],  预测的健康度值
            "forecast_timestamps": List[float], 预测对应的时间戳
            "level_series":       List[float],  水平分量序列
            "trend_series":       List[float],  趋势分量序列
            "season_series":      List[float],  季节分量序列（无季节性时全为0）
            "trend_direction":    str,          趋势方向 "improving"/"stable"/"degrading"
            "estimated_degradation_rate": float, 估计退化速率（健康度/时间单位）
            "confidence":         float,        预测置信度（基于残差方差）
        }
    """
    # ──── 空序列安全处理 ────
    empty_result: Dict[str, Any] = {
        "forecast_values": [],
        "forecast_timestamps": [],
        "level_series": [],
        "trend_series": [],
        "season_series": [],
        "trend_direction": "stable",
        "estimated_degradation_rate": 0.0,
        "confidence": 0.0,
    }

    if not health_scores or len(health_scores) == 0:
        return empty_result

    y = np.array(health_scores, dtype=np.float64)
    t = (
        np.array(timestamps, dtype=np.float64)
        if timestamps
        else np.arange(len(y), dtype=np.float64)
    )

    n = len(y)

    # ──── 短序列安全退化（< 5 个点）───
    if n < 5:
        # 简单线性回归作为退化预测
        if n < 2:
            # 单点：无法预测趋势，返回常数预测
            forecast_vals = [float(y[0])] * forecast_steps
            dt = float(np.mean(np.diff(t))) if n >= 2 else 1.0
            forecast_ts = [float(t[-1] + dt * (i + 1)) for i in range(forecast_steps)]
            return {
                "forecast_values": forecast_vals,
                "forecast_timestamps": forecast_ts,
                "level_series": [float(v) for v in y],
                "trend_series": [0.0] * n,
                "season_series": [0.0] * n,
                "trend_direction": "stable",
                "estimated_degradation_rate": 0.0,
                "confidence": 0.1,  # 极低置信度
            }

        # 2~4 个点：简单线性回归
        # 使用步索引而非时间戳，使斜率单位为"每步健康度变化"
        step_indices = np.arange(n, dtype=np.float64)
        slope, intercept = _simple_linear_regression(step_indices, y)
        # slope = 每步健康度变化量，intercept = 第 0 步的预测健康度
        dt = float(np.mean(np.diff(t))) if n >= 2 else 1.0
        forecast_vals = [
            float(intercept + slope * (n + i + 1)) for i in range(forecast_steps)
        ]
        forecast_ts = [float(t[-1] + dt * (i + 1)) for i in range(forecast_steps)]
        # 限制预测值在 0-100
        forecast_vals = [max(0.0, min(100.0, v)) for v in forecast_vals]

        # 转换为每时间单位退化速率（用于 deg_rate 返回值）
        deg_rate_per_time = slope / dt if dt > 0 else slope

        trend_dir = (
            "degrading" if slope < -0.5 else ("improving" if slope > 0.5 else "stable")
        )

        return {
            "forecast_values": forecast_vals,
            "forecast_timestamps": forecast_ts,
            "level_series": [float(v) for v in y],
            "trend_series": [float(slope)] * n,
            "season_series": [0.0] * n,
            "trend_direction": trend_dir,
            "estimated_degradation_rate": round(float(deg_rate_per_time), 4),
            "confidence": 0.3,  # 低置信度
        }

    dt = float(np.mean(np.diff(t)))
    init_window = min(season_length or 4, n)
    initial_slope, _ = _simple_linear_regression(t[:init_window], y[:init_window])
    level, trend, season, fitted, forecasts = native.holt(y, forecast_steps, alpha, beta, gamma,
        season_length if season_length is not None and season_length >= 2 else 0, initial_slope)
    forecast_vals = [max(0.0, min(100.0, float(v))) for v in forecasts]
    forecast_ts = [float(t[-1] + dt * h) for h in range(1, forecast_steps + 1)]

    # ──── 残差与置信度 ────
    residuals = y - fitted
    residual_var = float(np.var(residuals)) if n > 2 else 0.0
    # 置信度：残差方差越小说明模型拟合越好
    # 标准化到 0-1 范围：residual_var < 5 → 高置信度，> 50 → 低置信度
    confidence = max(0.0, min(1.0, 1.0 - residual_var / 50.0))

    # ──── 趋势方向判定 ────
    avg_trend = float(np.mean(trend[-5:]) if n >= 5 else float(trend[-1]))
    # 退化速率：趋势的平均值（健康度/时间单位）
    deg_rate = avg_trend

    if deg_rate < -1.0:
        trend_direction = "degrading"
    elif deg_rate > 1.0:
        trend_direction = "improving"
    else:
        trend_direction = "stable"

    return {
        "forecast_values": [round(v, 2) for v in forecast_vals],
        "forecast_timestamps": [round(v, 2) for v in forecast_ts],
        "level_series": [round(float(v), 4) for v in level],
        "trend_series": [round(float(v), 4) for v in trend],
        "season_series": [round(float(v), 4) for v in season],
        "trend_direction": trend_direction,
        "estimated_degradation_rate": round(deg_rate, 4),
        "confidence": round(confidence, 4),
    }


# ═══════════════════════════════════════════════════════════════
# Kalman 滤波平滑
# ═══════════════════════════════════════════════════════════════


def kalman_smooth_health_scores(
    health_scores: List[float],
    process_noise: float = 1.0,
    measurement_noise: float = 5.0,
) -> Dict[str, Any]:
    """
    Kalman 滤波平滑 health_score 序列。

    状态模型：
        状态向量 x = [health_score, degradation_rate]
        状态转移 F = [[1, dt], [0, 1]]
        观测矩阵 H = [[1, 0]]

    过程噪声 Q 和观测噪声 R 可调，默认值适合健康度 0-100 的场景。

    参数:
        health_scores: 历史健康度序列（0-100）
        process_noise: 过程噪声标准差，默认 1.0
        measurement_noise: 观测噪声标准差，默认 5.0

    返回:
        {
            "smoothed_scores":     List[float],  Kalman 滤波平滑后的健康度
            "estimated_rates":     List[float],  估计的退化速率序列
            "prediction_confidence": float,      预测置信度（基于最终协方差）
            "current_trend":       str,          当前趋势方向
        }
    """
    # ──── 空序列安全处理 ────
    empty_result: Dict[str, Any] = {
        "smoothed_scores": [],
        "estimated_rates": [],
        "prediction_confidence": 0.0,
        "current_trend": "stable",
    }

    if not health_scores or len(health_scores) == 0:
        return empty_result

    y = np.array(health_scores, dtype=np.float64)
    n = len(y)

    # ──── 短序列安全退化（< 5 个点）───
    if n < 5:
        # 简单移动平均作为平滑结果
        smoothed = list(y)
        rates = [0.0] * n

        if n >= 2:
            # 用最后几个点的差分估计退化速率
            rate = float(np.mean(np.diff(y[-3:]) if n >= 3 else np.diff(y)))
            rates[-1] = rate
            # 简单线性平滑
            if n >= 3:
                smoothed = [
                    float(0.25 * y[i - 1] + 0.5 * y[i] + 0.25 * y[i + 1])
                    if i > 0 and i < n - 1
                    else float(y[i])
                    for i in range(n)
                ]

        avg_rate = float(
            np.mean(rates[-3:]) if n >= 3 else (rates[-1] if n >= 1 else 0.0)
        )
        trend = (
            "degrading"
            if avg_rate < -1.0
            else ("improving" if avg_rate > 1.0 else "stable")
        )

        return {
            "smoothed_scores": [round(v, 2) for v in smoothed],
            "estimated_rates": [round(v, 4) for v in rates],
            "prediction_confidence": 0.3,
            "current_trend": trend,
        }

    scores, rates, final_health_var = native.kalman(y, process_noise, measurement_noise)
    smoothed_scores = [round(float(v), 2) for v in scores]
    estimated_rates = [round(float(v), 4) for v in rates]

    # ──── 最终协方差 → 预测置信度 ────
    # 用最终状态协方差的 health 分量来衡量置信度
    # P[0,0] 越小 → 置信度越高
    # 标准化到 0-1：var < 5 → 高置信度，var > 50 → 低置信度
    confidence = max(0.0, min(1.0, 1.0 - final_health_var / 50.0))

    # ──── 当前趋势 ────
    current_rate = float(rates[-1])
    if current_rate < -1.0:
        current_trend = "degrading"
    elif current_rate > 1.0:
        current_trend = "improving"
    else:
        current_trend = "stable"

    return {
        "smoothed_scores": smoothed_scores,
        "estimated_rates": estimated_rates,
        "prediction_confidence": round(confidence, 4),
        "current_trend": current_trend,
    }


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


def _simple_linear_regression(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple:
    """
    简单线性回归，返回 (slope, intercept)。

    用于短序列的退化预测和 Holt-Winters 趋势初始化。
    """
    if len(x) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0
    return native.regression(x, y)
