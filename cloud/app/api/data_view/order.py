from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from app.algorithms.order import (
    AutomaticOrderPipeline,
    ConstantSpeedOrderPipeline,
    LocalSpeedEstimates,
    OrderParameters,
    ScalarSpeed,
    SpeedSearchRange,
    SpeedTrajectory,
)
from . import router, prepare_signal, _get_channel_name
from app.services.diagnosis.signal_utils import denoise_signal, DenoisingError
from .errors import denoising_http_error
from datetime import datetime, timezone
import logging
import numpy as np
import asyncio

logger = logging.getLogger(__name__)


@router.get("/{device_id}/{batch_index}/{channel}/order")
async def get_channel_order(
    device_id: str,
    batch_index: int,
    channel: int,
    freq_min: float = Query(
        default=10.0, ge=1.0, le=500.0, description="转频搜索下限 (Hz)"
    ),
    freq_max: float = Query(
        default=100.0, ge=1.0, le=500.0, description="转频搜索上限 (Hz)"
    ),
    samples_per_rev: int = Query(
        default=1024, ge=64, le=4096, description="每转采样点数"
    ),
    max_order: int = Query(default=50, ge=5, le=200, description="返回的最大阶次"),
    rot_freq: Optional[float] = Query(
        default=None,
        ge=1.0,
        le=500.0,
        description="直接指定转频(Hz)，传入则跳过自动估计",
    ),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    denoise: str = Query(
        default="none",
        description="预处理方法: none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd",
    ),
    db: Session = Depends(get_db),
):
    """实时计算阶次谱：恒速等角采样、缓变逐帧谱平均或快速变速连续相位跟踪。

    响应字段保持兼容；orders 为 FFT bin 阶次轴，spectrum 为单边峰值幅值。
    自动估计使用未去噪信号，显式 denoise 只影响重采样输入。快速变速无可靠
    脊线时返回 400，不回退固定转频或缓变正常谱。
    """
    record = (
        db.query(SensorData)
        .filter(
            SensorData.device_id == device_id,
            SensorData.batch_index == batch_index,
            SensorData.channel == channel,
        )
        .first()
    )

    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    try:
        sample_rate = record.sample_rate or 25600
        # 五秒限制先于去趋势和慢去噪，自动估计与重采样使用同一个时间窗口。
        max_samples = int(sample_rate * 5)
        raw_sig = prepare_signal(record.data[:max_samples], detrend=detrend)
        # VMD 等去噪可能耗时较长，不能直接占用事件循环。
        sig = await asyncio.to_thread(denoise_signal, raw_sig, denoise)
        # 参数校验
        if freq_min >= freq_max:
            raise ValueError("freq_min 必须小于 freq_max")

        parameters = OrderParameters(
            samples_per_revolution=samples_per_rev,
            max_order=float(max_order),
        )
        if rot_freq is not None:
            analysis = await asyncio.to_thread(
                ConstantSpeedOrderPipeline(parameters).run,
                sig,
                sample_rate,
                ScalarSpeed(float(rot_freq), "query_parameter"),
            )
        else:
            analysis = await asyncio.to_thread(
                AutomaticOrderPipeline(
                    parameters=parameters,
                    search=SpeedSearchRange(freq_min, freq_max),
                ).run,
                sig,
                sample_rate,
                raw_sig,
            )
        if analysis.status != "valid" or analysis.spectrum is None:
            raise ValueError(analysis.reason or "转频/相位不可判定，未生成正常阶次谱")
        order_axis = analysis.spectrum.order_bins
        spectrum = analysis.spectrum.amplitude
        tracking_method = analysis.tracking_method
        if isinstance(analysis.speed, ScalarSpeed):
            rot_freq_val = float(analysis.speed.frequency_hz)
            rot_freq_std = 0.0
        elif isinstance(analysis.speed, LocalSpeedEstimates):
            rot_freq_val = analysis.speed.median_hz
            rot_freq_std = analysis.speed.std_hz
        elif isinstance(analysis.speed, SpeedTrajectory):
            rot_freq_val = float(np.median(analysis.speed.frequency_hz))
            rot_freq_std = float(np.std(analysis.speed.frequency_hz))
        else:
            raise TypeError("未知转速表示")

        device = db.query(Device).filter(Device.device_id == device_id).first()

        # 仅更新明确的批次级记录；不创建“正常”诊断，也不触碰通道/去噪缓存。
        try:
            diag = (
                db.query(Diagnosis)
                .filter(
                    Diagnosis.device_id == device_id,
                    Diagnosis.batch_index == batch_index,
                    Diagnosis.channel == 0,
                    Diagnosis.denoise_method == "none",
                )
                .order_by(Diagnosis.analyzed_at.desc(), Diagnosis.id.desc())
                .first()
            )
            if diag is not None:
                existing_order = diag.order_analysis or {}
                existing_order["rot_freq_hz"] = round(rot_freq_val, 3)
                existing_order["rot_rpm"] = round(rot_freq_val * 60.0, 1)
                diag.order_analysis = existing_order
                flag_modified(diag, "order_analysis")
                diag.rot_freq = round(rot_freq_val, 3)
                db.commit()
        except Exception as db_err:
            logger.warning(f"阶次追踪转频写入数据库失败: {db_err}")
            db.rollback()

        return {
            "code": 200,
            "data": {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "is_special": bool(record.is_special),
                "rot_freq": round(rot_freq_val, 3),
                "rot_rpm": round(rot_freq_val * 60.0, 1),
                "rot_freq_std": round(rot_freq_std, 3),
                "tracking_method": tracking_method,
                "samples_per_rev": samples_per_rev,
                "orders": [round(float(o), 6) for o in order_axis.tolist()],
                "spectrum": [round(float(a), 6) for a in spectrum.tolist()],
            },
        }
    except DenoisingError as e:
        raise denoising_http_error(e) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"阶次谱计算失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"阶次谱计算失败: {e}")
