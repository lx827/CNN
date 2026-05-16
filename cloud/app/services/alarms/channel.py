"""
通道级振动特征与齿轮诊断告警
"""
import re
from app.models import Alarm
from . import _get_threshold, _has_recent_unresolved_alarm


def _check_feature_alarms(
    db, device, channel: int, channel_name: str, features: dict, batch_index: int = None
) -> list:
    """
    检查单通道振动特征是否超过阈值，生成通道级告警。
    返回本次新生成的告警列表。
    """
    new_alarms = []
    metric_labels = {
        "rms": "均方根 (RMS)",
        "peak": "峰值",
        "kurtosis": "峭度",
        "crest_factor": "峰值因子",
    }

    for metric, label in metric_labels.items():
        value = features.get(metric)
        if value is None:
            continue

        warn_thr = _get_threshold(device, metric, "warning")
        crit_thr = _get_threshold(device, metric, "critical")

        if value >= crit_thr:
            if _has_recent_unresolved_alarm(db, device.device_id, "振动特征", "critical", channel):
                continue
            severity_pct = min(100, int((value - crit_thr) / max(crit_thr * 0.5, 1e-9) * 100))
            alarm = Alarm(
                device_id=device.device_id,
                level="critical",
                category="振动特征",
                channel=channel,
                channel_name=channel_name,
                batch_index=batch_index,
                title=f"{channel_name} {label}严重超标：{value:.4f}",
                description=(
                    f"通道 {channel}（{channel_name}）的 {label} 检测到异常。\n"
                    f"• 当前值：{value:.4f}\n"
                    f"• 严重阈值：{crit_thr}\n"
                    f"• 预警阈值：{warn_thr}\n"
                    f"• 超出严重阈值约 {severity_pct}%"
                ),
                suggestion=f"1. 检查 {channel_name} 传感器连接；2. 排查该部位机械故障；3. 必要时停机检修。",
            )
            db.add(alarm)
            new_alarms.append(alarm)
        elif value >= warn_thr:
            if _has_recent_unresolved_alarm(db, device.device_id, "振动特征", "warning", channel):
                continue
            severity_pct = min(100, int((value - warn_thr) / max(crit_thr - warn_thr, 1e-9) * 100))
            alarm = Alarm(
                device_id=device.device_id,
                level="warning",
                category="振动特征",
                channel=channel,
                channel_name=channel_name,
                batch_index=batch_index,
                title=f"{channel_name} {label}预警：{value:.4f}",
                description=(
                    f"通道 {channel}（{channel_name}）的 {label} 检测到异常。\n"
                    f"• 当前值：{value:.4f}\n"
                    f"• 预警阈值：{warn_thr}\n"
                    f"• 严重阈值：{crit_thr}\n"
                    f"• 处于预警区间约 {severity_pct}%"
                ),
                suggestion=f"1. 加强 {channel_name} 监测频率；2. 观察趋势变化；3. 安排计划性检查。",
            )
            db.add(alarm)
            new_alarms.append(alarm)

    return new_alarms


def _check_gear_alarms(
    db, device, channel_diagnosis: dict, batch_index: int = None
) -> list:
    """
    检查齿轮诊断指标，生成通道级告警。
    channel_diagnosis 格式: {ch_name: {"gear": {...}, ...}}
    """
    new_alarms = []
    channel_names = device.channel_names or {}
    metric_labels = {
        "ser": "齿轮边频带能量比 (SER)",
        "fm0": "齿轮FM0指标",
        "car": "齿轮倒频谱幅值比 (CAR)",
        "sideband_count": "齿轮边频带显著数量",
    }

    for ch_key, diagnosis in channel_diagnosis.items():
        m = re.search(r"\d+", ch_key)
        ch_num = int(m.group()) if m else 1
        ch_name = channel_names.get(str(ch_num), f"通道{ch_num}")
        gear = diagnosis.get("gear", {})
        if not gear:
            continue

        # 提取指标值
        indicators = gear.get("fault_indicators", {})
        metrics = {
            "ser": indicators.get("ser", {}).get("value", gear.get("ser", 0)),
            "fm0": indicators.get("fm0", {}).get("value", gear.get("fm0", 0)),
            "car": indicators.get("car", {}).get("value", gear.get("car", 0)),
            "sideband_count": indicators.get("sideband_count", {}).get("value", len([sb for sb in gear.get("sidebands", []) if sb.get("significant")])),
        }

        for metric, label in metric_labels.items():
            value = metrics.get(metric)
            if value is None:
                continue
            warn_thr = _get_threshold(device, metric, "warning")
            crit_thr = _get_threshold(device, metric, "critical")

            if value >= crit_thr:
                if _has_recent_unresolved_alarm(db, device.device_id, "齿轮诊断", "critical", ch_num):
                    continue
                severity_pct = min(100, int((value - crit_thr) / max(crit_thr * 0.5, 1e-9) * 100))
                alarm = Alarm(
                    device_id=device.device_id,
                    level="critical",
                    category="齿轮诊断",
                    channel=ch_num,
                    channel_name=ch_name,
                    batch_index=batch_index,
                    title=f"{ch_name} {label}严重超标：{value:.4f}",
                    description=(
                        f"通道 {ch_num}（{ch_name}）的 {label} 检测到严重异常。\n"
                        f"• 当前值：{value:.4f}\n"
                        f"• 严重阈值：{crit_thr}\n"
                        f"• 预警阈值：{warn_thr}\n"
                        f"• 超出严重阈值约 {severity_pct}%"
                    ),
                    suggestion="1. 检查齿轮箱润滑状态；2. 检查齿轮啮合间隙；3. 排查齿面磨损或点蚀；4. 必要时停机检修。",
                )
                db.add(alarm)
                new_alarms.append(alarm)
            elif value >= warn_thr:
                if _has_recent_unresolved_alarm(db, device.device_id, "齿轮诊断", "warning", ch_num):
                    continue
                severity_pct = min(100, int((value - warn_thr) / max(crit_thr - warn_thr, 1e-9) * 100))
                alarm = Alarm(
                    device_id=device.device_id,
                    level="warning",
                    category="齿轮诊断",
                    channel=ch_num,
                    channel_name=ch_name,
                    batch_index=batch_index,
                    title=f"{ch_name} {label}预警：{value:.4f}",
                    description=(
                        f"通道 {ch_num}（{ch_name}）的 {label} 检测到异常。\n"
                        f"• 当前值：{value:.4f}\n"
                        f"• 预警阈值：{warn_thr}\n"
                        f"• 严重阈值：{crit_thr}\n"
                        f"• 处于预警区间约 {severity_pct}%"
                    ),
                    suggestion="1. 加强齿轮箱监测频率；2. 观察振动趋势变化；3. 安排计划性检查。",
                )
                db.add(alarm)
                new_alarms.append(alarm)

    return new_alarms
