"""DataView 计算前提失败到外部 HTTP 契约的唯一映射。"""

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Literal, Union
from app.services.diagnosis.signal_utils import DenoisingError


class DenoisingFailureDetail(BaseModel):
    status: Literal["not_evaluable"]
    method: str
    reason: str


class RequestValidationIssue(BaseModel):
    loc: list[Union[str, int]]
    msg: str
    type: str


class DataViewUnprocessableResponse(BaseModel):
    """422包含显式去噪不可评估，或FastAPI请求参数验证失败。"""

    detail: Union[DenoisingFailureDetail, list[RequestValidationIssue]]


def configured_denoise(method):
    """HTTP调用不得把未识别的前处理选项默认成未去噪。"""
    from app.services.diagnosis.engine import DenoiseMethod

    try:
        return DenoiseMethod(method)
    except ValueError as exc:
        raise DenoisingError(str(method), "未知去噪方法") from exc


def denoising_http_error(error):
    """请求的去噪未产生有效表示，不能把原信号作为成功响应交付。"""
    return HTTPException(
        status_code=422,
        detail={
            "status": "not_evaluable",
            "method": error.method,
            "reason": error.reason,
        },
    )
