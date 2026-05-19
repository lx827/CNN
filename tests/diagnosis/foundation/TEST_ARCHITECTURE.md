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

## 测试覆盖矩阵（按依赖层排列）

| 层 | 模块 | 关键函数 | 测试文件 | 状态 |
|----|------|---------|---------|:--:|
| **L1** | `signal_utils` | `prepare_signal` | — | ❌ |
| **L1** | `signal_utils` | `estimate_rot_freq_spectrum` | `test_order_tracking_correctness.py` | ✅ |
| **L1** | `signal_utils` | `find_peaks_in_spectrum` | 间接 (`peak_snr` wrapper) | ⚠️ |
| **L1** | `signal_utils` | FFT, rms, kurtosis, bandpass | — | ❌ |
| **L1** | `vmd_denoise` | `vmd_denoise` | — | ❌ |
| **L2** | `bearing` | `envelope_analysis` | `test_envelope_correctness.py` (合成) | ✅ |
| **L2** | `order_tracking` | `_compute_order_spectrum` | `test_order_tracking_correctness.py` | ✅ |
| **L2** | `order_tracking` | `_compute_order_spectrum_varying_speed` | 同上 + CW 真实 | ✅ |
| **L2** | `preprocessing` | `wavelet_denoise`, `cepstrum_pre_whitening` | `regression/test_cpw_robustness.py` | ⚠️ 仅鲁棒 |
| **L2** | `features` | `_compute_bearing_fault_freqs` | `test_bearing_fault_freqs.py` | ✅ |
| **L2** | `features` | `compute_time_features` | — | ❌ |
| **L2** | `features` | `compute_fft_features`, `compute_envelope_features` | — | ❌ |
| **L2** | `features` | `has_bearing_params`/`has_gear_params` | `regression/test_none_params.py` | ✅ |
| **L3** | `engine` | `analyze_bearing` (各方法) | `test_envelope_correctness.py` (真实) | ⚠️ 仅 standard |
| **L3** | `engine` | `analyze_gear` | `test_gear_metrics_correctness.py` | ✅ |
| **L4** | `ensemble` | `run_research_ensemble` | — | ❌ |
| **L4** | `health_score` | `_compute_health_score` | — | ❌ |

---

## 调试级联流程

当 Layer 3/4 测试失败时，逐层追溯：

```
test_gear_metrics_correctness.py → FAIL
  │
  ├─ 先查 L2: test_bearing_fault_freqs.py → PASS ✓
  │   → 故障频率公式没问题
  │
  ├─ 再查 L1: test_order_tracking_correctness.py::rot_freq → FAIL ✗
  │   → 根因: Layer 1 转频估计在变速工况下错误
  │
  └─ 结论: 不是齿轮指标算法的问题，是底层转频估计对变速不鲁棒
```

---

## 下一步：补充 Layer 1 缺口

```
tests/diagnosis/foundation/
├── test_fft_correctness.py              # L1: 纯正弦FFT (幅值/频率)
├── test_preprocessing_correctness.py    # L1: prepare_signal (去直流/趋势)
└── test_time_features_correctness.py    # L2: kurt/crest/rms 公式
```
