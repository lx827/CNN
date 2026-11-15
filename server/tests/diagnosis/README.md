# 诊断测试

运行环境、测试选择与验收命令见 [测试索引](../../../docs/tests/INDEX.md)。所有 Python 命令在 `cloud/` 中通过 `uv run` 执行。

| 目录 | 当前用途 |
|------|----------|
| `regression/` | 无数据集依赖的 P0：参数安全、CPW、变速阶次 |
| `algorithms/` | 算法已知解与负对照、Domain、Engine 和 HTTP 契约 |
| `foundation/layer1/`、`layer2/` | 合成信号数学正确性 |
| `foundation/layer4/` | 合成信号去噪调度与转频估计 |
| `planetary/` | 行星运动学、Pipeline、基线门控、业务与 API |
| `real_data/` | 原始记录 reader、提交选样清单与串行评估入口 |
| `../test_diagnosis_workflow.py` | SQLite、缓存、重评、worker、事务与告警 |

数据来源、采样率和物理前提见 [数据集契约](../../../docs/datasets.md)。合成信号正确性、业务契约和真实效果分别验收，不用测试项数证明真实设备检出效果。
