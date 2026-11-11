"""
Pydantic 数据模型
用于：API 请求校验、响应序列化
"""
from pydantic import BaseModel, ConfigDict, model_validator
from typing import List, Optional, Dict, Literal
from datetime import datetime
from app.services.diagnosis.domain import EvaluationStatus, DiagnosisConclusion, validate_state


class DiagnosisState(BaseModel):
    """业务两轴及评分不变量；不能把缺少评估编码为健康。"""
    evaluation_status: EvaluationStatus
    diagnosis_conclusion: DiagnosisConclusion
    health_score: Optional[float]
    coverage: Literal["none", "partial", "complete"]

    @model_validator(mode="after")
    def coherent_state(self):
        validate_state(self.evaluation_status, self.diagnosis_conclusion, self.health_score, require_score=True)
        return self


class DiagnosisSnapshot(DiagnosisState):
    model_config = ConfigDict(extra="allow")
    contract_version: Literal[1]
    evaluations: List[dict]
    deductions: List[dict]
    fault_propositions: List[str]
    recommendation: str

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_status(cls, value):
        if isinstance(value, dict) and "status" in value:
            raise ValueError("legacy_diagnosis_status_is_not_supported")
        return value


class DiagnosisResponse(BaseModel):
    code: int = 200
    data: DiagnosisSnapshot


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
class DeviceOut(DiagnosisState):
    device_id: str
    name: str
    location: str
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
class DiagnosisOut(DiagnosisState):
    device_id: str
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
