# 风机齿轮箱智能故障诊断系统 — 评估框架补充测试计划

> **文档定位**：本计划面向 `tests/diagnosis/evaluation/` 目录下的现有评估框架，详细规划第二轮补充测试的架构、模块、指标与实施路线。  
> **当前状态**：现有框架覆盖去噪、轴承、齿轮、综合诊断、鲁棒性 5 大维度，但核心算法覆盖率仅约 60%，且缺少论文级分类量化指标（混淆矩阵、ROC/PR、Kappa、MCC 等）。  
> **目标**：将算法覆盖率提升至 ≥95%，并引入工业故障诊断（FDD）与 PHM 领域标准量化体系，使评估结果具备论文发表与同行对比的严谨性。

---

## 目录

1. [现有评估框架盘点](#1-现有评估框架盘点)
2. [论文级量化评估标准](#2-论文级量化评估标准)
3. [补充测试总体架构](#3-补充测试总体架构)
4. [各模块补充计划](#4-各模块补充计划)
   - 4.1 轴承诊断补充评估模块
   - 4.2 齿轮诊断补充评估模块
   - 4.3 去噪算法补充评估模块
   - 4.4 鲁棒性测试扩展模块
   - 4.5 高级分类量化指标模块（核心新增）
   - 4.6 D-S 证据融合独立评估模块
   - 4.7 健康度趋势与预后评估模块
   - 4.8 多通道共识诊断评估模块
5. [报告输出扩展](#5-报告输出扩展)
6. [实施优先级与里程碑](#6-实施优先级与里程碑)
7. [附录：指标公式速查](#7-附录指标公式速查)

---

## 1. 现有评估框架盘点

### 1.1 现有架构

```
main.py
  ├─ evaluate_denoise_methods()        → denoise_results
  ├─ evaluate_bearing_methods()        → bearing_results
  ├─ evaluate_gear_methods()           → gear_results
  ├─ evaluate_comprehensive_diagnosis() → comprehensive_results
  ├─ evaluate_noise_robustness()       → robustness_results
  └─ generate_final_report(...)        → final_report.md
```

| 模块 | 文件 | 评估对象 | 现有覆盖率 |
|------|------|----------|-----------|
| 去噪 | `denoise_eval.py` | 8 种去噪方法 | 72.7% (8/11) |
| 轴承 | `bearing_eval.py` | 7 种轴承方法 | 53.8% (7/13) |
| 齿轮 | `gear_eval.py` | 通用指标提取 | ~58% (7/12) |
| 综合 | `comprehensive_eval.py` | ensemble profile | 2 种 profile |
| 鲁棒性 | `robustness_eval.py` | 3 种轴承方法 | 23.1% (3/13) |

### 1.2 现有指标

**已有**：SNR(dB)、MSE、Pearson r、Kurtosis、BPFO/BPFI/BSF SNR、谐波数、谱峰清晰度、Accuracy、Precision、Recall、F1、Specificity、FAR、分离度、AUC(标量)、Wilcoxon p-value、执行时间。

**缺失**：混淆矩阵、ROC 曲线、PR 曲线、Cohen's Kappa、MCC、Balanced Accuracy、Macro/Weighted-F1、FDR、MDR、FIA、HI Monotonicity/Trendability/Prognosability。

### 1.3 数据集使用现状

| 数据集 | 工况 | 现有用途 |
|--------|------|----------|
| HUSTbear | 恒速轴承 | 去噪、轴承、综合、鲁棒性 |
| CW | 变速轴承 | 轴承诊断 |
| WTgearbox | 恒速行星齿轮 | 齿轮诊断、综合诊断 |

---

## 2. 论文级量化评估标准

### 2.1 分类性能指标（所有故障诊断论文必用）

| 指标 | 公式 | 说明 | 优先级 |
|------|------|------|--------|
| **Accuracy** | $(TP+TN)/(TP+TN+FP+FN)$ | 总体正确率 | 已有 |
| **Precision** | $TP/(TP+FP)$ | 查准率 | 已有 |
| **Recall / TDR** | $TP/(TP+FN)$ | 查全率 / 检测率 | 已有 |
| **F1-score** | $2PR/(P+R)$ | 调和平均 | 已有 |
| **Specificity** | $TN/(TN+FP)$ | 特异度 | 已有 |
| **Balanced Accuracy** | $(TPR+TNR)/2$ | 不平衡数据集专用 | **新增** |
| **Cohen's Kappa** | $(p_o-p_e)/(1-p_e)$ | 考虑随机一致的一致性 | **新增** |
| **MCC** | $\frac{TP\cdot TN - FP\cdot FN}{\sqrt{(TP+FP)(TP+FN)(TN+FP)(TN+FN)}}$ | 不平衡数据稳健综合指标 | **新增** |
| **Macro-F1** | $\frac{1}{C}\sum_{c=1}^{C} F1_c$ | 多分类每类同等重要 | **新增** |
| **Weighted-F1** | $\sum_{c=1}^{C}\frac{n_c}{N} \cdot F1_c$ | 按样本数加权 | **新增** |

### 2.2 故障检测与隔离指标（工业 FDD 标准）

| 指标 | 公式 | 说明 | 优先级 |
|------|------|------|--------|
| **FDR** (Fault Detection Rate) | $TP/(TP+FN)$ | 故障检出率 | **新增** |
| **FAR** (False Alarm Rate) | $FP/(FP+TN)$ | 虚警率 | 已有 |
| **MDR** (Missed Detection Rate) | $FN/(TP+FN)$ | 漏检率 | **新增** |
| **FIA** (Fault Isolation Accuracy) | 正确隔离数/总故障数 | 故障定位准确率 | **新增** |
| **Detection Score** | $FDR - FAR$ | 综合评分，范围 $[-1,1]$ | **新增** |

### 2.3 多分类评估

| 方法 | 说明 | 优先级 |
|------|------|--------|
| **混淆矩阵 (Confusion Matrix)** | 分析每类故障识别精度与误分类模式 | **新增** |
| **ROC 曲线 (One-vs-Rest)** | 每类故障绘制 TPR-FPR 曲线 | **新增** |
| **PR 曲线 (One-vs-Rest)** | 每类故障绘制 Precision-Recall 曲线 | **新增** |
| **Macro-AUC** | 多分类平均 AUC | **新增** |

### 2.4 健康度与预后指标（PHM 领域）

| 指标 | 公式/说明 | 优先级 |
|------|----------|--------|
| **Monotonicity** | $\frac{1}{K-1} \left| \#(\frac{d}{dx}>0) - \#(\frac{d}{dx}<0) \right|$，范围 $[0,1]$ | P2 |
| **Trendability** | HI 与时间的 Pearson 相关系数 | P2 |
| **Prognosability** | $\exp(-\frac{\text{std}_j(x_j(N_j))}{\text{mean}_j|x_j(1)-x_j(N_j)|})$，范围 $[0,1]$ | P2 |
| **Robustness** | HI 对随机波动的指数衰减平均 | P2 |

### 2.5 去噪评估指标

| 指标 | 说明 | 优先级 |
|------|------|--------|
| SNR Improvement ($\Delta$SNR) | 去噪前后 SNR 提升量 | 已有 |
| MSE / RMSE | 均方误差/均方根误差 | 已有 |
| Pearson Correlation | 波形保真度 | 已有 |
| **PSNR** | 峰值信噪比 | **新增** |
| **PRD** | 百分比均方根差 | **新增** |
| **NCC** | 归一化互相关 | **新增** |
| **Crest Factor Improvement** | 峰值因子改善 | **新增** |

---

## 3. 补充测试总体架构

补充测试在现有 5 个模块基础上，新增 3 个核心模块，并扩展原有模块的算法覆盖。新增代码统一放在 `tests/diagnosis/evaluation/` 目录下。

```
tests/diagnosis/evaluation/
├── main.py                          # 扩展：新增模块调度入口
├── config.py                        # 扩展：新增路径/参数配置
├── datasets.py                      # 扩展：新增数据集加载支持
├── utils.py                         # 扩展：新增高级指标计算函数
│
├── denoise_eval.py                  # 扩展：补充 3 种去噪方法
├── bearing_eval.py                  # 扩展：补充 6 种轴承方法
├── gear_eval.py                     # 扩展：补充行星解调/MSB/NA4/NB4
├── comprehensive_eval.py            # 扩展：新增 profile 与统计检验
├── robustness_eval.py               # 扩展：覆盖全部 13 种轴承方法
│
├── classification_metrics_eval.py   # 【新增】高级分类量化指标核心模块
├── ds_fusion_eval.py                # 【新增】D-S 证据融合独立评估
├── health_trend_eval.py             # 【新增】健康度趋势与预后评估
├── channel_consensus_eval.py        # 【新增】多通道共识诊断评估（可选）
│
└── report_generator.py              # 扩展：新增图表与报告章节
```

### 3.1 新增/扩展文件职责

| 文件 | 类型 | 职责 |
|------|------|------|
| `classification_metrics_eval.py` | **新增** | 统一计算混淆矩阵、ROC/PR 曲线、Kappa、MCC、Macro-F1、Balanced Accuracy、FDR/MDR/FIA，供所有诊断模块调用 |
| `ds_fusion_eval.py` | **新增** | 独立评估 D-S 融合对误报率的降低效果，对比融合前 vs 融合后的分类指标 |
| `health_trend_eval.py` | **新增** | 模拟多批次历史数据，评估健康度评分的 Monotonicity、Trendability、连续衰减扣分的单调性 |
| `channel_consensus_eval.py` | **新增** | 评估多通道共识诊断对单通道误判的修正能力 |
| `utils.py` | **扩展** | 补充 `compute_confusion_matrix`、`compute_roc_curve`、`compute_pr_curve`、`compute_cohen_kappa`、`compute_mcc`、`compute_balanced_accuracy`、`compute_macro_f1`、`compute_fdr_far_mdr`、`compute_psnr`、`compute_prd`、`compute_ncc` 等函数 |

---

## 4. 各模块补充计划

### 4.1 轴承诊断补充评估模块 (`bearing_eval.py` 扩展)

#### 目标
将轴承诊断方法覆盖率从 7/13 提升至 **13/13**。

#### 补充方法

| 方法 | 来源模块 | 评估策略 |
|------|----------|----------|
| `SC_SCOH` | `bearing_cyclostationary.py` | **降采样评估**：对信号降采样至 4096 点或截取 2 秒片段后执行，避免全量计算导致内存/时间问题。记录执行时间并纳入效率排名。 |
| `WP` | `wavelet_bearing.py` | 直接调用 `wavelet_packet_bearing_analysis()`，评估小波包敏感节点选取后包络谱的 BPFO SNR。 |
| `DWT` | `wavelet_bearing.py` | 调用 `dwt_bearing_analysis()`，评估 DWT 敏感层包络谱质量。 |
| `EMD_ENVELOPE` | `modality_bearing.py` | 调用 `emd_bearing_analysis()`，评估 EMD 敏感 IMF 重构后的包络谱。 |
| `CEEMDAN_ENVELOPE` | `modality_bearing.py` | 调用 `ceemdan_bearing_analysis()`，评估 CEEMDAN 敏感 IMF 重构后的包络谱。 |
| `VMD_ENVELOPE` | `modality_bearing.py` | 调用 `vmd_bearing_analysis()`，评估 VMD 敏感模态重构后的包络谱。 |

#### 新增量化指标（对全部 13 种方法统一计算）

- **混淆矩阵**：按故障类型（N/B/IR/OR/C）展开，记录每类之间的误分类情况
- **Macro-F1 / Weighted-F1**：多分类平均
- **Cohen's Kappa**：一致性检验
- **MCC**：不平衡数据稳健性
- **Balanced Accuracy**：各类别同等权重
- **FDR / MDR**：故障检出率 / 漏检率
- **FIA**：故障隔离准确率（按故障类型判断正确的比例）
- **Detection Score**：$FDR - FAR$
- **ROC 曲线**：以健康度分数作为阈值变量，绘制每类故障的 One-vs-Rest ROC
- **AUC-ROC**：计算 Macro-AUC

### 4.2 齿轮诊断补充评估模块 (`gear_eval.py` 扩展)

#### 目标
补充行星齿轮箱专用解调、MSB、ZOOM-FFT、NA4/NB4 等算法的评估。

#### 补充内容

| 算法/指标 | 来源 | 评估策略 |
|-----------|------|----------|
| **行星解调系列** | `gear/planetary_demod.py` | 在 WTgearbox 数据集上，对每种解调方法（narrowband/fullband/tsa/hp/vmd/sc_scoh/msb）计算区分力指标（健康 vs 故障的分离度），并统计执行时间。 |
| **MSB** | `gear/msb.py` | 调用 `msb_residual_sideband_analysis()`，计算调制信号双谱在故障频率处的峰值 SNR。 |
| **ZOOM-FFT 边频带** | `gear/metrics.py` | 调用 `analyze_sidebands_zoom_fft()`，评估细化谱下边频带的显著性。 |
| **NA4** | `gear/metrics.py` | 构造伪历史方差序列（使用前 5 个健康批次估计基准方差），验证 NA4 对断齿/裂纹的单调上升趋势。 |
| **NB4** | `gear/metrics.py` | 同上，验证 NB4 的单调性。 |
| **小波包能量熵** | `wavelet_packet.py` | 调用 `compute_wavelet_packet_energy_entropy()`，对比健康与故障样本的能量熵分布差异。 |

#### 新增量化指标

- **分离度 (Separation)**：健康均值 - 故障均值（已有，需扩展至新算法）
- **Wilcoxon p-value**：健康 vs 故障分布差异的统计显著性
- **混淆矩阵**（按故障类型：He/Br/Mi/Rc/We）
- **Macro-F1 / MCC / Kappa**
- **HI 质量指标**：对 `health_score` 序列计算 Monotonicity、Trendability（若有多批次数据）

### 4.3 去噪算法补充评估模块 (`denoise_eval.py` 扩展)

#### 目标
补充 3 种缺失去噪方法的评估，并引入论文级去噪指标。

#### 补充方法

| 方法 | 来源 | 评估策略 |
|------|------|----------|
| `wavelet_packet` | `wavelet_packet.py` | 调用 `wavelet_packet_denoise()`，对比降噪前后的 SNR、MSE、Pearson r。 |
| `ceemdan_wp` | `preprocessing.py` / 级联逻辑 | 先 CEEMDAN 再小波包阈值，评估级联效果是否优于单一方法。 |
| `eemd` | `emd_denoise.py` | 调用 `eemd_decompose()` + 敏感 IMF 选择，评估 EEMD 降噪效果。 |

#### 新增量化指标

- **PSNR**：峰值信噪比
- **PRD**：百分比均方根差
- **NCC**：归一化互相关
- **Crest Factor Improvement**：$CF_{after} - CF_{before}$
- **执行时间对比**：新增方法的效率排名

### 4.4 鲁棒性测试扩展模块 (`robustness_eval.py` 扩展)

#### 目标
将鲁棒性测试从 3 种方法扩展至 **全部 13 种轴承方法 + 8 种去噪方法**。

#### 扩展策略

**轴承方法鲁棒性（13 种）**：
- 对每个 BearingMethod，在 6 个 SNR 级别（20dB / 10dB / 5dB / 0dB / -5dB / -10dB）下测试
- 每个 SNR 级别记录：BPFO SNR、健康度分数、检出状态（TP/FP/TN/FN）
- 绘制 **SNR-Accuracy 曲线** 和 **SNR-F1 曲线**
- 计算 **SNR-AUC**：以 SNR 为横轴，Accuracy/F1 为纵轴的曲线下面积（衡量整体抗噪能力）

**去噪方法鲁棒性（8 种）**：
- 对每个 DenoiseMethod，在 3 个 SNR 级别（5dB / 0dB / -5dB）下测试
- 记录：$\Delta$SNR、MSE、Pearson r、PSNR、PRD
- 绘制 **SNR-$\Delta$SNR 曲线**

#### 新增量化指标

- **临界 SNR (Critical SNR)**：Accuracy 首次跌破 80% 或 F1 首次跌破 0.8 时的输入 SNR
- **鲁棒性指数 (Robustness Index)**：$\text{RI} = \frac{\text{AUC}_{\text{SNR-Accuracy}}}{\text{max possible AUC}}$，范围 $[0,1]$

### 4.5 高级分类量化指标模块（核心新增）

#### 目标
建立统一的分类性能评估基础设施，供所有诊断模块调用。

#### 文件：`classification_metrics_eval.py`

**公共 API 设计**：

```python
def evaluate_classification_performance(
    y_true: List[str],           # 真实标签列表
    y_pred: List[str],           # 预测标签列表
    scores: List[float],         # 连续分数（如 health_score，用于 ROC）
    labels: List[str],           # 所有类别标签
    output_dir: str              # 输出图表目录
) -> Dict[str, Any]:
    """
    统一计算所有高级分类指标，并保存图表。
    返回字典包含：
    - confusion_matrix: np.ndarray
    - accuracy, precision, recall, f1, specificity, balanced_accuracy
    - macro_f1, weighted_f1
    - cohen_kappa, mcc
    - fdr, far, mdr, fia, detection_score
    - roc_curves: Dict[label, (fpr, tpr, auc)]
    - pr_curves: Dict[label, (recall, precision, auc)]
    - macro_auc_roc, macro_auc_pr
    """
```

**输出图表**：
- `confusion_matrix.png`：归一化与非归一化两个版本
- `roc_curves.png`：所有类别的 One-vs-Rest ROC 曲线 + Macro-ROC
- `pr_curves.png`：所有类别的 One-vs-Rest PR 曲线 + Macro-PR

**调用方**：
- `bearing_eval.py`：在评估完成后调用，生成轴承诊断的混淆矩阵与 ROC
- `gear_eval.py`：生成齿轮诊断的混淆矩阵与 ROC
- `comprehensive_eval.py`：生成综合诊断的混淆矩阵与 ROC
- `ds_fusion_eval.py`：对比融合前后的混淆矩阵变化

### 4.6 D-S 证据融合独立评估模块（新增）

#### 目标
验证 D-S 证据理论融合是否真正降低误报率、提升故障隔离准确率。

#### 文件：`ds_fusion_eval.py`

**评估策略**：
1. 在 HUSTbear 和 WTgearbox 上分别运行 **单方法诊断**（每种 BearingMethod/GearMethod 独立运行）和 **D-S 融合后诊断**
2. 对比两组的分类指标：
   - 融合前：各方法独立的 Accuracy、FAR、FIA
   - 融合后：ensemble 输出的 Accuracy、FAR、FIA
3. 计算 **融合增益**：
   - $\Delta \text{Accuracy} = \text{Acc}_{\text{fusion}} - \max(\text{Acc}_{\text{single}})$
   - $\Delta \text{FAR} = \text{FAR}_{\text{fusion}} - \min(\text{FAR}_{\text{single}})$
   - $\Delta \text{FIA} = \text{FIA}_{\text{fusion}} - \max(\text{FIA}_{\text{single}})$

**输出**：
- `ds_fusion/comparison_table.md`：单方法 vs 融合的指标对比表
- `ds_fusion/far_reduction.png`：融合前后 FAR 对比柱状图
- `ds_fusion/confidence_distribution.png`：BPA 质量分布（高置信度 / 冲突 / 不确定）

### 4.7 健康度趋势与预后评估模块（新增）

#### 目标
评估健康度评分随时间的变化趋势质量，为预后（RUL）功能做指标储备。

#### 文件：`health_trend_eval.py`

**评估策略**：
1. **构造伪退化序列**：从 WTgearbox 数据集中，按故障严重程度排序（He → We → Rc → Mi → Br），模拟健康度下降过程
2. 对每个模拟序列计算：
   - **Monotonicity**：$\frac{1}{K-1} \left| \#(d>0) - \#(d<0) \right|$，目标 ≥ 0.85
   - **Trendability**：HI 与时间的 Pearson r，目标 |r| ≥ 0.90
   - **Prognosability**：失效时刻 HI 离散度，目标 ≥ 0.70
   - **Robustness**：HI 对随机波动的指数衰减平均
3. 评估 **连续衰减扣分**（`health_score_continuous.py`）的单调性：验证 sigmoid_deduction、cascade_deduction 在特征恶化时是否单调递减健康度

**输出**：
- `health_trend/monotonicity_report.md`
- `health_trend/hi_trajectory.png`：健康度轨迹曲线
- `health_trend/deduction_monotonicity.png`：各扣分路径的单调性验证

### 4.8 多通道共识诊断评估模块（新增，可选）

#### 目标
验证多通道共识诊断对单通道误判的修正能力。

#### 文件：`channel_consensus_eval.py`

**评估策略**：
1. 在 WTgearbox（2 通道）上，分别运行单通道诊断和双通道共识诊断
2. 对比：
   - 单通道 1 的 FIA vs 共识后的 FIA
   - 单通道 2 的 FIA vs 共识后的 FIA
   - 统计共识修正的误判案例数
3. 计算 **共识增益**：$\text{Consensus Gain} = \text{FIA}_{\text{consensus}} - \max(\text{FIA}_{\text{ch1}}, \text{FIA}_{\text{ch2}})$

**输出**：
- `channel_consensus/consensus_gain.png`
- `channel_consensus/correction_cases.md`

---

## 5. 报告输出扩展

### 5.1 输出目录结构扩展

```
tests/output/evaluation/
├── final_report.md                          # 扩展：新增章节
├── cache/
│   ├── denoise_results.json
│   ├── bearing_results.json
│   ├── gear_results.json
│   ├── comprehensive_results.json
│   ├── robustness_results.json
│   ├── classification_metrics.json          # 新增
│   ├── ds_fusion_results.json               # 新增
│   └── health_trend_results.json            # 新增
├── denoise/
│   ├── ... (原有)
│   └── psnr_prd_comparison.png              # 新增
├── bearing/
│   ├── ... (原有)
│   ├── confusion_matrix.png                 # 新增
│   ├── roc_curves.png                       # 新增
│   ├── pr_curves.png                        # 新增
│   └── missing_methods_report.md            # 新增：补充方法的专项报告
├── gear/
│   ├── ... (原有)
│   ├── planetary_demod_comparison.png       # 新增
│   ├── na4_nb4_trend.png                    # 新增
│   └── confusion_matrix.png                 # 新增
├── comprehensive/
│   ├── ... (原有)
│   └── classification_metrics_table.md      # 新增
├── robustness/
│   ├── ... (原有)
│   ├── snr_vs_accuracy_all_methods.png      # 扩展：全部方法
│   └── snr_vs_f1_all_methods.png            # 新增
├── classification/                          # 【新增目录】
│   ├── confusion_matrix_bearing.png
│   ├── confusion_matrix_gear.png
│   ├── roc_curves_bearing.png
│   ├── pr_curves_bearing.png
│   └── metrics_summary.md
├── ds_fusion/                               # 【新增目录】
│   ├── comparison_table.md
│   ├── far_reduction.png
│   └── confidence_distribution.png
└── health_trend/                            # 【新增目录】
    ├── monotonicity_report.md
    ├── hi_trajectory.png
    └── deduction_monotonicity.png
```

### 5.2 `final_report.md` 新增章节

在现有 9 章基础上，扩展为 **14 章**：

10. **高级分类量化指标汇总** — 混淆矩阵、ROC/PR、Kappa、MCC、Macro-F1、Balanced Accuracy、FDR/MDR/FIA
11. **轴承补充方法评估** — SC_SCOH、WP、DWT、EMD/CEEMDAN/VMD_ENVELOPE 的专项结果
12. **齿轮补充算法评估** — 行星解调、MSB、ZOOM-FFT、NA4/NB4、小波包能量熵
13. **D-S 证据融合增益分析** — 融合前后 FAR/FIA 对比、置信度分布
14. **健康度趋势质量评估** — Monotonicity、Trendability、Prognosability、Robustness

---

## 6. 实施优先级与里程碑

### Phase 1：基础设施（1-2 天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 扩展 `utils.py` | `utils.py` | 实现 `compute_confusion_matrix`、`compute_roc_curve`、`compute_pr_curve`、`compute_cohen_kappa`、`compute_mcc`、`compute_balanced_accuracy`、`compute_macro_f1`、`compute_fdr_far_mdr_fia`、`compute_psnr`、`compute_prd`、`compute_ncc` |
| 创建 `classification_metrics_eval.py` | **新增** | 封装统一分类评估 API |

### Phase 2：算法覆盖补充（2-3 天）

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 扩展 `bearing_eval.py` | **P0** | 补充 SC_SCOH（降采样）、WP、DWT、EMD/CEEMDAN/VMD_ENVELOPE |
| 扩展 `gear_eval.py` | **P0** | 补充行星解调系列、MSB、ZOOM-FFT、NA4/NB4、小波包能量熵 |
| 扩展 `denoise_eval.py` | **P1** | 补充 wavelet_packet、ceemdan_wp、eemed |
| 扩展 `robustness_eval.py` | **P1** | 覆盖全部 13 种轴承方法 + 8 种去噪方法 |

### Phase 3：高级评估模块（2-3 天）

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 创建 `ds_fusion_eval.py` | **P1** | D-S 融合独立评估 |
| 创建 `health_trend_eval.py` | **P2** | 健康度趋势质量评估（Monotonicity/Trendability/Prognosability） |
| 创建 `channel_consensus_eval.py` | **P3** | 多通道共识评估（可选） |

### Phase 4：报告扩展（1 天）

| 任务 | 说明 |
|------|------|
| 扩展 `report_generator.py` | 新增第 10-14 章生成逻辑，集成所有新增图表 |
| 扩展 `main.py` | 新增模块调度入口 |

### 预期成果

| 指标 | 目标 |
|------|------|
| 轴承方法覆盖率 | 13/13 (100%) |
| 齿轮方法覆盖率 | 12/12 (100%) |
| 去噪方法覆盖率 | 11/11 (100%) |
| 鲁棒性测试覆盖率 | 13/13 轴承 + 8/8 去噪 |
| 分类量化指标 | 混淆矩阵、ROC/PR、Kappa、MCC、Macro-F1、Balanced Accuracy、FDR/MDR/FIA 全部具备 |
| 报告章节 | 14 章（原 9 章 + 5 章新增） |

---

## 7. 附录：指标公式速查

### A.1 分类指标

| 指标 | 公式 |
|------|------|
| Accuracy | $A_c = \frac{TP+TN}{TP+TN+FP+FN}$ |
| Precision | $P = \frac{TP}{TP+FP}$ |
| Recall / TDR / FDR | $R = \frac{TP}{TP+FN}$ |
| Specificity | $S_p = \frac{TN}{TN+FP}$ |
| F1-score | $F1 = 2 \cdot \frac{P \cdot R}{P+R}$ |
| Balanced Accuracy | $BA = \frac{TPR + TNR}{2}$ |
| Cohen's Kappa | $\kappa = \frac{p_o - p_e}{1 - p_e}$ |
| MCC | $\text{MCC} = \frac{TP \cdot TN - FP \cdot FN}{\sqrt{(TP+FP)(TP+FN)(TN+FP)(TN+FN)}}$ |
| Macro-F1 | $\text{Macro-}F1 = \frac{1}{C}\sum_{c=1}^{C} F1_c$ |
| Weighted-F1 | $\text{Weighted-}F1 = \sum_{c=1}^{C}\frac{n_c}{N} \cdot F1_c$ |

### A.2 FDD 专用指标

| 指标 | 公式 |
|------|------|
| FAR | $\text{FAR} = \frac{FP}{FP+TN}$ |
| MDR | $\text{MDR} = \frac{FN}{TP+FN} = 1 - \text{FDR}$ |
| FIA | $\text{FIA} = \frac{\text{正确隔离的故障数}}{\text{总故障数}}$ |
| Detection Score | $\text{Score} = \text{FDR} - \text{FAR}$ |

### A.3 ROC / PR 曲线

| 指标 | 公式/说明 |
|------|----------|
| TPR (Recall) | $\frac{TP}{TP+FN}$ |
| FPR | $\frac{FP}{FP+TN}$ |
| Precision | $\frac{TP}{TP+FP}$ |
| AUC-ROC | ROC 曲线下面积 |
| AUC-PR | PR 曲线下面积 |
| Macro-AUC | 各类别 AUC 的算术平均 |

### A.4 HI 质量指标

| 指标 | 公式 |
|------|------|
| Monotonicity | $\text{Mon}(X) = \frac{1}{K-1} \left| \#(\frac{d}{dx}>0) - \#(\frac{d}{dx}<0) \right|$ |
| Trendability | $\text{Tre}(X,T) = \frac{K(\sum x_k t_k) - (\sum x_k)(\sum t_k)}{\sqrt{[K\sum x_k^2 - (\sum x_k)^2][K\sum t_k^2 - (\sum t_k)^2]}}$ |
| Prognosability | $\text{Pro} = \exp\left(-\frac{\text{std}_j(x_j(N_j))}{\text{mean}_j|x_j(1)-x_j(N_j)|}\right)$ |

### A.5 去噪指标

| 指标 | 公式 |
|------|------|
| PSNR | $\text{PSNR} = 20 \cdot \log_{10}\left(\frac{\max(|x|)}{\sqrt{\text{MSE}}}\right)$ |
| PRD | $\text{PRD} = \frac{\sqrt{\sum(x_{denoised}-x_{clean})^2}}{\sqrt{\sum x_{clean}^2}} \times 100\%$ |
| NCC | $\text{NCC} = \frac{\sum_i (c_i-\bar{c})(d_i-\bar{d})}{\sqrt{\sum_i(c_i-\bar{c})^2}\sqrt{\sum_i(d_i-\bar{d})^2}}$ |
| Crest Factor Improvement | $\Delta CF = CF_{after} - CF_{before}$ |

---

> **维护者**：AI Agent  
> **版本**：v1.0 — 基于现有评估框架（2026-05-17）与 PHM/FDD 领域论文标准制定  
> **关联文档**：`AGENTS.md`（数据集与算法参数）、`docs/algorithms/wavelet_and_modality_decomposition.md`（算法原理）、`docs/backend/app/services/diagnosis/`（代码接口）
