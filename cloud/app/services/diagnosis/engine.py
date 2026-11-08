"""
诊断策略调度器（Diagnosis Engine）

统一入口：前端通过 strategy / method 参数选择不同的诊断算法组合。
"""
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Any, Mapping

from .signal_utils import (
    prepare_signal, linear_detrend,
    compute_fft_spectrum,
    highpass_filter,
)
from app.algorithms.core import Spectrum
from app.algorithms.mechanics import BearingGeometry
from app.algorithms.bearing.analysis import analyze_envelope_spectrum
from app.algorithms.bearing.evaluation import evaluate_envelope
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.algorithms.order import (
    AutomaticOrderPipeline,
    ConstantSpeedOrderPipeline,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    ScalarSpeed,
    SpeedSearchRange,
    SpeedTrajectory,
    resample_constant_speed,
)
from .bearing import (
    fast_kurtogram,
    cpw_envelope_analysis,
    med_envelope_analysis,
    teager_envelope_analysis,
    spectral_kurtosis_envelope_analysis,
)
from .bearing_cyclostationary import bearing_sc_scoh_analysis
from .gear import (
    compute_fm0_order,
    compute_tsa_residual_order,
    compute_car,
    compute_fm4,
    compute_m6a,
    compute_m8a,
    compute_ser_order,
    analyze_sidebands_order,
    analyze_sidebands_zoom_fft,
    _evaluate_gear_faults,
)
from .gear.planetary_demod import (
    planetary_envelope_order_analysis,
    planetary_fullband_envelope_order_analysis,
    planetary_vmd_demod_analysis,
    planetary_tsa_envelope_analysis,
    planetary_hp_envelope_order_analysis,
    evaluate_planetary_demod_results,
)
from .preprocessing import wavelet_denoise
from .vmd_denoise import vmd_denoise
from .features import (
    compute_time_features,
    compute_fft_features,
)
from .health_score import _compute_health_score
from .recommendation import (
    _generate_recommendation,
    _generate_recommendation_all,
    _summarize_all_methods,
)


def bearing_geometry_from_config(values: Optional[Mapping]) -> Optional[BearingGeometry]:
    """业务配置适配：缺失表示未配置，畸形配置显式报错。"""
    if values is None or values == {}:
        return None
    if not isinstance(values, Mapping):
        raise ValueError("轴承参数必须是字典或 None")
    required = ("n", "d", "D")
    if any(key not in values or values[key] is None for key in required):
        raise ValueError("轴承参数 n、d、D 必须完整配置")
    raw_count = values["n"]
    if isinstance(raw_count, bool):
        raise ValueError("滚动体数量必须是整数")
    try:
        count = float(raw_count)
        if not np.isfinite(count) or not count.is_integer():
            raise ValueError("滚动体数量必须是整数")
        roller_diameter = float(values["d"])
        pitch_diameter = float(values["D"])
        alpha = float(values.get("alpha") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"轴承参数格式错误: {exc}") from exc
    return BearingGeometry(
        roller_count=int(count),
        roller_diameter=roller_diameter,
        pitch_diameter=pitch_diameter,
        contact_angle_deg=alpha,
    )


class DiagnosisStrategy(str, Enum):
    """诊断策略枚举"""
    STANDARD = "standard"           # 标准分析（包络+FFT+阶次）
    ADVANCED = "advanced"           # 高级分析（Kurtogram+CPW+MED）
    EXPERT = "expert"               # 专家模式（全算法+决策融合）


class BearingMethod(str, Enum):
    """轴承诊断方法"""
    ENVELOPE = "envelope"           # 标准包络分析
    KURTOGRAM = "kurtogram"         # Fast Kurtogram 自适应包络
    CPW = "cpw"                     # CPW 预白化 + 包络
    MED = "med"                     # MED 增强 + 包络
    TEAGER = "teager"               # Teager 能量算子 + 包络
    SPECTRAL_KURTOSIS = "spectral_kurtosis"  # 自适应谱峭度重加权包络
    SC_SCOH = "sc_scoh"             # 轴承谱相关/谱相干（循环平稳分析）
    MCKD = "mckd"                   # 最大相关峭度解卷积 + 包络
    WP = "wp"                           # 小波包轴承诊断
    DWT = "dwt"                         # DWT敏感层轴承诊断
    EMD_ENVELOPE = "emd_envelope"       # EMD敏感IMF轴承诊断
    CEEMDAN_ENVELOPE = "ceemdan_envelope" # CEEMDAN敏感IMF轴承诊断
    VMD_ENVELOPE = "vmd_envelope"       # VMD敏感模态轴承诊断


class GearMethod(str, Enum):
    """齿轮诊断方法"""
    STANDARD = "standard"           # 标准边频带分析 + SER
    ADVANCED = "advanced"           # FM0/FM4/NA4 + SER + CAR


class DenoiseMethod(str, Enum):
    """预处理方法"""
    NONE = "none"                   # 无预处理
    WAVELET = "wavelet"             # 小波阈值去噪
    VMD = "vmd"                     # VMD 变分模态分解降噪
    WAVELET_VMD = "wavelet_vmd"     # 小波+VMD 级联联合降噪
    WAVELET_LMS = "wavelet_lms"     # 小波+LMS 级联联合降噪
    EMD = "emd"                     # 经验模态分解降噪
    CEEMDAN = "ceemdan"             # 完备集成经验模态分解降噪
    SAVGOL = "savgol"               # Savitzky-Golay 多项式平滑
    WAVELET_PACKET = "wavelet_packet"  # 小波包能量阈值降噪
    CEEMDAN_WP = "ceemdan_wp"          # CEEMDAN+小波包级联降噪
    EEMD = "eemd"                      # 集成经验模态分解降噪


class DiagnosisEngine:
    """
    故障诊断引擎

    支持设备级默认策略 + 前端临时覆盖。
    """

    def __init__(
        self,
        strategy = DiagnosisStrategy.STANDARD,
        bearing_method = BearingMethod.ENVELOPE,
        gear_method = GearMethod.STANDARD,
        denoise_method = DenoiseMethod.NONE,
        bearing_params: Optional[Dict] = None,
        gear_teeth: Optional[Dict] = None,
    ):
        # 兼容字符串传入
        self.strategy = strategy if isinstance(strategy, DiagnosisStrategy) else DiagnosisStrategy(strategy)
        self.bearing_method = bearing_method if isinstance(bearing_method, BearingMethod) else BearingMethod(bearing_method)
        self.gear_method = gear_method if isinstance(gear_method, GearMethod) else GearMethod(gear_method)
        self.denoise_method = denoise_method if isinstance(denoise_method, DenoiseMethod) else DenoiseMethod(denoise_method)
        self.bearing_params = bearing_params or {}
        self.gear_teeth = gear_teeth or {}

    def preprocess(self, signal: np.ndarray) -> np.ndarray:
        """去直流 + 线性去趋势 + 可选去噪（所有诊断路径统一入口）"""
        arr = prepare_signal(np.array(signal, dtype=np.float64), detrend=True)
        if self.denoise_method == DenoiseMethod.WAVELET:
            return wavelet_denoise(arr, wavelet="db8")
        elif self.denoise_method == DenoiseMethod.VMD:
            return vmd_denoise(arr, K=5, alpha=2000)
        elif self.denoise_method == DenoiseMethod.WAVELET_VMD:
            from .preprocessing import cascade_wavelet_vmd
            result, _ = cascade_wavelet_vmd(arr)
            return result
        elif self.denoise_method == DenoiseMethod.WAVELET_LMS:
            from .preprocessing import cascade_wavelet_lms
            result, _ = cascade_wavelet_lms(arr)
            return result
        elif self.denoise_method == DenoiseMethod.EMD:
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="emd")
            return result
        elif self.denoise_method == DenoiseMethod.CEEMDAN:
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="ceemdan")
            return result
        elif self.denoise_method == DenoiseMethod.SAVGOL:
            from .savgol_denoise import sg_denoise
            result, _ = sg_denoise(arr)
            return result
        elif self.denoise_method == DenoiseMethod.WAVELET_PACKET:
            from .wavelet_packet import wavelet_packet_denoise
            result, _ = wavelet_packet_denoise(arr)
            return result
        elif self.denoise_method == DenoiseMethod.CEEMDAN_WP:
            from .emd_denoise import emd_denoise
            from .wavelet_packet import wavelet_packet_denoise
            step1, _ = emd_denoise(arr, method="ceemdan")
            step2, _ = wavelet_packet_denoise(step1)
            return step2
        elif self.denoise_method == DenoiseMethod.EEMD:
            from .emd_denoise import emd_denoise
            result, _ = emd_denoise(arr, method="eemd")
            return result
        return arr

    @staticmethod
    def _order_speed_summary(analysis: OrderAnalysis) -> tuple[Optional[float], float]:
        """只为旧标量调用方摘要速度，不把局部序列或轨迹伪装成恒速输入。"""
        if analysis.status != "valid":
            return None, 0.0
        if isinstance(analysis.speed, ScalarSpeed):
            return float(analysis.speed.frequency_hz), 0.0
        if isinstance(analysis.speed, LocalSpeedEstimates):
            return analysis.speed.median_hz, analysis.speed.std_hz
        if isinstance(analysis.speed, SpeedTrajectory):
            return (
                float(np.median(analysis.speed.frequency_hz)),
                float(np.std(analysis.speed.frequency_hz)),
            )
        raise TypeError("未知转速表示")

    def _analyze_order(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        estimation_signal: Optional[np.ndarray] = None,
    ) -> OrderAnalysis:
        """转速/阶次统一入口；估计信号与故障增强信号显式分离。"""
        parameters = OrderParameters(samples_per_revolution=1024, max_order=50)
        if rot_freq is not None:
            if not np.isfinite(rot_freq) or rot_freq <= 0:
                raise ValueError("已知转频必须是有限正数；未知转频请传 None")
            return ConstantSpeedOrderPipeline(parameters).run(
                signal, fs, ScalarSpeed(float(rot_freq), "caller_supplied"),
            )
        return AutomaticOrderPipeline(parameters=parameters).run(
            signal, fs, estimation_signal=estimation_signal,
        )

    def _estimate_rot_freq(self, signal: np.ndarray, fs: float):
        """旧 tuple 适配；不可判定返回 None，不再回退到 10 Hz。"""
        analysis = self._analyze_order(signal, fs)
        rot_freq, rot_std = self._order_speed_summary(analysis)
        if analysis.status != "valid" or analysis.spectrum is None:
            return None, np.array([]), np.array([]), "indeterminate", 0.0
        return (
            rot_freq,
            analysis.spectrum.order_bins,
            analysis.spectrum.amplitude,
            analysis.tracking_method,
            rot_std,
        )

    def analyze_bearing(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        preprocess: bool = True,
        max_freq: float = 1000.0,
        _cached_order: Optional[OrderAnalysis] = None,
    ) -> Dict[str, Any]:
        """
        轴承诊断分析

        返回结构化 spectrum、band、features 和 evaluation，不再返回旧包络数组字段。
        """
        arr = self.preprocess(signal) if preprocess else np.array(signal, dtype=np.float64)

        # 轴承包络与物理故障频率评估尚未消费连续相位；即使调用方已把轨迹摘要成
        # 标量 rot_freq，也必须以结构化缓存为准拒绝快速变速，不能绕过此前提。
        if (
            _cached_order is not None
            and _cached_order.status == "valid"
            and _cached_order.tracking_method == "varying_speed"
        ):
            raise ValueError("快速变速轴承物理频率评估尚未迁移连续相位接口，请先使用 /order")

        rot_std = 0.0
        if rot_freq is None:
            # 转速估计使用未做故障增强的线性去趋势信号；阶次/诊断仍可使用显式去噪结果。
            if _cached_order is None:
                raw_for_speed = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
                analysis = self._analyze_order(arr, fs, estimation_signal=raw_for_speed)
            else:
                analysis = _cached_order
            if analysis.status == "valid" and analysis.tracking_method == "varying_speed":
                raise ValueError("快速变速轴承物理频率评估尚未迁移连续相位接口，请先使用 /order")
            rot_freq, rot_std = self._order_speed_summary(analysis)
            # 包络本身不是快速变速补偿算法；std 仅用于故障频率搜索容差。

        # 变速工况：转速变异 > 10% 时对信号线性去趋势
        if rot_freq is not None and rot_freq > 0 and rot_std / rot_freq > 0.10:
            arr = linear_detrend(arr)

        geometry = bearing_geometry_from_config(self.bearing_params)
        if self.bearing_method == BearingMethod.ENVELOPE:
            pipeline = BearingEnvelopePipeline(geometry=geometry)
            diagnosis = pipeline.run(
                arr,
                fs,
                rot_frequency_hz=rot_freq,
                rot_frequency_std_hz=rot_std,
            )
            representation = diagnosis.analysis.representation
            analysis = diagnosis.analysis.envelope_analysis
            evaluation = diagnosis.evaluation
            metadata = {}
        else:
            # 其他方法仍保留各自的选带/增强流程，但共用同一指标和评估实现。
            if self.bearing_method == BearingMethod.KURTOGRAM:
                result = fast_kurtogram(arr, fs)
            elif self.bearing_method == BearingMethod.CPW:
                comb_freqs = []
                if self.gear_teeth:
                    z_in = (self.gear_teeth.get("input") or 0) if self.gear_teeth else 0
                    planet_count = (self.gear_teeth.get("planet_count") or self.gear_teeth.get("n_planets") or 0) if self.gear_teeth else 0
                    z_sun = (self.gear_teeth.get("sun") or 0) if self.gear_teeth else 0
                    z_ring = (self.gear_teeth.get("ring") or 0) if self.gear_teeth else 0
                    if z_in > 0 and rot_freq is not None and rot_freq > 0:
                        if planet_count >= 3 and z_sun > 0 and z_ring > 0:
                            comb_freqs.append(rot_freq * z_ring * z_sun / (z_sun + z_ring))
                        else:
                            comb_freqs.append(rot_freq * z_in)
                if rot_freq is not None and rot_freq > 0:
                    comb_freqs.append(rot_freq)
                result = cpw_envelope_analysis(arr, fs, comb_frequencies=comb_freqs)
            elif self.bearing_method == BearingMethod.MED:
                result = med_envelope_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.TEAGER:
                if rot_freq and rot_freq > 0:
                    angle_domain, _ = resample_constant_speed(
                        arr, fs, ScalarSpeed(float(rot_freq), "caller_supplied"),
                        samples_per_revolution=256,
                    )
                    result = teager_envelope_analysis(
                        angle_domain.samples - angle_domain.samples.mean(), 256 * rot_freq,
                    )
                else:
                    result = teager_envelope_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.SPECTRAL_KURTOSIS:
                result = spectral_kurtosis_envelope_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.SC_SCOH:
                result = bearing_sc_scoh_analysis(
                    arr, fs, bearing_params=self.bearing_params, rot_freq=rot_freq
                )
            elif self.bearing_method == BearingMethod.MCKD:
                from .mckd import mckd_envelope_analysis
                result = mckd_envelope_analysis(
                    arr, fs, bearing_params=self.bearing_params, rot_freq=rot_freq
                )
            elif self.bearing_method == BearingMethod.WP:
                from .wavelet_bearing import wavelet_packet_bearing_analysis
                result = wavelet_packet_bearing_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.DWT:
                from .wavelet_bearing import dwt_bearing_analysis
                result = dwt_bearing_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.EMD_ENVELOPE:
                from .modality_bearing import emd_bearing_analysis
                result = emd_bearing_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.CEEMDAN_ENVELOPE:
                from .modality_bearing import ceemdan_bearing_analysis
                result = ceemdan_bearing_analysis(arr, fs)
            elif self.bearing_method == BearingMethod.VMD_ENVELOPE:
                from .modality_bearing import vmd_bearing_analysis
                result = vmd_bearing_analysis(arr, fs)
            else:
                raise ValueError(f"不支持的轴承方法: {self.bearing_method}")

            representation = result.get("representation")
            if representation is not None:
                spectrum = representation.spectrum
            else:
                frequencies = result.get("envelope_freq", [])
                amplitudes = result.get("envelope_amp", [])
                spectrum = None
                if len(frequencies) and len(amplitudes):
                    spectrum = Spectrum(
                        frequency_hz=np.asarray(frequencies, dtype=np.float64),
                        amplitude=np.asarray(amplitudes, dtype=np.float64),
                        scaling="unnormalized",
                    )
            if spectrum is None:
                analysis = None
                evaluation = None
            else:
                analysis = analyze_envelope_spectrum(
                    spectrum,
                    geometry=geometry,
                    rot_frequency_hz=rot_freq,
                    rot_frequency_std_hz=rot_std,
                )
                evaluation = evaluate_envelope(analysis)
            metadata = {
                ("sc_scoh_indicators" if key == "fault_indicators" else key): value
                for key, value in result.items()
                if key not in {"method", "representation", "envelope_freq", "envelope_amp"}
            }

        spectrum = analysis.spectrum if analysis else None
        display_spectrum = spectrum.truncated(max_freq) if spectrum else None
        return {
            "method": self.bearing_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3) if rot_freq is not None else None,
            "spectrum": {
                "frequency_hz": display_spectrum.frequency_hz.tolist(),
                "amplitude": display_spectrum.amplitude.tolist(),
                "amplitude_unit": display_spectrum.amplitude_unit,
                "scaling": display_spectrum.scaling,
            } if display_spectrum else None,
            "band": {
                "low_hz": representation.band.low_hz,
                "high_hz": representation.band.high_hz,
                "center_hz": representation.band.center_hz,
                "width_hz": representation.band.width_hz,
            } if representation else None,
            "envelope_low_pass_hz": representation.envelope_low_pass_hz if representation else None,
            **metadata,
            "features": analysis.features.as_dict() if analysis else {
                "spectral_power_proxy": 0.0,
                "spectral_power_unit": "input_signal^2",
            },
            "evaluation": {
                "status": evaluation.status if evaluation else "indeterminate",
                "indicators": evaluation.indicators if evaluation else {},
            },
        }

    def analyze_gear(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        preprocess: bool = True,
        _cached_oa: Optional[np.ndarray] = None,
        _cached_os: Optional[np.ndarray] = None,
        _cached_order: Optional[OrderAnalysis] = None,
    ) -> Dict[str, Any]:
        """
        齿轮诊断分析

        核心修改：所有频域齿轮特征（SER、边频带、FM0）均基于阶次谱计算，
        且转频估计与阶次追踪（/order 端点）完全一致，确保诊断明细中的
        rot_freq_hz 与阶次谱页面显示值相同。

        Returns:
            {
                "method": str,
                "ser": float,
                "sidebands": List[Dict],
                "features": Dict,
                "fault_indicators": Dict,
            }
        """
        arr = self.preprocess(signal) if preprocess else np.array(signal, dtype=np.float64)

        rot_freq_used = rot_freq
        rot_std = 0.0
        if _cached_order is not None:
            analysis = _cached_order
        elif _cached_oa is None or _cached_os is None:
            raw_for_speed = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
            analysis = self._analyze_order(
                arr, fs, rot_freq=rot_freq, estimation_signal=raw_for_speed,
            )
        else:
            # 旧数组缓存只允许由恒速/缓变标量调用方提供，不能表达快速变速补偿。
            if rot_freq is None or not np.isfinite(rot_freq) or rot_freq <= 0:
                raise ValueError("旧阶次数组缓存必须同时提供有效标量转频")
            analysis = None
            order_axis = _cached_oa
            order_spectrum = _cached_os

        if analysis is not None:
            if analysis.status != "valid" or analysis.spectrum is None:
                raise ValueError(analysis.reason or "转频与阶次谱不可判定")
            if analysis.tracking_method == "varying_speed":
                raise ValueError("快速变速阶次谱已由 /order 支持；齿轮/TSA/行星解调仍要求恒速或缓变标量转频")
            order_axis = analysis.spectrum.order_bins
            order_spectrum = analysis.spectrum.amplitude
            rot_freq_used, rot_std = self._order_speed_summary(analysis)
        if rot_freq_used is None:
            raise ValueError("齿轮诊断需要有效标量转频")

        rot_freq = float(rot_freq_used)

        z_in = int(float(self.gear_teeth.get("input") or 0)) if self.gear_teeth else 0
        z_sun = int(float(self.gear_teeth.get("sun") or 0)) if self.gear_teeth else 0
        z_ring = int(float(self.gear_teeth.get("ring") or 0)) if self.gear_teeth else 0
        z_planet = int(float(self.gear_teeth.get("planet") or 0)) if self.gear_teeth else 0

        # 行星齿轮箱参数（供 _evaluate_gear_faults 使用）
        planet_count = int(self.gear_teeth.get("planet_count") or self.gear_teeth.get("n_planets") or 0) if self.gear_teeth else 0

        # 兼容：若配置了行星轮数但无 "sun" 键，将 "input" 视为太阳轮齿数
        if planet_count >= 3 and z_sun <= 0 and z_in > 0:
            z_sun = z_in

        # 啮合阶次计算（相对于输入轴转频）
        # 定轴齿轮箱: mesh_order = z_in（啮合频率 = 转频 × 齿数）
        # 行星齿轮箱(ring固定, sun输入): mesh_order = Z_ring×Z_sun/(Z_sun+Z_ring)
        #   例: 100×28/(28+100) = 21.875 ≈ 175/8
        if planet_count >= 3 and z_sun > 0 and z_ring > 0:
            mesh_order = round(z_ring * z_sun / (z_sun + z_ring), 4)
        elif z_in > 0:
            mesh_order = float(z_in)
        else:
            mesh_order = None
        mesh_freq = rot_freq * mesh_order if mesh_order else None

        result = {
            "method": self.gear_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3) if rot_freq is not None else None,
            "mesh_freq_hz": round(mesh_freq, 2) if mesh_freq else None,
            "mesh_order": round(mesh_order, 4) if mesh_order else None,
            "rot_freq_estimated_hz": round(rot_freq, 3),
            "rot_freq_std": round(rot_std, 4),
            "planet_count": planet_count,
            "is_planetary": planet_count >= 3,
        }

        # 行星齿轮箱特征阶次（相对于太阳轮转频，ring固定架构）
        if planet_count >= 3 and z_sun > 0 and z_ring > 0:
            # carrier_order = Z_sun / (Z_sun + Z_ring)
            carrier_order = round(z_sun / (z_sun + z_ring), 4)
            # sun_fault_order = (Z_ring - Z_sun) × planet_count / (Z_sun + Z_ring)
            #   例: (100-28)×4/(28+100) = 72×4/128 = 2.25
            #   但文档给出 25/8=3.125，需确认...
            #   实际太阳轮故障频率 = Z_ring × f_carrier × planet_count/(Z_ring)
            #   → (Z_ring/(Z_sun+Z_ring)) × planet_count × f_sun = (100/128)×4×f_sun = 3.125 × f_sun ✅
            sun_fault_order = round(z_ring / (z_sun + z_ring) * planet_count, 4)
            planet_fault_order = round(z_ring / (z_sun + z_ring), 4)
            result["carrier_order"] = carrier_order
            result["sun_fault_order"] = sun_fault_order
            result["planet_fault_order"] = planet_fault_order

        # 基于阶次谱的边频带分析（需要齿轮参数）
        if mesh_order and mesh_order > 0:
            # 行星齿轮箱边频带间隔是 carrier_order，不是 1
            sb_spacing = 1.0
            if planet_count >= 3 and z_sun > 0 and z_ring > 0:
                sb_spacing = round(z_sun / (z_sun + z_ring), 4)
            sb_result = analyze_sidebands_order(order_axis, order_spectrum, mesh_order, n_sidebands=6, spacing=sb_spacing)
            result["sidebands"] = sb_result["sidebands"]
            result["ser"] = sb_result["ser"]
            result["mesh_amp"] = sb_result["mesh_amp"]
        else:
            result["sidebands"] = []
            result["ser"] = 0.0

        # 无齿轮参数时的阶次谱统计特征（始终计算，不依赖 mesh_order）
        if order_spectrum is not None and len(order_spectrum) > 0:
            ospec = np.array(order_spectrum)
            total_energy = float(np.sum(ospec ** 2)) + 1e-12
            # 能量集中度：前 5 阶 / 总能量
            sorted_amps = np.sort(ospec)[::-1]
            top5_energy = float(np.sum(sorted_amps[:5] ** 2))
            result["order_peak_concentration"] = round(top5_energy / total_energy, 4)
            # 阶次谱峭度
            ospec_norm = ospec / (np.mean(ospec) + 1e-12)
            kurt = float(np.mean(ospec_norm ** 4) / (np.mean(ospec_norm ** 2) ** 2 + 1e-12) - 2)
            result["order_kurtosis"] = round(kurt, 2)

        # CAR 不需要齿轮参数，始终计算
        try:
            result["car"] = round(compute_car(arr, fs, rot_freq), 4)
        except Exception:
            result["car"] = 0.0

        # 高级齿轮指标（也基于阶次谱，需要齿轮参数）
        if self.gear_method == GearMethod.ADVANCED and mesh_order and mesh_order > 0:
            tsa = compute_tsa_residual_order(arr, fs, rot_freq, samples_per_rev=1024)
            if tsa.get("valid"):
                result["tsa_revolutions"] = int(tsa.get("revolutions", 0))
                result["residual_rms"] = round(float(np.sqrt(np.mean(np.asarray(tsa["residual"]) ** 2))), 6)
                result["fm0"] = round(compute_fm0_order(tsa["tsa_signal"], order_axis, order_spectrum, mesh_order), 4)
                diff_signal = tsa["differential"]
            else:
                result["tsa_revolutions"] = 0
                result["fm0"] = round(compute_fm0_order(arr, order_axis, order_spectrum, mesh_order), 4)
                # TSA 无法形成时才退化为高通近似。
                # mesh_freq 可能为 None/0（rot_freq=0 时），需守卫
                hp_cutoff = (mesh_freq or 0) * 0.5
                if hp_cutoff > 0:
                    diff_signal = highpass_filter(arr, fs, hp_cutoff)
                else:
                    # 无有效截止频率时，差分信号 = 原信号去均值
                    diff_signal = arr - np.mean(arr)

            result["fm4"] = round(compute_fm4(diff_signal), 4)
            result["m6a"] = round(compute_m6a(diff_signal), 4)
            result["m8a"] = round(compute_m8a(diff_signal), 4)

            # 边频带能量比 SER（基于阶次谱）
            result["ser"] = round(compute_ser_order(order_axis, order_spectrum, mesh_order), 4)

        # 故障指示器
        indicators = _evaluate_gear_faults(result)

        # === 小波包能量熵（齿轮频带能量重分布检测） ===
        # 对齿轮故障引起的频带能量集中度变化敏感，
        # 不依赖行星箱参数，始终计算作为补充频域特征
        try:
            from .wavelet_packet import compute_wavelet_packet_energy_entropy
            wp_entropy = compute_wavelet_packet_energy_entropy(arr, fs, level=3, gear_mesh_freq=mesh_freq)
            result["wavelet_packet_entropy"] = wp_entropy
        except Exception:
            result["wavelet_packet_entropy"] = {"energy_entropy": 0.0, "normalized_entropy": 0.0}

        # === 行星齿轮箱专用解调分析 ===
        # 行星箱频域指标(SER/CAR/sideband)无区分力，需用解调方法突破
        if planet_count >= 3 and z_sun > 0 and z_ring > 0 and rot_freq > 0:
            gear_teeth_dict = {
                "sun": z_sun, "ring": z_ring, "planet": z_planet,
                "planet_count": planet_count,
            }
            # Level 2a: 窄带包络阶次分析
            try:
                narrowband_result = planetary_envelope_order_analysis(arr, fs, rot_freq, gear_teeth_dict)
                result["planetary_narrowband_demod"] = narrowband_result
            except Exception:
                narrowband_result = {"method": "planetary_envelope_order", "error": "exception"}
                result["planetary_narrowband_demod"] = narrowband_result

            # Level 2b: 全频带包络阶次分析
            try:
                fullband_result = planetary_fullband_envelope_order_analysis(arr, fs, rot_freq, gear_teeth_dict)
                result["planetary_fullband_demod"] = fullband_result
            except Exception:
                fullband_result = {"method": "planetary_fullband_envelope_order", "error": "exception"}
                result["planetary_fullband_demod"] = fullband_result

            # Level 2c: TSA残差包络阶次分析（残差峭度区分力=3.31，最有效）
            try:
                tsa_env_result = planetary_tsa_envelope_analysis(arr, fs, rot_freq, gear_teeth_dict)
                result["planetary_tsa_demod"] = tsa_env_result
            except Exception:
                tsa_env_result = {"method": "planetary_tsa_envelope", "error": "exception"}
                result["planetary_tsa_demod"] = tsa_env_result

            # Level 2d: 高通滤波包络阶次分析
            try:
                hp_env_result = planetary_hp_envelope_order_analysis(arr, fs, rot_freq, gear_teeth_dict)
                result["planetary_hp_demod"] = hp_env_result
            except Exception:
                hp_env_result = {"method": "planetary_hp_envelope_order", "error": "exception"}
                result["planetary_hp_demod"] = hp_env_result

            # Level 3: VMD幅频联合解调 🔴慢（后台分析默认跳过，仅full-analysis时启用）
            if getattr(self, '_run_slow_methods', False):
                try:
                    vmd_result = planetary_vmd_demod_analysis(arr, fs, rot_freq, gear_teeth_dict, max_K=5)
                    result["planetary_vmd_demod"] = vmd_result
                except Exception:
                    vmd_result = {"method": "planetary_vmd_demod", "error": "exception"}
                    result["planetary_vmd_demod"] = vmd_result
            else:
                vmd_result = {"method": "planetary_vmd_demod", "error": "skipped_slow_method"}

            # Level 4: SC/SCoh 谱相关/谱相干（仅full-analysis时启用）
            if getattr(self, '_run_slow_methods', False):
                try:
                    from .gear.planetary_demod import planetary_sc_scoh_analysis
                    sc_scoh_result = planetary_sc_scoh_analysis(arr, fs, rot_freq, gear_teeth_dict)
                    result["planetary_sc_scoh"] = sc_scoh_result
                except Exception:
                    sc_scoh_result = {"method": "planetary_sc_scoh", "error": "exception"}
                    result["planetary_sc_scoh"] = sc_scoh_result

            # Level 5: MSB 调制信号双谱（仅full-analysis时启用）
            if getattr(self, '_run_slow_methods', False):
                try:
                    from .gear.planetary_demod import planetary_msb_analysis
                    msb_result = planetary_msb_analysis(arr, fs, rot_freq, gear_teeth_dict)
                    result["planetary_msb"] = msb_result
                except Exception:
                    msb_result = {"method": "planetary_msb", "error": "exception"}
                    result["planetary_msb"] = msb_result

            # 综合评估 → 融合各方法的故障指示器
            planetary_indicators = evaluate_planetary_demod_results(
                narrowband_result, vmd_result
            )
            # 合入主 indicators（行星箱专用指标以 planetary_ 前缀区分）
            for k, v in planetary_indicators.items():
                indicators[k] = v

            # 全频带包络峭度（crack 核心区分指标）
            # 健康 fullband_env_kurt = 6.8~20.1，crack = 1.8~4.2
            # 方向：越低越严重（crack使包络冲击减弱），warning<5.0, critical<3.0
            # 合理性门控：fek<1.0 时不做判定（非齿轮数据或信号异常，防止轴承数据误触发）
            if isinstance(fullband_result, dict) and "error" not in fullband_result:
                fek = fullband_result.get("envelope_kurtosis")
                if fek is not None:
                    fek_f = float(fek)
                    valid_planetary = fek_f >= 1.0  # 最低合理值（crack下限1.8）
                    indicators["planetary_fullband_env_kurt"] = {
                        "value": round(fek_f, 4),
                        "warning": valid_planetary and fek_f < 5.0,
                        "critical": valid_planetary and fek_f < 3.0,
                    }

        result["fault_indicators"] = indicators

        return result

    def analyze_comprehensive(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        skip_bearing: bool = False,
        skip_gear: bool = False,
    ) -> Dict[str, Any]:
        """
        综合分析

        Args:
            skip_bearing: True=跳过轴承分析（无轴承参数时自动设置）
            skip_gear:    True=跳过齿轮分析（无齿轮参数时自动设置）
        """
        arr = self.preprocess(signal)

        cached_order: Optional[OrderAnalysis] = None
        if rot_freq is None:
            raw_for_speed = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
            cached_order = self._analyze_order(arr, fs, estimation_signal=raw_for_speed)
            rot_freq, rot_std = self._order_speed_summary(cached_order)

        time_features = compute_time_features(arr)

        # 轴承分析
        bearing_result = self.analyze_bearing(
            arr, fs, rot_freq, preprocess=False, _cached_order=cached_order,
        ) if not skip_bearing else {}

        # 齿轮分析
        gear_result = self.analyze_gear(arr, fs, rot_freq, preprocess=False,
                                        _cached_order=cached_order) if not skip_gear else {}

        health_score, status, _ = _compute_health_score(
            self.gear_teeth,
            time_features, bearing_result, gear_result
        )

        return {
            "health_score": health_score, "status": status,
            "bearing": bearing_result, "gear": gear_result,
            "time_features": time_features,
            "recommendation": _generate_recommendation(bearing_result, gear_result, status),
        }

    def analyze_research_ensemble(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        profile: str = "runtime",
        max_seconds: float = 5.0,
    ) -> Dict[str, Any]:
        """运行多算法集成诊断。runtime 用于后台自动诊断，exhaustive 用于网页手动重算法。"""
        from .ensemble import run_research_ensemble

        return run_research_ensemble(
            signal,
            fs,
            bearing_params=self.bearing_params,
            gear_teeth=self.gear_teeth,
            denoise_method=self.denoise_method.value,
            rot_freq=rot_freq,
            profile=profile,
            max_seconds=max_seconds,
        )

    def analyze_all_methods(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        skip_bearing: bool = False,
        skip_gear: bool = False,
    ) -> Dict[str, Any]:
        """
        全算法对比分析（运行所有轴承方法和所有齿轮方法）

        Returns:
            {
                "health_score": int,
                "status": str,
                "rot_freq_hz": float,
                "time_features": Dict,
                "bearing_results": Dict[str, Dict],   # key: method name
                "gear_results": Dict[str, Dict],      # key: method name
                "summary": Dict,                       # 各方法检出结论汇总
                "recommendation": str,
            }
        """
        arr = np.array(signal, dtype=np.float64)
        if self.denoise_method != DenoiseMethod.NONE:
            arr = self.preprocess(arr)

        order_analysis: Optional[OrderAnalysis] = None
        if rot_freq is None:
            raw_for_speed = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
            order_analysis = self._analyze_order(arr, fs, estimation_signal=raw_for_speed)
            rot_freq, _ = self._order_speed_summary(order_analysis)

        original_bearing = self.bearing_method
        original_gear = self.gear_method

        bearing_results = {}
        if not skip_bearing:
            for method in BearingMethod:
                self.bearing_method = method
                try:
                    bearing_results[method.value] = self.analyze_bearing(
                        arr, fs, rot_freq, _cached_order=order_analysis,
                    )
                except Exception as e:
                    bearing_results[method.value] = {"error": str(e)}

        gear_results = {}
        if not skip_gear:
            # full-analysis 模式：启用慢方法（VMD/SC/SCoh/MSB）
            self._run_slow_methods = True
            for method in GearMethod:
                self.gear_method = method
                try:
                    gear_results[method.value] = self.analyze_gear(
                        arr, fs, rot_freq, _cached_order=order_analysis,
                    )
                except Exception as e:
                    gear_results[method.value] = {"error": str(e)}
            self._run_slow_methods = False

        # 恢复原始配置
        self.bearing_method = original_bearing
        self.gear_method = original_gear

        # 时域特征
        time_features = compute_time_features(arr)

        # 综合评估：取所有方法中最差的健康状态
        all_health_scores = []
        all_statuses = []
        for br in bearing_results.values():
            if "health_score" in br:
                all_health_scores.append(br["health_score"])
            if "status" in br:
                all_statuses.append(br["status"])
        for gr in gear_results.values():
            if "health_score" in gr:
                all_health_scores.append(gr["health_score"])
            if "status" in gr:
                all_statuses.append(gr["status"])

        # 用默认的 bearing=包络, gear=标准 计算综合健康度
        base_health_score, status, _ = _compute_health_score(
            self.gear_teeth,
            time_features,
            bearing_results.get(BearingMethod.ENVELOPE.value, {}),
            gear_results.get(GearMethod.STANDARD.value, {}),
        )

        # 若其他方法检出更差结果，融合到综合评分：取 min(base, worst_other)
        # 避免其他方法检出故障但综合评分被单一方法掩盖
        health_score = base_health_score
        if all_health_scores:
            worst_other = min(all_health_scores)
            if worst_other < base_health_score:
                health_score = int(round((base_health_score + worst_other) / 2))
                # worst_other 比 base 低 20 分以上 → 状态升级
                # 同步调整 health_score 以保持一致性（status=warning→hs<85, critical→hs<60）
                if worst_other < base_health_score - 20:
                    if status == "normal":
                        status = "warning"
                        health_score = min(health_score, 84)
                    elif status == "warning":
                        status = "critical"
                        health_score = min(health_score, 59)

        # 生成各方法检出结论汇总
        summary = _summarize_all_methods(bearing_results, gear_results)

        return {
            "health_score": health_score,
            "status": status,
            "rot_freq_hz": round(rot_freq, 3) if rot_freq is not None else None,
            "time_features": time_features,
            "bearing_results": bearing_results,
            "gear_results": gear_results,
            "summary": summary,
            "recommendation": _generate_recommendation_all(bearing_results, gear_results, status),
        }
