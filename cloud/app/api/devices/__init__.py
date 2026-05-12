"""
设备管理接口包
提供设备列表查询、边端配置读写
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/devices", tags=["设备管理"])


def _get_channel_params(device, channel_index, field):
    """
    从设备配置中按通道索引提取参数。
    支持两种格式：
      - 旧格式（设备级共用）: {input:18, output:27}
      - 新格式（通道级独立）: {"1":{input:18}, "2":{input:27}}
    """
    raw = getattr(device, field, None) if device else None
    if raw is None:
        return None
    ch_key = str(channel_index)
    if ch_key in raw:
        return raw[ch_key]
    # 旧格式兼容：如果顶层包含业务字段而非通道键，直接返回
    if "input" in raw or "n" in raw or "output" in raw:
        return raw
    return None


from .core import router as core_router
from .config import router as config_router

router.include_router(core_router)
router.include_router(config_router)
