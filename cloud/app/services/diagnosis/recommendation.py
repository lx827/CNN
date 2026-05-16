"""
诊断建议生成模块

改进：
1. 精确建议映射表 — 根据 deductions 组合匹配最精确的建议
2. D-S 融合高冲突提示 — conflict > 0.8 时提示人工复核
3. SC/SCoh 循环平稳证据建议
"""
from typing import Dict, Any, Optional

# ═══════ 精确建议映射表 ═══════
# 键: (deduction_name1, deduction_name2, ...) 排序后的元组
# 值: 精确建议字符串
SUGGESTION_MAP = {
    # 轴承复合故障：冲击 + 多频率匹配
    ("kurtosis_high", "bearing_multi_freq"):
        "检测到强冲击信号及多频率匹配异常，疑似轴承复合故障，建议安排精密诊断并准备备件。",
    # 轴承内圈故障：冲击 + BPFI 频率匹配
    ("bearing_multi_freq", "kurtosis_mild"):
        "检测到轴承多频率异常及轻度冲击特征，建议检查润滑状态并安排精密诊断。",
    # 齿轮断齿：边频带 + TSA 残差严重超标
    ("gear_ser_critical", "gear_tsa_residual_kurtosis_critical"):
        "齿轮边频带及TSA残差均严重超标，疑似断齿故障，建议立即停机检查。",
    # 齿轮磨损：边频带 + CAR 异常
    ("gear_ser_warning", "gear_car_warning"):
        "齿轮边频带和倒频谱指标均异常，疑似齿面磨损，建议关注啮合状态及载荷波动。",
    # 轴承 SC/SCoh 循环平稳证据
    ("bearing_sc_scoh_evidence",):
        "谱相干分析检测到周期性冲击证据（即使时域峭度不高），疑似早期微弱轴承故障，建议持续监测并安排精密诊断。",
    # D-S 融合高冲突
    ("ds_conflict_penalty",):
        "多种诊断方法结果不一致（D-S冲突系数>0.8），建议人工复核确认真实故障类型。",
    # 轴承统计异常 + 冲击
    ("bearing_statistical_abnormal", "kurtosis_mild"):
        "检测到轴承统计指标异常及冲击特征，建议配置轴承参数后重新诊断以精确定位故障。",
}


def _match_suggestion(deductions: list) -> Optional[str]:
    """从 deductions 列表匹配最精确的建议"""
    if not deductions:
        return None
    # 提取扣分名称
    names = sorted(d[0] for d in deductions)
    # 从长到短尝试匹配（优先最精确的组合）
    for length in range(min(len(names), 3), 0, -1):
        for i in range(len(names) - length + 1):
            key = tuple(names[i:i + length])
            if key in SUGGESTION_MAP:
                return SUGGESTION_MAP[key]
    return None


def _generate_recommendation(
    bearing_result: Dict,
    gear_result: Dict,
    status: str,
    ds_conflict_high: bool = False,
    deductions: Optional[list] = None,
) -> str:
    """
    生成诊断建议 — 精确映射版本

    优先级：
    1. 精确建议映射表（基于 deductions 组合）
    2. D-S 高冲突提示
    3. 传统条件分支建议
    4. 通用兜底
    """
    if status == "normal":
        return "设备运行正常，建议按周期继续监测。"

    # 1. 精确建议映射（最高优先级）
    if deductions:
        precise = _match_suggestion(deductions)
        if precise:
            # D-S 高冲突追加提示
            if ds_conflict_high:
                precise += " 注意：多种方法诊断结果不一致，建议人工复核。"
            return precise

    parts = []

    # 2. D-S 高冲突提示
    if ds_conflict_high:
        parts.append("多种诊断方法结果不一致（D-S冲突系数>0.8），建议人工复核确认真实故障类型。")

    # 3. 传统条件分支建议
    # 轴承建议
    bearing_ind = bearing_result.get("fault_indicators", {})
    bearing_faults = [k for k, v in bearing_ind.items() if isinstance(v, dict) and v.get("significant")]
    if bearing_faults:
        parts.append(f"检测到轴承故障特征（{'/'.join(bearing_faults)}），建议检查润滑状态并安排精密诊断。")

    # SC/SCoh 方法结果
    bearing_method = bearing_result.get("method", "")
    if bearing_method != "sc_scoh":
        scoh_max = 0.0
        try:
            for k, v in bearing_ind.items():
                if isinstance(v, dict) and "scoh_peak" in v:
                    scoh_max = max(scoh_max, float(v.get("scoh_peak", 0)))
        except (TypeError, ValueError):
            pass
        # SCoh 结果来自非 SC_SCOH 方法的 fault_indicators 中不包含 scoh_peak

    # 齿轮建议（有参数模式）
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

    # 无参数齿轮统计建议
    if gear_ind.get("order_kurtosis", {}).get("warning") or gear_ind.get("order_peak_concentration", {}).get("warning"):
        parts.append("检测到转速相关周期成分异常，建议配置齿轮参数后重新诊断以定位具体故障类型。")

    # 无参数轴承统计建议
    has_bearing_params = bool(bearing_result.get("features", {}).get("BPFO_env_ratio") is not None)
    if not has_bearing_params and status != "normal":
        if bearing_ind.get("envelope_peak_snr", {}).get("warning") or bearing_ind.get("envelope_kurtosis", {}).get("warning"):
            parts.append("检测到轴承相关频带存在异常冲击特征，建议配置轴承参数后重新诊断以定位具体故障类型。")

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
            if isinstance(info, dict) and info.get("significant"):
                bearing_faults.setdefault(fname, 0)
                bearing_faults[fname] += 1

    if bearing_faults:
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
        "mckd": "MCKD最大相关峭度解卷积+包络",
        "teager": "Teager能量算子+包络",
        "spectral_kurtosis": "自适应谱峭度包络",
        "sc_scoh": "谱相关/谱相干分析",
    }
    for method_key, result in bearing_results.items():
        if "error" in result:
            continue
        indicators = result.get("fault_indicators", {})
        detected = []
        for fname, info in indicators.items():
            if isinstance(info, dict) and info.get("significant"):
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