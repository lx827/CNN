# 后端服务层函数接口文档

> **文档用途**：完整记录 `cloud/app/services/` 目录下所有模块的公共函数/类接口，便于 AI Agent 快速定位和修改代码。
> **维护要求**：新增、修改或删除任何公共函数时，必须同步更新本文档。

---

## 目录

1. [分析引擎 (analyzer.py)](#1-分析引擎-analyzerpy)
2. [告警生成 (alarms/)](#2-告警生成-alarms)
3. [神经网络预测 (nn_predictor.py)](#3-神经网络预测-nn_predictorpy)
4. [离线监测 (offline_monitor.py)](#4-离线监测-offline_monitorpy)
5. [诊断引擎 (diagnosis/engine.py)](#5-诊断引擎-diagnosisenginepy)
6. [集成诊断 (diagnosis/ensemble.py)](#6-集成诊断-diagnosisensemblepy)
7. [轴承诊断 (diagnosis/bearing.py)](#7-轴承诊断-diagnosisbearingpy)
8. [齿轮诊断 (diagnosis/gear/)](#8-齿轮诊断-diagnosisgear)
9. [特征提取 (diagnosis/features.py)](#9-特征提取-diagnosisfeaturespy)
10. [规则诊断 (diagnosis/rule_based.py)](#10-规则诊断-diagnosisrule_basedpy)
11. [预处理与降噪 (diagnosis/preprocessing.py)](#11-预处理与降噪-diagnosispreprocessingpy)
12. [信号工具 (diagnosis/signal_utils.py)](#12-信号工具-diagnosissignal_utilspy)
13. [VMD分解 (diagnosis/vmd_denoise.py)](#13-vmd分解-diagnosisvmd_denoisepy)
14. [EMD分解 (diagnosis/emd_denoise.py)](#14-emd分解-diagnosisemd_denoisepy)
15. [小波包 (diagnosis/wavelet_packet.py)](#15-小波包-diagnosiswavelet_packetpy)
16. [其他诊断模块](#16-其他诊断模块)

---

## 1. 分析引擎 (analyzer.py)

故障分析引擎，按通道配置自动分派轴承/齿轮/混合分析，实现 NN → 新引擎 → 规则算法的三级回退。

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_safe_result` | `_safe_result(msg="分析失败", health=100)` | `dict` | 崩溃安全默认结果 |
| `_params_valid` | `_params_valid(params: Optional[Dict], kind: str) -> bool` | `bool` | 判断轴承/齿轮参数是否有效 |
| `analyze_device` | `analyze_device(channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None, rot_freq: Optional[float] = None, denoise_method: str = "")` | `dict` | 综合分析主入口 |

**`analyze_device` 内部逻辑**：
1. 优先调用 `nn_predictor.predict()`（若 `NN_ENABLED=True`）
2. NN 失败/未启用 → 调用 `DiagnosisEngine` 逐通道分析
3. 引擎崩溃 → 回退到 `rule_based._rule_based_analyze()`

---

## 2. 告警生成 (alarms/)

### 2.1 统一入口 (`alarms/__init__.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_get_threshold` | `_get_threshold(device: Device, metric: str, level: str) -> float` | `float` | 读取设备阈值配置，未配置使用默认值；显式置空则返回极大值禁用 |
| `_has_recent_unresolved_alarm` | `_has_recent_unresolved_alarm(db: Session, device_id: str, category: str, level: str, channel: int = None, hours: int = 1) -> bool` | `bool` | 检查最近 hours 小时内是否已有同类未处理告警 |
| `generate_alarms` | `generate_alarms(db: Session, device_id: str, health_score: int, fault_probabilities: dict, channel_features: dict = None, batch_index: int = None, order_analysis: dict = None, channel_diagnosis: dict = None)` | `list` | 综合告警生成入口，依次调用四类告警检查，WebSocket 推送新告警 |

### 2.2 通道级告警 (`alarms/channel.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_check_feature_alarms` | `_check_feature_alarms(db, device, channel: int, channel_name: str, features: dict, batch_index: int = None) -> list` | `list` | 检查 RMS/峰值/峭度/峰值因子是否超阈值 |
| `_check_gear_alarms` | `_check_gear_alarms(db, device, channel_diagnosis: dict, batch_index: int = None) -> list` | `list` | 检查 SER/FM0/CAR/边频带数量是否超标 |

### 2.3 设备级告警 (`alarms/device.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_check_device_alarms` | `_check_device_alarms(db, device, health_score: int, fault_probabilities: dict, batch_index: int = None, order_analysis: dict = None) -> list` | `list` | 健康度<60触发critical，<80触发warning |

### 2.4 诊断结果告警 (`alarms/diagnosis.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_check_diagnosis_alarms` | `_check_diagnosis_alarms(db, device, fault_probabilities: dict, batch_index: int = None) -> list` | `list` | 概率>60%触发critical，>30%触发warning |

---

## 3. 神经网络预测 (nn_predictor.py)

> 当前为预留接口，默认返回 None，云端自动回退到 analyzer.py 的简化算法。

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_load_model` | `_load_model()` | `Any` | 延迟加载神经网络模型，当前仅检查文件存在性 |
| `_preprocess` | `_preprocess(signal: np.ndarray, sample_rate: int = 1000) -> np.ndarray` | `np.ndarray` | 截断/填充到5000点，Z-score标准化，float32 |
| `predict` | `predict(channels_data: Dict[str, list], sample_rate: int = 1000) -> Optional[Dict]` | `Optional[Dict]` | 神经网络预测主函数，未启用或加载失败返回 None |

---

## 4. 离线监测 (offline_monitor.py)

> 完全独立的子系统，禁止被其他业务模块导入，是 `is_online` 字段的唯一写者。

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_get_offline_threshold` | `_get_offline_threshold(device: Device, now: datetime) -> datetime` | `datetime` | 根据通信间隔计算离线判定阈值（最小5分钟，最大10分钟） |
| `_is_device_offline` | `_is_device_offline(device: Optional[Device], now: Optional[datetime] = None) -> bool` | `bool` | 判断设备是否离线 |
| `offline_monitor_worker` | `async def offline_monitor_worker()` | `None` | 后台协程，每30秒扫描更新 `is_online`，广播状态变化 |

---

## 5. 诊断引擎 (diagnosis/engine.py)

核心调度类，实现轴承/齿轮/综合分析的入口。

### 5.1 枚举类型

| 枚举 | 成员 | 说明 |
|------|------|------|
| `DiagnosisStrategy` | `STANDARD`, `RESEARCH`, `FAST` | 诊断策略 |
| `BearingMethod` | `ENVELOPE`, `KURTOGRAM`, `CPW`, `MED`, `TEAGER`, `SPECTRAL_KURTOSIS`, `MCKD`, `CYCLIC_SPECTRAL` | 轴承诊断方法 |
| `GearMethod` | `STANDARD`, `VMD_DEMOD`, `FULL_ANALYSIS` | 齿轮诊断方法 |
| `DenoiseMethod` | `NONE`, `WAVELET`, `VMD`, `WAVELET_VMD`, `WAVELET_LMS`, `EMD`, `CEEMDAN`, `SAVGOL` | 去噪方法 |

### 5.2 DiagnosisEngine 类

| 方法 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `__init__` | `__init__(self, device=None, sample_rate: int = 25600, rot_freq: Optional[float] = None, strategy: DiagnosisStrategy = DiagnosisStrategy.STANDARD, bearing_method: BearingMethod = BearingMethod.ENVELOPE, gear_method: GearMethod = GearMethod.STANDARD, denoise_method: DenoiseMethod = DenoiseMethod.NONE)` | — | 初始化引擎 |
| `preprocess` | `preprocess(self, signal: np.ndarray) -> np.ndarray` | `np.ndarray` | 根据 `denoise_method` 路由到各去噪函数 |
| `analyze_bearing` | `analyze_bearing(self, signal: np.ndarray) -> dict` | `dict` | 轴承诊断入口 |
| `analyze_gear` | `analyze_gear(self, signal: np.ndarray) -> dict` | `dict` | 齿轮诊断入口 |
| `analyze_comprehensive` | `analyze_comprehensive(self, signal: np.ndarray) -> dict` | `dict` | 综合分析入口（轴承+齿轮+时域特征） |

### 5.3 模块级评估函数

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_evaluate_bearing_faults_statistical` | `_evaluate_bearing_faults_statistical(...)` | `dict` | 无轴承参数时的统计异常评估 |
| `_evaluate_bearing_faults` | `_evaluate_bearing_faults(...)` | `dict` | 有轴承参数时的特征频率匹配评估 |

---

## 6. 集成诊断 (diagnosis/ensemble.py)

多去噪+多方法集成诊断引擎，弱投票融合。

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_as_float` | `_as_float(value: Any, default: float = 0.0) -> float` | `float` | 安全浮点转换 |
| `_safe_denoise` | `_safe_denoise(value: str) -> DenoiseMethod` | `DenoiseMethod` | 安全解析去噪方法枚举 |
| `_profile_config` | `_profile_config(profile: str, denoise_method: str) -> Dict[str, list]` | `dict` | 返回配置的方法列表和去噪列表 |
| `_has_gear_params` | `_has_gear_params(gear_teeth: Optional[Dict]) -> bool` | `bool` | 判断齿轮参数有效性（input齿数>0） |
| `_has_bearing_params` | `_has_bearing_params(bearing_params: Optional[Dict]) -> bool` | `bool` | 判断轴承参数有效性（n,d,D均>0） |
| `_bearing_confidence` | `_bearing_confidence(result: Dict, time_features: Dict) -> Dict[str, Any]` | `dict` | 轴承投票置信度（impulse_context门控） |
| `_gear_confidence` | `_gear_confidence(result: Dict, has_gear_params: bool, time_features: Optional[Dict] = None) -> Dict[str, Any]` | `dict` | 齿轮投票置信度 |
| `_time_confidence` | `_time_confidence(time_features: Dict) -> float` | `float` | 时域冲击证据置信度 |
| `_fault_label` | `_fault_label(best_bearing: Dict, best_gear: Dict, bearing_score: float, gear_score: float) -> str` | `str` | 生成综合故障标签 |
| `run_research_ensemble` | `run_research_ensemble(device_id: str, batch_index: int, channel: int, signal: np.ndarray, fs: int, rot_freq: Optional[float], gear_teeth: Optional[Dict], bearing_params: Optional[Dict], profile: str = "balanced", denoise_method: str = "none", max_seconds: float = 5.0)` | `dict` | 集成诊断主入口 |

**`run_research_ensemble` 关键逻辑**：
- `exhaustive` profile 遍历 8 种去噪 + 全部轴承/齿轮方法
- 仅配置轴承 → `skip_gear=True`，仅配置齿轮 → `skip_bearing=True`
- 调用 D-S 证据理论融合 (`dempster_shafer_fusion`)，高冲突时切换 Murphy 平均法

---

## 7. 轴承诊断 (diagnosis/bearing.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `envelope_analysis` | `envelope_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None, max_freq: int = 1000)` | `dict` | 标准包络谱分析 |
| `fast_kurtogram` | `fast_kurtogram(signal: np.ndarray, fs: int, max_level: int = 6, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | 快速谱峭度图（STFT近似） |
| `cpw_envelope_analysis` | `cpw_envelope_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None, mesh_freq: Optional[float] = None)` | `dict` | 倒频谱预白化+包络 |
| `med_envelope_analysis` | `med_envelope_analysis(signal: np.ndarray, fs: int, filter_len: int = 30, max_iter: int = 30, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | 最小熵解卷积+包络 |
| `teager_envelope_analysis` | `teager_envelope_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | Teager能量算子+包络 |
| `spectral_kurtosis_envelope_analysis` | `spectral_kurtosis_envelope_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | 自适应谱峭度重加权包络 |

---

## 8. 齿轮诊断 (diagnosis/gear/)

### 8.1 公共接口 (`gear/__init__.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `compute_fm0` | `compute_fm0(tsa_signal: np.ndarray, mesh_freq: float, sample_rate: int, n_harmonics: int = 5)` | `float` | FM0粗故障检测 |
| `compute_er` | `compute_er(differential_signal: np.ndarray, freq: np.ndarray, amp: np.ndarray, mesh_freq: float, rot_freq: float)` | `float` | 能量比（多齿磨损） |
| `compute_ser` | `compute_ser(freq: np.ndarray, amp: np.ndarray, mesh_freq: float, rot_freq: float, n_sidebands: int = 6)` | `float` | 边频带能量比 |
| `analyze_sidebands` | `analyze_sidebands(freq: np.ndarray, amp: np.ndarray, mesh_freq: float, rot_freq: float, n_sidebands: int = 6)` | `dict` | 边频带分析 |
| `_evaluate_gear_faults` | `_evaluate_gear_faults(gear_result: Dict) -> Dict` | `dict` | 齿轮故障评估 |

### 8.2 指标计算 (`gear/metrics.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `compute_tsa_residual_order` | `compute_tsa_residual_order(signal: np.ndarray, fs: float, rot_freq: float)` | `Tuple` | TSA+残余+差分信号（阶次域） |
| `compute_fm4` | `compute_fm4(differential_signal: np.ndarray) -> float` | `float` | FM4局部故障检测（差分信号峭度） |
| `compute_m6a` | `compute_m6a(differential_signal: np.ndarray) -> float` | `float` | M6A六阶矩 |
| `compute_m8a` | `compute_m8a(differential_signal: np.ndarray) -> float` | `float` | M8A八阶矩 |
| `compute_car` | `compute_car(cepstrum: np.ndarray, quefrency: np.ndarray, rot_freq: float, n_harmonics: int = 5)` | `float` | 倒频谱幅值比 |
| `compute_ser_order` | `compute_ser_order(order_axis: np.ndarray, spectrum: np.ndarray, mesh_order: float, carrier_order: float, n_sidebands: int = 6)` | `float` | 阶次域SER |
| `analyze_sidebands_order` | `analyze_sidebands_order(order_axis: np.ndarray, spectrum: np.ndarray, mesh_order: float, carrier_order: float, n_sidebands: int = 6)` | `dict` | 阶次域边频分析 |
| `compute_fm0_order` | `compute_fm0_order(tsa_signal: np.ndarray, mesh_order: float, sample_rate: int, n_harmonics: int = 5)` | `float` | 阶次域FM0 |
| `compute_na4` | `compute_na4(residual_signal: np.ndarray, historical_residuals: Optional[List[np.ndarray]] = None)` | `float` | NA4趋势型故障检测 |
| `compute_nb4` | `compute_nb4(envelope_signal: np.ndarray, historical_envelopes: Optional[List[np.ndarray]] = None)` | `float` | NB4包络域局部齿损坏 |
| `analyze_sidebands_zoom_fft` | `analyze_sidebands_zoom_fft(signal: np.ndarray, fs: float, mesh_freq: float, rot_freq: float, n_sidebands: int = 6)` | `dict` | ZOOM-FFT高分辨率边频分析 |

### 8.3 行星齿轮箱 (`gear/planetary_demod.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `planetary_envelope_order_analysis` | `planetary_envelope_order_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | 窄带包络阶次分析（Level 2） |
| `planetary_vmd_demod_analysis` | `planetary_vmd_demod_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict, max_K: int = 5)` | `dict` | VMD幅频联合解调（Level 3） |
| `planetary_sc_scoh_analysis` | `planetary_sc_scoh_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | 谱相关/谱相干循环平稳分析 |
| `planetary_msb_analysis` | `planetary_msb_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | MSB残余边频带分析 |
| `planetary_cvs_med_analysis` | `planetary_cvs_med_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | 连续振动分离+MED增强 |
| `evaluate_planetary_demod_results` | `evaluate_planetary_demod_results(results: dict)` | `dict` | 行星箱结果评估统一入口 |

### 8.4 MSB分析 (`gear/msb.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `msb_residual_sideband_analysis` | `msb_residual_sideband_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | MSB-SE残余边频带分析 |

### 8.5 VMD定轴解调 (`gear/vmd_demod.py`)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `vmd_fixed_axis_demod_analysis` | `vmd_fixed_axis_demod_analysis(signal: np.ndarray, fs: float, rot_freq: float, gear_teeth: dict)` | `dict` | 定轴齿轮VMD幅频联合解调 |

---

## 9. 特征提取 (diagnosis/features.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `compute_time_features` | `compute_time_features(signal: np.ndarray) -> Dict[str, float]` | `dict` | 时域统计特征（Peak/RMS/Kurtosis/Crest） |
| `_compute_dynamic_baseline_features` | `_compute_dynamic_baseline_features(signal: np.ndarray) -> Dict[str, float]` | `dict` | 动态基线特征（kurt_mad_z, rms_mad_z, CUSUM, EWMA） |
| `compute_fft_features` | `compute_fft_features(signal: np.ndarray, fs: int, gear_teeth: Optional[dict] = None, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | 频域特征（啮合频率、边带能量） |
| `compute_envelope_features` | `compute_envelope_features(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, rot_freq: Optional[float] = None)` | `dict` | 包络特征（BPFO/BPFI/BSF匹配） |
| `remove_dc` | `remove_dc(signal: List[float]) -> np.ndarray` | `np.ndarray` | 去直流 |
| `compute_channel_features` | `compute_channel_features(signal: List[float]) -> Dict[str, float]` | `dict` | 单通道综合特征（时域+频域+包络） |
| `compute_fft` | `compute_fft(signal: List[float], sample_rate: int = 25600)` | `Tuple` | FFT频谱计算 |
| `compute_imf_energy` | `compute_imf_energy(signal: List[float], sample_rate: int = 25600) -> Dict[str, float]` | `dict` | IMF能量分布（频带能量近似） |
| `_compute_bearing_fault_freqs` | `_compute_bearing_fault_freqs(rot_freq: float, bearing_params: dict) -> dict` | `dict` | 计算BPFO/BPFI/BSF/FTF |
| `_compute_bearing_fault_orders` | `_compute_bearing_fault_orders(rot_freq: float, bearing_params: dict) -> dict` | `dict` | 计算轴承故障阶次 |
| `compute_nonparam_cusum_features` | `compute_nonparam_cusum_features(signal: np.ndarray) -> Dict[str, float]` | `dict` | 符号CUSUM+Mann-Whitney CUSUM |

---

## 10. 规则诊断 (diagnosis/rule_based.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `adaptive_rms_baseline` | `adaptive_rms_baseline(rot_freq_hz: float) -> float` | `float` | 自适应RMS基线 |
| `_rule_based_analyze` | `_rule_based_analyze(channels_data: Dict[str, List[float]], sample_rate: int = 25600, device=None)` | `dict` | 规则诊断主入口（崩溃回退用） |
| `compute_envelope_spectrum` | `compute_envelope_spectrum(signal: List[float], sample_rate: int = 25600, max_freq: int = 1000)` | `Tuple` | 包络谱计算 |
| `_band_energy` | `_band_energy(freq, amp, center: float, bandwidth: float) -> float` | `float` | 频带能量积分 |
| `_extract_spectrum_features` | `_extract_spectrum_features(freq, amp, rot_freq: float, gear_teeth: dict, bearing_params: dict) -> dict` | `dict` | 频谱特征提取 |
| `_extract_envelope_features` | `_extract_envelope_features(envelope_freq, envelope_amp, rot_freq: float, bearing_params: dict) -> dict` | `dict` | 包络特征提取 |
| `_extract_order_features` | `_extract_order_features(order_axis, spectrum, rot_freq: float, gear_teeth: dict, bearing_params: dict) -> dict` | `dict` | 阶次特征提取 |

---

## 11. 预处理与降噪 (diagnosis/preprocessing.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `wavelet_denoise` | `wavelet_denoise(signal: np.ndarray, wavelet: str = "db8", level: Optional[int] = None, threshold_mode: str = "soft", threshold_scale: float = 1.0)` | `np.ndarray` | 小波阈值去噪 |
| `cepstrum_pre_whitening` | `cepstrum_pre_whitening(signal: np.ndarray, sample_rate: int, mesh_freq: Optional[float] = None, rot_freq: Optional[float] = None, shaft_freqs: Optional[List[float]] = None)` | `np.ndarray` | 倒频谱预白化(CPW) |
| `minimum_entropy_deconvolution` | `minimum_entropy_deconvolution(signal: np.ndarray, filter_len: int = 30, max_iter: int = 30)` | `np.ndarray` | 最小熵解卷积(MED) |
| `cascade_wavelet_vmd` | `cascade_wavelet_vmd(signal: np.ndarray, wavelet: str = "db8", vmd_K: int = 5, vmd_alpha: int = 2000, ...)` | `np.ndarray` | 小波+VMD级联降噪 |
| `cascade_wavelet_lms` | `cascade_wavelet_lms(signal: np.ndarray, wavelet: str = "db8", filter_order: int = 32, mu: float = 0.01)` | `np.ndarray` | 小波+LMS级联降噪 |
| `joint_denoise` | `joint_denoise(strategy: str, signal: np.ndarray, **kwargs)` | `np.ndarray` | 联合降噪统一入口 |

---

## 12. 信号工具 (diagnosis/signal_utils.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `remove_dc` | `remove_dc(signal: np.ndarray) -> np.ndarray` | `np.ndarray` | 去直流 |
| `linear_detrend` | `linear_detrend(signal: np.ndarray) -> np.ndarray` | `np.ndarray` | 线性去趋势 |
| `prepare_signal` | `prepare_signal(signal, detrend: bool = False) -> np.ndarray` | `np.ndarray` | 信号预处理（去直流+可选去趋势） |
| `bandpass_filter` | `bandpass_filter(signal: np.ndarray, fs: float, low: float, high: float, order: int = 4)` | `np.ndarray` | 带通滤波 |
| `lowpass_filter` | `lowpass_filter(signal: np.ndarray, fs: float, cutoff: float, order: int = 4)` | `np.ndarray` | 低通滤波 |
| `highpass_filter` | `highpass_filter(signal: np.ndarray, fs: float, cutoff: float, order: int = 4)` | `np.ndarray` | 高通滤波 |
| `compute_fft_spectrum` | `compute_fft_spectrum(signal: np.ndarray, fs: float)` | `Tuple` | FFT频谱 |
| `compute_power_spectrum` | `compute_power_spectrum(signal: np.ndarray, fs: float)` | `Tuple` | 功率谱 |
| `find_peaks_in_spectrum` | `find_peaks_in_spectrum(freq, spectrum, target_freq, tolerance_percent: float = 3.0, min_snr: float = 3.0)` | `Tuple` | 频谱峰值搜索 |
| `compute_snr` | `compute_snr(peak_amp: float, spectrum: np.ndarray, method: str = "median") -> float` | `float` | 计算峰值SNR |
| `kurtosis` | `kurtosis(signal: np.ndarray, fisher: bool = False) -> float` | `float` | 峭度 |
| `rms` | `rms(signal: np.ndarray) -> float` | `float` | RMS |
| `crest_factor` | `crest_factor(signal: np.ndarray) -> float` | `float` | 峰值因子 |
| `estimate_rot_freq_spectrum` | `estimate_rot_freq_spectrum(signal: np.ndarray, fs: float)` | `float` | 频谱法估计转频 |
| `estimate_rot_freq_autocorr` | `estimate_rot_freq_autocorr(signal: np.ndarray, fs: float)` | `float` | 自相关法估计转频 |
| `estimate_rot_freq_envelope` | `estimate_rot_freq_envelope(signal: np.ndarray, fs: float)` | `float` | 包络法估计转频 |
| `zoom_fft_analysis` | `zoom_fft_analysis(signal: np.ndarray, fs: float, center_freq: float, bandwidth: float, n_fft: Optional[int] = None)` | `Tuple` | ZOOM-FFT细化谱分析 |

---

## 13. VMD分解 (diagnosis/vmd_denoise.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_vmd_core` | `_vmd_core(f: np.ndarray, alpha: float, tau: float, K: int, DC: bool, init: str, tol: float, max_iter: int = 200)` | `Tuple[np.ndarray, np.ndarray]` | VMD核心ADMM算法（内存优化版） |
| `vmd_decompose` | `vmd_decompose(signal: np.ndarray, K: int = 5, alpha: int = 2000, tau: float = 0.0, tol: float = 1e-7)` | `Tuple[np.ndarray, np.ndarray]` | VMD分解入口（信号截断至51200点防OOM） |
| `vmd_denoise` | `vmd_denoise(signal: np.ndarray, K: int = 5, alpha: int = 2000, corr_threshold: float = 0.3, kurt_threshold: float = 3.0)` | `np.ndarray` | VMD降噪（IMF筛选重构） |
| `vmd_select_impact_mode` | `vmd_select_impact_mode(signal: np.ndarray, fs: int, K: int = 5, alpha: int = 2000)` | `Tuple[np.ndarray, int]` | 选择峭度最大的冲击模态 |

---

## 14. EMD分解 (diagnosis/emd_denoise.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_find_extrema` | `_find_extrema(signal: np.ndarray)` | `Tuple` | 极值点检测 |
| `_refine_extrema_parabolic` | `_refine_extrema_parabolic(signal: np.ndarray, idx: np.ndarray)` | `np.ndarray` | 抛物线插值精化极值位置 |
| `_pad_extrema_rilling` | `_pad_extrema_rilling(signal: np.ndarray, max_idx: np.ndarray, min_idx: np.ndarray)` | `Tuple` | Rilling边界镜像填充 |
| `_compute_envelope_mean` | `_compute_envelope_mean(signal: np.ndarray, ...)` | `np.ndarray` | 包络均值计算（Pchip插值） |
| `_stop_sd` | `_stop_sd(proto_imf: np.ndarray, old: np.ndarray) -> float` | `float` | 标准差停止准则 |
| `_stop_rilling` | `_stop_rilling(upper_env: np.ndarray, lower_env: np.ndarray, ...)` | `bool` | Rilling双阈值停止准则 |
| `emd_decompose` | `emd_decompose(signal: np.ndarray, max_imfs: int = 10, max_sifts: int = 100, ...)` | `List[np.ndarray]` | EMD分解入口 |
| `ceemdan_decompose` | `ceemdan_decompose(signal: np.ndarray, ensemble_size: int = 50, noise_std: float = 0.2, ...)` | `List[np.ndarray]` | CEEMDAN分解入口 |
| `eemd_decompose` | `eemd_decompose(signal: np.ndarray, ensemble_size: int = 100, noise_std: float = 0.2, ...)` | `List[np.ndarray]` | EEMD分解入口 |
| `compute_imf_energy_entropy` | `compute_imf_energy_entropy(imfs: List[np.ndarray]) -> Dict` | `dict` | IMF能量熵计算 |
| `emd_denoise` | `emd_denoise(signal: np.ndarray, method: str = "ceemdan", corr_threshold: float = 0.35, kurt_threshold: float = 3.5)` | `np.ndarray` | EMD/CEEMDAN降噪入口 |

---

## 15. 小波包 (diagnosis/wavelet_packet.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `wavelet_packet_decompose` | `wavelet_packet_decompose(signal: np.ndarray, wavelet: str = "db8", level: int = 3)` | `Tuple` | 小波包分解 |
| `compute_wavelet_packet_energy_entropy` | `compute_wavelet_packet_energy_entropy(signal: np.ndarray, fs: float, wavelet: str = "db8", level: int = 3, gear_mesh_freq: Optional[float] = None)` | `dict` | 小波包能量熵 |
| `wavelet_packet_denoise` | `wavelet_packet_denoise(signal: np.ndarray, wavelet: str = "db8", level: int = 3, energy_threshold_ratio: float = 0.05)` | `np.ndarray` | 小波包降噪 |
| `compute_mswpee` | `compute_mswpee(signal: np.ndarray, fs: float, wavelet: str = "db8", level: int = 3, scales: List[int] = [1,2,3])` | `dict` | 多尺度小波包能量熵 |

---

## 16. 其他诊断模块

### 16.1 健康度评分 (diagnosis/health_score.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_compute_health_score` | `_compute_health_score(deductions: Dict[str, float], base_score: float = 100.0)` | `int` | 综合健康度评分 (0-100) |
| `get_ds_label` | `get_ds_label(ds_fusion_result: Optional[Dict]) -> Optional[str]` | `Optional[str]` | 从D-S融合结果提取标签 |
| `is_ds_conflict_high` | `is_ds_conflict_high(ds_fusion_result: Optional[Dict]) -> bool` | `bool` | 判断D-S冲突是否过高 |

### 16.2 健康度连续扣分 (diagnosis/health_score_continuous.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `sigmoid_deduction` | `sigmoid_deduction(value: float, threshold: float, steepness: float = 1.0, max_deduction: float = 30.0)` | `float` | Sigmoid平滑扣分 |
| `multi_threshold_deduction` | `multi_threshold_deduction(value: float, thresholds: List[Tuple[float, float]])` | `float` | 多阈值阶梯扣分 |
| `cascade_deduction` | `cascade_deduction(value: float, threshold: float, ratio: float = 0.5, max_deduction: float = 30.0)` | `float` | 级联递进扣分 |
| `compute_continuous_deductions` | `compute_continuous_deductions(time_features: Dict, bearing_indicators: Dict, gear_indicators: Dict)` | `Dict[str, float]` | 连续扣分计算入口 |

### 16.3 诊断建议 (diagnosis/recommendation.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_generate_recommendation` | `_generate_recommendation(deductions: Dict[str, float], bearing_indicators: Dict, gear_indicators: Dict, fault_label: str, health_score: int)` | `str` | 生成维护建议 |
| `_generate_recommendation_all` | `_generate_recommendation_all(bearing_results: Dict, gear_results: Dict, status: str) -> str` | `str` | 多方法综合建议 |
| `_summarize_all_methods` | `_summarize_all_methods(bearing_results: Dict, gear_results: Dict)` | `dict` | 多方法结果汇总 |

### 16.4 阶次跟踪 (diagnosis/order_tracking.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `_compute_order_spectrum` | `_compute_order_spectrum(signal: np.ndarray, fs: float, rot_freq: float, samples_per_rev: int = 1024, max_order: int = 50)` | `Tuple` | 单帧阶次跟踪（恒速） |
| `_compute_order_spectrum_multi_frame` | `_compute_order_spectrum_multi_frame(signal: np.ndarray, fs: float, rot_freq: float, ...)` | `Tuple` | 多帧平均阶次跟踪 |
| `_compute_order_spectrum_varying_speed` | `_compute_order_spectrum_varying_speed(signal: np.ndarray, fs: float, ...)` | `Tuple` | 变速阶次跟踪（STFT+等相位重采样） |

### 16.5 盲源分离 (diagnosis/bss.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `fast_ica` | `fast_ica(X: np.ndarray, n_components: Optional[int] = None, max_iter: int = 200, tol: float = 1e-4)` | `np.ndarray` | FastICA算法 |
| `vmd_ica_separation` | `vmd_ica_separation(signal: np.ndarray, fs: int, K: int = 5, alpha: int = 2000, ...)` | `np.ndarray` | VMD+ICA单通道扩展盲分离 |

### 16.6 LMS自适应滤波 (diagnosis/lms_filter.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `lms_filter` | `lms_filter(signal: np.ndarray, reference: np.ndarray, filter_order: int = 32, mu: float = 0.01)` | `np.ndarray` | LMS自适应滤波 |
| `nlms_filter` | `nlms_filter(signal: np.ndarray, reference: np.ndarray, filter_order: int = 32, mu: float = 0.01)` | `np.ndarray` | 归一化LMS |
| `vsslms_filter` | `vsslms_filter(signal: np.ndarray, reference: np.ndarray, filter_order: int = 32, ...)` | `np.ndarray` | 变步长LMS |

### 16.7 MCKD解卷积 (diagnosis/mckd.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `mckd_deconvolution` | `mckd_deconvolution(signal: np.ndarray, filter_len: int = 30, T: int = 1, M: int = 1, max_iter: int = 30)` | `np.ndarray` | MCKD最大相关峭度解卷积 |
| `mckd_envelope_analysis` | `mckd_envelope_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | MCKD+包络分析 |

### 16.8 轴承循环平稳分析 (diagnosis/bearing_cyclostationary.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `bearing_sc_scoh_analysis` | `bearing_sc_scoh_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | 谱相关/谱相干循环平稳分析 |

### 16.9 基于模态分解的轴承分析 (diagnosis/modality_bearing.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `emd_bearing_analysis` | `emd_bearing_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | EMD敏感IMF包络分析 |
| `ceemdan_bearing_analysis` | `ceemdan_bearing_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | CEEMDAN敏感IMF包络分析 |
| `vmd_bearing_analysis` | `vmd_bearing_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | VMD敏感模态包络分析 |

### 16.10 基于小波的轴承分析 (diagnosis/wavelet_bearing.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `wavelet_packet_bearing_analysis` | `wavelet_packet_bearing_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | 小波包敏感节点包络分析 |
| `dwt_bearing_analysis` | `dwt_bearing_analysis(signal: np.ndarray, fs: int, bearing_params: Optional[dict] = None, ...)` | `dict` | DWT细节系数包络分析 |

### 16.11 敏感分量选择 (diagnosis/sensitive_selector.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `score_components` | `score_components(components: List[np.ndarray], original: np.ndarray, fs: float, target_freq: Optional[float] = None, weights: Optional[Dict] = None)` | `List[float]` | 综合评分 |
| `select_top_components` | `select_top_components(...)` | `List[Tuple]` | 选择Top-K敏感分量 |
| `select_wp_sensitive_nodes` | `select_wp_sensitive_nodes(signal: np.ndarray, fs: float, level: int = 3)` | `List[int]` | 选择小波包敏感节点 |
| `select_emd_sensitive_imfs` | `select_emd_sensitive_imfs(imfs: List[np.ndarray], original: np.ndarray, fs: float)` | `List[int]` | 选择EMD敏感IMF |
| `select_vmd_sensitive_modes` | `select_vmd_sensitive_modes(modes: np.ndarray, original: np.ndarray, fs: float)` | `List[int]` | 选择VMD敏感模态 |

### 16.12 D-S证据融合 (diagnosis/fusion/ds_fusion.py)

| 函数/类 | 签名 | 返回值 | 功能说明 |
|---------|------|--------|----------|
| `EvidenceFrame` | `class EvidenceFrame` | — | 证据框架类 |
| `BPA` | `class BPA` | — | 基本概率分配类 |
| `dempster_combination` | `dempster_combination(bpa1: BPA, bpa2: BPA) -> Tuple[BPA, float]` | `Tuple` | Dempster组合规则 |
| `murphy_average_combination` | `murphy_average_combination(bpas: List[BPA]) -> Tuple[BPA, float]` | `Tuple` | Murphy平均法（高冲突回退） |
| `build_bpa_from_method` | `build_bpa_from_method(hits: Dict, method_key: str)` | `BPA` | 从方法结果构建BPA |
| `build_time_domain_bpa` | `build_time_domain_bpa(time_features: Dict)` | `BPA` | 时域特征BPA |
| `dempster_shafer_fusion` | `dempster_shafer_fusion(method_results: List[Dict], time_features: Optional[Dict] = None)` | `dict` | D-S融合入口 |

### 16.13 趋势预测 (diagnosis/trend_prediction.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `holt_winters_forecast` | `holt_winters_forecast(data: List[float], horizon: int = 5, seasonal_period: Optional[int] = None)` | `List[float]` | Holt-Winters三阶指数平滑预测 |
| `kalman_smooth_health_scores` | `kalman_smooth_health_scores(scores: List[float], process_var: float = 1.0, measure_var: float = 4.0)` | `List[float]` | Kalman滤波平滑健康度 |

### 16.14 概率校准 (diagnosis/probability_calibration.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `calibrate_fault_probabilities` | `calibrate_fault_probabilities(raw_probs: Dict[str, float], time_features: Optional[Dict] = None)` | `dict` | 故障概率校准入口 |
| `calibrate_snr_to_prob` | `calibrate_snr_to_prob(snr: float, fault_type: str = "generic") -> float` | `float` | SNR转概率 |

### 16.15 通道共识 (diagnosis/channel_consensus.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `cross_channel_consensus` | `cross_channel_consensus(channel_results: List[Dict]) -> dict` | `dict` | 多通道诊断结果交叉验证 |

### 16.16 Savitzky-Golay平滑 (diagnosis/savgol_denoise.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `sg_denoise` | `sg_denoise(signal: np.ndarray, window_length: int = 51, polyorder: int = 3)` | `np.ndarray` | S-G多项式平滑 |
| `sg_trend_residual` | `sg_trend_residual(signal: np.ndarray, window_length: int = 501)` | `Tuple` | 趋势提取+残余分离 |

### 16.17 轴承边频分析 (diagnosis/bearing_sideband.py)

| 函数 | 签名 | 返回值 | 功能说明 |
|------|------|--------|----------|
| `compute_sideband_density` | `compute_sideband_density(envelope_freq, envelope_amp, fault_freq: float, rot_freq: float)` | `dict` | 计算边频密度 |
| `evaluate_bearing_sideband_features` | `evaluate_bearing_sideband_features(...)` | `dict` | 轴承边频特征评估 |
