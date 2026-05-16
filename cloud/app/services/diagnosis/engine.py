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
    TEAGER = "teager"               # Teager 能量算子 + 包络
    SPECTRAL_KURTOSIS = "spectral_kurtosis"  # 自适应谱峭度重加权包络
    SC_SCOH = "sc_scoh"             # 轴承谱相关/谱相干（循环平稳分析）


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
        """去直流 + 可选去噪，与 /order 端点的 prepare_signal 行为一致"""
        arr = np.array(signal, dtype=np.float64)
        arr = arr - np.mean(arr)  # 统一去直流（零均值化）
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
        return arr

    def _estimate_rot_freq(self, signal: np.ndarray, fs: float):
        """
        使用与阶次追踪（/order 端点）相同的算法估计转频。
        返回 (rot_freq, order_axis, order_spectrum, tracking_method_str)，供 gear 诊断复用。
        """
        try:
            oa, os_, rf, rsd = _compute_order_spectrum_multi_frame(
                signal, fs, samples_per_rev=1024, max_order=50
            )
            method = "multi_frame"
            if rf > 0 and (rsd / rf) > 0.10:
                oa, os_, rf, rsd = _compute_order_spectrum_varying_speed(
                    signal, fs, samples_per_rev=1024, max_order=50
                )
                method = "varying_speed"
            return float(rf), oa, os_, method
        except Exception:
            rf = float(_estimate_rot_freq_simple(signal, fs))
            oa, os_ = _compute_order_spectrum(signal, fs, rf, samples_per_rev=1024)
            return rf, oa, os_, "single_frame"

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
        arr = self.preprocess(signal) if preprocess else np.array(signal, dtype=np.float64)

        if rot_freq is None:
            rot_freq, _, _, _ = self._estimate_rot_freq(arr, fs)

        # 选择轴承诊断方法
        if self.bearing_method == BearingMethod.KURTOGRAM:
            result = fast_kurtogram(arr, fs)
        elif self.bearing_method == BearingMethod.CPW:
            # CPW 需要齿轮/轴频作为 comb_frequencies
            comb_freqs = []
            if self.gear_teeth:
                z_in = (self.gear_teeth.get("input") or 0) if self.gear_teeth else 0
                planet_count = (self.gear_teeth.get("planet_count") or 0) if self.gear_teeth else 0
                z_sun = (self.gear_teeth.get("sun") or 0) if self.gear_teeth else 0
                z_ring = (self.gear_teeth.get("ring") or 0) if self.gear_teeth else 0
                if z_in > 0 and rot_freq is not None and rot_freq > 0:
                    # 行星齿轮箱 mesh_freq = Z_ring×Z_sun/(Z_sun+Z_ring) × rot_freq
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
            result = teager_envelope_analysis(arr, fs)
        elif self.bearing_method == BearingMethod.SPECTRAL_KURTOSIS:
            result = spectral_kurtosis_envelope_analysis(arr, fs)
        elif self.bearing_method == BearingMethod.SC_SCOH:
            result = bearing_sc_scoh_analysis(
                arr, fs, bearing_params=self.bearing_params, rot_freq=rot_freq
            )
        else:  # ENVELOPE
            result = envelope_analysis(arr, fs)

        # 提取包络域特征（基于轴承方法已计算好的包络谱，不再独立重算）
        env_features = compute_envelope_features(
            result.get("envelope_freq", []),
            result.get("envelope_amp", []),
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
        _cached_oa: Optional[np.ndarray] = None,
        _cached_os: Optional[np.ndarray] = None,
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

        order_axis = _cached_oa
        order_spectrum = _cached_os
        rot_freq_used = rot_freq
        rot_std = 0.0

        # 若已有缓存的阶次谱（来自 _estimate_rot_freq 的多帧计算结果），直接复用
        if order_axis is not None and order_spectrum is not None:
            pass  # 复用缓存
        elif rot_freq_used is not None and rot_freq_used > 0:
            # 有已知转频，用窄范围多帧平均（与 /order 端点行为一致）
            freq_min = max(1.0, rot_freq_used * 0.7)
            freq_max = rot_freq_used * 1.3
            try:
                order_axis, order_spectrum, rot_freq_used, rot_std = _compute_order_spectrum_multi_frame(
                    arr, fs, freq_range=(freq_min, freq_max), samples_per_rev=1024, max_order=50
                )
            except Exception:
                order_axis, order_spectrum = _compute_order_spectrum(arr, fs, rot_freq_used, samples_per_rev=1024)
        else:
            # 无已知转频，多帧平均同时估计转频+计算阶次谱
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

        rot_freq = float(rot_freq_used)

        z_in = int(float(self.gear_teeth.get("input") or 0)) if self.gear_teeth else 0
        z_sun = int(float(self.gear_teeth.get("sun") or 0)) if self.gear_teeth else 0
        z_ring = int(float(self.gear_teeth.get("ring") or 0)) if self.gear_teeth else 0
        z_planet = int(float(self.gear_teeth.get("planet") or 0)) if self.gear_teeth else 0

        # 行星齿轮箱参数（供 _evaluate_gear_faults 使用）
        planet_count = int(self.gear_teeth.get("planet_count") or 0) if self.gear_teeth else 0

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
            "rot_freq_hz": round(rot_freq, 3),
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
                diff_signal = highpass_filter(arr, fs, mesh_freq * 0.5)

            result["fm4"] = round(compute_fm4(diff_signal), 4)
            result["m6a"] = round(compute_m6a(diff_signal), 4)
            result["m8a"] = round(compute_m8a(diff_signal), 4)

            # 边频带能量比 SER（基于阶次谱）
            result["ser"] = round(compute_ser_order(order_axis, order_spectrum, mesh_order), 4)

        # 故障指示器
        indicators = _evaluate_gear_faults(result)

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

        if rot_freq is None and not skip_gear:
            rot_freq, cached_oa, cached_os, _ = self._estimate_rot_freq(arr, fs)
        elif rot_freq is None:
            # 无齿轮分析且无转频 → 用简化估计
            try:
                rot_freq, _, _, _ = self._estimate_rot_freq(arr, fs)
            except Exception:
                rot_freq = 20.0
            cached_oa = cached_os = None
        else:
            cached_oa = cached_os = None

        time_features = compute_time_features(arr)

        # 轴承分析
        bearing_result = self.analyze_bearing(arr, fs, rot_freq, preprocess=False) if not skip_bearing else {}

        # 齿轮分析
        gear_result = self.analyze_gear(arr, fs, rot_freq, preprocess=False,
                                        _cached_oa=cached_oa, _cached_os=cached_os) if not skip_gear else {}

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

        if rot_freq is None:
            rot_freq, _, _, _ = self._estimate_rot_freq(arr, fs)

        original_bearing = self.bearing_method
        original_gear = self.gear_method

        bearing_results = {}
        if not skip_bearing:
            for method in BearingMethod:
                self.bearing_method = method
                try:
                    bearing_results[method.value] = self.analyze_bearing(arr, fs, rot_freq)
                except Exception as e:
                    bearing_results[method.value] = {"error": str(e)}

        gear_results = {}
        if not skip_gear:
            # full-analysis 模式：启用慢方法（VMD/SC/SCoh/MSB）
            self._run_slow_methods = True
            for method in GearMethod:
                self.gear_method = method
                try:
                    gear_results[method.value] = self.analyze_gear(arr, fs, rot_freq)
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
        health_score, status, _ = _compute_health_score(
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


def _evaluate_bearing_faults_statistical(
    freq_arr: np.ndarray,
    amp_arr: np.ndarray,
    rot_freq: float,
) -> Dict[str, Any]:
    """
    无物理参数时的轴承统计诊断。
    基于包络谱统计特征评估是否存在异常冲击。

    新增指标：
      - low_freq_ratio: 低频能量占比（用于区分轴频谐波 vs 轴承故障）
      - envelope_crest_factor: 包络谱峰值因子（外圈故障分布较分散时兜底）
      - moderate_kurtosis: 中等峭度路径（外圈故障峭度通常不高但仍异常）
    """
    indicators = {}
    if len(amp_arr) == 0:
        return indicators

    background = np.median(amp_arr)
    peak_amp = float(np.max(amp_arr))
    snr = peak_amp / background if background > 0 else 0.0

    # 1. 包络谱峰值显著性（单峰异常——单一最强峰 vs 背景）
    #    健康轴承的旋转谐波也能产生 SNR~10-15 的包络谱峰值，
    #    需要更高阈值区分"旋转谐波主导"和"真正的轴承故障冲击"
    indicators["envelope_peak_snr"] = {
        "value": float(round(snr, 2)),
        "snr": float(round(snr, 2)),
        "significant": bool(snr > 20.0),
    }

    # 2. 包络谱峭度（频域峭度——区分"少量超强峰"vs"多个中等峰"）
    amp_norm = amp_arr / (np.mean(amp_arr) + 1e-12)
    kurt = float(np.mean(amp_norm ** 4) / (np.mean(amp_norm ** 2) ** 2 + 1e-12) - 2)
    indicators["envelope_kurtosis"] = {
        "value": float(round(kurt, 2)),
        "snr": float(round(max(0, kurt), 2)),
        "significant": bool(kurt > 15.0),
    }

    # 2b. 中等峭度路径：外圈/球故障时峭度常在 5-15，不触发高阈值但仍异常
    #     条件放宽至 kurt>5 AND snr>15（低于此的几乎都是旋转谐波噪声）
    indicators["moderate_kurtosis"] = {
        "value": float(round(kurt, 2)),
        "snr": float(round(max(0, kurt), 2)),
        "significant": bool(kurt > 5.0 and snr > 15.0),
    }

    freq_arr_np = np.array(freq_arr)

    # 3. 低频能量占比 — 若包络谱能量集中在 <3×转频 → 轴频谐波，非轴承故障
    low_cutoff = max(rot_freq * 3, 30.0)
    total_energy = float(np.sum(amp_arr ** 2)) + 1e-12
    low_mask = freq_arr_np <= low_cutoff
    low_energy = float(np.sum(amp_arr[low_mask] ** 2))
    low_freq_ratio = low_energy / total_energy
    # 旋转谐波主导标记：低频占比 > 40% 说明包络谱能量主要来自转频谐波而非轴承故障
    rotation_harmonic_dominant = low_freq_ratio > 0.4
    indicators["low_freq_ratio"] = {
        "value": float(round(low_freq_ratio, 4)),
        "snr": float(round((1.0 - low_freq_ratio) * 10, 2)),
        "significant": False,  # 辅助抑制误报，不单独判定
        "rotation_harmonic_dominant": rotation_harmonic_dominant,
    }

    # 4. 高频能量比 — 轴承故障冲击能量通常在高频段
    hf_threshold = max(500.0, rot_freq * 2)
    hf_mask = freq_arr_np >= hf_threshold
    hf_ratio = float(np.sum(amp_arr[hf_mask] ** 2)) / total_energy if np.any(hf_mask) else 0.0
    indicators["high_freq_ratio"] = {
        "value": float(round(hf_ratio, 4)),
        "snr": float(round(hf_ratio * 10, 2)),
        "significant": bool(hf_ratio > 0.65 and not rotation_harmonic_dominant),
    }

    # 5. 谱峰集中度 — 前5峰能量占比（故障时少数峰支配，健康时分布均匀）
    sorted_amps = np.sort(amp_arr)[::-1]
    top5_energy = float(np.sum(sorted_amps[:5] ** 2))
    peak_conc = float(top5_energy / total_energy)
    # 旋转谐波主导时，集中度是转频谐波导致的而非轴承故障，应抑制
    indicators["peak_concentration"] = {
        "value": float(round(peak_conc, 4)),
        "snr": float(round(peak_conc * 10, 2)),
        "significant": bool(peak_conc > 0.6 and not rotation_harmonic_dominant),
    }

    # 6. 包络谱峰值因子（crest_factor_in_spectrum）
    #    外圈故障：包络谱分布较均匀（多个中等峰），峰值因子偏低
    #    内圈故障：包络谱分布极不均匀（少数超强峰），峰值因子偏高
    env_rms = float(np.sqrt(np.mean(amp_arr ** 2)))
    env_cf = float(peak_amp / env_rms) if env_rms > 1e-12 else 0.0
    indicators["envelope_crest_factor"] = {
        "value": float(round(env_cf, 2)),
        "snr": float(round(env_cf, 2)),
        "significant": bool(env_cf > 35.0 and not rotation_harmonic_dominant),
    }

    return indicators


def _evaluate_bearing_faults(
    bearing_params: Optional[Dict],
    env_freq: List[float],
    env_amp: List[float],
    rot_freq: float,
) -> Dict[str, Any]:
    """
    评估轴承故障指示器 — 双路并行：
      1) 物理参数路径：精确匹配 BPFO/BPFI/BSF（需要轴承几何参数）
      2) 统计路径：包络谱全局统计特征（无参数时兜底；有参数时作为辅助佐证）
    两路结果独立并存，不互相替代。
    """
    if not env_freq or not env_amp or rot_freq <= 0:
        return {}

    freq_arr = np.array(env_freq, dtype=np.float64)
    amp_arr = np.array(env_amp, dtype=np.float64)
    df = freq_arr[1] - freq_arr[0] if len(freq_arr) > 1 else 1.0
    background = float(np.median(amp_arr))

    # ========== 统计路径：始终计算，作为兜底 + 佐证 ==========
    stat_indicators = _evaluate_bearing_faults_statistical(freq_arr, amp_arr, rot_freq)

    # 统计路径检出异常？
    stat_abnormal = any(
        v.get("significant") for v in stat_indicators.values() if isinstance(v, dict)
    )

    # ========== 物理参数路径 ==========
    has_params = bearing_params and any(v is not None for v in bearing_params.values())

    # 先获取物理参数
    n_balls = d_val = D_val = alpha = 0.0
    if has_params:
        try:
            n_balls = int(float(bearing_params.get("n") or 0))
            d_val = float(bearing_params.get("d") or 0)
            D_val = float(bearing_params.get("D") or 0)
            alpha = np.radians(float(bearing_params.get("alpha") or 0))
        except (TypeError, ValueError):
            has_params = False

    if n_balls <= 0 or d_val <= 1e-9 or D_val <= 1e-9:
        has_params = False

    if has_params:
        cos_a = np.cos(alpha)
        dd = (d_val / D_val) * cos_a
        freqs = {
            "BPFO": (n_balls / 2.0) * rot_freq * (1 - dd),
            "BPFI": (n_balls / 2.0) * rot_freq * (1 + dd),
            "BSF":  (D_val / (2.0 * d_val)) * rot_freq * (1 - dd ** 2),
        }

        param_indicators = {}
        for name, f_hz in freqs.items():
            if f_hz <= 0 or f_hz > freq_arr[-1]:
                param_indicators[name] = {"theory_hz": round(f_hz, 2), "detected_hz": None,
                                          "peak_amp": 0.0, "snr": 0.0, "significant": False}
                continue

            tol = max(f_hz * 0.05, df * 2)
            mask = np.abs(freq_arr - f_hz) <= tol

            # 谐波 SNR
            harmonic_snrs = []
            for h in range(2, 5):
                h_freq = f_hz * h
                if h_freq > freq_arr[-1]:
                    break
                h_tol = max(h_freq * 0.05, df * 2)
                h_mask = np.abs(freq_arr - h_freq) <= h_tol
                if np.any(h_mask):
                    h_peak = float(np.max(amp_arr[h_mask]))
                    h_snr = h_peak / background if background > 0 else 0.0
                    harmonic_snrs.append(h_snr)

            if np.any(mask):
                peak_idx = int(np.argmax(amp_arr[mask]))
                actual_idx = int(np.where(mask)[0][peak_idx])
                peak_amp = float(amp_arr[actual_idx])
                snr = peak_amp / background if background > 0 else 0.0

                # 频率路径判定：仅用于故障类型标注，不用于"是否故障"判断
                # 健康轴承也有低 SNR 的频率峰值（随机波动），所以阈值不能太低
                significant = snr > 4.5

                # BPFI 内圈专项：边频带验证（至少 2 个边带 SNR>3）
                sideband_snrs = []
                if name == "BPFI":
                    for offset in [rot_freq, -rot_freq]:
                        sb_f = f_hz + offset
                        if sb_f <= 0 or sb_f > freq_arr[-1]:
                            continue
                        sb_tol = max(sb_f * 0.05, df * 2)
                        sb_mask = np.abs(freq_arr - sb_f) <= sb_tol
                        if np.any(sb_mask):
                            sb_peak = float(np.max(amp_arr[sb_mask]))
                            sb_snr = sb_peak / background if background > 0 else 0.0
                            sideband_snrs.append(sb_snr)
                    strong_sb = sum(1 for s in sideband_snrs if s > 3.0)
                    if strong_sb >= 2 and snr > 4.0 and not significant:
                        significant = True

                param_indicators[name] = {
                    "theory_hz": round(f_hz, 2),
                    "detected_hz": round(float(freq_arr[actual_idx]), 2),
                    "peak_amp": round(peak_amp, 6),
                    "snr": round(snr, 2),
                    "significant": significant,
                    "harmonic_snrs": [round(s, 2) for s in harmonic_snrs],
                    "sideband_snrs": [round(s, 2) for s in sideband_snrs] if name == "BPFI" else None,
                }
            else:
                param_indicators[name] = {
                    "theory_hz": round(f_hz, 2), "detected_hz": None,
                    "peak_amp": 0.0, "snr": 0.0, "significant": False,
                }

        # 合并：物理参数路径 + 统计路径（以 _stat 后缀区分）
        return {**param_indicators, **{f"{k}_stat": v for k, v in stat_indicators.items()}}

    # 无物理参数时，纯粹统计诊断
    return stat_indicators
