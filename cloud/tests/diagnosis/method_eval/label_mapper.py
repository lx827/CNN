"""
预测标签推断模块

从云端诊断引擎的输出结果中推断预测故障标签。
支持三种推断策略（按优先级）：
1. D-S 融合 dominant_fault（最可靠，多算法投票）
2. fault_label 字段（启发式快速分类）
3. fault_indicators SNR 最高项（单一方法兜底）
"""
from typing import Any, Dict, List, Optional

from .config import (
    DS_TO_BEARING, DS_TO_GEAR,
    FAULT_LABEL_TO_BEARING, FAULT_LABEL_TO_GEAR,
    INDICATOR_TO_BEARING, INDICATOR_TO_GEAR,
    HEALTH_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════
# 轴承标签推断
# ═══════════════════════════════════════════════════════════

def infer_bearing_label_from_ensemble(
    result: Dict[str, Any],
    valid_labels: List[str],
    default: str = "healthy",
) -> str:
    """从 Ensemble (run_research_ensemble) 结果推断轴承预测标签。

    优先级：
    1. D-S 融合 dominant_fault（dominant_probability > 0.3 且 uncertainty < 0.4）
    2. fault_label 字段
    3. health_score >= HEALTH_THRESHOLD → healthy

    参数:
        result: run_research_ensemble() 的完整返回值
        valid_labels: 有效的标签集合（用于兜底校验）
        default: 默认标签

    返回:
        预测标签（如 "outer", "inner", "ball", "healthy", "composite"）
    """
    # ── 1. D-S 融合 ──
    ds = result.get("ensemble", {}).get("ds_fusion", {})
    if isinstance(ds, dict):
        dominant = ds.get("dominant_fault", "")
        dominant_prob = float(ds.get("dominant_probability", 0))
        uncertainty = float(ds.get("uncertainty", 1))

        if dominant_prob > 0.3 and uncertainty < 0.4 and dominant:
            mapped = DS_TO_BEARING.get(dominant)
            if mapped and mapped in valid_labels:
                return mapped

    # ── 2. fault_label ──
    fault_label = result.get("fault_label", "")
    if fault_label:
        mapped = FAULT_LABEL_TO_BEARING.get(fault_label)
        if mapped and mapped in valid_labels:
            return mapped

    # ── 3. health_score ──
    hs = int(result.get("health_score", 100))
    if hs >= HEALTH_THRESHOLD:
        return "healthy"

    return default


def infer_bearing_label_from_single(
    bearing_result: Dict[str, Any],
    health_score: int,
    valid_labels: List[str],
    default: str = "healthy",
) -> str:
    """从单一轴承方法 (analyze_bearing) 结果推断预测标签。

    策略：
    - health_score >= HEALTH_THRESHOLD → healthy
    - 否则从 fault_indicators 中找 SNR 最高的物理参数项

    参数:
        bearing_result: analyze_bearing() 的返回值
        health_score: 综合健康度（从 analyze_comprehensive 获取）
        valid_labels: 有效标签集合
        default: 默认标签
    """
    if health_score >= HEALTH_THRESHOLD:
        return "healthy"

    indicators = bearing_result.get("fault_indicators", {}) or {}

    # 找 SNR 最高的物理参数项（排除 _stat 统计项）
    best_snr = 0
    best_fault = None
    for name, item in indicators.items():
        if not isinstance(item, dict):
            continue
        if name.endswith("_stat"):
            continue
        if not item.get("significant", False):
            continue
        snr = float(item.get("snr", 0))
        if snr > best_snr:
            best_snr = snr
            mapped = INDICATOR_TO_BEARING.get(name)
            if mapped and mapped in valid_labels:
                best_fault = mapped

    return best_fault if best_fault else default


# ═══════════════════════════════════════════════════════════
# 齿轮标签推断
# ═══════════════════════════════════════════════════════════

def infer_gear_label_from_ensemble(
    result: Dict[str, Any],
    valid_labels: List[str],
    default: str = "healthy",
) -> str:
    """从 Ensemble 结果推断齿轮预测标签。

    同轴承逻辑，但使用齿轮标签映射。
    """
    # ── 1. D-S 融合 ──
    ds = result.get("ensemble", {}).get("ds_fusion", {})
    if isinstance(ds, dict):
        dominant = ds.get("dominant_fault", "")
        dominant_prob = float(ds.get("dominant_probability", 0))
        uncertainty = float(ds.get("uncertainty", 1))

        if dominant_prob > 0.3 and uncertainty < 0.4 and dominant:
            mapped = DS_TO_GEAR.get(dominant)
            if mapped and mapped in valid_labels:
                return mapped

    # ── 2. fault_label ──
    fault_label = result.get("fault_label", "")
    if fault_label:
        mapped = FAULT_LABEL_TO_GEAR.get(fault_label)
        if mapped and mapped in valid_labels:
            return mapped

    # ── 3. 从 gear indicators 推断具体子类型 ──
    best_gear = result.get("gear", {})
    if best_gear:
        try:
            from app.services.diagnosis.health_score import _infer_gear_subtype_from_indicators
            subtype = _infer_gear_subtype_from_indicators(best_gear)
            if subtype and subtype in valid_labels:
                return subtype
        except Exception:
            pass

    # ── 4. health_score ──
    hs = int(result.get("health_score", 100))
    if hs >= HEALTH_THRESHOLD:
        return "healthy"

    # health_score < 阈值：无法推断具体类型 → 返回默认故障类型（而非 healthy）
    for fallback in ["break", "wear", "crack", "missing"]:
        if fallback in valid_labels:
            return fallback

    return default


def infer_gear_label_from_single(
    gear_result: Dict[str, Any],
    health_score: int,
    valid_labels: List[str],
    default: str = "healthy",
) -> str:
    """从单一齿轮方法 (analyze_gear) 结果推断预测标签。

    策略：
    - health_score >= HEALTH_THRESHOLD → healthy
    - 否则根据 SER/FM4/FM0 等指标值推断
    """
    if health_score >= HEALTH_THRESHOLD:
        return "healthy"

    ser = float(gear_result.get("ser", 0))
    fm4 = float(gear_result.get("fm4", 0))
    fm0 = float(gear_result.get("fm0", 0))

    # 简化规则推断
    if fm0 > 10:
        return "break" if "break" in valid_labels else default
    elif fm4 > 10:
        return "crack" if "crack" in valid_labels else default
    elif ser > 2.0:
        return "wear" if "wear" in valid_labels else default
    elif ser > 1.0:
        return "missing" if "missing" in valid_labels else default

    return default


# ═══════════════════════════════════════════════════════════
# 二分类推断（健康 vs 故障）
# ═══════════════════════════════════════════════════════════

def infer_binary_label(health_score: int, threshold: int = HEALTH_THRESHOLD) -> str:
    """二分类：健康 vs 故障"""
    return "healthy" if health_score >= threshold else "fault"
