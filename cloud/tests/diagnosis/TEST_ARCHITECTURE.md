# 诊断测试架构

测试按证据职责组织，运行方式见 [测试索引](../../../docs/tests/INDEX.md)。

| 证据职责 | 当前入口 | 判断依据 |
|----------|----------|----------|
| 信号基元 | `foundation/layer1/` | 已知频率、幅值、统计量、滤波与合成调制 |
| 特征与预处理 | `foundation/layer2/` | 已知解、单位、参数和非法输入边界 |
| 去噪调度 | `foundation/layer4/test_engine_deep.py` | 合成信号与明确不可判定路径 |
| 算法族 | `algorithms/`、`planetary/` | 数学参考、负对照、前提与实际 Pipeline 串联 |
| 统一诊断 | `algorithms/test_diagnosis_domain.py` | Evidence 去重、对象 coverage、评估状态与结论 |
| 持久化业务 | `../test_diagnosis_workflow.py` | 实际 HTTP、SQLite、缓存身份、事务与告警 |
| 原始数据 | `real_data/` | 来源格式、真实采样率、分组、前提门控及效果评估 |
| 必跑回归 | `regression/` | None 参数、CPW 和变速阶次，全部合成信号 |

先验证算法公式、单位与物理前提，再验证业务消费。真实记录使用提交清单和 [数据集契约](../../../docs/datasets.md)；通道与窗口不能增加独立采集数。

按模块或单文件选择测试。脚本式测试可能在导入时运行计算，不对 `cloud/tests/` 整体 discover。
