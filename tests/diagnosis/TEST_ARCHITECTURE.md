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
| `signal_utils` | `remove_dc` / `linear_detrend` / `prepare_signal` (去直流/去趋势) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `estimate_rot_freq_spectrum` / `estimate_rot_freq_envelope` / `estimate_rot_freq_autocorr` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `find_peaks_in_spectrum` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `compute_fft_spectrum` / `compute_power_spectrum` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `rms` / `peak_value` / `kurtosis` / `skewness` / `crest_factor` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `bandpass_filter` / `highpass_filter` / `lowpass_filter` / `lowpass_filter_complex` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `compute_snr` (委托 `_compute_peak_snr`) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `parabolic_interpolation` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `zoom_fft_analysis` | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `_search_peak_in_band` (原子函数) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `_estimate_background` (原子函数) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `_compute_peak_snr` (原子函数) | `layer1/test_signal_utils_correctness.py` | ✅ |
| `signal_utils` | `_estimate_noise_mad` (原子函数, 2025-05新增) | `layer1/test_signal_utils_correctness.py` | △ 间接 — 无直接单元测试，经 savgol/preprocessing 间接覆盖 |
| `signal_utils` | `_snr_by_residual_std` (原子函数, 2025-05新增) | `layer1/test_signal_utils_correctness.py` | △ 间接 — 无直接单元测试，经 savgol `snr_improvement` 间接覆盖 |
| `vmd_denoise` | `vmd_decompose` / `vmd_denoise` / `vmd_select_impact_mode` | `layer1/test_vmd_denoise_correctness.py` | ✅ |
| `health_score_continuous` | `sigmoid_deduction` / `multi_threshold_deduction` / `cascade_deduction` / `compute_continuous_deductions` | `layer1/test_health_score_continuous.py` | ✅ |
| `bearing_sideband` | `compute_sideband_density` / `evaluate_bearing_sideband_features` | `layer1/test_bearing_sideband.py` | ✅ |
| `channel_consensus` | `cross_channel_consensus` | `layer1/test_channel_consensus.py` | ✅ |
| `recommendation` | `_generate_recommendation` / `_match_suggestion` | `layer1/test_recommendation.py` | ✅ |
| `gear/msb` | `msb_residual_sideband_analysis` | `layer1/test_msb_correctness.py` | ✅ |
| `savgol_denoise` | `sg_denoise` / `sg_trend_residual` | `layer1/test_savgol_denoise_correctness.py` | ✅ |
| `wavelet_packet` | `wavelet_packet_decompose` / `compute_wavelet_packet_energy_entropy` / `wavelet_packet_denoise` / `compute_mswpee` | `layer1/test_wavelet_packet_correctness.py` | ✅ |
| `bearing_cyclostationary` | `_compute_sc_scoh_bearing` / `bearing_sc_scoh_analysis` | `layer1/test_bearing_cyclostationary_correctness.py` | ✅ |
| `modality_bearing` | `emd_bearing_analysis` / `ceemdan_bearing_analysis` / `vmd_bearing_analysis` | `layer1/test_modality_bearing_correctness.py` | ✅ |
| `sensitive_selector` | `compute_correlation` / `compute_envelope_entropy` / `compute_energy_ratio` / `compute_center_freq` / `compute_freq_match_score` (原子评分) | `layer1/test_sensitive_selector_correctness.py` | ✅ |
| `sensitive_selector` | `score_components` / `select_top_components` | `layer1/test_sensitive_selector_correctness.py` | ✅ |
| `sensitive_selector` | `select_wp_sensitive_nodes` / `select_emd_sensitive_imfs` / `select_vmd_sensitive_modes` | `layer1/test_sensitive_selector_correctness.py` | ✅ |
| `trend_prediction` | `holt_winters_forecast` / `kalman_smooth_health_scores` | `layer1/test_trend_prediction_correctness.py` | ✅ |
| `probability_calibration` | `calibrate_fault_probabilities` / `_sigmoid_prob` / `calibrate_snr_to_prob` | `layer1/test_probability_calibration_correctness.py` | ✅ |

### Layer 2 — 特征提取 & 信号处理（依赖 Layer 1）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `features` | `_compute_bearing_fault_freqs` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `_compute_bearing_fault_orders` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_time_features` (peak/rms/kurt/crest…) | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_fft_features` (mesh freq, sidebands) / `compute_envelope_features` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_channel_features` / `compute_fft` / `compute_imf_energy` | `layer2/test_features_correctness.py` | ✅ |
| `features` | `compute_nonparam_cusum_features` | `layer2/test_features_correctness.py` | ✅ |
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
| `preprocessing` | `joint_denoise` (联合去噪) | `layer2/test_preprocessing_correctness.py` | ✅ |
| `preprocessing` | `cascade_wavelet_vmd` | `layer2/test_preprocessing_cascade_correctness.py` | ✅ |
| `preprocessing` | `cascade_wavelet_lms` | `layer2/test_preprocessing_cascade_correctness.py` | ✅ |
| `gear/metrics` | `compute_tsa_residual_order` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/metrics` | `compute_fm0_order` / `compute_fm4` / `compute_car` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/metrics` | `compute_m6a` / `compute_m8a` / `compute_na4` / `compute_nb4` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/metrics` | `compute_ser_order` / `analyze_sidebands_order` / `analyze_sidebands_zoom_fft` | `layer2/test_gear_metrics_correctness.py` | ✅ |
| `gear/planetary_demod` | `planetary_envelope_order_analysis` / `planetary_fullband_envelope_order_analysis` | `layer2/test_planetary_demod_correctness.py` | ✅ |
| `gear/planetary_demod` | `planetary_vmd_demod_analysis` / `planetary_tsa_envelope_analysis` | `layer2/test_planetary_demod_correctness.py` | ✅ |
| `gear/planetary_demod` | `planetary_hp_envelope_order_analysis` / `planetary_sc_scoh_analysis` | `layer2/test_planetary_demod_correctness.py` | ✅ |
| `gear/planetary_demod` | `planetary_msb_analysis` / `planetary_cvs_med_analysis` | `layer2/test_planetary_demod_correctness.py` | ✅ |
| `gear/planetary_demod` | `evaluate_planetary_demod_results` (结果评估) | `layer2/test_planetary_demod_correctness.py` | ✅ |
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
| ✅ 已覆盖 | **79** (含间接覆盖) |
| △ 间接覆盖 | **2** (`_estimate_noise_mad`, `_snr_by_residual_std`) |
| ⚠️ 需数据集 | 1 |
| ❌ 未覆盖 | **0** |
| 📋 公共函数总数 | 85 |

---

## 测试绘图设计规范（图即判定）

> 设计目标：**任何人看 3 秒钟就能回答"这个功能对不对"**，不需要读代码、不需要懂振动诊断。
>
> 核心原则：**图不是"结果展示"，而是"正确性证明"**。

### 为什么需要这个规范

当前测试绘图常见的问题：

| 问题类型 | 典型表现 | 后果 |
|---------|---------|------|
| **无 Ground Truth** | 只画"检出峰值"，不画"理论值该在哪" | 不知道偏差多少算对 |
| **无阈值线** | 只画 SNR 柱状图，不标判定线 | 不知道哪个算通过 |
| **状态不直观** | 用颜色深浅表示，没有 ✓/✗ | 色盲 / 截图压缩后无法分辨 |
| **图与判定脱节** | 画了漂亮的频谱，但 test 的 passed 是另一套逻辑 | 图对了但测试挂了，看不懂为什么 |
| **Layer 4/5 过于简陋** | 只有绿/红横条 | 完全不知道测了什么、为什么失败 |
| **降噪类只画波形** | "看起来干净了"，但无量化指标 | 视觉上干净 ≠ 算法正确 |

### 全局视觉语义（所有 Layer 强制统一）

```python
# 颜色编码 —— 必须在每张图的标题或图例中声明判定标准
COLOR_PASS    = '#52C41A'  # 绿 = 通过 / 正确 / 健康 / 在容差内
COLOR_FAIL    = '#FF4D4F'  # 红 = 失败 / 错误 / 故障 / 超容差
COLOR_GT      = '#D9D9D9'  # 灰 = Ground Truth / 理论值 / 期望范围 / 已知标准
COLOR_THRESH  = '#FAAD14'  # 橙 = 阈值线 / 警告边界 / 判定分界线
COLOR_EST     = '#165DFF'  # 蓝 = 算法估计值 / 实际计算结果 / 当前输出

# 文字标记 —— 必须直接标在数据点或子图标题上
MARK_OK = '✓ PASS'         # 通过 —— 用绿色粗体
MARK_NG = '✗ FAIL'         # 失败 —— 用红色粗体
MARK_WARN = '△ WARN'       # 警告 / 边界 —— 用橙色
```

**铁律：每张图必须包含以下至少 3 种元素：**

1. **Ground Truth 参照** —— 理论值、期望范围、已知标准必须在图上可见（不能只在标题文字里）。
2. **判定阈值可视化** —— 用橙色虚线画出通过/失败的边界，并配文字说明（如 `"SNR>3 为通过"`）。
3. **通过状态直接标记** —— 每个数据点或每组数据必须有 ✓/✗ 标记（或颜色编码），不能只在图例里说明。
4. **定量差异标注** —— 相对误差百分比、绝对差值、SNR 数值必须直接写在图上对应位置。
5. **判定标准写入标题** —— 图标题必须包含"怎样算对"，例如 `"频率检出 — 误差<5%或<Δf/2为通过"`。

---

### Layer 1 — 信号基元：数学精度可视化

> Layer 1 是纯数学运算。正确性 = 计算值与理论值的重合度。图必须能量化误差，不能只是"看起来对"。

#### 1.1 时域/频域基元（signal_utils, filters, FFT, interpolation）

| 功能类别 | 推荐图类型 | 图上必须出现的元素 |
|---------|-----------|-------------------|
| `prepare_signal` | **时域波形对比**（原始 vs 处理后，并排） | ① 原始信号的 DC 值标注；② 处理后理论应为 0 的参考线（`axhline(y=0)`）；③ 残余误差 RMS 标注在图上；④ 去趋势后的线性拟合斜率标注（应≈0）。 |
| `bandpass/lowpass/highpass` | **频谱对比图**（原始 + 滤波后 + 标注） | ① 原始混合信号频谱（灰色，透明度 0.5）；② 滤波后频谱（蓝色）；③ **通带区域用绿色半透明阴影标注**，并写 `"通带 150-250Hz"`；④ **阻带理论衰减线**（橙色虚线，如 `-40dB`）；⑤ 被保留的频率峰值用虚线标注 `"保留 200Hz"`。 |
| `compute_fft_spectrum` | **频率检出精度放大图** | ① 理论频率（红色虚线，`axvline`）；② FFT 粗峰值位置（橙色点）；③ **频率分辨率 Δf 直接标注**（如 `Δf=0.5Hz`）；④ 误差百分比写在峰值旁（`误差=0.3% ✓`）；⑤ 图标题包含判定标准 `"误差<Δf/2 为通过"`。 |
| `parabolic_interpolation` | **亚 bin 精度对比图**（局部放大） | ① 真实频率（红色虚线，粗线）；② FFT 粗 bin 峰值（橙色点 + 标注 `"FFT=100Hz, 误差=0.7Hz"`）；③ 插值结果（蓝色点 + 标注 `"插值=100.3Hz, 误差=0.02Hz ✓"`）；④ 三个值在图上用不同线型区隔。 |
| `find_peaks_in_spectrum` | **谐波族搜索标记图** | ① 频谱基线（蓝色细线）；② 基频用红色大圆点（`scatter, s=80`）；③ 谐波用橙色菱形（`marker='D'`）；④ 每个谐波旁标注 `"2×, SNR=12dB"`；⑤ 缺失的谐波用灰色虚线标注 `"3× 未检出 △"`。 |

**Layer 1 绘图示例（统计指标）：**

```
图标题：统计指标验证 — 期望值 vs 计算值（|相对误差|<5%为通过）

  期望值(灰)  实际值(蓝)    判定标注
     ┃          ┃
   ████       ████   ← Δ=0.3% ✓（绿色，标在柱子上方）
   ████       ████
   ─────────────────
    峭度        RMS
    
  每个柱子上方直接写：
    - 相对误差百分比
    - 绿色 ✓ 或 红色 ✗
    - 判定依据（如"理论=3.0，实际=3.02"）
```

#### 1.2 统计指标（kurtosis, rms, crest, skewness...）

- **必须并排对比**：期望值（灰色柱） vs 实际值（蓝色柱）。
- **必须在每个柱子上方标注**：相对误差百分比 + ✓/✗。
- **必须画参考线**：峭度理论=3（橙色虚线 + `"高斯信号峭度=3"`）；偏度理论=0。
- **crest_factor 正弦信号**：理论值≈√2，图上必须标注 `"理论≈1.414"`。

#### 1.3 去噪类算法（VMD, wavelet, S-G, EMD...）

> 去噪类不能只画"时域波形看起来干净了"，必须**量化与 ground truth 的相似度**。

**推荐图类型：三栏对比图 + 量化指标栏**

```
┌─────────────────┬─────────────────┬─────────────────┐
│   纯净信号(已知GT) │   加噪信号(输入)   │   降噪后输出     │
│   (绿色边框)      │   (红色边框)      │   (蓝色边框)    │
├─────────────────┼─────────────────┼─────────────────┤
│   时域波形        │   时域波形        │   时域波形       │
│   + 频谱         │   + 频谱         │   + 频谱        │
└─────────────────┴─────────────────┴─────────────────┘

图下方统一标注（黑色粗体）：
  SNR_before = 5.2dB  →  SNR_after = 18.6dB  (提升 13.4dB ✓)
  与GT相关系数 r = 0.94  (阈值>0.9, 通过 ✓)
  频谱峰值频率偏差：0.1Hz  (阈值<Δf, 通过 ✓)
```

**必须包含的量化指标（至少 2 个）：**

- SNR 提升（dB）
- 与纯净信号的相关系数
- 特征频率保留精度（如主峰频率偏差）
- 时域波形保真度（如 MSE 或波形相似系数）

#### 1.4 VMD 分解（vmd_decompose）

- **必须画原始信号频谱**（灰色），标注各分量理论频率（红色虚线）。
- **每个 IMF 子图**必须标注峰值频率，并与理论频率对比写误差。
- **必须验证分离度**：相邻 IMF 的主频差应 > 最小频率间隔，用表格或子图标题标注。

#### 1.5 转频估计（estimate_rot_freq_*）

- **必须画真实转速对比**：理论值（灰色柱/线） vs 估计值（蓝色柱/点）。
- **必须标注相对误差百分比**（`误差=2.1% ✓`）。
- **变速工况**：用灰色横带表示期望转速范围，估计值用点标注在带内/带外，并标 ✓/✗。

---

### Layer 2 — 特征提取 & 信号处理：故障特征显著性可视化

> Layer 2 不是测数学精度，而是测"故障特征能不能从噪声中被揪出来"。图必须展示"信噪比"和"特征显著性"，以及"会不会误报"。

#### 2.1 轴承诊断（envelope, kurtogram, MED, CPW, MCKD, Teager...）

**核心图类型：包络谱 + 故障频率标注图（最重要的验证图）**

```
图标题：轴承外圈故障包络谱验证 — BPFO=90.0Hz, SNR>3为通过

  幅值 ↑
       |         ↑ 检出峰值 90.3Hz
       |        /|\    SNR=8.3dB  ✓（绿色，标在峰值旁）
       |       / | \
       |      /  |  \      ┃ BPFO=90.0Hz（理论，橙色虚线）
       |     /   |   \     ┃ ← 必须标注"理论值"
       |    /    |    \
       +----+----+----+----+----+----+→ 频率(Hz)
          30   60   90  120  150  180
       
  [浅绿色阴影区] = 故障频率 ±5% 容差带（标注"通过带"）
  [灰色谱线]     = 包络谱基底
  [蓝色竖线]     = 算法检出的最高峰
  [红色虚线]     = 理论故障频率及其谐波
```

**每张轴承诊断图必须包含：**

1. **理论故障频率线**：BPFO/BPFI/BSF/FTF 用橙色虚线标出，并写 `"BPFO=3.57×fr=89.3Hz"`。
2. **检出峰值标注**：最高峰频率 + 幅值 + SNR 数值，直接写在峰值上方。
3. **SNR 阈值线**：画一条水平橙色虚线 `"SNR=3 阈值"`，峰值超过此线才算通过。
4. **通过状态**：在峰值旁用绿色 `✓` 或红色 `✗` 标出。
5. **容差带**：理论频率 ±5% 区域用浅绿/浅红半透明阴影标出，标注 `"±5%容差"`。

**真实数据测试图（HUSTbear / CW）的额外要求：**

```
每个数据集文件一个子图：
  ┌─────────────────────────────────────┐
  │ 文件名: 0.5X_OR_20Hz-X             │
  │ 已知状态: 外圈故障 (期望检出 BPFO)  │
  │ 包络谱峰值: 91.2Hz, SNR=6.5        │
  │ 判定: ✓ 正确检出 BPFO              │
  └─────────────────────────────────────┘
  
  如果健康文件被误报：
  │ 判定: ✗ 误报！健康文件检出 SNR=4.2 │
```

#### 2.2 阶次跟踪（order_tracking）

**标杆设计（参考现有 `17_cw_variable` 图，应推广为标准）：**

```
CW 变速数据集 — 转频估计验证
─────────────────────────────────────────
灰色横带 = 预期转速范围 [14.1-29.0]Hz（标注在带右侧）
  蓝点 ○  = 频谱法估计值 = 26.3Hz  → 在带内 ✓
  绿菱 ◇  = 阶次跟踪法  = 27.1Hz  → 在带内 ✓
  
右侧大字体标注：
  ✓ = 在预期范围内
  ✗ = 偏离预期范围
  
额外增加：方法一致性列
  两种方法差异 < 20% → 一致 ✓
  两种方法差异 > 20% → 冲突 △（黄色警告）
```

#### 2.3 齿轮诊断指标（FM0, FM4, CAR, SER, TSA）

> 齿轮指标没有单一"理论值"，正确性体现在"健康信号低、故障信号高，且两类有明显分离"。

**推荐图类型：健康 vs 故障 分组对比图**

```
WTgearbox 行星齿轮箱 — FM4 指标验证
─────────────────────────────────────────
        健康(He)  断齿(Br)  缺齿(Mi)  裂纹(Rc)  磨损(We)
FM4:    [灰柱]    [红柱]    [红柱]    [红柱]    [红柱]
        2.1       12.5✓     9.3✓      7.8✓      5.2✓
        
橙色虚线：FM4>5 判定为故障 ─────────────────────────

判定逻辑（必须写在图下方）：
  健康状态 FM4<5 ✓，故障状态 FM4>5 ✓ → 功能正确
  若健康 FM4>5 或 故障 FM4<5 → 标红 ✗
```

**必须画阈值线**：每个指标必须有经验阈值线（橙色虚线），并标注 `"FM4>5 为故障"`。
**必须分组**：同一指标下，健康样本和各类故障样本必须并排，展示分离度。
**必须标注分离度**：计算 `"健康均值 vs 故障均值 的比值"` 或 `"最小间隙"`，写在图标题中。

#### 2.4 齿轮行星箱解调（planetary_demod）

- **必须画太阳轮/行星轮/内齿圈的理论故障频率线**。
- **必须标注各方法（VMD/SC/SCoh/CVS）的故障 SNR**。
- **必须验证方法一致性**：多种解调方法对同一故障的检出结果用表格或热图展示。

#### 2.5 健康度评分（health_score）

- **必须画阈值线**：`warning=80`（橙色虚线）、`fault=50`（红色虚线）。
- **必须按场景分组**：纯健康信号、纯故障信号、混合信号的健康度并排。
- **必须标注状态区域**：0-50 标红底 `"critical"`，50-80 标黄底 `"warning"`，80-100 标绿底 `"normal"`。
- **必须验证单调性**：如果输入故障加重，健康度应下降，画趋势箭头验证。

---

### Layer 3 — 集成调度：多方法一致性可视化

> Layer 3 测的是"调度器能不能把各种方法组织好，得出一致结论"。图必须展示"多种方法是否指向同一结论"，以及"综合结果是否合理"。

#### 3.1 Engine 集成（analyze_bearing / analyze_gear / analyze_comprehensive）

**推荐图类型：方法一致性矩阵（heatmap 或表格可视化）**

```
engine.analyze_bearing() — 13 种方法对同一外圈故障信号的判定一致性
─────────────────────────────────────────────────────────────────
              | BPFO | BPFI | BSF | FTF | 健康 | 置信度 | 结果
──────────────┼──────┼──────┼─────┼─────┼──────┼────────┼──────
envelope      |  ✓   |      |     |     |      |  0.82  | ✓
kurtogram     |  ✓   |      |     |     |      |  0.75  | ✓
MED           |      |  ✓   |     |     |      |  0.68  | △
CPW           |  ✓   |      |     |     |      |  0.71  | ✓
Teager        |  ✓   |      |     |     |      |  0.69  | ✓
...           |      |      |     |     |      |        |
──────────────┼──────┼──────┼─────┼─────┼──────┼────────┼──────
共识投票       |  4票 |  1票 |  0  |  0  |  0   |  0.76  | ✓
─────────────────────────────────────────────────────────────────

颜色语义：
  深绿单元格 = 该方法高置信度检出此故障（>0.7）
  浅绿单元格 = 中置信度检出（0.4-0.7）
  灰色单元格 = 未检出（<0.4）
  红色单元格 = 错误检出（与健康/已知状态冲突）

这张图的价值：
  如果改了 kurtogram 后它突然报 BPFI，一眼看出"共识被破坏"（红色单元格）。
```

#### 3.2 Ensemble 集成（run_research_ensemble）

**推荐图类型：双图组合（雷达图/柱状图 + 区分度散点图）**

```
左图：同一轴承信号、不同去噪方法的健康度一致性
─────────────────────────────────────────
方法：     none    wavelet    VMD      MED
健康度：    85      82        78       80
颜色：     绿      绿        绿       绿
判定：     ✓一致   ✓一致     ✓一致    ✓一致

如果四种方法差异 > 20：
  标黄 △ "方法分歧大，需检查"

右图：健康 vs 故障设备的 ensemble 健康度分布
─────────────────────────────────────────
  健康簇 ● ● ● ●  (hs=88, 92, 85, 90)
  故障簇 ● ● ● ●  (hs=35, 42, 28, 51)
  
  分离度 = min(健康) - max(故障) = 85 - 51 = 34 ✓
  阈值：分离度>20 为通过（橙色虚线标注）
  
  如果健康/故障有重叠：标红 ✗ "无法区分"
```

#### 3.3 Analyzer 集成（analyze_device）

**推荐图类型：多通道综合判定瀑布图**

```
设备 WTG-001 — 多通道综合分析验证
─────────────────────────────────────────
通道1:  ████████░░░░░░░░░░░░  健康度=72 [黄]
        轴承: normal ✓    齿轮: warning △
        
通道2:  ████░░░░░░░░░░░░░░░░  健康度=45 [红]
        轴承: critical ✗  齿轮: warning △
        
─────────────────────────────────────────
综合:   ████░░░░░░░░░░░░░░░░  健康度=45 [红]
        ← 取最差通道（验证保守策略）
        
判定逻辑验证（必须写在图下方）：
  规则：任一通道路轴承 critical → 设备级应为 critical
  实际：通道2轴承 critical → 设备级 critical ✓
  若设备级=72（与通道1相同）→ 标红 ✗ "未保守取最差"
```

---

### Layer 4 — 中央调度器深层：边界覆盖可视化

> Layer 4 测的是"调度器内部逻辑分支、参数回退、异常处理"。当前绘图极其简陋（只有红绿条），必须改进为"逻辑覆盖图"。图必须展示"所有分支都被覆盖且正确"。

#### 4.1 Engine.preprocess — 多 denoise 方法分支

**推荐图类型：决策树覆盖图（流程图风格）**

```
engine.preprocess() — 分支覆盖验证
─────────────────────────────────────────
输入信号特征 → [判定条件] → 输出结果 → 验证

  峭度=2.1, RMS=0.8
      ↓
  [峭度<3 且 RMS正常?] → YES → [skip_denoise=True]
                              → 输出: 原始信号
                              → 验证: 未修改 ✓
                              
  峭度=6.5, 转速=45Hz
      ↓
  [峭度>5?] → YES → [高速分支?] → YES → [VMD分支]
                                         → 输出: VMD降噪
                                         → 验证: 峭度降至3.2 ✓
                                         
  输入=None
      ↓
  [信号有效?] → NO → [异常回退分支]
                   → 输出: 原始信号(None)
                   → 验证: 不崩溃 ✓
                   
未覆盖分支：无 ✓（绿色标注）
未覆盖分支：wavelet_lms 在低转速下未触发 △（黄色警告）
```

**必须展示：**

- 每个触发过的分支路径（用粗线连接）。
- 每个分支的输入条件（如 `"峭度=6.5"`）。
- 每个分支的输出结果。
- 验证结果（✓ 输出符合预期）。
- **未覆盖的分支**（用灰色虚线 + `"未覆盖"` 标注）。

#### 4.2 _estimate_rot_freq — 方法级联回退

**推荐图类型：级联流程验证图**

```
转频估计 — 方法级联回退验证
─────────────────────────────────────────
信号类型      spectrum法   autocorr法   envelope法   最终选择   验证
────────────┼────────────┼────────────┼────────────┼─────────┼─────
恒速25Hz    25.0Hz ✓    25.0Hz ✓    25.1Hz ✓    spectrum  ✓
变速CW      18.3Hz ✗    19.1Hz ✓    —(跳过)      autocorr  ✓
极低SNR     —(无峰)      —(无峰)      —(无峰)      默认25Hz  ✓
脉冲噪声    12.5Hz ✗    12.8Hz ✗    24.9Hz ✓    envelope  ✓
────────────┴────────────┴────────────┴────────────┴─────────┴─────

回退触发统计：
  级联到第2层：1/10 次
  级联到第3层：1/10 次
  使用默认值：1/10 次
  
如果某行预期回退到 autocorr，但实际用了默认值 → 标红 ✗
```

---

### Layer 5 — 应用入口辅助函数：逻辑等价性可视化

> Layer 5 测的是辅助函数的逻辑正确性。当前也是简陋红绿条。必须展示"输入输出映射是否符合预期"。

#### 5.1 _bearing_confidence / _gear_confidence

**推荐图类型：输入-输出映射热力图**

```
_bearing_confidence() — 置信度计算验证
─────────────────────────────────────────
输入参数空间 → 输出置信度 (0~1)

热力图：X轴=SNR(0~10), Y轴=峭度(3~15)

        SNR→
        0    2    4    6    8   10
  峭度  ┌────┬────┬────┬────┬────┐
  3    │0.1 │0.2 │0.3 │0.4 │0.5 │  ← 低置信度区（浅红）
       ├────┼────┼────┼────┼────┤
  5    │0.2 │0.4 │0.6 │0.7 │0.8 │
       ├────┼────┼────┼────┼────┤
  10   │0.3 │0.6 │0.8 │0.9 │0.95│  ← 高置信度区（深绿）
       ├────┼────┼────┼────┼────┤
  15   │0.4 │0.7 │0.85│0.92│0.98│
       └────┴────┴────┴────┴────┘

验证点（白圈标注）：
  (SNR=6, 峭度=10) → 预期=0.85, 实际=0.83, 误差=2% ✓
  (SNR=2, 峭度=3)  → 预期=0.15, 实际=0.20, 误差=33% △（边界容差）

必须验证：
  ✓ 单调性：SNR/峭度增加 → 置信度不下降
  ✓ 边界：SNR=0, 峭度=3 → 置信度≈0
  ✓ 边界：SNR=10, 峭度=15 → 置信度≈1
  ✗ 若出现 SNR↑但置信度↓ → 标红热力图单元格
```

#### 5.2 _time_confidence — 时域证据门控

**推荐图类型：门控逻辑真值表可视化**

```
_time_confidence() — 门控逻辑真值表验证
──────────────────────────────────────────────────────────
          | crest>10 | kurt>5 | rot_dom | 门控输出 | 预期 | 结果
case_1    |    ✓     |   ✗    |   ✗     |   OPEN   | OPEN | ✓
case_2    |    ✗     |   ✓    |   ✗     |   OPEN   | OPEN | ✓
case_3    |    ✗     |   ✗    |   ✗     |  CLOSED  |CLOSED| ✓
case_4    |    ✓     |   ✗    |   ✓     |  CLOSED  |CLOSED| ✓
case_5    |    ✗     |   ✓    |   ✓     |  CLOSED  |CLOSED| ✓
case_6    |    ✗     |   ✗    |   ✓     |  CLOSED  |CLOSED| ✓
──────────────────────────────────────────────────────────
未覆盖组合：无 ✓

可视化方式：
  绿色行 = 实际输出与预期一致
  红色行 = 实际输出与预期冲突（必须标出输入参数和实际输出值）
  灰色行 = 未测试的组合
```

#### 5.3 _fault_label — 故障标签映射

**推荐图类型：输入向量 → 输出标签 的映射图**

```
输入：各故障类型置信度向量 [BPFO, BPFI, BSF, FTF, 健康]
──────────────────────────────────────────────────────────
[0.8, 0.1, 0.0, 0.0, 0.1] → 预期="BPFO", 实际="BPFO" ✓
[0.2, 0.2, 0.2, 0.2, 0.2] → 预期="unknown", 实际="BPFO" ✗（应平局）
[0.0, 0.0, 0.0, 0.0, 0.9] → 预期="健康", 实际="健康" ✓
──────────────────────────────────────────────────────────

用桑基图或流向图展示：
  输入置信度分布 → 处理逻辑（阈值/平局处理） → 输出标签
```

---

### 跨层汇总图（新增，当前完全缺失）

除了每层自己的图，还需要一张**跨层依赖健康度图**，用于快速定位问题层级：

```
诊断算法全链路健康度 — Layer 1 → Layer 5
────────────────────────────────────────────────────────────
Layer 1:  ████████████████████░░░  信号基元      92% (14/15 pass)
               ↓
Layer 2:  ██████████████████░░░░░  特征提取      85% (17/20 pass)
               ↓
Layer 3:  ███████████████████░░░░  集成调度      90% (9/10 pass)
               ↓
Layer 4:  ████████████████████░░░  深层逻辑      95% (19/20 pass)
               ↓
Layer 5:  █████████████████████░░  辅助函数      96% (24/25 pass)
────────────────────────────────────────────────────────────

红色箭头说明：如果 Layer N 失败，先查 Layer N-1 是否全部通过。

Layer 2 的 3 个失败测试分析：
  - 2 个根因：Layer 1 的 find_peaks 阈值调整后，谐波搜索漏检 → 已追溯到 Layer 1
  - 1 个根因：真实数据边界 case（CW 变速 9.8Hz 下限）→ 需单独处理
  
自动溯源标注：
  Layer 2 的失败项旁标红色虚线箭头指向 Layer 1 对应失败项
```

---

### 一张好图的判定清单（Checklist）

在评审任何 `plot_results.py` 新增的图时，使用此清单。必须至少满足 **4/5** 项：

- [ ] **Ground Truth 可见？** 理论值、期望范围、已知标准是否在图上用线/阴影/点直接标出？
- [ ] **阈值可见且带说明？** 判定通过/失败的边界是否用橙色虚线画出，并配文字 `"XXX>3 为通过"`？
- [ ] **通过状态直接标出？** 每个数据点或每组数据旁是否有 ✓/✗（或明确的颜色编码 + 图例）？
- [ ] **定量差异在图上？** 误差百分比、SNR、绝对差值是否直接写在对应位置（不是只在图例里）？
- [ ] **标题自解释？** 图标题是否包含"怎样算对"（如 `"频率检出 — 误差<5%为通过"`）？

**进阶项（Layer 2+ 推荐）：**

- [ ] **失败可定位？** 如果这张图有红色 ✗，能否不看代码就知道是哪个输入/参数导致的？
- [ ] **边界被覆盖？** 是否展示了空信号、极短信号、None 参数等边界情况的结果？
- [ ] **跨方法一致性？** 对于集成类功能，是否展示了多种方法的结果对比？

---

### 实施路线图

| 优先级 | 改进项 | 涉及文件 | 工作量 |
|-------|--------|---------|--------|
| **P0** | 统一颜色语义常量（`COLOR_PASS/FAIL/GT/THRESH/EST`） | 全部 `plot_results.py` | 低 |
| **P0** | Layer 1 `plot_results.py` 改为严格只读 JSON | `layer1/plot_results.py` | 中（需拆出合成信号 ground truth 到 JSON） |
| **P0** | 所有图标题加入判定标准说明 | 全部 `plot_results.py` | 低 |
| **P1** | Layer 2 轴承诊断图增加：故障频率线 + SNR阈值 + 容差带 | `layer2/plot_results.py` | 中 |
| **P1** | Layer 2 齿轮指标图增加：健康vs故障分组 + 阈值线 + 分离度 | `layer2/plot_results.py` | 中 |
| **P1** | 新增跨层依赖健康度汇总图 | 新增 `foundation/plot_summary.py` | 中 |
| **P2** | Layer 4 从"红绿横条"升级为"决策树覆盖图" | `layer4/plot_results.py` | 高 |
| **P2** | Layer 5 从"红绿横条"升级为"输入输出映射图/真值表" | `layer5/plot_results.py` | 高 |
| **P2** | Layer 3 新增"方法一致性矩阵热图" | `layer3/plot_results.py` | 高 |

---

### 附录：现有绘图问题速查表

| 文件 | 当前问题 | 改进方向 |
|------|---------|---------|
| `layer1/plot_results.py` | 大量图重跑计算（非只读JSON），违反 SKILL.md 铁律 | 将 ground truth 数据预写入 JSON，绘图时只读 |
| `layer1/plot_results.py` 图3 (FFT) | 无频率分辨率标注，无误差阈值说明 | 标题加 `"Δf=XHz, 误差<Δf/2为通过"` |
| `layer1/plot_results.py` 图5 (统计) | 误差标注颜色区分度不够 | 使用统一的 `COLOR_PASS/FAIL`，加 ✓/✗ |
| `layer2/plot_results.py` plot_bearing | 目标vs检出散点图缺少容差带 | 增加 `"±5%容差"` 阴影区 |
| `layer2/plot_results.py` plot_gear_metrics | 指标值无健康/故障分组对比 | 按数据集分组，画阈值线 |
| `layer4/plot_results.py` | 只有简陋红绿条，完全无法定位问题 | 按上文章节重绘为决策树/流程图 |
| `layer5/plot_results.py` | 同上 | 按上文章节重绘为映射图/真值表 |

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
