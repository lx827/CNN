# Layer 1 信号基元 — 测试报告

> 生成时间：2026-05-19 | 分支：`fix/nodata-v2`
> 图表：25 张 PNG → `layer1/output/plots/`

---

## 总览

| 指标 | 数值 |
|------|------|
| 测试模块 | **14** |
| 总测试数 | **151** |
| 通过 | **151** |
| 失败 | 0 |
| 通过率 | **100%** |

---

## 模块覆盖清单

| # | 模块 | 测试文件 | 测试数 | 图表 |
|---|------|---------|:--:|:--:|
| 1 | `signal_utils` | `test_signal_utils_correctness.py` | 60 | 01~09, 14, 16~17 |
| 2 | `vmd_denoise` | `test_vmd_denoise_correctness.py` | 19 | 10~12, 15 |
| 3 | `health_score_continuous` | `test_health_score_continuous.py` | 11 | — |
| 4 | `bearing_sideband` | `test_bearing_sideband.py` | 2 | — |
| 5 | `channel_consensus` | `test_channel_consensus.py` | 4 | — |
| 6 | `recommendation` | `test_recommendation.py` | 8 | — |
| 7 | `gear/msb` | `test_msb_correctness.py` | 7 | 20 |
| 8 | `savgol_denoise` | `test_savgol_denoise_correctness.py` | 5 | 18 |
| 9 | `wavelet_packet` | `test_wavelet_packet_correctness.py` | 8 | 19 |
| 10 | `bearing_cyclostationary` | `test_bearing_cyclostationary_correctness.py` | 5 | 21 |
| 11 | `modality_bearing` | `test_modality_bearing_correctness.py` | 3 | 22 |
| 12 | `sensitive_selector` | `test_sensitive_selector_correctness.py` | 6 | 23 |
| 13 | `trend_prediction` | `test_trend_prediction_correctness.py` | 6 | 24 |
| 14 | `probability_calibration` | `test_probability_calibration_correctness.py` | 7 | 25 |

---

## 图表清单

| 编号 | 文件名 | 内容 |
|:--:|------|------|
| 01 | `01_prepare_signal.png` | DC去除 + 线性去趋势(y=kx+b) 前后对比 |
| 02 | `02_filters.png` | 带通/低通/高通频谱四宫格 |
| 03 | `03_fft_spectrum.png` | 25/50/200Hz FFT频率检出 |
| 04 | `04_find_peaks.png` | 谐波族搜索 |
| 05 | `05_statistics.png` | 5项统计指标期望vs实际 |
| 06 | `06_parabolic_interp.png` | 抛物线插值亚bin精度 |
| 07 | `07_snr_energy.png` | SNR+频带能量 |
| 08 | `08_rot_freq.png` | 三方法转频估计对比 |
| 09 | `09_zoom_fft.png` | ZOOM-FFT vs 标准FFT |
| 10 | `10_vmd_decompose.png` | VMD三分量分解 |
| 11 | `11_vmd_denoise.png` | VMD降噪时域+频域6宫格 |
| 12 | `12_vmd_impact.png` | VMD冲击模态选择 |
| 13 | `13_summary.png` | 全部14模块通过率汇总 |
| 14 | `14_real_rotfreq.png` | WTgearbox+HUSTbear转频估计 |
| 15 | `15_real_vmd.png` | HUSTbear+CW VMD峭度对比 |
| 16 | `16_all_synthetic.png` | 8种合成信号统计指标 |
| 17 | `17_cw_variable.png` | CW变速转频估计 |
| 18 | `18_savgol.png` | S-G平滑通过率 |
| 19 | `19_wavelet_packet.png` | 小波包通过率 |
| 20 | `20_msb.png` | MSB通过率 |
| 21 | `21_cyclostationary.png` | 循环平稳通过率 |
| 22 | `22_modality_bearing.png` | 模态分解轴承诊断通过率 |
| 23 | `23_sensitive_selector.png` | 敏感分量选择通过率 |
| 24 | `24_trend_prediction.png` | 趋势预测通过率 |
| 25 | `25_probability_calibration.png` | 概率校准通过率 |

---

## 已知限制

| 限制 | 模块 | 详情 |
|------|------|------|
| WTgearbox ≥45Hz 转频不准 | `signal_utils` | 行星齿轮箱啮合频率强干扰基频 |
| HUSTbear 25/35Hz 转频不准 | `signal_utils` | 频谱法检出谐波而非基频 |
| HUSTbear 复合故障转频不准 | `signal_utils` | 故障频率杂散干扰 |
| SUGGESTION_MAP 键序问题 | `recommendation` | 部分键未按字母序排列，与 `sorted()` 不一致 |

---

## 运行命令

```bash
cd d:\code\CNN

# 全部 14 个 Layer 1 测试
python tests/diagnosis/foundation/layer1/test_signal_utils_correctness.py
python tests/diagnosis/foundation/layer1/test_vmd_denoise_correctness.py
python tests/diagnosis/foundation/layer1/test_health_score_continuous.py
python tests/diagnosis/foundation/layer1/test_bearing_sideband.py
python tests/diagnosis/foundation/layer1/test_channel_consensus.py
python tests/diagnosis/foundation/layer1/test_recommendation.py
python tests/diagnosis/foundation/layer1/test_msb_correctness.py
python tests/diagnosis/foundation/layer1/test_savgol_denoise_correctness.py
python tests/diagnosis/foundation/layer1/test_wavelet_packet_correctness.py
python tests/diagnosis/foundation/layer1/test_bearing_cyclostationary_correctness.py
python tests/diagnosis/foundation/layer1/test_modality_bearing_correctness.py
python tests/diagnosis/foundation/layer1/test_sensitive_selector_correctness.py
python tests/diagnosis/foundation/layer1/test_trend_prediction_correctness.py
python tests/diagnosis/foundation/layer1/test_probability_calibration_correctness.py

# 绘图
python tests/diagnosis/foundation/layer1/plot_results.py
```
