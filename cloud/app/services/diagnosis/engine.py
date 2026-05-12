"""
诊断策略调度器（Diagnosis Engine）

统一入口：前端通过 strategy / method 参数选择不同的诊断算法组合。
"""
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Any

from .signal_utils import (
    prepare_signal,
    compute_fft_spectrum,
    estimate_rot_freq_spectrum as _estimate_rot_freq_simple,
)
from .order_tracking import (
    _compute_order_spectrum_multi_frame,
    _compute_order_spectrum_varying_speed,
    _compute_order_spectrum,
)
from .bearing import (
    envelope_analysis,
    fast_kurtogram,
    cpw_envelope_analysis,
    med_envelope_analysis,
)
from .gear import (
    compute_fm0_order,
    compute_car,
    compute_fm4,
    compute_m6a,
    compute_m8a,
    compute_ser_order,
    analyze_sidebands_order,
    _evaluate_gear_faults,
)
from .preprocessing import wavelet_denoise
from .vmd_denoise import vmd_denoise
from .features import (
    compute_time_features,
    compute_fft_features,
    compute_envelope_features,
)
from .signal_utils import highpass_filter
from .health_score import _compute_health_score
from .recommendation import (
    _generate_recommendation,
    _generate_recommendation_all,
    _summarize_all_methods,
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


class GearMethod(str, Enum):
    """齿轮诊断方法"""
    STANDARD = "standard"           # 标准边频带分析 + SER
    ADVANCED = "advanced"           # FM0/FM4/NA4 + SER + CAR


class DenoiseMethod(str, Enum):
    """预处理方法"""
    NONE = "none"                   # 无预处理
    WAVELET = "wavelet"             # 小波阈值去噪
    VMD = "vmd"                     # VMD 变分模态分解降噪


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
        """根据配置执行预处理"""
        arr = np.array(signal, dtype=np.float64)
        if self.denoise_method == DenoiseMethod.WAVELET:
            return wavelet_denoise(arr, wavelet="db8")
        elif self.denoise_method == DenoiseMethod.VMD:
            return vmd_denoise(arr, K=5, alpha=2000)
        return arr

    def _estimate_rot_freq(self, signal: np.ndarray, fs: float) -> float:
        """
        使用与阶次追踪（/order 端点）相同的算法估计转频。
        优先多帧平均；若转速波动剧烈（CV > 10%），自动降级到变速跟踪。
        """
        try:
            _, _, rot_freq, rot_std = _compute_order_spectrum_multi_frame(
                signal, fs, samples_per_rev=1024, max_order=50
            )
            if rot_freq > 0 and (rot_std / rot_freq) > 0.10:
                _, _, rot_freq, rot_std = _compute_order_spectrum_varying_speed(
                    signal, fs, samples_per_rev=1024, max_order=50
                )
            return float(rot_freq)
        except Exception:
            return float(_estimate_rot_freq_simple(signal, fs))

    def analyze_bearing(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        preprocess: bool = True,
    ) -> Dict[str, Any]:
        """
        轴承诊断分析

        Returns:
            {
                "method": str,
                "envelope_freq": List[float],
                "envelope_amp": List[float],
                "features": Dict,
                "fault_indicators": Dict,
            }
        """
        arr = self.preprocess(signal) if preprocess else np.array(signal, dtype=np.float64) if preprocess else np.array(signal, dtype=np.float64)

        if rot_freq is None:
            rot_freq = self._estimate_rot_freq(arr, fs)

        # 选择轴承诊断方法
        if self.bearing_method == BearingMethod.KURTOGRAM:
            result = fast_kurtogram(arr, fs)
        elif self.bearing_method == BearingMethod.CPW:
            # CPW 需要齿轮/轴频作为 comb_frequencies
            comb_freqs = []
            if self.gear_teeth:
                z_in = (self.gear_teeth.get("input") or 0) if self.gear_teeth else 0
                if z_in > 0 and rot_freq is not None and rot_freq > 0:
                    comb_freqs.append(rot_freq * z_in)
            if rot_freq is not None and rot_freq > 0:
                comb_freqs.append(rot_freq)
            result = cpw_envelope_analysis(arr, fs, comb_frequencies=comb_freqs)
        elif self.bearing_method == BearingMethod.MED:
            result = med_envelope_analysis(arr, fs)
        else:  # ENVELOPE
            result = envelope_analysis(arr, fs)

        # 提取包络域特征
        env_features = compute_envelope_features(
            arr, fs,
            bearing_params=self.bearing_params,
            rot_freq=rot_freq,
        )

        # 故障指示器：判断哪些轴承特征频率显著
        indicators = _evaluate_bearing_faults(
            self.bearing_params,
            result.get("envelope_freq", []),
            result.get("envelope_amp", []),
            rot_freq,
        )

        return {
            "method": self.bearing_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3),
            **{k: v for k, v in result.items() if k != "method"},
            "features": env_features,
            "fault_indicators": indicators,
        }

    def analyze_gear(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
        preprocess: bool = True,
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
        arr = self.preprocess(signal)

        order_axis = None
        order_spectrum = None
        rot_freq_used = rot_freq
        rot_std = 0.0

        if rot_freq_used is None:
            try:
                order_axis, order_spectrum, rot_freq_used, rot_std = _compute_order_spectrum_multi_frame(
                    arr, fs, samples_per_rev=1024, max_order=50
                )
                if rot_freq_used > 0 and (rot_std / rot_freq_used) > 0.10:
                    order_axis, order_spectrum, rot_freq_used, rot_std = _compute_order_spectrum_varying_speed(
                        arr, fs, samples_per_rev=1024, max_order=50
                    )
            except Exception:
                rot_freq_used = _estimate_rot_freq_simple(arr, fs)
                order_axis, order_spectrum = _compute_order_spectrum(arr, fs, rot_freq_used, samples_per_rev=1024)
                rot_std = 0.0
        else:
            order_axis, order_spectrum = _compute_order_spectrum(arr, fs, rot_freq_used, samples_per_rev=1024)

        rot_freq = float(rot_freq_used)

        z_in = int(float(self.gear_teeth.get("input") or 0)) if self.gear_teeth else 0
        mesh_freq = rot_freq * z_in if z_in > 0 else None
        mesh_order = float(z_in) if z_in > 0 else None

        result = {
            "method": self.gear_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3),
            "mesh_freq_hz": round(mesh_freq, 2) if mesh_freq else None,
            "mesh_order": round(mesh_order, 2) if mesh_order else None,
            "rot_freq_estimated_hz": round(rot_freq, 3),
            "rot_freq_std": round(rot_std, 4),
        }

        # 基于阶次谱的边频带分析
        if mesh_order and mesh_order > 0:
            sb_result = analyze_sidebands_order(order_axis, order_spectrum, mesh_order)
            result["sidebands"] = sb_result["sidebands"]
            result["ser"] = sb_result["ser"]
            result["mesh_amp"] = sb_result["mesh_amp"]
        else:
            result["sidebands"] = []
            result["ser"] = 0.0

        # 高级齿轮指标（也基于阶次谱）
        if self.gear_method == GearMethod.ADVANCED and mesh_order and mesh_order > 0:
            result["fm0"] = round(compute_fm0_order(arr, order_axis, order_spectrum, mesh_order), 4)
            result["car"] = round(compute_car(arr, fs, rot_freq), 4)

            # 差分信号（简化版：用高通滤波近似）
            diff_approx = highpass_filter(arr, fs, mesh_freq * 0.5)
            result["fm4"] = round(compute_fm4(diff_approx), 4)
            result["m6a"] = round(compute_m6a(diff_approx), 4)
            result["m8a"] = round(compute_m8a(diff_approx), 4)

            # 边频带能量比 SER（基于阶次谱）
            result["ser"] = round(compute_ser_order(order_axis, order_spectrum, mesh_order), 4)

        # 故障指示器
        indicators = _evaluate_gear_faults(result)
        result["fault_indicators"] = indicators

        return result

    def analyze_comprehensive(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        综合分析（轴承 + 齿轮 + 时域特征）

        Returns:
            {
                "health_score": int,
                "status": str,
                "bearing": Dict,
                "gear": Dict,
                "time_features": Dict,
                "recommendation": str,
            }
        """
        arr = self.preprocess(signal)

        if rot_freq is None:
            rot_freq = self._estimate_rot_freq(arr, fs)

        # 时域特征
        time_features = compute_time_features(arr)

        # 轴承分析（避免重复预处理）
        bearing_result = self.analyze_bearing(arr, fs, rot_freq, preprocess=False)

        # 齿轮分析（避免重复预处理）
        gear_result = self.analyze_gear(arr, fs, rot_freq, preprocess=False)

        # 综合健康度评分
        health_score, status = _compute_health_score(
            self.gear_teeth,
            time_features, bearing_result, gear_result
        )

        return {
            "health_score": health_score,
            "status": status,
            "bearing": bearing_result,
            "gear": gear_result,
            "time_features": time_features,
            "recommendation": _generate_recommendation(bearing_result, gear_result, status),
        }

    def analyze_all_methods(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
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

        if rot_freq is None:
            rot_freq = self._estimate_rot_freq(arr, fs)

        # 保存原始方法配置
        original_bearing = self.bearing_method
        original_gear = self.gear_method

        # 运行所有轴承诊断方法
        bearing_results = {}
        for method in BearingMethod:
            self.bearing_method = method
            try:
                result = self.analyze_bearing(arr, fs, rot_freq)
                bearing_results[method.value] = result
            except Exception as e:
                bearing_results[method.value] = {"error": str(e)}

        # 运行所有齿轮诊断方法
        gear_results = {}
        for method in GearMethod:
            self.gear_method = method
            try:
                result = self.analyze_gear(arr, fs, rot_freq)
                gear_results[method.value] = result
            except Exception as e:
                gear_results[method.value] = {"error": str(e)}

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
        health_score, status = _compute_health_score(
            self.gear_teeth,
            time_features,
            bearing_results.get(BearingMethod.ENVELOPE.value, {}),
            gear_results.get(GearMethod.STANDARD.value, {}),
        )

        # 生成各方法检出结论汇总
        summary = _summarize_all_methods(bearing_results, gear_results)

        return {
            "health_score": health_score,
            "status": status,
            "rot_freq_hz": round(rot_freq, 3),
            "time_features": time_features,
            "bearing_results": bearing_results,
            "gear_results": gear_results,
            "summary": summary,
            "recommendation": _generate_recommendation_all(bearing_results, gear_results, status),
        }


def _evaluate_bearing_faults(
    bearing_params: Optional[Dict],
    env_freq: List[float],
    env_amp: List[float],
    rot_freq: float,
) -> Dict[str, Any]:
    """评估轴承故障指示器"""
    if not bearing_params or not env_freq or not env_amp:
        return {}

    freq_arr = np.array(env_freq)
    amp_arr = np.array(env_amp)

    # 计算轴承特征频率
    n_balls = int(float(bearing_params.get("n") or 0))
    d = float(bearing_params.get("d") or 0)
    D = float(bearing_params.get("D") or 0)
    alpha = np.radians(float(bearing_params.get("alpha") or 0))

    if n_balls <= 0 or d <= 0 or D <= 0:
        return {}

    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a

    freqs = {
        "BPFO": (n_balls / 2.0) * rot_freq * (1 - dd),
        "BPFI": (n_balls / 2.0) * rot_freq * (1 + dd),
        "BSF": (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
        "FTF": 0.5 * rot_freq * (1 - dd),
    }

    indicators = {}
    for name, f_hz in freqs.items():
        # 容差带 ±3%
        tol = f_hz * 0.03
        mask = np.abs(freq_arr - f_hz) <= tol
        if np.any(mask):
            peak_idx = np.argmax(amp_arr[mask])
            actual_idx = np.where(mask)[0][peak_idx]
            peak_amp = float(amp_arr[actual_idx])
            background = np.median(amp_arr)
            snr = peak_amp / background if background > 0 else 0.0

            indicators[name] = {
                "theory_hz": round(f_hz, 2),
                "detected_hz": round(float(freq_arr[actual_idx]), 2),
                "peak_amp": round(peak_amp, 6),
                "snr": round(snr, 2),
                "significant": snr > 3.0,
            }
        else:
            indicators[name] = {
                "theory_hz": round(f_hz, 2),
                "detected_hz": None,
                "peak_amp": 0.0,
                "snr": 0.0,
                "significant": False,
            }

    return indicators
