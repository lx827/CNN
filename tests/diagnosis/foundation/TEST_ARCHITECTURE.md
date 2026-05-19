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

## 测试覆盖矩阵（完整 — 按依赖层排列）

### Layer 1 — 信号基元（零依赖，先测）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `signal_utils` | `prepare_signal` (去直流/去趋势) | — | ❌ |
| `signal_utils` | `estimate_rot_freq_spectrum` | `test_order_tracking_correctness.py` | ✅ |
| `signal_utils` | `find_peaks_in_spectrum` | `test_envelope_correctness.py` (间接) | ⚠️ |
| `signal_utils` | `compute_fft_spectrum` (FFT 幅值谱) | — | ❌ |
| `signal_utils` | `rms`, `peak_value`, `kurtosis`, `skewness` | — | ❌ |
| `signal_utils` | `bandpass_filter`, `highpass_filter`, `lowpass_filter` | — | ❌ |
| `vmd_denoise` | `vmd_denoise` | — | ❌ |
| `health_score_continuous` | 连续扣分函数 | — | ❌ |
| `bearing_sideband` | 边带密度/不对称分析 | — | ❌ |
| `channel_consensus` | 多通道投票 | — | ❌ |
| `recommendation` | `_generate_recommendation` | — | ❌ |
| `gear/msb` | MSB 残余边频带 | — | ❌ |

### Layer 2 — 特征提取 & 信号处理（依赖 Layer 1）

| 模块 | 函数 | 测试 | 状态 |
|------|------|------|:--:|
| `features` | `_compute_bearing_fault_freqs` | `test_bearing_fault_freqs.py` | ✅ |
| `features` | `_compute_bearing_fault_orders` | — | ❌ |
| `features` | `compute_time_features` (peak/rms/kurt/crest…) | — | ❌ |
| `features` | `compute_fft_features` (mesh freq, sidebands) | — | ❌ |
| `features` | `compute_envelope_features` (BPFO/BPFI match) | — | ❌ |
| `features`— | `has_bearing_params` / `has_gear_params` | `regression/test_none_params.py` | ✅ |
| `bearing` | `envelope_analysis` (Hilbert 包络) | `test_envelope_correctness.py` | ✅ |
| `bearing` | `fast_kurtogram` (谱峭度选带) | — | ❌ |
| `bearing` | `cpw_envelope_analysis` (倒频谱预白化) | `regression/test_cpw_robustness.py` | ⚠️ 鲁棒 |
| `bearing` | `med_envelope_analysis` (最小熵解卷积) | — | ❌ |
| `bearing` | `teager_envelope_analysis` (Teager 算子) | — | ❌ |
| `bearing` | `spectral_kurtosis_envelope_analysis` | — | ❌ |
| `bearing` | `mckd_envelope_analysis` (MCKD) | — | ❌ |
| `bearing` | `bearing_sc_scoh_analysis` (循环平稳) | — | ❌ |
| `bearing` | 模态轴承 (EMD/CEEMDAN/VMD envelop) | — | ❌ |
| `order_tracking` | `_compute_order_spectrum` | `test_order_tracking_correctness.py` | ✅ |
| `order_tracking` | `_compute_order_spectrum_varying_speed` | 同上 + CW 真实 | ✅ |
| `preprocessing` | `wavelet_denoise` | — | ❌ |
| `preprocessing` | `cepstrum_pre_whitening` | `regression/test_cpw_robustness.py` | ⚠️ 鲁棒 |
| `preprocessing` | `minimum_entropy_deconvolution` | — | ❌ |
| `preprocessing` | `cascade_wavelet_vmd` / `cascade_wavelet_lms` | — | ❌ |
| `gear/metrics` | `compute_fm0` / `compute_fm4` / `compute_car` | `test_gear_metrics_correctness.py` | ⚠️ 间接 |
| `gear/metrics` | `compute_ser_order` / `analyze_sidebands` | 同上 | ⚠️ 间接 |
| `gear/planetary_demod` | 行星箱 VMD/SC/SCoh/CVS 解调 | — | ❌ |
| `rule_based` | `_rule_based_analyze` | — | ❌ |
| `health_score` | `_compute_health_score` | — | ❌ |

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
| ✅ 已覆盖 | 6 |
| ⚠️ 部分/鲁棒 | 6 |
| ❌ 未覆盖 | **34** |

---

## 测试拆分方案（按优先级）

```
Priority 0 (L1 — 底层阻塞): 必须最先完成
  test_signal_utils_correctness.py    ← prepare_signal, FFT, rms/kurt, bandpass, find_peaks
  test_vmd_correctness.py             ← VMD 分解对合成信号的模态分离

Priority 1 (L2 — 特征正确性):
  test_time_features_correctness.py   ← kurt/crest/rms/skew 公式
  test_bearing_methods_correctness.py ← kurtogram/cpw/med/teager 各方法合成验
  test_gear_metrics_standalone.py     ← FM0/FM4/SER/CAR 独立验(不经过 engine)
  test_preprocessing_correctness.py   ← wavelet/MED 去噪效果

Priority 2 (L2-L3 — 集成):
  test_health_score_correctness.py    ← 不同故障组合的健康度输出
  test_ensemble_correctness.py        ← 多算法投票
```
