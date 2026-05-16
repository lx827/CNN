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
    t = np.array(timestamps, dtype=np.float64) if timestamps else np.arange(len(y), dtype=np.float64)

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
        forecast_vals = [float(intercept + slope * (n + i + 1)) for i in range(forecast_steps)]
        forecast_ts = [float(t[-1] + dt * (i + 1)) for i in range(forecast_steps)]
        # 限制预测值在 0-100
        forecast_vals = [max(0.0, min(100.0, v)) for v in forecast_vals]

        # 转换为每时间单位退化速率（用于 deg_rate 返回值）
        deg_rate_per_time = slope / dt if dt > 0 else slope

        trend_dir = "degrading" if slope < -0.5 else ("improving" if slope > 0.5 else "stable")

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

    # ──── 标准 Holt-Winters 计算 ────
    has_season = season_length is not None and season_length >= 2

    # 时间步长（假设近似均匀采样）
    dt = float(np.mean(np.diff(t)))

    # 初始化
    level = np.zeros(n, dtype=np.float64)
    trend = np.zeros(n, dtype=np.float64)
    season = np.zeros(n, dtype=np.float64)

    # 水平初始值：前几个点的均值
    init_window = min(season_length or 4, n)
    level[0] = float(np.mean(y[:init_window]))

    # 趋势初始值：前几个点的线性回归斜率
    if n >= 2:
        slope_init, _ = _simple_linear_regression(t[:init_window], y[:init_window])
        trend[0] = slope_init
    else:
        trend[0] = 0.0

    # 季节初始值（仅在季节性模式时）
    if has_season:
        m = season_length
        # 至少需要 2 个完整季节周期来初始化
        if n >= 2 * m:
            # 用前两个周期的平均值差来估计季节分量
            season_init = np.zeros(m, dtype=np.float64)
            avg1 = float(np.mean(y[:m]))
            avg2 = float(np.mean(y[m:2 * m]))
            overall_avg = float(np.mean(y[:2 * m]))
            for j in range(m):
                season_init[j] = (y[j] - avg1 + y[m + j] - avg2) / 2.0
            # 归一化季节分量使得总和为 0
            season_init -= np.mean(season_init)
            season[:m] = season_init
        else:
            # 不够两个完整周期，季节分量初始为 0
            season[:m] = 0.0

    # ──── 递推计算 ────
    fitted = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if has_season:
            m = season_length
            # Holt-Winters 加法模型
            season_offset = season[i - m] if i >= m else season[i % m]
            level[i] = alpha * (y[i] - season_offset) + (1 - alpha) * (level[i - 1] + trend[i - 1])
            trend[i] = beta * (level[i] - level[i - 1]) + (1 - beta) * trend[i - 1]
            season_idx = i - m if i >= m else i
            season[i] = gamma * (y[i] - level[i]) + (1 - gamma) * season[season_idx]
            fitted[i] = level[i - 1] + trend[i - 1] + season_offset
        else:
            # Holt 双指数平滑（无季节性）
            level[i] = alpha * y[i] + (1 - alpha) * (level[i - 1] + trend[i - 1])
            trend[i] = beta * (level[i] - level[i - 1]) + (1 - beta) * trend[i - 1]
            fitted[i] = level[i - 1] + trend[i - 1]

    # 第 0 步拟合值
    fitted[0] = level[0] + trend[0] + (season[0] if has_season else 0.0)

    # ──── 预测 ────
    forecast_vals = []
    forecast_ts = []
    last_level = float(level[-1])
    last_trend = float(trend[-1])

    for h in range(1, forecast_steps + 1):
        if has_season:
            m = season_length
            # 季节分量取最近一个周期对应位置的值
            season_idx = (n - m + h) % m if n >= m else h % m
            s_val = float(season[n - m + season_idx]) if n >= m else 0.0
            f_val = last_level + h * last_trend + s_val
        else:
            f_val = last_level + h * last_trend
        # 限制预测值在 0-100
        f_val = max(0.0, min(100.0, f_val))
        forecast_vals.append(f_val)
        forecast_ts.append(float(t[-1] + dt * h))

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

        avg_rate = float(np.mean(rates[-3:]) if n >= 3 else (rates[-1] if n >= 1 else 0.0))
        trend = "degrading" if avg_rate < -1.0 else ("improving" if avg_rate > 1.0 else "stable")

        return {
            "smoothed_scores": [round(v, 2) for v in smoothed],
            "estimated_rates": [round(v, 4) for v in rates],
            "prediction_confidence": 0.3,
            "current_trend": trend,
        }

    # ──── 标准 Kalman 滤波 ────
    # 时间步长（假设均匀采样，dt=1 为单位时间步）
    dt = 1.0

    # 状态转移矩阵 F
    F = np.array([
        [1.0, dt],
        [0.0, 1.0],
    ], dtype=np.float64)

    # 观测矩阵 H
    H = np.array([[1.0, 0.0]], dtype=np.float64)

    # 过程噪声协方差 Q
    # Q 的结构：health_score 过程噪声小，退化速率过程噪声稍大
    q_health = process_noise ** 2
    q_rate = process_noise ** 2 * 2.0  # 速率估计不确定性更大
    Q = np.array([
        [q_health, 0.0],
        [0.0, q_rate],
    ], dtype=np.float64)

    # 观测噪声协方差 R
    R = np.array([[measurement_noise ** 2]], dtype=np.float64)

    # 初始化状态
    x = np.array([float(y[0]), 0.0], dtype=np.float64)  # [health, rate]
    P = np.array([
        [measurement_noise ** 2, 0.0],
        [0.0, 10.0],  # 速率初始不确定性较大
    ], dtype=np.float64)

    smoothed_scores = []
    estimated_rates = []

    for i in range(n):
        # ──── 预测步骤 ────
        if i > 0:
            x_pred = F @ x
            P_pred = F @ P @ F.T + Q
        else:
            x_pred = x.copy()
            P_pred = P.copy()

        # ──── 更新步骤 ────
        # 观测值
        z = np.array([float(y[i])], dtype=np.float64)

        # Kalman 增益
        S = H @ P_pred @ H.T + R  # 创新协方差
        K = P_pred @ H.T @ np.linalg.inv(S)  # Kalman 增益

        # 状态更新
        innovation = z - H @ x_pred  # 创新（观测 - 预测）
        x = x_pred + K @ innovation

        # 协方差更新
        I_KH = np.eye(2) - K @ H
        P = I_KH @ P_pred @ I_KH.T + K @ R @ K.T  # Joseph 形式（数值稳定）

        # 记录平滑结果
        smoothed_scores.append(round(float(x[0]), 2))
        estimated_rates.append(round(float(x[1]), 4))

    # ──── 最终协方差 → 预测置信度 ────
    # 用最终状态协方差的 health 分量来衡量置信度
    # P[0,0] 越小 → 置信度越高
    final_health_var = float(P[0, 0])
    # 标准化到 0-1：var < 5 → 高置信度，var > 50 → 低置信度
    confidence = max(0.0, min(1.0, 1.0 - final_health_var / 50.0))

    # ──── 当前趋势 ────
    current_rate = float(x[1])
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
    n = len(x)
    if n < 2:
        return 0.0, float(y[0]) if n == 1 else 0.0

    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))

    # 协方差与方差
    x_var = float(np.sum((x - x_mean) ** 2))
    xy_cov = float(np.sum((x - x_mean) * (y - y_mean)))

    if x_var == 0:
        return 0.0, y_mean

    slope = xy_cov / x_var
    intercept = y_mean - slope * x_mean

    return slope, intercept