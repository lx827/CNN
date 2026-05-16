"""
多通道一致性投票模块

核心功能：
- cross_channel_consensus — 统计各通道检出的故障类型一致性
- 若 2/3 通道同时检测到同类故障，提升该故障的置信度 10~15%
- 若仅单通道异常，降低设备级健康度扣分，并在建议中提示"单通道异常，可能是传感器问题"

本模块不混装其他功能，仅负责跨通道一致性分析。
"""
from typing import Dict, List, Any, Optional, Tuple


def cross_channel_consensus(
    channel_results: List[Dict[str, Any]],
    min_channels_for_consensus: int = 2,
) -> Dict[str, Any]:
    """
    跨通道一致性投票

    统计各通道检出的故障类型，通过多数投票确定设备级故障标签。
    一致性高的故障类型获得置信度提升，不一致的故障类型降低权重。

    Args:
        channel_results: 各通道的诊断结果列表
        min_channels_for_consensus: 形成一致性所需的最少通道数

    Returns:
        {
            "consensus_faults": Dict[str, Dict],  # 各故障类型的一致性信息
            "single_channel_faults": List[str],   # 仅单通道检出的故障
            "consensus_fault_label": str,         # 一致性最高的故障标签
            "consensus_boost": float,             # 置信度提升系数
            "single_channel_penalty": float,      # 单通道扣分降低系数
            "recommendation_hint": str,           # 建议提示
        }
    """
    if not channel_results:
        return {
            "consensus_faults": {},
            "single_channel_faults": [],
            "consensus_fault_label": "unknown",
            "consensus_boost": 1.0,
            "single_channel_penalty": 1.0,
            "recommendation_hint": "",
        }

    n_channels = len(channel_results)

    # 收集各通道检出的故障类型
    fault_votes: Dict[str, List[int]] = {}  # fault_type → [channel_indices]

    for ch_idx, result in enumerate(channel_results):
        # 轴承故障
        bearing_ind = result.get("bearing", {}).get("fault_indicators", {})
        for name, info in bearing_ind.items():
            if isinstance(info, dict) and info.get("significant"):
                # BPFO → 轴承外圈故障, BPFI → 轴承内圈故障, BSF → 滚动体故障
                fault_key = "轴承异常"
                if "BPFO" in name:
                    fault_key = "轴承外圈故障"
                elif "BPFI" in name:
                    fault_key = "轴承内圈故障"
                elif "BSF" in name:
                    fault_key = "滚动体故障"
                fault_votes.setdefault(fault_key, []).append(ch_idx)

        # 齿轮故障
        gear_ind = result.get("gear", {}).get("fault_indicators", {})
        for name, info in gear_ind.items():
            if isinstance(info, dict) and (info.get("critical") or info.get("warning")):
                fault_votes.setdefault("齿轮磨损", []).append(ch_idx)

        # 峭度异常（齿轮设备）
        ensemble = result.get("ensemble", {})
        if ensemble.get("has_gear_params"):
            tf = result.get("time_features", {})
            kurt = tf.get("kurtosis", 3.0)
            if kurt > 12.0:
                fault_votes.setdefault("齿轮磨损", []).append(ch_idx)

    # 分析一致性
    consensus_faults = {}
    single_channel_faults = []
    best_fault = "unknown"
    best_count = 0

    for fault_type, channels in fault_votes.items():
        count = len(channels)
        ratio = count / n_channels
        is_consensus = count >= min_channels_for_consensus

        consensus_faults[fault_type] = {
            "channels": channels,
            "count": count,
            "ratio": round(ratio, 2),
            "is_consensus": is_consensus,
        }

        if is_consensus:
            if count > best_count:
                best_count = count
                best_fault = fault_type
        else:
            single_channel_faults.append(fault_type)

    # 置信度提升系数：一致故障 boost 10~15%
    consensus_boost = 1.0
    if best_count >= min_channels_for_consensus:
        consensus_boost = 1.0 + 0.1 * min(best_count / n_channels, 0.5)

    # 单通道扣分降低系数：单通道检出时降低扣分权重
    single_channel_penalty = 1.0
    if single_channel_faults and not consensus_faults:
        single_channel_penalty = 0.5  # 无一致性故障时扣分减半

    # 建议提示
    recommendation_hint = ""
    if single_channel_faults and n_channels >= 2:
        ch_names = [f"通道{i+1}" for i in fault_votes.get(single_channel_faults[0], [])]
        recommendation_hint = f"仅{','.join(ch_names)}检出异常，可能是传感器问题或局部噪声，建议确认传感器状态。"

    return {
        "consensus_faults": consensus_faults,
        "single_channel_faults": single_channel_faults,
        "consensus_fault_label": best_fault,
        "consensus_boost": round(consensus_boost, 2),
        "single_channel_penalty": round(single_channel_penalty, 2),
        "recommendation_hint": recommendation_hint,
    }