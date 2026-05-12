"""
诊断建议生成模块
"""
from typing import Dict, Any


def _generate_recommendation(
    bearing_result: Dict,
    gear_result: Dict,
    status: str,
) -> str:
    """生成诊断建议"""
    if status == "normal":
        return "设备运行正常，建议按周期继续监测。"

    parts = []

    # 轴承建议
    bearing_ind = bearing_result.get("fault_indicators", {})
    bearing_faults = [k for k, v in bearing_ind.items() if v.get("significant")]
    if bearing_faults:
        parts.append(f"检测到轴承故障特征（{'/'.join(bearing_faults)}），建议检查润滑状态并安排精密诊断。")

    # 齿轮建议
    gear_ind = gear_result.get("fault_indicators", {})
    if gear_ind.get("ser", {}).get("critical"):
        parts.append("齿轮边频带能量严重超标，建议立即停机检查啮合状态。")
    elif gear_ind.get("ser", {}).get("warning"):
        parts.append("齿轮边频带能量异常，建议关注啮合状态及载荷波动。")

    if gear_ind.get("sideband_count", {}).get("critical"):
        parts.append("齿轮边频数量达到危险水平，建议立即检查。")
    elif gear_ind.get("sideband_count", {}).get("warning"):
        parts.append("齿轮边频数量异常，建议关注。")

    if gear_ind.get("fm0", {}).get("critical"):
        parts.append("齿轮粗故障指标(FM0)达到危险阈值，建议立即检查齿面状态。")
    elif gear_ind.get("fm0", {}).get("warning"):
        parts.append("齿轮粗故障指标(FM0)异常，建议关注齿面磨损。")

    if gear_ind.get("car", {}).get("critical"):
        parts.append("齿轮倒频谱幅值比(CAR)严重超标，建议立即检查。")
    elif gear_ind.get("car", {}).get("warning"):
        parts.append("齿轮倒频谱幅值比(CAR)异常，建议关注。")

    if not parts:
        parts.append("检测到异常信号特征，建议结合工况进一步分析。")

    return " ".join(parts)


def _generate_recommendation_all(bearing_results: Dict, gear_results: Dict, status: str) -> str:
    """基于所有方法结果生成建议"""
    if status == "normal":
        return "设备运行正常，所有诊断方法均未检出显著故障特征，建议按周期继续监测。"

    parts = []

    # 统计各轴承方法检出的故障
    bearing_faults = {}
    for result in bearing_results.values():
        indicators = result.get("fault_indicators", {})
        for fname, info in indicators.items():
            if info.get("significant"):
                bearing_faults.setdefault(fname, 0)
                bearing_faults[fname] += 1

    if bearing_faults:
        # 按被多少种方法检出来排序
        sorted_faults = sorted(bearing_faults.items(), key=lambda x: x[1], reverse=True)
        fault_desc = ", ".join([f"{name}({count}种方法)" for name, count in sorted_faults])
        parts.append(f"轴承诊断：{fault_desc}检出显著特征。")

    # 齿轮指标
    gear_warnings = []
    gear_criticals = []
    for result in gear_results.values():
        indicators = result.get("fault_indicators", {})
        for fname, info in indicators.items():
            if isinstance(info, dict):
                if info.get("critical"):
                    gear_criticals.append(fname)
                elif info.get("warning"):
                    gear_warnings.append(fname)

    if gear_criticals:
        parts.append(f"齿轮诊断：{'/'.join(set(gear_criticals))}指标达到危险阈值，建议立即检查。")
    elif gear_warnings:
        parts.append(f"齿轮诊断：{'/'.join(set(gear_warnings))}指标达到预警阈值，建议关注啮合状态。")

    if not parts:
        parts.append("检测到部分异常信号特征，建议结合工况进一步分析。")

    return " ".join(parts)


def _summarize_all_methods(bearing_results: Dict, gear_results: Dict) -> Dict[str, Any]:
    """汇总所有方法的检出结论"""
    summary = {
        "bearing_detections": [],
        "gear_detections": [],
    }

    # 轴承各方法检出情况
    method_name_map = {
        "envelope": "标准包络分析",
        "kurtogram": "Fast Kurtogram",
        "cpw": "CPW预白化+包络",
        "med": "MED最小熵解卷积+包络",
    }
    for method_key, result in bearing_results.items():
        if "error" in result:
            continue
        indicators = result.get("fault_indicators", {})
        detected = []
        for fname, info in indicators.items():
            if info.get("significant"):
                detected.append({
                    "fault_type": fname,
                    "theory_hz": info.get("theory_hz"),
                    "detected_hz": info.get("detected_hz"),
                    "snr": info.get("snr"),
                })
        if detected:
            summary["bearing_detections"].append({
                "method": method_name_map.get(method_key, method_key),
                "method_key": method_key,
                "detected_faults": detected,
                "features": result.get("features", {}),
            })
        else:
            summary["bearing_detections"].append({
                "method": method_name_map.get(method_key, method_key),
                "method_key": method_key,
                "detected_faults": [],
                "features": result.get("features", {}),
            })

    # 齿轮各方法检出情况
    gear_method_name_map = {
        "standard": "标准边频带分析",
        "advanced": "高级时域指标",
    }
    for method_key, result in gear_results.items():
        if "error" in result:
            continue
        indicators = result.get("fault_indicators", {})
        detected = []
        for fname, info in indicators.items():
            if isinstance(info, dict) and info.get("critical"):
                detected.append({
                    "indicator": fname,
                    "value": info.get("value"),
                    "level": "critical",
                })
            elif isinstance(info, dict) and info.get("warning"):
                detected.append({
                    "indicator": fname,
                    "value": info.get("value"),
                    "level": "warning",
                })
        # 边频带显著数量
        sidebands = result.get("sidebands", [])
        sig_sb = [sb for sb in sidebands if sb.get("significant")]
        summary["gear_detections"].append({
            "method": gear_method_name_map.get(method_key, method_key),
            "method_key": method_key,
            "detected_indicators": detected,
            "ser": result.get("ser"),
            "sideband_count": len(sig_sb),
            "sidebands": sidebands,
            "fm0": result.get("fm0"),
            "fm4": result.get("fm4"),
            "car": result.get("car"),
            "m6a": result.get("m6a"),
            "m8a": result.get("m8a"),
        })

    return summary
