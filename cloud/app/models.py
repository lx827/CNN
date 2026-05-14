"""
数据表模型（SQLAlchemy）
对应 MySQL/SQLite 里的真实表结构

核心设计：
- devices: 设备信息，含通道数配置、通道名称
- sensor_data: 振动原始数据
  - 普通数据：每个设备最多16个批次（循环覆盖），is_special=0
  - 特殊数据：手动触发采集，is_special=1，独立自增batch_index（从101起），不覆盖
- diagnosis: 诊断结果，关联到具体批次
- alarms: 告警记录
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, UniqueConstraint
from app.database import Base
from datetime import datetime


class Device(Base):
    """设备信息表"""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), unique=True, index=True, comment="设备编号")
    name = Column(String(100), comment="设备名称")
    location = Column(String(200), comment="安装位置")
    channel_count = Column(Integer, default=3, comment="振动通道数")
    channel_names = Column(JSON, comment="通道名称映射，如 {'1':'轴承附近','2':'驱动端','3':'风扇端'}")
    sample_rate = Column(Integer, default=25600, comment="采样率 Hz")
    window_seconds = Column(Integer, default=10, comment="采集窗口秒数")
    health_score = Column(Integer, default=100, comment="健康度 0-100")
    status = Column(String(20), default="normal", comment="状态: normal/warning/fault")
    runtime_hours = Column(Integer, default=0, comment="运行时长(小时)")
    upload_interval = Column(Integer, default=10, comment="自动采集上传间隔(秒)")
    task_poll_interval = Column(Integer, default=5, comment="任务轮询间隔(秒)")
    alarm_thresholds = Column(JSON, default=dict, comment="告警阈值配置，如 {rms:{warning:5,critical:10}}")
    gear_teeth = Column(JSON, nullable=True, comment="齿轮参数，如 {input:18, output:27}")
    bearing_params = Column(JSON, nullable=True, comment="轴承参数，如 {n:9, d:7.94, D:39.04, alpha:0}")
    compression_enabled = Column(Integer, default=1, comment="边端是否启用数据压缩 0/1")
    downsample_ratio = Column(Integer, default=8, comment="边端降采样压缩比")
    is_online = Column(Integer, default=1, comment="是否在线 1=在线 0=离线，由离线监测器维护")
    last_seen_at = Column(DateTime, nullable=True, comment="设备最后一次数据上传时间")
    created_at = Column(DateTime, default=datetime.utcnow)


class SensorData(Base):
    """传感器原始数据表（振动信号等）

    存储策略：
    - 普通数据 (is_special=0)：每个设备最多保留 16 个批次，新数据覆盖最旧批次。
      batch_index 范围 1~16。
    - 特殊数据 (is_special=1)：手动触发采集，batch_index 从 101 起自增，永不覆盖。
    同一批次的不同通道共享 batch_index。
    is_analyzed 标记该批次是否已完成故障诊断。
    """
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True, comment="设备编号")
    batch_index = Column(Integer, default=1, comment="批次序号")
    channel = Column(Integer, comment="通道号 1/2/3/...")
    data = Column(JSON, comment="振动信号数组")
    sample_rate = Column(Integer, default=25600, comment="采样率 Hz")
    is_analyzed = Column(Integer, default=0, comment="是否已检测 0/1")
    is_special = Column(Integer, default=0, comment="是否特殊采集 0=普通 1=特殊")
    analyzed_at = Column(DateTime, nullable=True, comment="检测完成时间")
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="采样时间")

    # 联合索引：快速查询某设备某批次的所有通道
    __table_args__ = (
        UniqueConstraint("device_id", "batch_index", "channel", name="uix_sensor_batch_ch"),
    )


class Diagnosis(Base):
    """诊断结果表，记录每次分析的结果"""
    __tablename__ = "diagnosis"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True)
    batch_index = Column(Integer, comment="关联的 sensor_data 批次号")
    channel = Column(Integer, nullable=True, default=0, comment="通道号 1/2/3/...")
    health_score = Column(Integer, comment="健康度 0-100")
    fault_probabilities = Column(JSON, comment="各故障类型概率")
    imf_energy = Column(JSON, comment="IMF 能量分布")
    order_analysis = Column(JSON, nullable=True, comment="阶次/包络/频谱分析明细")
    rot_freq = Column(Float, nullable=True, comment="估计转频 Hz")
    status = Column(String(20), default="normal", comment="综合状态")
    engine_result = Column(JSON, nullable=True, comment="analyze_comprehensive 完整结果（通道级）")
    full_analysis = Column(JSON, nullable=True, comment="analyze_all_methods 完整结果（通道级）")
    denoise_method = Column(String(20), nullable=True, default="none", comment="去噪方法 none/wavelet/vmd/med")
    analyzed_at = Column(DateTime, default=datetime.utcnow, comment="分析时间")


class Alarm(Base):
    """告警记录表"""
    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True)
    level = Column(String(20), comment="级别: info/warning/critical")
    category = Column(String(50), comment="类别: 振动/温度/齿轮/轴承")
    channel = Column(Integer, nullable=True, comment="通道号 1/2/3/...")
    channel_name = Column(String(100), nullable=True, comment="通道名称，如'轴承附近'")
    title = Column(String(200), comment="告警标题")
    description = Column(Text, comment="详细描述")
    suggestion = Column(Text, comment="处理建议")
    batch_index = Column(Integer, nullable=True, comment="关联的 sensor_data 批次号")
    is_resolved = Column(Integer, default=0, comment="是否已处理 0/1")
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class CollectionTask(Base):
    """采集任务表（持久化，替代内存队列）
    
    前端请求采集 → 创建任务(status=pending)
    边端轮询 → 获取pending任务 → 标记为processing
    边端完成上传 → 标记为completed
    """
    __tablename__ = "collection_tasks"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True, comment="目标设备")
    status = Column(String(20), default="pending", comment="状态: pending/processing/completed/failed")
    sample_rate = Column(Integer, default=25600, comment="采样率 Hz")
    duration = Column(Integer, default=10, comment="采集时长秒")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    started_at = Column(DateTime, nullable=True, comment="开始执行时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    result_batch_index = Column(Integer, nullable=True, comment="完成后关联的batch_index")
    error_message = Column(String(500), nullable=True, comment="错误信息")
