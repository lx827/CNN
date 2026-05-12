"""
诊断结果告警
基于故障概率生成告警
"""
from app.models import Alarm
from . import _has_recent_unresolved_alarm


def _check_diagnosis_alarms(
    db, device, fault_probabilities: dict, batch_index: int = None
) -> list:
    """
    基于诊断结果生成设备级故障概率告警。
    去重：同一设备同类未处理告警 1 小时内不重复生成。
    """
    new_alarms = []

    for fault_name, prob in fault_probabilities.items():
        if fault_name == "正常运行":
            continue
        if prob > 0.6:
            if not _has_recent_unresolved_alarm(db, device.device_id, "故障诊断", "critical"):
                alarm = Alarm(
                    device_id=device.device_id,
                    level="critical",
                    category="故障诊断",
                    batch_index=batch_index,
                    title=f"高置信度故障：{fault_name} ({prob:.1%})",
                    description=f"诊断算法判定 '{fault_name}' 概率高达 {prob:.1%}，建议重点排查。",
                    suggestion=f"请针对 {fault_name} 进行专项检查，必要时更换相关部件。",
                )
                db.add(alarm)
                new_alarms.append(alarm)
        elif prob > 0.3:
            if not _has_recent_unresolved_alarm(db, device.device_id, "故障诊断", "warning"):
                alarm = Alarm(
                    device_id=device.device_id,
                    level="warning",
                    category="故障诊断",
                    batch_index=batch_index,
                    title=f"疑似故障：{fault_name} ({prob:.1%})",
                    description=f"诊断算法检测到 '{fault_name}' 概率为 {prob:.1%}，建议关注。",
                    suggestion=f"持续观察该故障趋势，如概率继续上升请安排检修。",
                )
                db.add(alarm)
                new_alarms.append(alarm)

    return new_alarms
