# Layer 1 信号基元 — 测试报告

> 生成时间：2026-05-19 | 分支：`fix/nodata-v2`

---

## 总览

| 指标 | 数值 |
|------|------|
| 测试文件 | 6 |
| 总测试数 | **104** |
| 通过 | **104** |
| 失败 | 0 |
| 通过率 | **100%** |
| 图表 | 17 张 |
| 已标注已知限制 | 6 项 |

---

## 测试覆盖矩阵

### signal_utils（60 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| `prepare_signal` | 3 | 零均值化、线性去趋势、list 输入 |
| 滤波器 | 4 | 带通/低通/高通 + 极短信号安全 |
| FFT 频谱 | 3 | 25/50/200Hz 正弦频率+幅值精度 |
| `find_peaks_in_spectrum` | 2 | 谐波族搜索（正弦+齿轮啮合） |
| 统计指标 | 5 | 高斯峭度/偏度、正弦RMS/峰值因子/峰值 |
| `parabolic_interpolation` | 1 | 100.3Hz 亚 bin 插值精度 |
| SNR & 频带能量 | 3 | SNR、_band_energy、_order_band_energy |
| 转频估计（合成） | 3 | spectrum/autocorr/envelope 三方法 |
| ZOOM-FFT | 2 | 200Hz 细化谱 + 无效输入安全 |
| 全部合成信号 | 8 | 6种信号×8变体→FFT+统计+峰值 |
| 转频估计（WTgearbox） | 8 | 20~55Hz 全部8种转速 |
| 转频估计（HUSTbear） | 7 | 5健康+球故障+复合故障 |
| 滤波&峰值（HUSTbear） | 5 | 20~40Hz 带通滤波+FFT验证 |
| CW 变速 | 6 | 3状态×2变体 转频估计 |

**已知限制：**

- WTgearbox ≥45Hz：行星齿轮箱啮合频率强干扰基频，`estimate_rot_freq_spectrum` 无法准确估计
- HUSTbear 25/35Hz：频谱法不稳定，检出谐波而非基频
- HUSTbear 复合故障：故障频率杂散干扰

### vmd_denoise（19 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| `vmd_decompose` | 5 | 三频合成信号→3 IMFs + 频率验证 |
| `vmd_denoise` | 1 | 加噪正弦 SNR 改善 |
| `vmd_select_impact_mode` | 1 | 轴承冲击→最佳IMF选择 |
| 真实 HUSTbear | 6 | 3转速×2状态(健康/球故障) |
| 真实 CW 变速 | 6 | 3状态×升速/降速 |

### health_score_continuous（11 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| `sigmoid_deduction` | 4 | 远低于/远高于/等于阈值 + 单调性 |
| `multi_threshold_deduction` | 3 | 低于所有/超过所有/中间值 |
| `cascade_deduction` | 2 | 中间值级联 + 低于所有阈值 |
| `compute_continuous_deductions` | 2 | 正常指标 + 高峭度指标 |

### bearing_sideband（2 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| 合成有调制 | 1 | BPFO±fr 强边频带，density=1.0 |
| 合成无调制 | 1 | 仅BPFO峰无调制，density=0.0 |

### channel_consensus（4 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| 3通道全BPFO | 1 | 形成一致→标签=轴承外圈故障, boost=1.05 |
| 仅1通道BPFO | 1 | 无一致性→label=unknown |
| 空输入 | 1 | 安全兜底 |
| 混合故障 | 1 | 3通道3种故障→无一致 |

### recommendation（8 测试）

| 类别 | 测试数 | 内容 |
|------|:--:|------|
| `_match_suggestion` | 3 | SCoh证据匹配 + 键序问题(已知限制) + 未知组合 |
| `_generate_recommendation` | 3 | normal/DS冲突/gear SER critical |
| `SUGGESTION_MAP` | 2 | 映射表条目数 + 键类型验证 |

**已知限制：** `SUGGESTION_MAP` 中部分键未按字母序排列，与 `_match_suggestion` 内部的 `sorted()` 不一致，导致部分多键组合无法匹配。例如 `("kurtosis_high", "bearing_multi_freq")` 排序后为 `("bearing_multi_freq", "kurtosis_high")` 无法匹配原键。

---

## 数据集覆盖

| 数据集 | 类型 | 用途 | 样本数 |
|--------|------|------|:--:|
| 合成信号 | 6种 | FFT/统计/峰值/边频带 | 8 |
| WTgearbox | 行星齿轮箱 | 转频估计 | 8 |
| HUSTbear | 轴承 | 转频/滤波/VMD | 18 |
| CW | 变速轴承 | 转频/VMD | 12 |

---

## 未覆盖模块

| 模块 | 原因 |
|------|------|
| `gear/msb.py` | 计算量大，需后续单独处理 |

---

## 运行命令

```bash
cd d:\code\CNN
# 请进入虚拟环境
# 全部 Layer 1 测试
python tests/diagnosis/foundation/layer1/test_signal_utils_correctness.py
python tests/diagnosis/foundation/layer1/test_vmd_denoise_correctness.py
python tests/diagnosis/foundation/layer1/test_health_score_continuous.py
python tests/diagnosis/foundation/layer1/test_bearing_sideband.py
python tests/diagnosis/foundation/layer1/test_channel_consensus.py
python tests/diagnosis/foundation/layer1/test_recommendation.py

# 绘图
python tests/diagnosis/foundation/layer1/plot_results.py
```
