# 诊断算法分层测试架构

> 诊断功能由多层依赖组成。测试必须按依赖顺序：Layer 1 → Layer 2 → Layer 3。
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
  signal_utils.py        (prepare_signal, FFT, 转频估计, 谱峰搜索)
  vmd_denoise.py         (VMD分解)
  health_score_continuous.py (连续扣分)
  bearing_sideband.py    (边带分析)
  channel_consensus.py   (通道一致性)
  recommendation.py      (建议生成)
  gear/msb.py            (调制双谱)
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
│   └── plot_results.py
├── output/                           # Layer 1+2 旧测试输出（兼容保留）
│   └── plots/
└── plot_results.py                   # 旧汇总绘图脚本
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
| `health_score_continuous` | 连续扣分函数 | `layer2/test_health_score_correctness.py` (集成) | ⚠️ |
| `bearing_sideband` | 边带密度/不对称分析 | — | ❌ |
| `channel_consensus` | 多通道投票 | — | ❌ |
| `recommendation` | `_generate_recommendation` | — | ❌ |
| `gear/msb` | MSB 残余边频带 | — | ❌ |

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

### Layer 3-5 — 调度 & 集成（依赖 Layer 1+2）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `engine` | `analyze_bearing` (分发 13 种轴承方法) | `test_envelope_correctness.py` (真实) | ⚠️ 仅 1 种 |
| `engine` | `analyze_gear` (分发 2 种齿轮方法) | `test_gear_metrics_correctness.py` | ✅ |
| `engine` | `analyze_comprehensive` | — | ❌ |
| `engine` | `analyze_all_methods` | — | ❌ |
| `engine` | `analyze_research_ensemble` | — | ❌ |
| `ensemble` | `run_research_ensemble` | — | ❌ |
| `analyzer` | `analyze_device` | — | ❌ |

### 统计

| 状态 | 数量 |
|:--:|------|
| ✅ 已覆盖 | 30 |
| ⚠️ 部分/鲁棒 | 3 |
| ❌ 未覆盖 | **13** |

---

## 测试拆分方案（按优先级）

```
Priority 0 (L1 — 底层阻塞): 必须最先完成
  layer1/test_signal_utils_correctness.py    ← prepare_signal, FFT, rms/kurt, bandpass, find_peaks
  layer1/test_vmd_denoise_correctness.py     ← VMD 分解对合成信号的模态分离

Priority 1 (L2 — 特征正确性):
  layer2/test_features_correctness.py        ← kurt/crest/rms/skew 公式 + 轴承频率 + FFT特征
  layer2/test_bearing_correctness.py         ← envelope/kurtogram/med/teager/sk 合成验证
  layer2/test_bearing_advanced_correctness.py ← cpw/mckd/sc-scoh 合成验证
  layer2/test_gear_metrics_correctness.py    ← FM0/FM4/SER/CAR/TSA 独立验(不经过 engine)
  layer2/test_preprocessing_correctness.py   ← wavelet/MED/CPW 去噪效果
  layer2/test_preprocessing_cascade_correctness.py ← cascade_wavelet_vmd/lms
  layer2/test_order_tracking_correctness.py  ← 恒定/缓变/变速阶次跟踪

Priority 2 (L2-L3 — 集成):
  layer2/test_health_score_correctness.py    ← 不同故障组合的健康度输出
  layer2/test_rule_based_correctness.py      ← 规则诊断分类能力
  layer2/test_planetary_demod_correctness.py ← 行星齿轮箱解调
```

---

## 运行方式

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate

# Layer 1
python ../tests/diagnosis/foundation/layer1/test_signal_utils_correctness.py
python ../tests/diagnosis/foundation/layer1/test_vmd_denoise_correctness.py

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

# 绘图（独立运行，不重跑分析）
python ../tests/diagnosis/foundation/layer1/plot_results.py
python ../tests/diagnosis/foundation/layer2/plot_results.py
```
