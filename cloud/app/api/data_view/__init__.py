"""
振动数据查看接口
支持：
  1. 查询某设备的最近批次（含普通和特殊数据）
  2. 查询某批次某通道的原始时域数据
  3. 实时计算 FFT 频谱、STFT、包络、阶次、倒谱、齿轮诊断
  4. 删除整条批次数据

所有频谱都是请求时实时计算，不预存。
"""
from fastapi import APIRouter
from app.models import Device
from .errors import DataViewUnprocessableResponse

router = APIRouter(prefix="/api/data", tags=["振动数据查看"], responses={
    422: {"model": DataViewUnprocessableResponse,
          "description": "请求参数不合法，或指定去噪未产生有效表示（not_evaluable、method、reason）"},
})

# ── 公共工具函数（统一入口，消除重复） ──
# prepare_signal 实际实现在 signal_utils.py，此处重导出以保持 data_view 子模块兼容
from app.services.diagnosis.signal_utils import prepare_signal  # noqa: F401
from app.core.json_utils import sanitize_for_json as _sanitize_for_json  # noqa: F401


def _extract_device_param(params, device_keys):
    """
    兼容前端通道级格式与后端设备级格式。
    前端 Settings.vue 保存的格式：{ "1": {input: 18, output: 27}, "2": {...} }
    后端诊断引擎期望的格式：{input: 18, output: 27}

    如果 params 已经是设备级，直接返回；
    如果是通道级，提取第一个包含 device_keys 中任意 key 的有效通道参数。

    注：此函数仅做格式转换，不涉及"默认诊断逻辑"。
    默认参数的注入逻辑在各接口中显式处理，详见 DIAGNOSIS_LOGIC.md。
    """
    if not params or not isinstance(params, dict):
        return params
    if any(k in params for k in device_keys):
        return params
    for key in sorted(params.keys()):
        ch = params.get(key)
        if ch and isinstance(ch, dict) and any(k in ch for k in device_keys):
            return ch
    return params



def _get_channel_name(device: Device, channel_num: int) -> str:
    """从设备配置获取通道名称"""
    if device and device.channel_names:
        name = device.channel_names.get(str(channel_num))
        if name:
            return name
    defaults = {
        1: "通道1-轴承附近",
        2: "通道2-驱动端",
        3: "通道3-风扇端",
    }
    return defaults.get(channel_num, f"通道{channel_num}")


# 导入子模块以注册路由
from . import core, spectrum, envelope, order, cepstrum, gear, research, export, diagnosis_ops
