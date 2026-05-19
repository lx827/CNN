# 诊断算法分层测试架构

> 诊断功能由多层依赖组成。测试必须按依赖顺序：Layer 1 → Layer 2 → Layer 3 → Layer 4 → Layer 5。
> Layer N 出错时，先查 Layer N-1 是否全部通过，以排除底层问题。

---

## 完整依赖关系图（基于实际 import 链）

```
Layer 5: 应用入口
  ensemble.py ──→ engine, features, health_score, recommendation
  analyzer.py ──→ engine, features, order_tracking, rule_based, channel_consensus
  │
Layer 4: 中央调度器
  engine.py ──→ signal_utils, order_tracking, bearing, gear,
                preprocessing, vmd_denoise, features, health_score, recommendation
  │
Layer 3: 模块聚合
  gear/__init__.py ──→ signal_utils, .metrics, .msb, .planetary_demod, .vmd_demod
  │
Layer 2: 特征提取 & 复杂信号处理（依赖 Layer 1）
  features.py ──→ signal_utils
  bearing.py  ──→ signal_utils, preprocessing
  order_tracking.py ──→ signal_utils
  preprocessing.py ──→ signal_utils, vmd_denoise
  gear/metrics.py ──→ signal_utils
  gear/planetary_demod.py ──→ signal_utils, order_tracking, .metrics
  health_score.py ──→ health_score_continuous
  rule_based.py ──→ features, order_tracking
  │
Layer 1: 信号处理基元（零内部依赖）
  signal_utils.py             (prepare_signal, FFT, 转频估计, 谱峰搜索)
  vmd_denoise.py              (VMD分解)
  health_score_continuous.py  (连续扣分)
  bearing_sideband.py         (边带分析)
  channel_consensus.py        (通道一致性)
  recommendation.py           (建议生成)
  gear/msb.py                 (调制双谱)
  savgol_denoise.py           (S-G多项式平滑)
  wavelet_packet.py           (小波包能量熵)
  bearing_cyclostationary.py  (谱相关/谱相干)
  modality_bearing.py         (EMD/CEEMDAN/VMD轴承诊断)
  sensitive_selector.py       (敏感分量评分选择)
  trend_prediction.py         (Holt-Winters/Kalman趋势预测)
  probability_calibration.py  (概率校准/SNR→概率)
```

**每个 import 箭头代表"如果被依赖模块出错，依赖它的模块必然出错"。**

---

## 测试目录结构

```
tests/diagnosis/foundation/
├── layer1/                           # Layer 1 信号基元
│   ├── synthetic_signals.py          # 合成信号生成器（含 ground truth）
│   ├── test_signal_utils_correctness.py
│   ├── test_vmd_denoise_correctness.py
│   ├── test_health_score_continuous.py
│   ├── test_bearing_sideband.py
│   ├── test_channel_consensus.py
│   ├── test_recommendation.py
│   ├── test_msb_correctness.py
│   ├── test_savgol_denoise_correctness.py
│   ├── test_wavelet_packet_correctness.py
│   ├── test_bearing_cyclostationary_correctness.py
│   ├── test_modality_bearing_correctness.py
│   ├── test_sensitive_selector_correctness.py
│   ├── test_trend_prediction_correctness.py
│   ├── test_probability_calibration_correctness.py
│   └── plot_results.py
├── layer2/                           # Layer 2 特征提取 & 信号处理
│   ├── test_features_correctness.py
│   ├── test_bearing_correctness.py
│   ├── test_bearing_advanced_correctness.py
│   ├── test_preprocessing_correctness.py
│   ├── test_preprocessing_cascade_correctness.py
│   ├── test_gear_metrics_correctness.py
│   ├── test_order_tracking_correctness.py
│   ├── test_health_score_correctness.py
│   ├── test_rule_based_correctness.py
│   ├── test_planetary_demod_correctness.py
│   ├── LAYER2_ISSUES.md
│   └── plot_results.py
├── layer3/                           # Layer 3 模块聚合 & 集成调度
│   ├── test_engine_integration.py
│   ├── test_ensemble_integration.py
│   ├── test_analyzer_integration.py
│   ├── LAYER3_ISSUES.md
│   └── plot_results.py
├── layer4/                           # Layer 4 中央调度器深层
│   ├── test_engine_deep.py
│   └── plot_results.py
├── layer5/                           # Layer 5 应用入口辅助函数
│   ├── test_ensemble_helpers.py
│   ├── test_analyzer_helpers.py
│   └── plot_results.py
└── output/                           # 旧测试输出（兼容保留）
    └── plots/
```

---

## 测试覆盖矩阵（完整 — 按依赖层排列）

### Layer 1 — 信号基元（零依赖，先测）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `signal_utils` | `prepare_signal` (去直流/去趋势) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `estimate_rot_freq_spectrum` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `find_peaks_in_spectrum` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `compute_fft_spectrum` (FFT 幅值谱) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `rms`, `peak_value`, `kurtosis`, `skewness` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `bandpass_filter`, `highpass_filter`, `lowpass_filter` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `parabolic_interpolation` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `zoom_fft_analysis` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `vmd_denoise` | `vmd_decompose` / `vmd_denoise` / `vmd_select_impact_mode` | `layer1/test_vmd_denoise_correctness.py` | ✅ |
| `health_score_continuous` | `sigmoid_deduction` / `multi_threshold_deduction` / `cascade_deduction` / `compute_continuous_deductions` | `layer1/test_health_score_continuous.py` | ✅ |
| `bearing_sideband` | `compute_sideband_density` | `layer1/test_bearing_sideband.py` | ✅ |
| `channel_consensus` | `cross_channel_consensus` | `layer1/test_channel_consensus.py` | ✅ |
| `recommendation` | `_generate_recommendation` / `_match_suggestion` | `layer1/test_recommendation.py` | ✅ |
| `gear/msb` | `msb_residual_sideband_analysis` | `layer1/test_msb_correctness.py` | ✅ |
| `savgol_denoise` | `sg_denoise` / `sg_trend_residual` | `layer1/test_savgol_denoise_correctness.py` | ✅ |
| `wavelet_packet` | `wavelet_packet_decompose` / `compute_wavelet_packet_energy_entropy` / `wavelet_packet_denoise` / `compute_mswpee` | `layer1/test_wavelet_packet_correctness.py` | ✅ |
| `bearing_cyclostationary` | `_compute_sc_scoh_bearing` / `bearing_sc_scoh_analysis` | `layer1/test_bearing_cyclostationary_correctness.py` | ✅ |
| `modality_bearing` | `emd_bearing_analysis` / `ceemdan_bearing_analysis` / `vmd_bearing_analysis` | `layer1/test_modality_bearing_correctness.py` | ✅ |
| `sensitive_selector` | `score_components` / `select_top_components` / `select_emd_sensitive_imfs` / `select_vmd_sensitive_modes` | `layer1/test_sensitive_selector_correctness.py` | ✅ |
| `trend_prediction` | `holt_winters_forecast` / `kalman_smooth_health_scores` | `layer1/test_trend_prediction_correctness.py` | ✅ |
| `probability_calibration` | `calibrate_fault_probabilities` / `_sigmoid_prob` / `calibrate_snr_to_prob` | `layer1/test_probability_calibration_correctness.py` | ✅ |

### Layer 2 — 特征提取 & 信号处理（依赖 Layer 1）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `features` | `_compute_bearing_fault_freqs` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `_compute_bearing_fault_orders` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_time_features` (peak/rms/kurt/crest…) | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_fft_features` (mesh freq, sidebands) | `layer2/test_features_correctness.py` | ✅ |
| `features` | `has_bearing_params` / `has_gear_params` | `layer2/test_features_correctness.py` | ✅ |
| `bearing` | `envelope_analysis` (Hilbert 包络) | `layer2/test_bearing_correctness.py` | ✅ |
| `bearing` | `fast_kurtogram` (谱峭度选带) | `layer2/test_bearing_correctness.py` | ✅ |
| `bearing` | `cpw_envelope_analysis` (倒频谱预白化) | `layer2/test_bearing_advanced_correctness.py` | ✅ |
| `bearing` | `med_envelope_analysis` (最小熵解卷积) | `layer2/test_bearing_correctness.py` | ✅ |
| `bearing` | `teager_envelope_analysis` (Teager 算子) | `layer2/test_bearing_correctness.py` | ✅ |
| `bearing` | `spectral_kurtosis_envelope_analysis` | `layer2/test_bearing_correctness.py` | ✅ |
| `bearing` | `mckd_envelope_analysis` (MCKD) | `layer2/test_bearing_advanced_correctness.py` | ✅ |
| `bearing` | `bearing_sc_scoh_analysis` (循环平稳) | `layer2/test_bearing_advanced_correctness.py` | ✅ |
| `order_tracking` | `_compute_order_spectrum` | `layer2/test_order_tracking_correctness.py` | ✅ |
| `order_tracking` | `_compute_order_spectrum_multi_frame` | `layer2/test_order_tracking_correctness.py` | ✅ |
| `order_tracking` | `_compute_order_spectrum_varying_speed` | `layer2/test_order_tracking_correctness.py` | ✅ |
| `preprocessing` | `wavelet_denoise` | `layer2/test_preprocessing_correctness.py` | ✅ |
| `preprocessing` | `cepstrum_pre_whitening` | `layer2/test_preprocessing_correctness.py` | ✅ |
| `preprocessing` | `minimum_entropy_deconvolution` | `layer2/test_preprocessing_correctness.py` | ✅ |
| `preprocessing` | `cascade_wavelet_vmd` | `layer2/test_preprocessing_cascade_correctness.py` | ✅ |
| `preprocessing` | `cascade_wavelet_lms` | `layer2/test_preprocessing_cascade_correctness.py` | ✅ |
| `gear/metrics` | `compute_tsa_residual_order` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/metrics` | `compute_fm0` / `compute_fm4` / `compute_car` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/metrics` | `compute_ser_order` / `analyze_sidebands` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/planetary_demod` | 行星箱 VMD/SC/SCoh/CVS 解调 | `layer2/test_planetary_demod_correctness.py` | ✅ |
| `rule_based` | `_rule_based_analyze` | `layer2/test_rule_based_correctness.py` | ✅ |
| `health_score` | `_compute_health_score` | `layer2/test_health_score_correctness.py` | ✅ |

### Layer 3 — 模块聚合 & 集成调度（依赖 Layer 1+2）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `engine` | `analyze_bearing` (分发 13 种轴承方法) | `layer3/test_engine_integration.py` | ✅ |
| `engine` | `analyze_gear` (分发 2 种齿轮方法) | `layer3/test_engine_integration.py` | ✅ |
| `engine` | `analyze_comprehensive` | `layer3/test_engine_integration.py` | ✅ |
| `ensemble` | `run_research_ensemble` | `layer3/test_ensemble_integration.py` | ✅ |
| `analyzer` | `analyze_device` | `layer3/test_analyzer_integration.py` | ✅ |

### Layer 4 — 中央调度器深层（依赖 Layer 2+3）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `engine` | `preprocess` (多 denoise 方法分支) | `layer4/test_engine_deep.py` | ✅ |
| `engine` | `_estimate_rot_freq` (转频估计 + 回退) | `layer4/test_engine_deep.py` | ✅ |
| `engine` | `analyze_all_methods` | — | ⚠️ 需数据集 |

### Layer 5 — 应用入口辅助函数（依赖 Layer 1-4）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `ensemble` | `_bearing_confidence` | `layer5/test_ensemble_helpers.py` | ✅ |
| `ensemble` | `_gear_confidence` | `layer5/test_ensemble_helpers.py` | ✅ |
| `ensemble` | `_time_confidence` | `layer5/test_ensemble_helpers.py` | ✅ |
| `ensemble` | `_fault_label` | `layer5/test_ensemble_helpers.py` | ✅ |
| `analyzer` | `_safe_result` | `layer5/test_analyzer_helpers.py` | ✅ |

### 统计

| 状态 | 数量 |
|:--:|------|
| ✅ 已覆盖 | **66** |
| ⚠️ 需数据集 | 1 |
| ❌ 未覆盖 | **0** |

---

## 运行方式

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate

# Layer 1
python ../tests/diagnosis/foundation/layer1/test_signal_utils_correctness.py
python ../tests/diagnosis/foundation/layer1/test_vmd_denoise_correctness.py
python ../tests/diagnosis/foundation/layer1/test_health_score_continuous.py
python ../tests/diagnosis/foundation/layer1/test_bearing_sideband.py
python ../tests/diagnosis/foundation/layer1/test_channel_consensus.py
python ../tests/diagnosis/foundation/layer1/test_recommendation.py
python ../tests/diagnosis/foundation/layer1/test_msb_correctness.py
python ../tests/diagnosis/foundation/layer1/test_savgol_denoise_correctness.py
python ../tests/diagnosis/foundation/layer1/test_wavelet_packet_correctness.py
python ../tests/diagnosis/foundation/layer1/test_bearing_cyclostationary_correctness.py
python ../tests/diagnosis/foundation/layer1/test_modality_bearing_correctness.py
python ../tests/diagnosis/foundation/layer1/test_sensitive_selector_correctness.py
python ../tests/diagnosis/foundation/layer1/test_trend_prediction_correctness.py
python ../tests/diagnosis/foundation/layer1/test_probability_calibration_correctness.py

# Layer 2
python ../tests/diagnosis/foundation/layer2/test_features_correctness.py
python ../tests/diagnosis/foundation/layer2/test_bearing_correctness.py
python ../tests/diagnosis/foundation/layer2/test_bearing_advanced_correctness.py
python ../tests/diagnosis/foundation/layer2/test_preprocessing_correctness.py
python ../tests/diagnosis/foundation/layer2/test_preprocessing_cascade_correctness.py
python ../tests/diagnosis/foundation/layer2/test_gear_metrics_correctness.py
python ../tests/diagnosis/foundation/layer2/test_order_tracking_correctness.py
python ../tests/diagnosis/foundation/layer2/test_health_score_correctness.py
python ../tests/diagnosis/foundation/layer2/test_rule_based_correctness.py
python ../tests/diagnosis/foundation/layer2/test_planetary_demod_correctness.py

# Layer 3
python ../tests/diagnosis/foundation/layer3/test_engine_integration.py
python ../tests/diagnosis/foundation/layer3/test_ensemble_integration.py
python ../tests/diagnosis/foundation/layer3/test_analyzer_integration.py

# Layer 4
python ../tests/diagnosis/foundation/layer4/test_engine_deep.py

# Layer 5
python ../tests/diagnosis/foundation/layer5/test_ensemble_helpers.py
python ../tests/diagnosis/foundation/layer5/test_analyzer_helpers.py

# 绘图（独立运行，不重跑分析）
python ../tests/diagnosis/foundation/layer1/plot_results.py
python ../tests/diagnosis/foundation/layer2/plot_results.py
python ../tests/diagnosis/foundation/layer3/plot_results.py
python ../tests/diagnosis/foundation/layer4/plot_results.py
python ../tests/diagnosis/foundation/layer5/plot_results.py
```
