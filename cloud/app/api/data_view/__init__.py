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
from typing import Tuple
import numpy as np
from scipy import signal as scipy_signal

router = APIRouter(prefix="/api/data", tags=["振动数据查看"])

# ── 公共工具函数（统一入口，消除重复） ──
# prepare_signal 实际实现在 signal_utils.py，此处重导出以保持 data_view 子模块兼容
from app.services.diagnosis.signal_utils import prepare_signal  # noqa: F401


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


def _sanitize_for_json(obj):
    """递归将 numpy 类型转换为 Python 原生类型，确保 JSON 可序列化"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _compute_cepstrum(
    sig: np.ndarray, fs: float,
    max_quefrency_ms: float = 500.0
) -> Tuple[np.ndarray, np.ndarray, list]:
    """
    计算功率倒谱（Power Cepstrum）
    改进：加窗 + 对数谱去均值，消除 quefrency=0 处的虚假长竖线
    """
    N = len(sig)
    window = np.hanning(N)
    sig_windowed = sig * window

    spectrum = np.fft.fft(sig_windowed)
    log_spectrum = np.log(np.abs(spectrum) + 1e-10)
    log_spectrum = log_spectrum - np.mean(log_spectrum)

    cepstrum = np.real(np.fft.ifft(log_spectrum))

    quefrency = np.arange(N) / fs
    half = N // 2
    quef_ms = quefrency[:half] * 1000.0
    cep = cepstrum[:half]

    mask = quef_ms <= max_quefrency_ms
    quef_ms = quef_ms[mask]
    cep = cep[mask]

    peaks = []
    if len(cep) > 10:
        search_mask = (quef_ms >= 3.0) & (quef_ms <= 200.0)
        search_cep = cep[search_mask]
        search_quef = quef_ms[search_mask]

        if len(search_cep) > 10:
            peak_indices, _ = scipy_signal.find_peaks(search_cep, distance=50)
            sorted_indices = sorted(peak_indices, key=lambda i: search_cep[i], reverse=True)

            top_amp = None
            for idx in sorted_indices:
                amp = float(search_cep[idx])
                if top_amp is None:
                    top_amp = amp
                elif amp < top_amp * 0.5:
                    break
                q_ms = float(search_quef[idx])
                too_close = any(abs(p["quefrency_ms"] - q_ms) < 3.0 for p in peaks)
                if too_close:
                    continue
                freq_hz = 1000.0 / q_ms if q_ms > 0 else 0.0
                peaks.append({
                    "quefrency_ms": round(q_ms, 2),
                    "freq_hz": round(freq_hz, 2),
                    "amplitude": round(amp, 4),
                })
    return quef_ms, cep, peaks


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
