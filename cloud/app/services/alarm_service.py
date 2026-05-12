"""
告警生成服务（通道级）
支持两类告警：
  1. 诊断结果告警（健康度 + 故障概率）—— 设备级
  2. 振动特征阈值告警（RMS/峭度/峰值/峰值因子）—— 通道级

阈值从设备的 alarm_thresholds 字段读取，支持用户自定义。
去重策略：同一设备同类未处理告警在 1 小时内不重复生成。
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Alarm, Device
from app.core.websocket import manager


# 默认阈值（当设备未配置时使用）
# 基于真实 .npy 数据校准（H组健康 / I,O组故障）
DEFAULT_THRESHOLDS = {
    "rms": {"warning": 0.015, "critical": 0.030},
    "peak": {"warning": 0.100, "critical": 0.150},
    "kurtosis": {"warning": 5.5, "critical": 7.0},
    "crest_factor": {"warning": 9.0, "critical": 10.5},
    # 齿轮诊断指标阈值
    "ser": {"warning": 1.5, "critical": 3.0},
    "fm0": {"warning": 5.0, "critical": 10.0},
    "car": {"warning": 1.2, "critical": 2.0},
    "sideband_count": {"warning": 2, "critical": 4},
}


def _get_threshold(device: Device, metric: str, level: str) -> float:
    """读取设备的阈值配置，未配置则使用默认值；显式置空(null)则禁用该级别告警"""
    thresholds = device.alarm_thresholds or {}
    metric_cfg = thresholds.get(metric)
    if metric_cfg is not None:
        val = metric_cfg.get(level)
        if val is not None:
            return val
        # 用户配置了该指标但此级别为 null，返回极大值（不触发此级别告警）
        return 99999
    return ALARM_THRESHOLDS.get(metric, {}).get(level, 99999)


def _has_recent_unresolved_alarm(
    db: Session, device_id: str, category: str, level: str, channel: int = None, hours: int = 1
) -> bool:
    """
    检查该设备最近 hours 小时内是否已有同类未处理告警。
    通道级告警用 device_id + channel + category + level 去重。
    设备级告警用 device_id + category + level 去重。
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    query = db.query(Alarm).filter(
        Alarm.device_id == device_id,
        Alarm.category == category,
        Alarm.level == level,
        Alarm.is_resolved == 0,
        Alarm.created_at >= since,
    )
    if channel is not None:
        query = query.filter(Alarm.channel == channel)
    else:
        query = query.filter(Alarm.channel.is_(None))
    return query.first() is not None


def _check_feature_alarms(
    db: Session, device: Device, channel: int, channel_name: str, features: dict, batch_index: int = None
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


def _check_diagnosis_alarms(
    db: Session, device: Device, health_score: int, fault_probabilities: dict,
    batch_index: int = None, order_analysis: dict = None
) -> list:
    """
    基于诊断结果生成设备级告警。
    去重：同一设备同类未处理告警 1 小时内不重复生成。
    """
    new_alarms = []

    # 规则 1：健康度过低
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

    # 规则 2：单项故障概率过高
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


def _check_gear_alarms(
    db: Session, device: Device, channel_diagnosis: dict, batch_index: int = None
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
        ch_num = int(ch_key.replace("ch", "")) if ch_key.startswith("ch") else 1
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


def generate_alarms(
    db: Session,
    device_id: str,
    health_score: int,
    fault_probabilities: dict,
    channel_features: dict = None,
    batch_index: int = None,
    order_analysis: dict = None,
    channel_diagnosis: dict = None,
):
    """
    综合告警生成入口

    参数：
      device_id: 设备ID
      health_score: 健康度
      fault_probabilities: 故障概率字典
      channel_features: 通道级特征，格式 {ch_name: {rms:..., peak:..., ...}}
      batch_index: 关联的数据批次号
      order_analysis: 阶次分析结果
      channel_diagnosis: 通道级诊断结果，格式 {ch_name: {gear: {...}, bearing: {...}}}
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        return []

    new_alarms = []

    # 1. 通道级振动特征阈值告警
    if channel_features:
        channel_names = device.channel_names or {}
        for ch_key, features in channel_features.items():
            # ch_key 可能是 "ch1", "ch2"...
            ch_num = int(ch_key.replace("ch", "")) if ch_key.startswith("ch") else 1
            ch_name = channel_names.get(str(ch_num), f"通道{ch_num}")
            alarms = _check_feature_alarms(db, device, ch_num, ch_name, features, batch_index)
            new_alarms.extend(alarms)

    # 2. 通道级齿轮诊断告警
    if channel_diagnosis:
        gear_alarms = _check_gear_alarms(db, device, channel_diagnosis, batch_index)
        new_alarms.extend(gear_alarms)

    # 3. 设备级诊断结果告警
    diag_alarms = _check_diagnosis_alarms(db, device, health_score, fault_probabilities, batch_index, order_analysis)
    new_alarms.extend(diag_alarms)

    if new_alarms:
        db.commit()
        # WebSocket 推送
        for alarm in new_alarms:
            import asyncio
            msg = {
                "type": "new_alarm",
                "data": {
                    "id": alarm.id,
                    "title": alarm.title,
                    "level": alarm.level,
                    "channel": alarm.channel,
                    "channel_name": alarm.channel_name,
                    "created_at": alarm.created_at.isoformat() if alarm.created_at else None,
                }
            }
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(manager.broadcast(msg))
            except Exception:
                pass

    return new_alarms
