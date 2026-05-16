from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
import asyncio
import logging

from app.database import get_db
from app.models import SensorData, Device, Diagnosis
from app.services.diagnosis import (
    DiagnosisEngine, DenoiseMethod, DiagnosisStrategy,
    BearingMethod, GearMethod,
)
from . import router, prepare_signal, _get_channel_name
from .gear import _extract_device_param
from .diagnosis_ops import _sanitize_for_json

logger = logging.getLogger(__name__)


def _save_research_diagnosis(db: Session, device_id: str, batch_index: int,
                             channel: int, denoise: str, result: dict):
    """将研究诊断结果写入 diagnosis 表缓存，供 DataView 等模块读取。"""
    try:
        diag = db.query(Diagnosis).filter(
            Diagnosis.device_id == device_id,
            Diagnosis.batch_index == batch_index,
            Diagnosis.channel == channel,
            Diagnosis.denoise_method == denoise,
        ).first()

        health_score = result.get("health_score")
        status = result.get("status", "normal")

        if diag:
            diag.health_score = health_score
            diag.status = status
            diag.full_analysis = _sanitize_for_json(result)
            diag.analyzed_at = __import__("datetime").datetime.utcnow()
        else:
            diag = Diagnosis(
                device_id=device_id,
                batch_index=batch_index,
                channel=channel,
                denoise_method=denoise,
                health_score=health_score,
                status=status,
                full_analysis=_sanitize_for_json(result),
                analyzed_at=__import__("datetime").datetime.utcnow(),
            )
            db.add(diag)
        db.commit()
    except Exception as exc:
        logger.warning("保存研究诊断缓存失败: %s", exc)
        db.rollback()

# ── 分析方法元数据（名称、分类、说明） ──
METHOD_INFO = {
    # 轴承诊断方法
    "envelope": {
        "category": "bearing",
        "label": "包络分析",
        "description": "标准包络谱分析：带通滤波 → Hilbert 解调 → 包络谱。检测轴承特征频率(BPFO/BPFI/BSF/FTF)谐波族，是最基础的轴承诊断方法。",
    },
    "kurtogram": {
        "category": "bearing",
        "label": "Fast Kurtogram",
        "description": "快速谱峭度图自适应选带包络：自动搜索受噪声污染最小、冲击最显著的频带，再执行包络分析。对未知共振频带的轴承诊断特别有效。",
    },
    "cpw": {
        "category": "bearing",
        "label": "CPW 预白化包络",
        "description": "倒频谱预白化 + 包络分析：先通过倒频谱编辑消除齿轮啮合、轴频等确定性干扰，再对预白化信号做包络分析。齿轮箱中轴承诊断的标准流程。",
    },
    "med": {
        "category": "bearing",
        "label": "MED 增强包络",
        "description": "最小熵解卷积 + 包络分析：设计 FIR 逆滤波器锐化被传递路径衰减的故障冲击，再做包络分析。低信噪比下冲击增强效果显著。",
    },
    "teager": {
        "category": "bearing",
        "label": "Teager 能量包络",
        "description": "Teager 能量算子增强 + Kurtogram 包络：TEO 对瞬态冲击极度敏感，先增强弱冲击成分，再用谱峭度自适应选带做包络分析。适合早期微弱故障检测。",
    },
    "spectral_kurtosis": {
        "category": "bearing",
        "label": "谱峭度重加权包络",
        "description": "自适应谱峭度重加权包络：结合谱峭度、冲击度和局部 SNR 联合选带，对多频带冲击场景的检测率高于单一 Kurtogram。",
    },
    "sc_scoh": {
        "category": "bearing",
        "label": "谱相关/谱相干分析",
        "description": "轴承循环平稳分析：计算谱相关密度(SC)和谱相干系数(SCoh)，在 BPFO/BPFI/BSF 等故障频率处检测循环平稳特征。适合恒速工况下的轴承诊断。",
    },
    "mckd": {
        "category": "bearing",
        "label": "MCKD 增强包络",
        "description": "最大相关峭度解卷积 + 包络分析：引入故障周期约束优化周期性冲击序列检测，对轴承内圈/外圈故障更敏感。与 MED 互补，MED 最大化全局峭度，MCKD 最大化周期性冲击。",
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
    # 行星齿轮箱专用方法（仅在行星箱参数配置时可用）
    "planetary_narrowband": {
        "category": "planetary",
        "label": "窄带包络阶次分析",
        "description": "行星齿轮箱 Level 2a：对 mesh_order 频带做窄带滤波 → Hilbert 包络 → 阶次谱，搜索 sun/planet/carrier 故障阶次峰值。",
    },
    "planetary_fullband": {
        "category": "planetary",
        "label": "全频带包络阶次分析",
        "description": "行星齿轮箱 Level 2b：对全频带信号做包络后计算阶次谱，不依赖窄带滤波参数选择。",
    },
    "planetary_tsa_envelope": {
        "category": "planetary",
        "label": "TSA 残差包络阶次分析",
        "description": "行星齿轮箱 Level 2c：先做 TSA 提取同步啮合成分，再对残差做包络阶次分析。实测区分力最强(3.31×)，是最有效的行星箱诊断方法。",
    },
    "planetary_hp_envelope": {
        "category": "planetary",
        "label": "高通滤波包络阶次分析",
        "description": "行星齿轮箱 Level 2d：高通滤波去除低频旋转成分后做包络阶次分析，适合低速行星箱。",
    },
    "planetary_vmd_demod": {
        "category": "planetary",
        "label": "VMD 幅频联合解调",
        "description": "行星齿轮箱 Level 3：VMD 分解 → 选择围绕 mesh_freq 的敏感 IMF → 幅值解调谱 + 频率解调谱。计算较慢，仅在 full-analysis 模式启用。",
    },
    "planetary_sc_scoh": {
        "category": "planetary",
        "label": "谱相关/谱相干解调",
        "description": "行星齿轮箱 Level 4：基于 AM-FM 模型的谱相关密度分析，在二维谱面上识别离散故障特征点群。计算较慢。",
    },
    "planetary_msb": {
        "category": "planetary",
        "label": "MSB 残余边频带分析",
        "description": "行星齿轮箱 Level 5：调制信号双谱(MSB)提取残余边频带信息，不受制造误差干扰，故障时 MSB 幅值单调增长。计算较慢。",
    },
}


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
):
    """
    独立运行单个分析方法或全部方法。

    method 参数值：
    - 'all': 运行所有轴承+齿轮方法（等效 full-analysis）
    - 轴承方法: envelope / kurtogram / cpw / med / teager / spectral_kurtosis / wp / dwt / emd_envelope / ceemdan_envelope / vmd_envelope
    - 齿轮方法: gear_standard / gear_advanced
    - 行星箱方法: planetary_narrowband / planetary_fullband / planetary_tsa_envelope
                  / planetary_hp_envelope / planetary_vmd_demod / planetary_sc_scoh / planetary_msb
    """
    record = db.query(SensorData).filter(
        SensorData.device_id == device_id,
        SensorData.batch_index == batch_index,
        SensorData.channel == channel,
    ).first()
    if not record or not record.data:
        raise HTTPException(status_code=404, detail="数据不存在")

    device = db.query(Device).filter(Device.device_id == device_id).first()

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data, detrend=detrend)

        # 限制信号长度（最多 5 秒）
        max_samples = sample_rate * 5
        if len(signal) > max_samples:
            signal = signal[:max_samples]

        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = _extract_device_param(device.bearing_params or {}, ("n", "d", "D", "alpha"))
            gear_teeth = _extract_device_param(device.gear_teeth or {}, ("input", "output"))

        denoise_map = {
            "none": DenoiseMethod.NONE, "wavelet": DenoiseMethod.WAVELET,
            "vmd": DenoiseMethod.VMD, "wavelet_vmd": DenoiseMethod.WAVELET_VMD,
            "wavelet_lms": DenoiseMethod.WAVELET_LMS,
            "emd": DenoiseMethod.EMD, "ceemdan": DenoiseMethod.CEEMDAN,
            "savgol": DenoiseMethod.SAVGOL,
            "wavelet_packet": DenoiseMethod.WAVELET_PACKET,
            "ceemdan_wp": DenoiseMethod.CEEMDAN_WP,
            "eemd": DenoiseMethod.EEMD,
        }
        denoise_method = denoise_map.get(denoise, DenoiseMethod.NONE)

        # ── 运行全部方法 ──
        if method == "all":
            engine = DiagnosisEngine(
                strategy=DiagnosisStrategy.EXPERT,
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
            )
            engine._run_slow_methods = True
            result = await asyncio.to_thread(
                engine.analyze_all_methods, signal, sample_rate
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
            # 写入数据库缓存，供 DataView 读取
            _save_research_diagnosis(db, device_id, batch_index, channel, denoise, result)
            return {"code": 200, "data": _sanitize_for_json(response_data)}

        # ── 运行单个轴承方法 ──
        bearing_method_map = {
            "envelope": BearingMethod.ENVELOPE,
            "kurtogram": BearingMethod.KURTOGRAM,
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
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
            )
            result = await asyncio.to_thread(
                engine.analyze_bearing, signal, sample_rate
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
            )
            result = await asyncio.to_thread(
                engine.analyze_gear, signal, sample_rate
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

        # ── 运行单个行星齿轮箱方法 ──
        planetary_method_map = {
            "planetary_narrowband": "planetary_envelope_order_analysis",
            "planetary_fullband": "planetary_fullband_envelope_order_analysis",
            "planetary_tsa_envelope": "planetary_tsa_envelope_analysis",
            "planetary_hp_envelope": "planetary_hp_envelope_order_analysis",
            "planetary_vmd_demod": "planetary_vmd_demod_analysis",
            "planetary_sc_scoh": "planetary_sc_scoh_analysis",
            "planetary_msb": "planetary_msb_analysis",
        }
        if method in planetary_method_map:
            from app.services.diagnosis.gear.planetary_demod import (
                planetary_envelope_order_analysis,
                planetary_fullband_envelope_order_analysis,
                planetary_tsa_envelope_analysis,
                planetary_hp_envelope_order_analysis,
                planetary_vmd_demod_analysis,
                planetary_sc_scoh_analysis,
                planetary_msb_analysis,
            )
            func_name = planetary_method_map[method]
            func_map = {
                "planetary_envelope_order_analysis": planetary_envelope_order_analysis,
                "planetary_fullband_envelope_order_analysis": planetary_fullband_envelope_order_analysis,
                "planetary_tsa_envelope_analysis": planetary_tsa_envelope_analysis,
                "planetary_hp_envelope_order_analysis": planetary_hp_envelope_order_analysis,
                "planetary_vmd_demod_analysis": planetary_vmd_demod_analysis,
                "planetary_sc_scoh_analysis": planetary_sc_scoh_analysis,
                "planetary_msb_analysis": planetary_msb_analysis,
            }
            func = func_map[func_name]

            # 先估计转频
            from app.services.diagnosis.signal_utils import estimate_rot_freq_spectrum
            engine = DiagnosisEngine(
                denoise_method=denoise_method,
                bearing_params=bearing_params,
                gear_teeth=gear_teeth,
            )
            arr = engine.preprocess(signal)
            rot_freq, _, _, _, _ = engine._estimate_rot_freq(arr, sample_rate)

            result = await asyncio.to_thread(func, arr, sample_rate, rot_freq, gear_teeth)
            response_data = {
                "device_id": record.device_id,
                "batch_index": record.batch_index,
                "channel": record.channel,
                "channel_name": _get_channel_name(device, record.channel),
                "sample_rate": sample_rate,
                "method": method,
                "method_info": METHOD_INFO.get(method, {}),
                "rot_freq_hz": round(float(rot_freq), 3),
                "denoise": denoise,
                **result,
            }
            return {"code": 200, "data": _sanitize_for_json(response_data)}

        raise HTTPException(status_code=400, detail=f"未知分析方法: {method}")

    except HTTPException:
        raise
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
):
    """
    Run a user-triggered, multi-algorithm research diagnosis.

    This endpoint is intentionally separate from real-time monitoring because
    kurtogram, MED, TEO and TSA metrics are CPU-heavy.
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
    denoise_map = {
        "none": DenoiseMethod.NONE,
        "wavelet": DenoiseMethod.WAVELET,
        "vmd": DenoiseMethod.VMD,
        "wavelet_vmd": DenoiseMethod.WAVELET_VMD,
        "wavelet_lms": DenoiseMethod.WAVELET_LMS,
        "emd": DenoiseMethod.EMD,
        "ceemdan": DenoiseMethod.CEEMDAN,
        "savgol": DenoiseMethod.SAVGOL,
        "wavelet_packet": DenoiseMethod.WAVELET_PACKET,
        "ceemdan_wp": DenoiseMethod.CEEMDAN_WP,
        "eemd": DenoiseMethod.EEMD,
    }

    try:
        sample_rate = record.sample_rate or 25600
        signal = prepare_signal(record.data, detrend=detrend)

        bearing_params = {}
        gear_teeth = {}
        if device:
            bearing_params = _extract_device_param(device.bearing_params or {}, ("n", "d", "D", "alpha"))
            gear_teeth = _extract_device_param(device.gear_teeth or {}, ("input", "output"))

        engine = DiagnosisEngine(
            denoise_method=denoise_map.get(denoise, DenoiseMethod.NONE),
            bearing_params=bearing_params,
            gear_teeth=gear_teeth,
        )

        result = await asyncio.to_thread(
            engine.analyze_research_ensemble,
            signal,
            sample_rate,
            None,
            profile,
            max_seconds,
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
        # 写入数据库缓存，供 DataView 读取
        _save_research_diagnosis(db, device_id, batch_index, channel, denoise, result)
        return {"code": 200, "data": _sanitize_for_json(response_data)}
    except Exception as exc:
        logger.error("research analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"research analysis failed: {exc}")
