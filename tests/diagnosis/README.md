# tests/diagnosis — 诊断算法回归与有效性测试

> 所有测试脚本需在 cloud venv 中运行，并添加 cloud 模块路径。

## 目录结构

```
tests/diagnosis/
├── README.md                              # 本文档
├── __init__.py                            # 包标记
├── algorithm_evaluation_framework.py      # 学术论文级评价框架
├── planetary_e2e_results.json            # 行星齿轮箱 E2E 结果缓存
│
├── regression/                             # 回归测试（每次部署前必须通过）
│   ├── test_none_params.py                # None 参数鲁棒性
│   ├── test_cpw_robustness.py             # CPW 边界参数
│   └── test_varying_speed_order.py        # 变速阶次跟踪
│
├── effectiveness/                          # 核心有效性测试
│   ├── test_effectiveness.py              # 主测试（CW+WTgearbox）
│   ├── test_dataset_effectiveness.py      # HUSTbear+CW 批量
│   └── test_core_algorithms.py            # HUSTbear 核心算法
│
├── gear/                                   # 齿轮诊断专项
│   ├── test_gear_detail.py                # 齿轮诊断明细
│   ├── test_gear_values.py                # 齿轮指标值对比
│   ├── test_time_features.py              # 时域特征明细
│   ├── test_fm4.py                        # FM4/M6A/M8A 区分力
│   └── test_c2_features.py                # c1/c2 通道对比
│
├── planetary/                              # 行星齿轮箱端到端
│   ├── test_planetary_e2e.py              # 端到端完整流水线
│   └── test_planetary_demod.py            # 解调方法区分力
│
├── algorithms/                             # 新算法/引擎回归
│   ├── test_engine_regressions.py         # 引擎回归
│   ├── test_new_algorithms.py             # 新算法验证
│   ├── test_emd_denoise.py               # EMD/CEEMDAN 降噪
│   ├── test_research_ensemble.py          # Research Ensemble
│   └── test_scoh_fix.py                   # SC/SCoh 归一化修复
│
├── benchmark/                              # 辅助评估/基准
│   ├── test_benchmark.py                  # 离线基准评估
│   └── test_rot_freq_estimation.py        # 转频估计测试
│
├── debug/                                  # 调试/诊断
│   └── debug_cw_fp.py                     # CW 误判原因诊断
│
└── evaluation/                             # 离线评估框架（论文级指标）
    ├── main.py                            # 统一调度入口
    ├── bearing_eval.py                    # 轴承算法评价
    ├── gear_eval.py                       # 齿轮算法评价
    ├── denoise_eval.py                    # 去噪算法评价
    ├── robustness_eval.py                 # 鲁棒性测试
    ├── comprehensive_eval.py              # 综合诊断评价
    ├── classification_metrics_eval.py     # 高级分类指标
    ├── ds_fusion_eval.py                  # D-S 融合评价
    ├── health_trend_eval.py               # 健康度趋势评价
    ├── channel_consensus_eval.py          # 多通道共识评价
    ├── report_generator.py                # 报告生成器
    ├── utils.py                           # 通用工具函数
    ├── config.py                          # 全局配置
    └── datasets.py                        # 数据集加载
```

## 运行方式

```bash
cd D:\code\CNN\cloud
. venv/Scripts/activate

# 回归测试（部署前必过）
python ../tests/diagnosis/regression/test_none_params.py
python ../tests/diagnosis/regression/test_cpw_robustness.py
python ../tests/diagnosis/regression/test_varying_speed_order.py

# 有效性测试
python ../tests/diagnosis/effectiveness/test_effectiveness.py

# 齿轮专项
python ../tests/diagnosis/gear/test_fm4.py

# 行星齿轮箱 E2E
python ../tests/diagnosis/planetary/test_planetary_e2e.py

# 新算法验证
python ../tests/diagnosis/algorithms/test_new_algorithms.py

# 离线评估框架（生成论文/竞赛图表）
python ../tests/diagnosis/evaluation/main.py
```

服务器端：
```bash
cd /opt/CNN/cloud
source venv/bin/activate
python ../tests/diagnosis/regression/test_none_params.py
```

## 测试文件说明

### 回归测试（核心，每次部署前必须通过）

| 文件 | 用途 |
|------|------|
| `regression/test_none_params.py` | 验证 bearing_params/gear_teeth 为 None 时算法不崩溃 |
| `regression/test_cpw_robustness.py` | 验证 CPW 对 rot_freq=None/0/负值/空频组合的鲁棒性 |
| `regression/test_varying_speed_order.py` | 验证变速阶次跟踪算法的正确性 |

### 有效性测试（评估检出率和误诊率）

| 文件 | 用途 | 数据集 |
|------|------|--------|
| `effectiveness/test_effectiveness.py` | **主测试**：CW轴承+WTgearbox全面有效性评估 | CW + WTgearbox |
| `effectiveness/test_dataset_effectiveness.py` | HUSTbear+CW 全工况批量评估 | HUSTbear + CW |
| `effectiveness/test_core_algorithms.py` | HUSTbear 核心算法验证 | HUSTbear |

### 齿轮诊断专项（WTgearbox）

| 文件 | 用途 |
|------|------|
| `gear/test_gear_detail.py` | 齿轮诊断明细：fault_indicators/votes/时域特征 |
| `gear/test_gear_values.py` | 齿轮指标值对比：健康 vs 故障 |
| `gear/test_time_features.py` | 各工况时域特征明细（kurt/crest/rms） |
| `gear/test_fm4.py` | FM4/M6A/M8A 对行星齿轮箱的区分力测试 |
| `gear/test_c2_features.py` | c1/c2 通道特征对比 |

### 行星齿轮箱端到端（WTgearbox 160 文件）

| 文件 | 用途 |
|------|------|
| `planetary/test_planetary_e2e.py` | 端到端完整诊断流水线评估（检出率/误报率/区分力） |
| `planetary/test_planetary_demod.py` | 全部解调方法对健康/故障的区分力统计 + 计算时间 |

### 新算法/引擎回归

| 文件 | 用途 |
|------|------|
| `algorithms/test_engine_regressions.py` | 诊断引擎回归：无参数走统计诊断、齿轮 TSA/残差、转频稳定 |
| `algorithms/test_new_algorithms.py` | 新算法验证（HUSTbear/CW/WTgearbox） |
| `algorithms/test_emd_denoise.py` | EMD/CEEMDAN 降噪回归 |
| `algorithms/test_research_ensemble.py` | Research Ensemble 回归测试 |
| `algorithms/test_scoh_fix.py` | SC/SCoh 归一化修复验证 |

### 辅助评估/基准

| 文件 | 用途 |
|------|------|
| `benchmark/test_benchmark.py` | 离线基准评估框架：三数据集批量运行，统计健康度分布 |
| `benchmark/test_rot_freq_estimation.py` | 转频估计（转速提取）算法测试 |

### 调试/诊断

| 文件 | 用途 |
|------|------|
| `debug/debug_cw_fp.py` | CW 健康数据误判原因诊断：逐项打印健康度评分的中间值和扣分项 |

### 当前有效性基线（2026-05-15）

**CW 轴承数据集（仅轴承参数）**：
- 健康(H)：0% 误诊 ✅
- 内圈(I)：75% 检出（I-A升速工况漏检）
- 外圈(O)：100% 检出 ✅

**WTgearbox 行星齿轮箱（仅齿轮参数）**：
- 健康(He)：12.5% 误诊（N1_45/55 kurt>12 已知局限）
- 缺齿(Mi)：75% 检出 ✅
- 断齿(Br)：12.5% 检出（kurt与健康重叠，已知局限）
- 磨损(We)：12.5% 检出（同上）
- 裂纹(Rc)：0% 检出（时域特征与健康无异，已知局限）

> **根本原因**：行星齿轮箱的频域指标(SER/CAR/sideband/FM4/M6A/M8A)对健康/故障无区分力，
> 时域峭度与健康N1子集重叠(kurt=8~22)。这是行星齿轮箱诊断的公认难题。
