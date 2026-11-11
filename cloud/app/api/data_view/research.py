from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import asyncio
import logging
from typing import Optional, Literal
from .bearing_options import get_bearing_options
from app.services.diagnosis.signal_utils import DenoisingError
from .errors import denoising_http_error, configured_denoise
from app.services.diagnosis.gear.planetary import (
    analyze_planetary_gear, gear_config_for_channel, is_planetary_config, planetary_geometry_from_config,
)
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.order import ScalarSpeed
from app.algorithms.composite.cvs import CVSAlignment
from app.algorithms.pipelines.composite import CompositeAnalysis, CompositeDiagnosis, ResearchCompositePipeline
from app.services.diagnosis.composite import analyze_composite_research, composite_to_dict
from app.services.diagnosis.adapters import adapt_method_result
from app.services.diagnosis.domain import DiagnosisKey

from app.database import get_db
from app.models import SensorData, Device
from app.services.diagnosis import (
    DiagnosisEngine, DiagnosisStrategy,
    BearingMethod, GearMethod,
)
from . import router, prepare_signal, _get_channel_name, _extract_device_param, _sanitize_for_json

logger = logging.getLogger(__name__)


# ── 分析方法元数据（名称、分类、说明） ──
METHOD_INFO = {
    # 轴承诊断方法
    "envelope": {
        "category": "bearing",
        "label": "包络分析",
        "description": "标准包络谱分析：带通滤波 → Hilbert 解调 → 包络谱。检测轴承特征频率(BPFO/BPFI/BSF/FTF)谐波族，是最基础的轴承诊断方法。",
    },
    "filter_bank_sk": {
        "category": "bearing",
        "label": "二叉滤波器组谱峭度",
        "description": "真实 Butterworth 二叉频带滤波器组与 Hilbert 解析复谱峭度（复高斯基准减2）；达到工程阈值后选带。不称 Fast Kurtogram，无显著冲击频带时不可判定。",
    },
    "cpw": {
        "category": "bearing",
        "label": "CPW 预白化包络",
        "description": "仅在显式提供稳定梳状频率并确认整段稳定时执行倒谱编辑，再用滤波器组选带；未确认、空频率或变速梳状干扰均不可判定。",
    },
    "med": {
        "category": "bearing",
        "label": "MED 增强包络",
        "description": "最小熵解卷积 + 包络分析：设计 FIR 逆滤波器锐化被传递路径衰减的故障冲击，再做包络分析。低信噪比下冲击增强效果显著。",
    },
    "teager": {
        "category": "bearing",
        "label": "Teager 能量包络",
        "description": "先限带，再计算原始 TEO；仅对 Hilbert 包络输入截负。多分量交叉项仍存在，属于工程组合，不提供变速补偿。幅值单位为输入幅值平方。",
    },
    "spectral_kurtosis": {
        "category": "bearing",
        "label": "谱峭度重加权包络",
        "description": "真实滤波器组复谱峭度与冲击度、局部幅值比的工程重加权选带；阈值是工程启发式，未验证真实数据集检测率。",
    },
    "sc_scoh": {
        "category": "bearing",
        "label": "谱相关/谱相干分析",
        "description": "复 FFT 频移交叉乘积与专属 SC/SCoh 背景评估，仅在可靠几何/转频给出的候选附近搜索。缺候选、频率不可分辨或变速时不可判定，不套用包络谱 SNR。",
    },
    "mckd": {
        "category": "bearing",
        "label": "MCKD 增强包络",
        "description": "显式选择 BPFO/BPFI/BSF/FTF，按目标频率/采样周期或几何与转频求周期，优化相关峭度。不选择目标时明确调用 MED 并以 MED 返回，绝不默认 BPFO。",
    },
    "wp": {
        "category": "bearing",
        "label": "小波包轴承诊断",
        "description": "小波包分解 + 敏感频带包络分析：对信号做小波包分解，选择能量或峭度最高的节点做包络分析。频带划分比DWT更精细，适合多共振频带轴承。",
    },
    "dwt": {
        "category": "bearing",
        "label": "DWT 敏感层轴承诊断",
        "description": "离散小波变换 + 敏感层包络分析：对信号做多级DWT分解，选择峭度最高的细节层做包络分析。计算快速，适合实时诊断。",
    },
    "emd_envelope": {
        "category": "bearing",
        "label": "EMD 敏感 IMF 包络",
        "description": "EMD 分解 + 敏感 IMF 包络分析：对信号做EMD分解，选择峭度最高的IMF做包络分析。自适应模态数，适合变速工况。",
    },
    "ceemdan_envelope": {
        "category": "bearing",
        "label": "CEEMDAN 敏感 IMF 包络",
        "description": "CEEMDAN 分解 + 敏感 IMF 包络分析：对信号做CEEMDAN分解，选择峭度最高的IMF做包络分析。抑制模态混叠，IMF更纯净。",
    },
    "vmd_envelope": {
        "category": "bearing",
        "label": "VMD 敏感模态包络",
        "description": "VMD 分解 + 敏感模态包络分析：对信号做VMD分解，选择峭度最高的模态做包络分析。频带划分自适应且数学严格。",
    },
    # 齿轮诊断方法
    "gear_standard": {
        "category": "gear",
        "label": "齿轮标准分析",
        "description": "标准边频带分析 + SER：基于阶次谱计算边频带能量比(SER)和边频带结构，检测齿轮啮合频率两侧的调制边带。",
    },
    "gear_advanced": {
        "category": "gear",
        "label": "齿轮高级指标",
        "description": "FM0/FM4/M6A/M8A/SER/CAR 全指标：基于 TSA 残差/差分信号的完整齿轮指标体系。FM0 粗故障检测、FM4 局部故障检测、M6A/M8A 表面损伤检测、SER 边频带能量比、CAR 倒频谱幅值比。",
    },
    "planetary_narrowband": {
        "category": "planetary", "label": "行星啮合带包络",
        "description": "固定齿圈、明确参考轴与完整齿数的恒速行星排；啮合带包络及局部事件候选不直接定位断齿或裂纹，无健康基线时不可评估。",
    },
    "planetary_fullband": {
        "category": "planetary", "label": "行星全带包络",
        "description": "全带 Hilbert 包络及事件候选阶次；多分量交叉项可能存在。无可比健康基线时只保留原始证据。",
    },
    "planetary_tsa_residual": {
        "category": "planetary", "label": "行星架 TSA 非同步残差包络",
        "description": "按行星架角域完整转周期平均，再对非同步残差计算包络阶次。同架同步事件进入 TSA 并从残差抑制，不代表所有故障都在残差。",
    },
    "planetary_highpass": {
        "category": "planetary", "label": "行星高通包络",
        "description": "明确高通频带后做宽带包络，检查谱覆盖与事件分辨率。未校准指标不进入告警。",
    },
}

COMPOSITE_METHODS = {
    "composite_vmd_amfm": ("vmd_amfm", "VMD 幅频解调", "按已知恒定转频及机械对象提取调幅/调频谱；调制目标与载波分开。"),
    "composite_msb": ("modulation_bispectrum", "调制信号双谱", "四阶复谱先平均再取幅值，查看相位耦合；不将耦合峰直接判为齿轮故障。"),
    "composite_cvs_med_msb": ("cvs_med_msb", "单行星分离 → MED → MSB", "需真实空间方位、行星编号和连续相位；缺少对齐记录时不可判定，不回退原信号。"),
    "composite_vmd_ica": ("vmd_ica", "VMD → ICA 分量分离", "单通道分解后构造虚拟观测，再分离与选择分量；不等价于新增真实测点。"),
    "composite_mswpee": ("mswpee", "多尺度小波包能量熵", "粗粒化后逐尺度查看小波包能量熵，保留不同采样率；不输出故障标签。"),
}
METHOD_INFO.update({key: {"category": "composite", "label": label, "description": description,
                         "research_only": True, "production_eligible": False}
                    for key, (_, label, description) in COMPOSITE_METHODS.items()})


class CompositeResearchRequest(BaseModel):
    method: Literal["composite_vmd_amfm", "composite_msb", "composite_cvs_med_msb", "composite_vmd_ica", "composite_mswpee"]
    rot_freq_hz: Optional[float] = Field(default=None, gt=0)
    options: dict = Field(default_factory=dict)
    alignment: Optional[dict] = None


def _run_composite_method(record, device, method, rot_freq_hz, options=None, alignment=None):
    """同一研究调度边界，GET与POST复用；不写生产缓存或调用生产聚合。"""
    import numpy as np
    internal = COMPOSITE_METHODS[method][0]
    geometry = None
    reason = None
    if internal in {"vmd_amfm", "modulation_bispectrum", "cvs_med_msb"}:
        config = gear_config_for_channel(device.gear_teeth if device else None, record.channel)
        if not config:
            reason = "missing_mechanical_geometry"
        elif is_planetary_config(config):
            geometry = planetary_geometry_from_config(config)
        else:
            geometry = FixedAxisGearGeometry(config.get("input"), config.get("output"))
        if rot_freq_hz is None:
            reason = "constant_reference_speed_required"
    if reason:
        analysis = CompositeAnalysis(internal, "indeterminate", (), reason=reason)
        diagnosis = CompositeDiagnosis(analysis, ResearchCompositePipeline().evaluate(analysis))
    else:
        context = None
        if alignment is not None:
            try:
                context = CVSAlignment(**{
                    **alignment,
                    "carrier_phase_rad": np.asarray(alignment["carrier_phase_rad"], dtype=float),
                    "planet_phase_rad": np.asarray(alignment["planet_phase_rad"], dtype=float),
                })
            except (KeyError, TypeError) as exc:
                raise ValueError("invalid_CVS_alignment_record") from exc
        diagnosis = analyze_composite_research(
            internal, record.data, record.sample_rate or 25600,
            geometry=geometry, speed=ScalarSpeed(rot_freq_hz, "explicit_research_input") if rot_freq_hz else None,
            alignment=context, options=options,
        )
    return {**composite_to_dict(diagnosis), "device_id": record.device_id, "batch_index": record.batch_index,
            "channel": record.channel, "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": record.sample_rate or 25600, "analysis_method": method,
            "method_info": METHOD_INFO[method], "rot_freq_hz": rot_freq_hz}


@router.post("/{device_id}/{batch_index}/{channel}/composite-analysis")
async def post_channel_composite_analysis(device_id: str, batch_index: int, channel: int,
                                          request: CompositeResearchRequest, db: Session = Depends(get_db)):
    """显式研究组合；CVS相位记录放请求体，既不猜空间零位也不存诊断缓存。"""
    record = db.query(SensorData).filter(SensorData.device_id == device_id,
        SensorData.batch_index == batch_index, SensorData.channel == channel).first()
    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")
    device = db.query(Device).filter(Device.device_id == device_id).first()
    try:
        result = await asyncio.to_thread(_run_composite_method, record, device, request.method,
                                         request.rot_freq_hz, request.options, request.alignment)
        return {"code": 200, "data": _sanitize_for_json(result)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"研究组合参数无效: {exc}") from exc


@router.get("/method-info")
async def get_method_info():
    """返回所有可用分析方法的信息（分类、名称、说明）。"""
    return {"code": 200, "data": METHOD_INFO}


@router.get("/{device_id}/{batch_index}/{channel}/method-analysis")
async def get_channel_method_analysis(
    device_id: str,
    batch_index: int,
    channel: int,
    method: str = Query(default="all", description="分析方法名或'all'运行全部"),
    denoise: str = Query(default="none", description="none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd"),
    detrend: bool = Query(default=False, description="是否线性去趋势"),
    db: Session = Depends(get_db),
    bearing_options: dict = Depends(get_bearing_options),
    rot_freq_hz: Optional[float] = Query(default=None, gt=0),
):
    """
    独立运行单个分析方法或全部方法。

    method 参数值：
    - 'all': 运行所有轴承+齿轮方法（等效 full-analysis）
    - 轴承方法: envelope / filter_bank_sk / cpw / med / teager / spectral_kurtosis / wp / dwt / emd_envelope / ceemdan_envelope / vmd_envelope
    - 齿轮方法: gear_standard / gear_advanced
    - 行星箱方法: planetary_narrowband / planetary_fullband / planetary_tsa_residual / planetary_highpass
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel,
    ).first()
    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    device = db.query(Device).filter(Device.device_id == device_id).first()

    if method in COMPOSITE_METHODS:
        if denoise != "none" or detrend:
            raise HTTPException(status_code=400, detail="研究组合按自身阶段处理原始信号，请选择不去噪且不去趋势")
        try:
            result = await asyncio.to_thread(_run_composite_method, record, device, method, rot_freq_hz)
            return {"code": 200, "data": _sanitize_for_json(result)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"研究组合参数无效: {exc}") from exc

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data[:int(sample_rate * 5)], detrend=detrend)

        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = _extract_device_param(device.bearing_params or {}, ("n", "d", "D", "alpha"))
            gear_teeth = gear_config_for_channel(device.gear_teeth, channel)

        denoise_method = configured_denoise(denoise)
        diagnosis_key = DiagnosisKey(device_id, batch_index, channel, denoise_method.value)

        # ── 运行全部方法 ──
        if method == "all":
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.EXPERT,
                bearing_options=bearing_options,
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
                diagnosis_key=diagnosis_key,
            )
            result = await asyncio.to_thread(
                engine.analyze_all_methods, signal, sample_rate, rot_freq_hz
            )
            response_data = {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "method": "all",
                "denoise": denoise,
                **result,
            }
            return {"code": 200, "data": _sanitize_for_json(response_data)}

        # ── 运行单个轴承方法 ──
        bearing_method_map = {
            "envelope": BearingMethod.ENVELOPE,
            "filter_bank_sk": BearingMethod.FILTER_BANK_SK,
            "cpw": BearingMethod.CPW,
            "med": BearingMethod.MED,
            "teager": BearingMethod.TEAGER,
            "spectral_kurtosis": BearingMethod.SPECTRAL_KURTOSIS,
            "sc_scoh": BearingMethod.SC_SCOH,
            "mckd": BearingMethod.MCKD,
            "wp": BearingMethod.WP,
            "dwt": BearingMethod.DWT,
            "emd_envelope": BearingMethod.EMD_ENVELOPE,
            "ceemdan_envelope": BearingMethod.CEEMDAN_ENVELOPE,
            "vmd_envelope": BearingMethod.VMD_ENVELOPE,
        }
        if method in bearing_method_map:
            engine = DiagnosisEngine(
                bearing_method=bearing_method_map[method],
                bearing_options=bearing_options,
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
                diagnosis_key=diagnosis_key,
            )
            result = await asyncio.to_thread(
                engine.analyze_bearing, signal, sample_rate, rot_freq_hz
            )
            response_data = {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "method": method,
                "method_info": METHOD_INFO.get(method, {}),
                "denoise": denoise,
                **result,
            }
            return {"code": 200, "data": _sanitize_for_json(response_data)}

        # ── 运行单个齿轮方法 ──
        gear_method_map = {
            "gear_standard": GearMethod.STANDARD,
            "gear_advanced": GearMethod.ADVANCED,
        }
        if method in gear_method_map:
            engine = DiagnosisEngine(
                gear_method=gear_method_map[method],
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
                diagnosis_key=diagnosis_key,
            )
            result = await asyncio.to_thread(
                engine.analyze_gear, signal, sample_rate, rot_freq_hz
            )
            response_data = {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "method": method,
                "method_info": METHOD_INFO.get(method, {}),
                "denoise": denoise,
                **result,
            }
            return {"code": 200, "data": _sanitize_for_json(response_data)}

        planetary_methods = {
            "planetary_narrowband": "narrowband", "planetary_fullband": "fullband",
            "planetary_tsa_residual": "tsa_residual", "planetary_highpass": "highpass",
        }
        if method in planetary_methods:
            engine = DiagnosisEngine(denoise_method=denoise_method, gear_teeth=gear_teeth,
                                     diagnosis_key=diagnosis_key)
            selected = planetary_methods[method]
            def analyze_selected_planetary():
                arr = engine.preprocess(signal)
                order_analysis = engine._analyze_order(arr, sample_rate, rot_freq=rot_freq_hz, estimation_signal=signal)
                raw = analyze_planetary_gear(arr, sample_rate, gear_teeth,
                    order_analysis=order_analysis, include_tsa=selected == "tsa_residual", methods=(selected,))
                return adapt_method_result(raw, key=diagnosis_key, object_id="gear", method="planetary_gear",
                    signal=signal, physical_parameters=bool(gear_teeth))
            result = await asyncio.to_thread(analyze_selected_planetary)
            return {"code": 200, "data": _sanitize_for_json({
                "device_id": record.device_id, "batch_index": record.batch_index,
                "channel": record.channel, "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate, "analysis_method": method,
                "method_info": METHOD_INFO[method], "denoise": denoise, **result,
            })}

        raise HTTPException(status_code=400, detail=f"未知分析方法: {method}")

    except HTTPException:
        raise
    except DenoisingError as exc:
        raise denoising_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"分析参数无效: {exc}") from exc
    except Exception as exc:
        logger.error("method analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析方法执行失败: {exc}")


@router.get("/{device_id}/{batch_index}/{channel}/research-analysis")
async def get_channel_research_analysis(
    device_id: str,
    batch_index: int,
    channel: int,
    detrend: bool = Query(default=False, description="whether to linearly detrend"),
    profile: str = Query(default="balanced", description="runtime/balanced/exhaustive"),
    denoise: str = Query(default="none", description="none/wavelet/vmd/wavelet_vmd/wavelet_lms/emd/ceemdan/savgol/wavelet_packet/ceemdan_wp/eemd"),
    max_seconds: float = Query(default=5.0, ge=1.0, le=10.0),
    db: Session = Depends(get_db),
    bearing_options: dict = Depends(get_bearing_options),
    rot_freq_hz: Optional[float] = Query(default=None, gt=0),
):
    """
    Run a user-triggered, multi-algorithm research diagnosis.

    This endpoint is intentionally separate from real-time monitoring because
    filter_bank_sk, MED, TEO and TSA metrics are CPU-heavy.
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel,
    ).first()
    if not record or not record.data:
        raise HTTPException(status_code=404, detail="data not found")

    device = db.query(Device).filter(Device.device_id == device_id).first()

    profile = profile if profile in {"runtime", "balanced", "exhaustive"} else "balanced"

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data[:int(sample_rate * min(max_seconds, 5.0))], detrend=detrend)

        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = _extract_device_param(device.bearing_params or {}, ("n", "d", "D", "alpha"))
            gear_teeth = gear_config_for_channel(device.gear_teeth, channel)

        engine = DiagnosisEngine(
            denoise_method=configured_denoise(denoise),
            bearing_options=bearing_options,
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
            diagnosis_key=DiagnosisKey(device_id, batch_index, channel, denoise),
        )

        result = await asyncio.to_thread(
            engine.analyze_research_ensemble,
            signal,
            sample_rate,
            rot_freq_hz,
            profile,
            max_seconds,
        )

        logger.info(
            "[research-analysis] device=%s batch=%s ch=%s profile=%s "
            "evaluation_status=%s conclusion=%s coverage=%s objects=%d",
            device_id, batch_index, channel, profile,
            result["evaluation_status"], result["diagnosis_conclusion"], result["coverage"],
            len(result["evaluations"]),
        )

        response_data = {
            "device_id": record.device_id,
            "batch_index": record.batch_index,
            "channel": record.channel,
            "channel_name": _get_channel_name(device, record.channel),
            "sample_rate": sample_rate,
            "is_special": bool(record.is_special),
            "profile": profile,
            "denoise": denoise,
            **result,
        }
        return {"code": 200, "data": _sanitize_for_json(response_data)}
    except DenoisingError as exc:
        raise denoising_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"分析参数无效: {exc}") from exc
    except Exception as exc:
        logger.error("research analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"research analysis failed: {exc}")
