# Tests — 回归测试与评估套件

> **文档用途**：统一记录所有测试文件的位置、用途、运行方式和依赖，避免重复编写测试。
> **维护要求**：新增测试文件时，必须在此索引中添加条目。

---

## 目录结构

```
tests/
├── README.md                              # 原始测试说明（旧版）
├── diagnosis/
│   ├── __init__.py
│   ├── regression/                        # [P0] 回归测试 — 每次修改后必跑
│   │   ├── test_none_params.py            # None 参数安全测试
│   │   ├── test_cpw_robustness.py         # CPW 鲁棒性测试
│   │   └── test_varying_speed_order.py    # 变速阶次跟踪测试
│   ├── algorithms/                        # 新增算法单元测试
│   │   ├── test_engine_regressions.py     # 诊断引擎回归（无参数/TSA/转频）
│   │   ├── test_research_ensemble.py      # 多算法集成诊断测试
│   │   ├── test_new_algorithms.py         # 新算法（EMD/MCKD/小波包/SG）测试
│   │   ├── test_emd_denoise.py            # EMD/CEEMDAN 降噪测试
│   │   └── test_scoh_fix.py               # SC/SCoh 循环平稳修复验证
│   ├── gear/                              # 齿轮诊断专项测试
│   │   ├── test_time_features.py          # 行星箱时域特征明细
│   │   ├── test_fm4.py                    # FM4 指标测试
│   │   ├── test_gear_detail.py            # 齿轮诊断细节调试
│   │   ├── test_gear_values.py            # 齿轮指标数值验证
│   │   └── test_c2_features.py            # C2 通道特征测试
│   ├── planetary/                         # 行星齿轮箱专项测试
│   │   ├── test_planetary_e2e.py          # 端到端评估（160文件检出率/误报率）
│   │   └── test_planetary_demod.py        # VMD/SC/SCoh/CVS 解调方法测试
│   ├── method_eval/                       # 方法级分类评估框架
│   │   ├── README.md                      # 评估框架说明
│   │   ├── main.py                        # 主入口
│   │   ├── config.py                      # 评估配置
│   │   ├── label_mapper.py                # 标签映射
│   │   ├── plot_generator.py              # 图表生成
│   │   ├── replot.py                      # 重新绘图工具
│   │   ├── visualizer.py                  # 可视化工具
│   │   ├── _final_gear_check.py           # 齿轮最终检查
│   │   ├── test_bearing_hustbear.py       # HUSTbear 轴承评估（11方法+集成）
│   │   ├── test_bearing_cw.py             # CW 轴承评估
│   │   ├── test_gear_wtgearbox.py         # WTgearbox 齿轮评估
│   │   └── test_binary_all.py             # 全部二分类评估
│   ├── evaluation/                        # 多维度评价框架
│   │   ├── main.py                        # 主入口（综合评估）
│   │   ├── config.py                      # 配置文件
│   │   ├── utils.py                       # 工具函数
│   │   ├── datasets.py                    # 数据集加载
│   │   ├── _check_imports.py              # 导入验证
│   │   ├── denoise_eval.py                # 去噪方法评估
│   │   ├── bearing_eval.py                # 轴承方法评估
│   │   ├── gear_eval.py                   # 齿轮方法评估
│   │   ├── comprehensive_eval.py          # 综合诊断评估
│   │   ├── robustness_eval.py             # 噪声鲁棒性评估
│   │   ├── classification_metrics_eval.py # 分类指标评估
│   │   ├── ds_fusion_eval.py              # D-S 融合评估
│   │   ├── health_trend_eval.py           # 健康趋势评估
│   │   ├── channel_consensus_eval.py      # 通道一致性评估
│   │   ├── report_generator.py            # 报告生成
│   │   └── generate_contest_plots.py      # 竞赛图表生成
│   ├── effectiveness/                     # 诊断有效性测试
│   │   ├── test_effectiveness.py          # 参数驱动跳过逻辑测试
│   │   ├── test_core_algorithms.py        # 核心算法有效性
│   │   └── test_dataset_effectiveness.py  # 数据集有效性
│   ├── benchmark/                         # 离线基准评估
│   │   ├── test_benchmark.py              # 三数据集批量评估
│   │   └── test_rot_freq_estimation.py    # 转频估计准确性
│   ├── contest/                           # 竞赛/答辩实验脚本
│   │   ├── main.py                        # 主入口
│   │   ├── config.py                      # 配置
│   │   ├── style.py                       # 图表风格
│   │   ├── experiment_a_bearing.py        # 实验A：轴承诊断
│   │   ├── experiment_b_gear.py           # 实验B：齿轮诊断
│   │   ├── experiment_c_denoise.py        # 实验C：去噪方法
│   │   ├── experiment_d_robustness.py     # 实验D：鲁棒性
│   │   ├── experiment_e_fusion.py         # 实验E：融合方法
│   │   └── experiment_f_health.py         # 实验F：健康度评分
│   ├── foundation/                         # [P0+] 基础算法正确性测试
│   │   ├── synthetic_signals.py             # 合成信号生成器（含 ground truth）
│   │   ├── test_bearing_fault_freqs.py      # 轴承故障频率计算
│   │   ├── test_envelope_correctness.py     # 包络谱正确性
│   │   ├── test_order_tracking_correctness.py # 阶次跟踪正确性
│   │   ├── test_cepstrum_correctness.py     # 倒谱正确性
│   │   ├── plot_results.py                  # [独立绘图] 读 JSON 生成对比图
│   │   └── output/                          # JSON 结果 + PNG 图表
│   ├── debug/                             # 调试脚本（临时）
│   │   └── debug_cw_fp.py                 # CW 健康数据误判诊断
│   └── output/                            # 测试输出（图表等）
└── output/                                # 顶层测试输出
```

---

## 0. 基础算法正确性测试（P0+ — 验证算法计算是否正确）

> **用途**：使用合成信号（含已知 ground truth）+ 真实数据集，验证基础算法（轴承频率/包络/阶次/倒谱）的计算结果是否正确。
> **数据输出**：测试结果以 JSON 存入 `output/`，独立绘图脚本 `plot_results.py` 读取 JSON 生成对比图，无需重跑分析。

| 文件 | 验证内容 | 测试方式 |
|------|---------|---------|
| `test_bearing_fault_freqs.py` | BPFO/BPFI/BSF/FTF 公式计算 | 与手动理论值对比，相对误差 < 0.001% |
| `test_envelope_correctness.py` | 包络谱峰值 SNR 检测 | 合成冲击信号（50/100/150Hz）+ 合成轴承信号 + 真实 HUSTbear 数据 |
| `test_order_tracking_correctness.py` | 转频估计 + 变速跟踪 | 合成正弦信号（10/25/50/80Hz）+ 扫频信号 + 真实 HUSTbear 数据 |
| `test_cepstrum_correctness.py` | 倒谱峰值检测 | 合成齿轮啮合信号（mesh=450Hz）+ 合成谐波信号 |

**一键运行**：

```bash
cd /d/code/CNN
d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\foundation\test_bearing_fault_freqs.py
d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\foundation\test_envelope_correctness.py
d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\foundation\test_order_tracking_correctness.py
d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\foundation\test_cepstrum_correctness.py
```

**独立绘图**（不重跑分析）：

```bash
d:\code\CNN\cloud\venv\Scripts\python.exe tests\diagnosis\foundation\plot_results.py
```

---

## 1. 回归测试（P0 — 每次修改后必须运行）

> **⚠️ 重要**：对 `cloud/app/services/diagnosis/` 下任何文件的修改完成后，必须运行以下回归测试。

### 1.1 `test_none_params.py` — None 参数安全

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_none_params.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证设备参数为 None 时诊断引擎不崩溃 |
| **测试范围** | `_compute_bearing_fault_freqs`, `_extract_spectrum_features`, `DiagnosisEngine` 各方法 |
| **数据集** | 不需要（使用合成信号） |
| **通过标准** | 所有 assert 通过，无异常抛出 |

### 1.2 `test_cpw_robustness.py` — CPW 鲁棒性

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_cpw_robustness.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证 CPW 在非法参数（rot_freq=None/-5/0, 空 comb_frequencies）下不崩溃 |
| **数据集** | 不需要（使用合成信号） |
| **通过标准** | 所有边界条件测试通过 |

### 1.3 `test_varying_speed_order.py` — 变速阶次跟踪

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_varying_speed_order.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证变速工况下阶次跟踪算法正确性 |
| **数据集** | 需要 HUSTbear 数据集 `D:\code\wavelet_study\dataset\HUSTbear\down8192` |
| **通过标准** | 转频估计在合理范围，多帧 vs 单帧阶次谱差异可接受 |

### 1.4 一键回归测试

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/regression/test_none_params.py && python ../tests/diagnosis/regression/test_cpw_robustness.py && python ../tests/diagnosis/regression/test_varying_speed_order.py && echo "ALL REGRESSION TESTS PASSED"
```

---

## 2. 新增算法测试

> 位于 `tests/diagnosis/algorithms/`，用于验证新加算法模块的正确性。

| 文件 | 用途 | 需要数据集 | 运行方式 |
|------|------|-----------|---------|
| `test_engine_regressions.py` | 诊断引擎核心回归（无参数/TSA/转频/健康区分） | HUSTbear/CW（可选） | `python ../tests/diagnosis/algorithms/test_engine_regressions.py` |
| `test_research_ensemble.py` | 多算法集成诊断（ensemble）正确性 | 无 | 同上 |
| `test_new_algorithms.py` | EMD/MCKD/小波包/SG 等新算法功能验证 | 无 | 同上 |
| `test_emd_denoise.py` | EMD/CEEMDAN 降噪模块测试 | 无 | 同上 |
| `test_scoh_fix.py` | SC/SCoh 循环平稳分析修复验证 | 无 | 同上 |

---

## 3. 齿轮诊断专项测试

| 文件 | 用途 | 需要数据集 | 说明 |
|------|------|-----------|------|
| `test_time_features.py` | 行星齿轮箱时域特征明细（kurt/crest/rms/skew） | WTgearbox | 查看 He_N1/N2 各转速下时域特征分布 |
| `test_fm4.py` | FM4 指标测试 | WTgearbox | 验证 FM4 对齿轮故障的区分力 |
| `test_gear_detail.py` | 齿轮诊断细节调试 | WTgearbox | 逐项打印诊断结果 |
| `test_gear_values.py` | 齿轮指标数值验证 | WTgearbox | 验证 SER/CAR/阶次峭度等指标数值 |
| `test_c2_features.py` | C2 通道特征测试 | WTgearbox | 与 C1 通道对比 |

---

## 4. 行星齿轮箱专项测试

| 文件 | 用途 | 数据集 | 运行时间 |
|------|------|--------|---------|
| `test_planetary_e2e.py` | 端到端评估：160 文件批量诊断，统计检出率/误报率/区分力 | WTgearbox (160文件) | ~10分钟 |
| `test_planetary_demod.py` | VMD/SC/SCoh/CVS/TSA 等解调方法单独测试 | WTgearbox | ~3分钟 |

```bash
# 端到端评估
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/planetary/test_planetary_e2e.py
```

---

## 5. 方法级分类评估框架 (`method_eval/`)

> 对每种诊断方法独立评估二分类/多分类性能，生成 ROC 曲线、混淆矩阵等。

| 文件 | 用途 | 数据集 |
|------|------|--------|
| `main.py` | 主入口，运行全部评估 | — |
| `test_bearing_hustbear.py` | HUSTbear 轴承评估：11种方法+集成，二分类+五分类 | HUSTbear |
| `test_bearing_cw.py` | CW 轴承评估：变速工况下的轴承方法性能 | CW |
| `test_gear_wtgearbox.py` | WTgearbox 齿轮评估：齿轮方法性能 | WTgearbox |
| `test_binary_all.py` | 全部二分类评估（健康 vs 故障） | 三个数据集 |

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/method_eval/test_bearing_hustbear.py
```

---

## 6. 多维度评价框架 (`evaluation/`)

> 系统性地评估去噪、轴承、齿轮、综合诊断、鲁棒性等各维度。

| 文件 | 用途 |
|------|------|
| `main.py` | 主入口，运行全部评估维度 |
| `denoise_eval.py` | 去噪方法对比评估 |
| `bearing_eval.py` | 轴承诊断方法评估 |
| `gear_eval.py` | 齿轮诊断方法评估 |
| `comprehensive_eval.py` | 综合诊断（轴承+齿轮）评估 |
| `robustness_eval.py` | 噪声鲁棒性评估 |
| `classification_metrics_eval.py` | 分类指标（准确率/召回率/F1） |
| `ds_fusion_eval.py` | D-S 证据融合效果评估 |
| `health_trend_eval.py` | 健康度趋势评估 |
| `channel_consensus_eval.py` | 多通道一致性评估 |
| `report_generator.py` | 评估报告生成 |

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/evaluation/main.py
```

---

## 7. 其他测试

### 7.1 有效性测试 (`effectiveness/`)

| 文件 | 用途 |
|------|------|
| `test_effectiveness.py` | 参数驱动跳过逻辑测试：仅轴承/仅齿轮/都有/都无 四种场景 |
| `test_dataset_effectiveness.py` | 数据集本身的诊断可行性评估 |

### 7.2 竞赛实验 (`contest/`)

> 大创/答辩用实验脚本，一键生成图表。

```bash
cd /d/code/CNN/cloud
. venv/Scripts/activate
python ../tests/diagnosis/contest/main.py
```

### 7.3 调试 (`debug/`)

| 文件 | 用途 |
|------|------|
| `debug_cw_fp.py` | CW 健康数据误判原因诊断，逐项打印扣分项 |

---

## 8. 测试运行环境要求

| 数据集 | 路径 | 用途 |
|--------|------|------|
| HUSTbear | `D:\code\wavelet_study\dataset\HUSTbear\down8192` | 轴承诊断评估 |
| CW | `D:\code\CNN\CW\down8192_CW` | 变速轴承诊断评估 |
| WTgearbox | `D:\code\wavelet_study\dataset\WTgearbox\down8192` | 齿轮诊断评估 |

> 回归测试（P0）不需要数据集，使用合成信号即可运行。

---

## 9. 何时运行哪些测试

| 修改范围 | 最小测试集 |
|---------|-----------|
| `features.py`, `engine.py`, `ensemble.py` | P0回归 + algorithms/ |
| `bearing.py`, `bearing_cyclostationary.py` | P0回归 + `test_bearing_hustbear.py` |
| `gear/`, `planetary_demod.py` | P0回归 + `test_planetary_e2e.py` |
| `health_score.py` | P0回归 + `test_effectiveness.py` |
| `order_tracking.py` | `test_varying_speed_order.py` |
| `preprocessing.py`, `vmd_denoise.py` | P0回归 + `test_cpw_robustness.py` |
| API 路由 (`data_view/`, `ingest.py` 等) | P0回归 + 手动 API 调用验证 |

---

*文档生成时间：2026-05-19*
*维护者：AI Agent（新增测试文件时请务必同步更新）*
