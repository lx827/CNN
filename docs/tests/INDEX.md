# 测试与验收入口

Python 环境由根目录单项目统一管理。仓库根目录先执行 `uv sync`（Windows 构建用 Git Bash 的 `vsdev uv sync`），以下 Python 命令在 `cloud/` 执行；前端命令在 `wind-turbine-diagnosis/` 执行。按模块或单文件选择测试，脚本式测试可能在导入时计算，不对 `cloud/tests/` 整体 discover。

计算包安装后的行为在根目录运行 `uv run --no-sync python tests/test_compute_package.py -v`，检查真实编译器/目标/SIMD 信息及独立分发依赖。源码变更重建、ISA 缓存和双平台说明见 [计算库构建说明](../native_compute.md)。

算法正确性以公式、单位、物理前提、已知解、独立参考和负对照为依据。业务测试验证状态与副作用；真实数据输出与性能分别核对。文档链接检查不能替代正确性验证。

## P0 回归

修改 `cloud/app/services/diagnosis/` 或 `cloud/app/algorithms/` 下任何文件后，以下三件必须全部通过，均使用合成信号：

```bash
cd cloud
uv run python tests/diagnosis/regression/test_none_params.py
uv run python tests/diagnosis/regression/test_cpw_robustness.py
uv run python tests/diagnosis/regression/test_varying_speed_order.py
```

覆盖 None 参数与未知状态、CPW 非法参数，以及解析转速积分、角域重采样、已知阶次、近频峰、单边幅值、快速扫频和不同采样率分辨率。设置 `TEST_PLOT=1` 可出图至 `regression/output/`。

## 诊断算法与业务

| 边界 | 当前入口 | 证据 |
|------|----------|------|
| 信号基元与特征 | `cloud/tests/diagnosis/foundation/layer1/`、`layer2/` | 合成信号、手算统计、滤波、阶次与预处理 |
| 去噪调度 | `foundation/layer4/test_engine_deep.py`（同诊断目录） | 合成信号与转频不可判定 |
| 证据与状态 | `algorithms/test_diagnosis_domain.py` | 依赖去重、冲突、对象 coverage、状态与单次权重 |
| 唯一生产流程 | `cloud/tests/test_diagnosis_workflow.py` | SQLite 迁移、HTTP、缓存、重评、worker、事务回滚、告警与转频隔离 |
| 标准包络 | `algorithms/test_bearing_envelope_analysis.py`、`test_bearing_envelope_pipeline.py`、`test_bearing_envelope_api.py` | 谱峰唯一归属、幅值、边带、前提门控、Engine 与 HTTP |
| 高级轴承 | `algorithms/test_bearing_*_advanced.py`、`test_bearing_advanced_business.py`、`test_bearing_advanced_api.py` | 谱峭度、反卷积、CPW/TEO、循环平稳已知解、负对照与专属评估 |
| 定轴齿轮 | `algorithms/test_fixed_axis_gear.py`、`test_fixed_axis_gear_api.py` | TSA 恒等式、矩与边带手算、健康参考、重评与 HTTP |
| 行星齿轮 | `planetary/test_planetary_pipeline.py`、`test_planetary_business.py`、`test_planetary_api.py` | 运动学、参考轴、角域残差、健康参考与工况、Engine 和 HTTP |
| 阶次 | `algorithms/test_order_pipeline.py`、`test_order_integration.py` | 解析积分、快扫频、幅值与谱轴、Engine、HTTP 与持久化 |
| 分解 | `algorithms/test_decomposition_*.py` | 小波/EMD/VMD 数学参考、频率序、质量门控、反例与实际消费者 |
| 复合研究 | `algorithms/test_composite_pipelines.py`、`test_composite_research_api.py` | 已知解、阶段串联、消融、五组合 HTTP 与生产隔离 |
| 引擎回归 | `algorithms/test_engine_regressions.py` | 无参数、TSA、噪声转频和零信号不可判定，全部合成信号 |
| 公共数值 | `cloud/tests/test_numeric_algorithms.py`、`test_numeric_routes.py` | FFT/STFT/倒谱、统计、通用包络、显示抽点与响应契约 |
| 去噪失败 | `cloud/tests/test_preprocessing_failures.py` | 真实 HTTP/worker、失败状态、无告警与 422 schema |

诊断目录单文件示例：

```bash
uv run python tests/diagnosis/algorithms/test_engine_regressions.py
uv run python tests/diagnosis/planetary/test_planetary_pipeline.py
uv run python -m unittest tests.test_diagnosis_workflow tests.test_preprocessing_failures -v
```

完整测试职责见 [诊断测试架构](../../cloud/tests/diagnosis/TEST_ARCHITECTURE.md)。算法族前提见 [算法索引](../algorithms/INDEX.md)。

## 本地真实数据测试

`cloud/tests/diagnosis/real_data/` 使用提交清单和 `DATA_ROOT/raw_sources/`。来源、采样率、分组、机械参数和测速前提见 [数据集契约](../datasets.md)。独立 worktree 可设置 `CNN_DATA_ROOT` 共享数据根。

`common.LoadedRecord` 统一表示采集窗口；`bearing.py`、`gear.py` 读取原始格式，`effectiveness.load_record` 按数据身份分派。固定选样、SHA256、标签、分组和条件假设保存在 `real_data/manifests/effectiveness.json`。这些是本地测试代码，不提供 HTTP 接口或数据库接入。

格式、reader 与统计合同检查：

```bash
uv run python -m unittest tests.diagnosis.real_data.test_common tests.diagnosis.real_data.test_bearing tests.diagnosis.real_data.test_gear tests.diagnosis.real_data.test_effectiveness -v
```

格式测试使用临时小文件，缺本地真实清单时 reader 测试可跳过。真实验收需运行显式清单入口并检查报告；缺文件、样本、通道或坏格式均须非零退出。窗口最多 5 秒，HUST 齿轮按 1.28 秒块边界截断，按实际时长报告。通道和窗口不能增加独立采集数。

固定本地真实数据测试使用提交清单，逐记录、逐通道串行运行：

```powershell
$env:CNN_DATA_ROOT='D:/code/CNN/data'
uv run python -m tests.diagnosis.real_data.effectiveness --data-root $env:CNN_DATA_ROOT
```

现有产品前提与显式物理参数假设分开统计，健康参考记录不进入输出核对分母，失败和 unknown 保留在分母。本次核对数据接入与规范输出，不设检出效果达标目标。运行方式、输出契约和仅重新渲染本地报告的命令见 [真实数据测试说明](../benchmarks/diagnosis_effectiveness.md)。

## 本地性能基准

在 `cloud/` 安装可选 benchmark 依赖组并执行固定配置：

```powershell
uv sync --group benchmark
uv run --group benchmark python -m tests.diagnosis.benchmarks.run --data-root D:/code/CNN/data
uv run --group benchmark python -m tests.diagnosis.benchmarks.export --input D:/code/CNN/data/real_diagnosis/performance/20261112
```

配置位于 `cloud/tests/diagnosis/benchmarks/config.json`，测量边界、正确性观察和原生内核契约见 [性能基准说明](../benchmarks/diagnosis_performance.md)。计时排除导入、加载、预热和序列化；受限本地进程的测量不等同于生产整机负载验收。

所有生成的结果、JSON、CSV、日志、图表和自动实验 Markdown 保留在 `DATA_ROOT/real_diagnosis/`。仓库只保存源码、冻结清单/配置和手写运行说明。

## 后端读写与采集

| 入口（`cloud/tests/`） | 覆盖 |
|-----------------------|------|
| `test_read_paths.py` | 摘要查询、排序、JSON、缓存、索引迁移与 HTTP |
| `test_event_loop.py` | 慢去噪期间 STFT、倒谱、阶次端点的协程调度 |
| `test_analysis_worker_json.py` | NumPy 入库、通道缓存、批次标记、告警输入与 JSON 推送 |
| `test_hustbear_registration.py` | 内存 SQLite 注册、幂等和冲突整批回滚 |
| `test_dc24_acquisition.py` | 认证、任务、四通道 CSV、下载、FFT/RMS/包络与错误归档 |
| `test_dc24_driver.py` | 回环 TCP、控制帧、分片、24 位计数、停止、取消和序号缺口 |
| `test_dc24_live.py` | 原厂档位、示波窗口、保存、上传、缓存上限与 WS |

```bash
uv run python -m unittest tests.test_analysis_worker_json tests.test_read_paths tests.test_event_loop tests.test_hustbear_registration -v
uv run python -m unittest tests.test_dc24_acquisition tests.test_dc24_driver tests.test_dc24_live -v
```

DC24 工具链在 `dc24/` 直跑：

```bash
uv run python tests/test_dc24_start.py -v
uv run python tests/test_dc24_vendor.py -v
uv run python tests/test_dc24_edge_pi.py -v
```

start 实际调用 Windows 批处理的 `--check`。vendor 需要配置原厂 DLL，使用回环模拟器，未配置时跳过。edge_pi 的纯逻辑测试验证窗口、缺口与重试；集成测试加载真实 cdylib，使用假设备和假云端核对完整收件，无 Rust 工具链时可跳过。MSVC 编译遵守根 AGENTS 的 `vsdev` 约定。

## 前端

在 `wind-turbine-diagnosis/` 执行全部 Node 测试和构建：

```bash
node --test tests/*.test.cjs
npm run build
```

测试使用真实 Vue setup/watch/卸载及受控 API/ECharts/WS 替身，覆盖诊断状态、coverage、研究结果、机械表单、监测/看板刷新、采集保存与停止、登录返回和错误消息。它们不验证浏览器像素或真实设备检出效果。

## 按改动选择验证

| 修改范围 | 最小验证 |
|----------|----------|
| 诊断算法或服务 | P0 + 对应算法已知解/负对照 + 实际业务消费者 |
| Domain、assessment、存储或编排 | P0 + domain/workflow 的 HTTP、worker、缓存、事务与告警 |
| 阶次 | P0 + order Pipeline/集成 + foundation 对应信号验证 |
| API 路由 | 对应 HTTP 测试和手动调用；涉及诊断实现时加 P0 |
| 原始 reader 或选样 | 格式合同 + 原始记录显式串行验收 |
| 前端 | 对应 Node 生命周期/契约测试 + 构建 |
| 文档 | `bash docs/internal/check_markdown_links.sh` |
