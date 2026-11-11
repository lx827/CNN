# 本地诊断测试交接

当前范围是四套本地原始数据的数据对象、可复用格式读取器、固定选样的真实数据测试、输出核对与性能测量。调用现有算法和规范诊断状态，不提供新的 HTTP 接口，不注册设备、不写业务数据库；未部署生产环境。

主仓数据根为 `D:/code/CNN/data`。Ottawa 轴承、HUSTbear 轴承、HUSTgearbox 定轴齿轮和 WT 行星齿轮的原始文件位于 `raw_sources/`，来源、采样率与物理前提见 [数据集契约](docs/datasets.md)。独立 worktree 使用 `CNN_DATA_ROOT` 或显式 `--data-root` 共享数据。

`cloud/tests/diagnosis/real_data/common.py` 的 `LoadedRecord` 表示一次采集的有限窗口，包含振动通道、原采样率、辅助信号和来源元数据。`bearing.py`、`gear.py` 负责格式读取，`effectiveness.load_record` 按数据身份分派；多通道与切窗不增加独立采集数。固定测试计划、标签、分组、来源哈希和条件假设保存在提交清单与配置中。

在 uv workspace 已同步的 `cloud/` 中运行：

```powershell
$env:CNN_DATA_ROOT='D:/code/CNN/data'
uv run python -m tests.diagnosis.real_data.effectiveness --data-root $env:CNN_DATA_ROOT
uv run --group benchmark python -m tests.diagnosis.benchmarks.run --data-root $env:CNN_DATA_ROOT
```

本地测试已执行。真实数据测试输出位于 `D:/code/CNN/data/real_diagnosis/effectiveness/`，性能输出位于 `D:/code/CNN/data/real_diagnosis/performance/`；完整结果、JSON、CSV、日志、图表和自动生成的实验 Markdown 均留在该数据根，不提交 Git。仓库保存源码、冻结清单/配置与手写说明。

当前验收命令和测试选择见 [测试索引](docs/tests/INDEX.md)，运行口径见 [真实数据测试](docs/benchmarks/diagnosis_effectiveness.md) 与 [性能基准](docs/benchmarks/diagnosis_performance.md)。真实数据测试区分现有产品前提与声明假设下的条件情景；性能测量记录受限进程的计算开销。本次范围为接入重构和输出核对，不包含检出效果优化验收。

算法与业务的权威契约仍为 [算法索引](docs/algorithms/INDEX.md)、[证据与状态](docs/backend/assessment.md)、[诊断编排](docs/backend/diagnosis.md) 和 [持久化](docs/backend/persistence.md)。本地实验不会将临时健康参考、假设速度或测试输出写回生产配置。
