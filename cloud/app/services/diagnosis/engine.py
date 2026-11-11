"""
诊断策略调度器（Diagnosis Engine）

统一入口：前端通过 strategy / method 参数选择不同的诊断算法组合。
"""
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Any, Mapping

from .signal_utils import prepare_signal, linear_detrend, denoise_signal
from app.algorithms.core import Spectrum
from app.algorithms.mechanics import BearingGeometry, FixedAxisGearGeometry
from app.algorithms.pipelines.gear.fixed_axis import FixedAxisGearPipeline
from app.algorithms.bearing.analysis import analyze_envelope_spectrum
from app.algorithms.bearing.evaluation import evaluate_envelope
from app.algorithms.pipelines.bearing import BearingEnvelopePipeline
from app.algorithms.order import (
    AutomaticOrderPipeline,
    ConstantSpeedOrderPipeline,
    LocalSpeedEstimates,
    OrderAnalysis,
    OrderParameters,
    OrderSpectrum,
    ScalarSpeed,
    SpeedSearchRange,
    SpeedTrajectory,
)
from .advanced_bearing import ADVANCED_BEARING_METHODS, analyze_advanced_bearing
from .gear.planetary import analyze_planetary_gear, is_planetary_config
from app.algorithms.gear.planetary.types import PlanetaryBaseline, PlanetaryMomentHistory
from .features import compute_time_features, has_bearing_params, has_gear_params
from .adapters import adapt_method_result, combine_method_results, unavailable_result
from .domain import DiagnosisKey


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
    FILTER_BANK_SK = "filter_bank_sk"  # 二叉 IIR 滤波器组复谱峭度包络
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
        bearing_options: Optional[Dict] = None,
        planetary_baseline: Optional[PlanetaryBaseline] = None,
        planetary_history: Optional[PlanetaryMomentHistory] = None,
        diagnosis_key: Optional[DiagnosisKey] = None,
    ):
        # 兼容字符串传入
        self.strategy = strategy if isinstance(strategy, DiagnosisStrategy) else DiagnosisStrategy(strategy)
        self.bearing_method = bearing_method if isinstance(bearing_method, BearingMethod) else BearingMethod(bearing_method)
        self.gear_method = gear_method if isinstance(gear_method, GearMethod) else GearMethod(gear_method)
        self.denoise_method = denoise_method if isinstance(denoise_method, DenoiseMethod) else DenoiseMethod(denoise_method)
        self.bearing_params = bearing_params or {}
        self.gear_teeth = gear_teeth or {}
        self.bearing_options = dict(bearing_options or {})
        self.planetary_baseline = planetary_baseline
        self.planetary_history = planetary_history
        self.diagnosis_key = diagnosis_key or DiagnosisKey("interactive", 1, 1, self.denoise_method.value)

    def preprocess(self, signal: np.ndarray) -> np.ndarray:
        """去趋势后由唯一业务入口执行去噪；失败显式向上游传播。"""
        arr = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
        return denoise_signal(arr, self.denoise_method.value)

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

    def analyze_bearing(self, signal, fs, rot_freq=None, preprocess=True, max_freq=1000.0, _cached_order=None):
        """对象算法与业务状态适配的唯一公共轴承入口。"""
        if rot_freq is not None and (not np.isfinite(rot_freq) or rot_freq <= 0):
            raise ValueError("已知转频必须是有限正数；未知转频请传 None")
        try:
            raw = self._analyze_bearing(signal, fs, rot_freq, preprocess=preprocess, max_freq=max_freq, _cached_order=_cached_order)
            return adapt_method_result(raw, key=self.diagnosis_key, object_id="bearing",
                                       method=self.bearing_method.value, signal=signal,
                                       physical_parameters=has_bearing_params(self.bearing_params))
        except Exception as exc:
            return unavailable_result(str(exc), key=self.diagnosis_key, object_id="bearing",
                                      method=self.bearing_method.value, indeterminate=True)

    def _analyze_bearing(
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
        if rot_freq is not None and (not np.isfinite(rot_freq) or rot_freq <= 0):
            raise ValueError("已知转频必须是有限正数；未知转频请传 None")

        # 轴承包络与物理故障频率评估尚未消费连续相位；即使调用方已把轨迹摘要成
        # 标量 rot_freq，也必须以结构化缓存为准拒绝快速变速，不能绕过此前提。
        if (
            _cached_order is not None
            and _cached_order.status == "valid"
            and _cached_order.tracking_method == "varying_speed"
        ):
            raise ValueError("快速变速轴承物理频率评估尚未迁移连续相位接口，请先使用 /order")

        rot_std = self._order_speed_summary(_cached_order)[1] if _cached_order is not None else 0.0
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
        if self.bearing_method.value in ADVANCED_BEARING_METHODS:
            result = analyze_advanced_bearing(
                self.bearing_method.value, arr, fs, geometry, rot_freq, rot_std,
                options=self.bearing_options, max_freq=max_freq,
            )
            result.update(strategy=self.strategy.value, rot_freq_hz=rot_freq)
            return result
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
            # 模态分解入口由独立 #74 切片迁移。
            if self.bearing_method == BearingMethod.WP:
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
                key: value
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

    def _analyze_fixed_axis_gear(
        self,
        arr: np.ndarray,
        fs: float,
        order: OrderAnalysis,
        z_in: int,
    ) -> Dict[str, Any]:
        """定轴业务适配；数学与阈值均委托独立 Pipeline。"""
        geometry = FixedAxisGearGeometry(input_teeth=z_in) if z_in > 0 else None
        pipeline = FixedAxisGearPipeline(geometry=geometry)
        diagnosis = pipeline.run(
            arr,
            fs,
            order_analysis=order,
            include_tsa=self.gear_method == GearMethod.ADVANCED,
            history=None,  # 数据库尚无历史方差契约，NA4/NB4 明确不可判定。
        )
        analysis = diagnosis.analysis
        evaluation = diagnosis.evaluation
        metrics = {
            "fm0": analysis.fm0,
            "fm4": analysis.fm4,
            "m6a": analysis.m6a,
            "m8a": analysis.m8a,
            "na4": analysis.na4,
            "nb4": analysis.nb4,
            "car": analysis.car,
            "ser": analysis.sideband_analysis.ser,
        }
        metric_payload = {
            name: {
                "status": metric.status,
                "value": metric.value,
                "unit": metric.unit,
                "reason": metric.reason,
                "details": metric.details,
            }
            for name, metric in metrics.items()
        }

        def scalar(metric):
            return round(float(metric.value), 6) if metric.status == "evaluated" else None

        rot_frequency = analysis.rot_frequency_hz
        mesh_order = analysis.mesh_order
        mesh_frequency = (
            mesh_order * rot_frequency
            if mesh_order is not None and rot_frequency is not None else None
        )
        sidebands = [
            {
                "order": item.order,
                "spacing": 1.0,
                "order_low": item.lower_order,
                "order_high": item.upper_order,
                "amp_low": item.lower_amplitude,
                "amp_high": item.upper_amplitude,
                "asymmetry": item.asymmetry,
                "significant": item.order in evaluation.significant_sideband_orders,
            }
            for item in analysis.sideband_analysis.sidebands
        ]
        result = {
            "method": self.gear_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_frequency, 6) if rot_frequency is not None else None,
            "rot_freq_estimated_hz": round(rot_frequency, 6) if rot_frequency is not None else None,
            "rot_freq_std": analysis.rot_frequency_std_hz,
            "tracking_method": order.tracking_method,
            "mesh_freq_hz": round(mesh_frequency, 6) if mesh_frequency is not None else None,
            "mesh_order": mesh_order,
            "planet_count": 0,
            "is_planetary": False,
            "ser": scalar(analysis.sideband_analysis.ser),
            "sidebands": sidebands,
            "mesh_amp": analysis.sideband_analysis.mesh_amplitude,
            "fm0": scalar(analysis.fm0),
            "fm4": scalar(analysis.fm4),
            "m6a": scalar(analysis.m6a),
            "m8a": scalar(analysis.m8a),
            "na4": scalar(analysis.na4),
            "nb4": scalar(analysis.nb4),
            "car": scalar(analysis.car),
            "metrics": metric_payload,
            "analysis_status": evaluation.status,
            "evaluation": {
                "status": evaluation.status,
                "indicators": evaluation.indicators,
            },
            "fault_indicators": evaluation.indicators,
            "order_peak_concentration": analysis.order_statistics.peak_concentration,
            "order_kurtosis": analysis.order_statistics.kurtosis,
            "tsa_status": analysis.tsa_status,
            "tsa_reason": analysis.tsa_reason,
            "tsa_revolutions": analysis.tsa.synchronous.revolutions if analysis.tsa else None,
            "residual_rms": (
                float(np.sqrt(np.mean(analysis.tsa.residual_signal**2)))
                if analysis.tsa else None
            ),
        }
        # 与本次基础指标无关的小波包结果仅保留原始读数，不混入定轴阈值评估。
        try:
            from .wavelet_packet import compute_wavelet_packet_energy_entropy
            result["wavelet_packet_entropy"] = compute_wavelet_packet_energy_entropy(
                arr, fs, level=3, gear_mesh_freq=mesh_frequency,
            )
        except Exception:
            result["wavelet_packet_entropy"] = {"energy_entropy": 0.0, "normalized_entropy": 0.0}
        return result

    def analyze_gear(self, signal, fs, rot_freq=None, preprocess=True, _cached_order=None):
        if rot_freq is not None and (not np.isfinite(rot_freq) or rot_freq <= 0):
            raise ValueError("已知转频必须是有限正数；未知转频请传 None")
        try:
            raw = self._analyze_gear(signal, fs, rot_freq, preprocess, _cached_order)
            return adapt_method_result(raw, key=self.diagnosis_key, object_id="gear",
                                       method="planetary_gear" if is_planetary_config(self.gear_teeth) else self.gear_method.value,
                                       signal=signal, physical_parameters=has_gear_params(self.gear_teeth))
        except Exception as exc:
            return unavailable_result(str(exc), key=self.diagnosis_key, object_id="gear",
                                      method="planetary_gear" if is_planetary_config(self.gear_teeth) else self.gear_method.value,
                                      indeterminate=True)

    def _analyze_gear(
        self, signal: np.ndarray, fs: float, rot_freq: Optional[float] = None,
        preprocess: bool = True, _cached_order: Optional[OrderAnalysis] = None,
    ) -> Dict[str, Any]:
        """按机械对象分派；行星结果的表示、指标和评估由同一个 Pipeline 产生。"""
        arr = self.preprocess(signal) if preprocess else np.asarray(signal, dtype=np.float64)
        analysis = _cached_order
        if analysis is None:
            raw_for_speed = prepare_signal(np.asarray(signal, dtype=np.float64), detrend=True)
            analysis = self._analyze_order(arr, fs, rot_freq=rot_freq, estimation_signal=raw_for_speed)
        if is_planetary_config(self.gear_teeth):
            return analyze_planetary_gear(
                arr, fs, self.gear_teeth, order_analysis=analysis,
                include_tsa=self.gear_method == GearMethod.ADVANCED,
                baseline=self.planetary_baseline, history=self.planetary_history,
            )
        if analysis.status != "valid" or analysis.spectrum is None:
            raise ValueError(analysis.reason or "转频与阶次谱不可判定")
        z_in = int(float(self.gear_teeth.get("input") or 0)) if self.gear_teeth else 0
        return self._analyze_fixed_axis_gear(arr, fs, analysis, z_in)

    def analyze_comprehensive(self, signal, fs, rot_freq=None, skip_bearing=False, skip_gear=False):
        """与全方法和后台入口共用同一证据组合与状态生成器。"""
        bearing = self.analyze_bearing(signal, fs, rot_freq) if not skip_bearing and (self.bearing_params or not self.gear_teeth) else {}
        gear = self.analyze_gear(signal, fs, rot_freq) if not skip_gear and (self.gear_teeth or not self.bearing_params) else {}
        results = {name: value for name, value in (("bearing", bearing), ("gear", gear)) if value}
        return {**combine_method_results(results), "bearing": bearing, "gear": gear,
                "time_features": compute_time_features(np.asarray(signal)), "rot_freq_hz": rot_freq}

    def analyze_research_ensemble(self, signal, fs, rot_freq=None, profile="runtime", max_seconds=5.0):
        from .ensemble import run_research_ensemble
        return run_research_ensemble(
            signal, fs, bearing_params=self.bearing_params, gear_teeth=self.gear_teeth,
            denoise_method=self.denoise_method.value, rot_freq=rot_freq,
            profile=profile, max_seconds=max_seconds, bearing_options=self.bearing_options,
            diagnosis_key=self.diagnosis_key,
        )

    def analyze_all_methods(self, signal, fs, rot_freq=None, skip_bearing=False, skip_gear=False):
        from .ensemble import run_research_ensemble
        return run_research_ensemble(
            signal, fs, bearing_params={} if skip_bearing else self.bearing_params,
            gear_teeth={} if skip_gear else self.gear_teeth, denoise_method=self.denoise_method.value,
            rot_freq=rot_freq, profile="exhaustive", bearing_options=self.bearing_options,
            diagnosis_key=self.diagnosis_key,
        )
