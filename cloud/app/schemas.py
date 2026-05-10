"""
Pydantic 数据模型
用于：API 请求校验、响应序列化
"""
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime


# ==================== 通用 ====================
class ResponseModel(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[dict] = None


# ==================== 认证 ====================
class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ==================== 设备 ====================
class DeviceOut(BaseModel):
    device_id: str
    name: str
    location: str
    health_score: int
    status: str
    runtime_hours: int

    class Config:
        from_attributes = True


# ==================== 传感器数据接入 ====================
class IngestData(BaseModel):
    """边端上传的数据格式"""
    device_id: str
    timestamp: Optional[datetime] = None
    channels: Dict[str, List[float]]  # {"ch1": [0.1, -0.2, ...], "ch2": [...]}
    sample_rate: int = 1000


# ==================== 监测 ====================
class MonitorData(BaseModel):
    device_id: str
    channel: int
    data: List[float]
    sample_rate: int
    timestamp: datetime


# ==================== 诊断 ====================
class DiagnosisOut(BaseModel):
    device_id: str
    health_score: int
    fault_probabilities: Dict[str, float]
    imf_energy: Dict[str, float]
    status: str
    analyzed_at: datetime

    class Config:
        from_attributes = True


# ==================== 告警 ====================
class AlarmOut(BaseModel):
    id: int
    device_id: str
    level: str
    category: str
    title: str
    description: str
    suggestion: str
    is_resolved: int
    created_at: datetime

    class Config:
        from_attributes = True


class AlarmListResponse(BaseModel):
    total: int
    items: List[AlarmOut]
