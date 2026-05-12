"""
设备级综合告警
基于设备健康度生成告警
"""
from app.models import Alarm
from . import _has_recent_unresolved_alarm


def _check_device_alarms(
    db, device, health_score: int, fault_probabilities: dict,
    batch_index: int = None, order_analysis: dict = None
) -> list:
    """
    基于诊断结果生成设备级综合健康度告警。
    去重：同一设备同类未处理告警 1 小时内不重复生成。
    """
    new_alarms = []

    # 提取 Top-2 故障类型用于描述
    top_faults = sorted(
        [(k, v) for k, v in fault_probabilities.items() if k != "正常运行"],
        key=lambda x: x[1],
        reverse=True
    )[:2]
    fault_desc = ""
    if top_faults:
        fault_desc = "\n主要故障概率：\n" + "\n".join(
            [f"• {name}：{prob:.1%}" for name, prob in top_faults]
        )

    # 构建阶次分析描述
    order_desc = ""
    if order_analysis:
        rot_info = f"估计转速: {order_analysis.get('rot_rpm', 'N/A')} RPM ({order_analysis.get('rot_freq_hz', 'N/A')} Hz)。"
        spec = order_analysis.get("spectrum_features", {})
        env = order_analysis.get("envelope_features", {})
        order = order_analysis.get("order_features", {})

        # 提取显著异常
        anomalies = []
        if spec.get("mesh_freq_ratio", 0) > 0.05:
            anomalies.append(f"啮合频率能量占比 {spec['mesh_freq_ratio']*100:.1f}%")
        if spec.get("sideband_count", 0) >= 2:
            anomalies.append(f"边频带数量 {spec['sideband_count']} 个")
        for name in ["BPFO", "BPFI", "BSF"]:
            env_ratio = env.get(f"{name}_env_ratio", 0)
            order_ratio = order.get(f"{name}_order_ratio", 0)
            if env_ratio > 0.03 or order_ratio > 0.03:
                anomalies.append(f"{name} 包络/阶次异常 (env={env_ratio*100:.1f}%, order={order_ratio*100:.1f}%)")

        if anomalies:
            order_desc = "\n频域/阶次异常证据：\n" + "\n".join([f"• {a}" for a in anomalies[:4]])
        else:
            order_desc = "\n频域/阶次分析未检出显著异常。"
        order_desc = rot_info + order_desc

    if health_score < 60:
        if not _has_recent_unresolved_alarm(db, device.device_id, "综合健康度", "critical"):
            alarm = Alarm(
                device_id=device.device_id,
                level="critical",
                category="综合健康度",
                batch_index=batch_index,
                title=f"设备健康度严重下降：{health_score} 分",
                description=(
                    f"系统分析显示设备整体健康度已降至 {health_score} 分（正常≥80，预警≥60）。"
                    f"{fault_desc}\n"
                    f"{order_desc}\n"
                    f"建议立即停机检查。"
                ),
                suggestion="1. 检查齿轮箱润滑状态；2. 检查各轴承温度；3. 联系维修人员现场排查。",
            )
            db.add(alarm)
            new_alarms.append(alarm)
    elif health_score < 80:
        if not _has_recent_unresolved_alarm(db, device.device_id, "综合健康度", "warning"):
            alarm = Alarm(
                device_id=device.device_id,
                level="warning",
                category="综合健康度",
                batch_index=batch_index,
                title=f"设备健康度预警：{health_score} 分",
                description=(
                    f"设备健康度下降至 {health_score} 分（正常≥80，预警≥60）。"
                    f"{fault_desc}\n"
                    f"{order_desc}\n"
                    f"存在潜在故障风险。"
                ),
                suggestion="1. 加强监测频率；2. 关注振动趋势变化；3. 安排计划性检修。",
            )
            db.add(alarm)
            new_alarms.append(alarm)

    return new_alarms
