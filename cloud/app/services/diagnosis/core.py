"""
诊断策略调度器（Diagnosis Engine）

统一入口：前端通过 strategy / method 参数选择不同的诊断算法组合。
"""
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Any

from .utils import prepare_signal, compute_fft_spectrum, estimate_rot_freq_spectrum as _estimate_rot_freq_simple
from .bearing import (
    envelope_analysis,
    fast_kurtogram,
    cpw_envelope_analysis,
    med_envelope_analysis,
)
from .gear import (
    compute_fm0,
    compute_fm4,
    compute_na4,
    compute_ser,
    compute_car,
    compute_m6a,
    compute_m8a,
    analyze_sidebands,
)
from .preprocessing import wavelet_denoise
from .vmd_denoise import vmd_denoise
from .features import (
    compute_time_features,
    compute_fft_features,
    compute_envelope_features,
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

    def analyze_bearing(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
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
        arr = self.preprocess(signal)

        if rot_freq is None:
            rot_freq = _estimate_rot_freq_simple(arr, fs)

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
        indicators = self._evaluate_bearing_faults(
            result.get("envelope_freq", []),
            result.get("envelope_amp", []),
            rot_freq,
        )

        return {
            "method": self.bearing_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3),
            **result,
            "features": env_features,
            "fault_indicators": indicators,
        }

    def analyze_gear(
        self,
        signal: np.ndarray,
        fs: float,
        rot_freq: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        齿轮诊断分析

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

        if rot_freq is None:
            rot_freq = _estimate_rot_freq_simple(arr, fs)

        z_in = (self.gear_teeth.get("input") or 0) if self.gear_teeth else 0
        mesh_freq = rot_freq * z_in if z_in > 0 else None

        result = {
            "method": self.gear_method.value,
            "strategy": self.strategy.value,
            "rot_freq_hz": round(rot_freq, 3),
            "mesh_freq_hz": round(mesh_freq, 2) if mesh_freq else None,
        }

        # 边频带分析
        if mesh_freq and mesh_freq > 0:
            sb_result = analyze_sidebands(arr, fs, mesh_freq, rot_freq)
            result["sidebands"] = sb_result["sidebands"]
            result["ser"] = sb_result["ser"]
            result["mesh_amp"] = sb_result["mesh_amp"]
        else:
            result["sidebands"] = []
            result["ser"] = 0.0

        # 高级齿轮指标
        if self.gear_method == GearMethod.ADVANCED and mesh_freq and mesh_freq > 0:
            # 用 FFT 提取啮合谐波来近似 TSA 分量
            xf, yf = compute_fft_spectrum(arr, fs)
            # 构造差分信号（简化版：移除啮合频率附近能量）
            # 实际应使用 TSA，这里用带阻近似
            result["fm0"] = round(compute_fm0(arr, mesh_freq, fs), 4)
            result["car"] = round(compute_car(arr, fs, rot_freq), 4)

            # 差分信号（简化版：用高通滤波近似）
            from .utils import highpass_filter
            diff_approx = highpass_filter(arr, fs, mesh_freq * 0.5)
            result["fm4"] = round(compute_fm4(diff_approx), 4)
            result["m6a"] = round(compute_m6a(diff_approx), 4)
            result["m8a"] = round(compute_m8a(diff_approx), 4)

            # 边频带能量比 SER
            result["ser"] = round(compute_ser(arr, fs, mesh_freq, rot_freq), 4)

        # 故障指示器
        indicators = self._evaluate_gear_faults(result)
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
            rot_freq = _estimate_rot_freq_simple(arr, fs)

        # 时域特征
        time_features = compute_time_features(arr)

        # 轴承分析
        bearing_result = self.analyze_bearing(arr, fs, rot_freq)

        # 齿轮分析
        gear_result = self.analyze_gear(arr, fs, rot_freq)

        # 综合健康度评分
        health_score, status = self._compute_health_score(
            time_features, bearing_result, gear_result
        )

        return {
            "health_score": health_score,
            "status": status,
            "bearing": bearing_result,
            "gear": gear_result,
            "time_features": time_features,
            "recommendation": self._generate_recommendation(bearing_result, gear_result, status),
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
            rot_freq = _estimate_rot_freq_simple(arr, fs)

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
        health_score, status = self._compute_health_score(
            time_features,
            bearing_results.get(BearingMethod.ENVELOPE.value, {}),
            gear_results.get(GearMethod.STANDARD.value, {}),
        )

        # 生成各方法检出结论汇总
        summary = self._summarize_all_methods(bearing_results, gear_results)

        return {
            "health_score": health_score,
            "status": status,
            "rot_freq_hz": round(rot_freq, 3),
            "time_features": time_features,
            "bearing_results": bearing_results,
            "gear_results": gear_results,
            "summary": summary,
            "recommendation": self._generate_recommendation_all(bearing_results, gear_results, status),
        }

    def _summarize_all_methods(self, bearing_results: Dict, gear_results: Dict) -> Dict[str, Any]:
        """汇总所有方法的检出结论"""
        summary = {
            "bearing_detections": [],
            "gear_detections": [],
        }

        # 轴承各方法检出情况
        method_name_map = {
            "envelope": "标准包络分析",
            "kurtogram": "Fast Kurtogram",
            "cpw": "CPW预白化+包络",
            "med": "MED最小熵解卷积+包络",
        }
        for method_key, result in bearing_results.items():
            if "error" in result:
                continue
            indicators = result.get("fault_indicators", {})
            detected = []
            for fname, info in indicators.items():
                if info.get("significant"):
                    detected.append({
                        "fault_type": fname,
                        "theory_hz": info.get("theory_hz"),
                        "detected_hz": info.get("detected_hz"),
                        "snr": info.get("snr"),
                    })
            if detected:
                summary["bearing_detections"].append({
                    "method": method_name_map.get(method_key, method_key),
                    "method_key": method_key,
                    "detected_faults": detected,
                    "features": result.get("features", {}),
                })
            else:
                summary["bearing_detections"].append({
                    "method": method_name_map.get(method_key, method_key),
                    "method_key": method_key,
                    "detected_faults": [],
                    "features": result.get("features", {}),
                })

        # 齿轮各方法检出情况
        gear_method_name_map = {
            "standard": "标准边频带分析",
            "advanced": "高级时域指标",
        }
        for method_key, result in gear_results.items():
            if "error" in result:
                continue
            indicators = result.get("fault_indicators", {})
            detected = []
            for fname, info in indicators.items():
                if isinstance(info, dict) and info.get("critical"):
                    detected.append({
                        "indicator": fname,
                        "value": info.get("value"),
                        "level": "critical",
                    })
                elif isinstance(info, dict) and info.get("warning"):
                    detected.append({
                        "indicator": fname,
                        "value": info.get("value"),
                        "level": "warning",
                    })
            # 边频带显著数量
            sidebands = result.get("sidebands", [])
            sig_sb = [sb for sb in sidebands if sb.get("significant")]
            summary["gear_detections"].append({
                "method": gear_method_name_map.get(method_key, method_key),
                "method_key": method_key,
                "detected_indicators": detected,
                "ser": result.get("ser"),
                "sideband_count": len(sig_sb),
                "sidebands": sidebands,
                "fm0": result.get("fm0"),
                "fm4": result.get("fm4"),
                "car": result.get("car"),
                "m6a": result.get("m6a"),
                "m8a": result.get("m8a"),
            })

        return summary

    def _generate_recommendation_all(self, bearing_results: Dict, gear_results: Dict, status: str) -> str:
        """基于所有方法结果生成建议"""
        if status == "normal":
            return "设备运行正常，所有诊断方法均未检出显著故障特征，建议按周期继续监测。"

        parts = []

        # 统计各轴承方法检出的故障
        bearing_faults = {}
        for result in bearing_results.values():
            indicators = result.get("fault_indicators", {})
            for fname, info in indicators.items():
                if info.get("significant"):
                    bearing_faults.setdefault(fname, 0)
                    bearing_faults[fname] += 1

        if bearing_faults:
            # 按被多少种方法检出来排序
            sorted_faults = sorted(bearing_faults.items(), key=lambda x: x[1], reverse=True)
            fault_desc = ", ".join([f"{name}({count}种方法)" for name, count in sorted_faults])
            parts.append(f"轴承诊断：{fault_desc}检出显著特征。")

        # 齿轮指标
        gear_warnings = []
        gear_criticals = []
        for result in gear_results.values():
            indicators = result.get("fault_indicators", {})
            for fname, info in indicators.items():
                if isinstance(info, dict):
                    if info.get("critical"):
                        gear_criticals.append(fname)
                    elif info.get("warning"):
                        gear_warnings.append(fname)

        if gear_criticals:
            parts.append(f"齿轮诊断：{'/'.join(set(gear_criticals))}指标达到危险阈值，建议立即检查。")
        elif gear_warnings:
            parts.append(f"齿轮诊断：{'/'.join(set(gear_warnings))}指标达到预警阈值，建议关注啮合状态。")

        if not parts:
            parts.append("检测到部分异常信号特征，建议结合工况进一步分析。")

        return " ".join(parts)

    def _evaluate_bearing_faults(
        self,
        env_freq: List[float],
        env_amp: List[float],
        rot_freq: float,
    ) -> Dict[str, Any]:
        """评估轴承故障指示器"""
        if not self.bearing_params or not env_freq or not env_amp:
            return {}

        from .utils import find_peaks_in_spectrum

        freq_arr = np.array(env_freq)
        amp_arr = np.array(env_amp)

        # 计算轴承特征频率
        n_balls = self.bearing_params.get("n") or 0
        d = self.bearing_params.get("d") or 0
        D = self.bearing_params.get("D") or 0
        alpha = np.radians(self.bearing_params.get("alpha") or 0)

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

    def _evaluate_gear_faults(self, gear_result: Dict) -> Dict[str, Any]:
        """评估齿轮故障指示器"""
        indicators = {}

        ser = gear_result.get("ser", 0.0)
        indicators["ser"] = {
            "value": round(ser, 4),
            "warning": ser > 1.5,
            "critical": ser > 3.0,
        }

        if "fm0" in gear_result:
            fm0 = gear_result["fm0"]
            indicators["fm0"] = {
                "value": round(fm0, 4),
                "warning": fm0 > 5,
                "critical": fm0 > 10,
            }

        if "car" in gear_result:
            car = gear_result["car"]
            indicators["car"] = {
                "value": round(car, 4),
                "warning": car > 1.2,
                "critical": car > 2.0,
            }

        # 边频带统计
        sidebands = gear_result.get("sidebands", [])
        significant_count = sum(1 for sb in sidebands if sb.get("significant"))
        indicators["sideband_count"] = {
            "value": significant_count,
            "warning": significant_count >= 2,
            "critical": significant_count >= 4,
        }

        return indicators

    def _compute_health_score(
        self,
        time_features: Dict,
        bearing_result: Dict,
        gear_result: Dict,
    ) -> tuple:
        """
        计算综合健康度评分 (0-100)

        改进策略：
        - 多指标同时异常才大幅扣分（避免单一误检导致过度扣分）
        - 时域特征权重提高（峭度对冲击最敏感）
        - 无齿轮参数时跳过齿轮扣分
        - 轴承扣分权重降低，但多故障叠加时增强
        """
        score = 100.0
        deductions = []  # 记录各项扣分，用于调试

        # ===== 时域特征扣分 =====
        kurt = time_features.get("kurtosis", 3.0)
        if kurt > 15:
            deductions.append(("kurtosis_critical", 15))
        elif kurt > 8:
            deductions.append(("kurtosis_warning", 8))
        elif kurt > 5:
            deductions.append(("kurtosis_mild", 4))

        crest = time_features.get("crest_factor", 5.0)
        if crest > 12:
            deductions.append(("crest_critical", 8))
        elif crest > 9:
            deductions.append(("crest_warning", 4))

        rms = time_features.get("rms", 0.0)
        # RMS 异常通常表示整体振动水平升高

        # ===== 轴承故障扣分（权重降低，多故障叠加增强）=====
        bearing_ind = bearing_result.get("fault_indicators", {})
        bearing_significant = 0
        bearing_mild = 0
        for name, info in bearing_ind.items():
            if info.get("significant"):
                bearing_significant += 1
            elif info.get("snr", 0) > 2:
                bearing_mild += 1

        if bearing_significant >= 2:
            deductions.append(("bearing_multi", 12))  # 多故障特征同时显著
        elif bearing_significant == 1:
            deductions.append(("bearing_single", 5))   # 单一故障特征
        if bearing_mild >= 2:
            deductions.append(("bearing_mild", 3))

        # ===== 齿轮故障扣分（仅在存在齿轮参数时）=====
        gear_ind = gear_result.get("fault_indicators", {})
        has_gear_params = self.gear_teeth and self.gear_teeth.get("input", 0) > 0

        if has_gear_params:
            if gear_ind.get("ser", {}).get("critical"):
                deductions.append(("gear_ser_critical", 12))
            elif gear_ind.get("ser", {}).get("warning"):
                deductions.append(("gear_ser_warning", 6))

            if gear_ind.get("sideband_count", {}).get("critical"):
                deductions.append(("gear_sb_critical", 8))
            elif gear_ind.get("sideband_count", {}).get("warning"):
                deductions.append(("gear_sb_warning", 4))

            if gear_ind.get("fm0", {}).get("critical"):
                deductions.append(("gear_fm0_critical", 8))
            elif gear_ind.get("fm0", {}).get("warning"):
                deductions.append(("gear_fm0_warning", 4))

        # ===== 计算总分（累加扣分，但封顶）=====
        total_deduction = sum(d[1] for d in deductions)
        # 封顶：最多扣 70 分，保留 30 分底线
        total_deduction = min(total_deduction, 70)
        score -= total_deduction

        health_score = int(max(0, min(100, score)))

        # 状态判定：结合分数 + 关键指标
        has_critical = any("critical" in d[0] for d in deductions)
        has_warning = any("warning" in d[0] for d in deductions)

        if health_score >= 85:
            status = "normal"
        elif health_score >= 60:
            status = "warning" if (has_warning or has_critical) else "normal"
        else:
            status = "fault" if has_critical else "warning"

        return health_score, status

    def _generate_recommendation(
        self,
        bearing_result: Dict,
        gear_result: Dict,
        status: str,
    ) -> str:
        """生成诊断建议"""
        if status == "normal":
            return "设备运行正常，建议按周期继续监测。"

        parts = []

        # 轴承建议
        bearing_ind = bearing_result.get("fault_indicators", {})
        bearing_faults = [k for k, v in bearing_ind.items() if v.get("significant")]
        if bearing_faults:
            parts.append(f"检测到轴承故障特征（{'/'.join(bearing_faults)}），建议检查润滑状态并安排精密诊断。")

        # 齿轮建议
        gear_ind = gear_result.get("fault_indicators", {})
        if gear_ind.get("ser", {}).get("warning"):
            parts.append("齿轮边频带能量异常，建议关注啮合状态及载荷波动。")

        if not parts:
            parts.append("检测到异常信号特征，建议结合工况进一步分析。")

        return " ".join(parts)
