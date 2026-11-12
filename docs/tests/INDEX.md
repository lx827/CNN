# 测试与验收入口

Python 环境由根目录单项目统一管理。仓库根目录先执行 `uv sync`（Windows 构建用 Git Bash 的 `vsdev uv sync`），以下 Python 命令在 `cloud/` 执行；前端命令在 `wind-turbine-diagnosis/` 执行。按模块或单文件选择测试，脚本式测试可能在导入时计算，不对 `cloud/tests/` 整体 discover。

计算包安装后的行为在根目录运行 `uv run --no-sync python -m unittest discover -s tests -p 'test_compute*.py' -v`，检查真实编译器/目标/SIMD 信息、独立分发依赖、公共插值/三对角求解、输出所有权，以及生成类型存根和 `py.typed` 的安装。源码变更重建、ISA 缓存和双平台说明见 [计算库构建说明](../native_compute.md)。

本地 `emd.sift 0.8.1` 参考差分先显式启用 `emd-reference` 组（Windows 用 `vsdev uv sync --group emd-reference`），再执行上述根测试。参考未安装会跳过差分，生命周期测试仍运行，不能把跳过记作参考通过。C++ 接口测试通过 CMake 选项 `CNN_COMPUTE_BUILD_TESTS=ON` 构建并由 CTest 运行。受控测量入口与边界见 [原生 EMD 契约](../algorithms/decomposition/native_emd.md)。

集成筛分可定向运行 `uv run --no-sync python -m unittest discover -s tests -p 'test_compute_emd_ensemble.py' -v`，覆盖 EEMD single/flip、complete ensemble 的参考边界、随机性与所有权。CTest 中的 `emd_ensemble_contract` 验证内部执行接口同一工作区的跨规模复用；它与 Python 公开入口测试互补。

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
| EMD 筛分替换 | `algorithms/test_emd_sift_contract.py` | 公开入口注入、固定随机序列、四种配置组合、冻结预算与模态伪等价负例 |
| EMD 原生候选 | `algorithms/test_native_emd.py` | PCHIP/cubic × SD/Rilling 的 EMD/EEMD/CEEMDAN 差分、局部误差预算、所有权与失败边界；显式数据根下核对五条固定短向量 |
| EMD 性能准入规则 | `benchmarks/test_native_performance.py` | 冻结时间边界、零容差峰值、MAD/块间噪声、漏块与重复块；不执行性能测量 |
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

EMD 筛分替换与事前冻结的数值对照可独立运行：

```bash
uv run python -m unittest tests.diagnosis.algorithms.test_emd_sift_contract -v
```

[冻结契约](../../cloud/tests/diagnosis/benchmarks/native_emd_contract.json) 与 [手写对照资产](../../cloud/tests/diagnosis/algorithms/emd_reference_contract.py) 供后续 Python/原生差分复用；测试本身不生成需要提交的波形或 golden 数组，不表示已有原生性能结论。

已安装计算扩展后，四种插值/停止组合的 EMD 族原生候选在 `cloud/` 执行：

```powershell
$env:CNN_DATA_ROOT='D:/code/CNN/data'
uv run --no-sync python -m unittest tests.diagnosis.algorithms.test_native_emd -v
```

未设置 `CNN_DATA_ROOT` 时仅跳过固定真实数据项；显式设置后缺向量或 SHA256 不符均失败。固定项复用既有性能 campaign 的四个真实来源与一条合成 4096 点输入，包含原采样率/参数身份，并覆盖四配置的三个公开算法族。Windows baseline、AVX2 与 WSL Ubuntu 的对应测试分别验收；WSL 使用独立 Linux 环境和构建目录，不能代表生产 ECS 整机资源验收。端到端成本与两倍性能目标由下述 #106 独立基准验收。

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

#106 的同公式 Python/原生 EMD 族入口为 `cloud/tests/diagnosis/benchmarks/native_performance.py`，冻结配置为同目录 `native_performance_config.json`。五条原 SHA256 短向量 × 两档参数 × 三个算法族共 30 项，固定 PCHIP/SD；先 `prepare`、`check`，再 `measure`、`profile`、`report`。三块顺序为 AB/BA/AB，各后端每块五次计时，独立正确性/质量与 profile worker 不混入计时或 OS 峰值门槛。Windows/WSL 全矩阵、Linux 源码构建与 ECS 资源子集的命令及采用边界见 [性能基准说明](../benchmarks/diagnosis_performance.md)。

冻结准入计算可在 `cloud/` 独立验证，不运行基准：

```bash
uv run --no-sync python -m unittest tests.diagnosis.benchmarks.test_native_performance -v
```

旧 #79 `run.py` 仍是 Windows-only 的广义诊断基准，独立配置 `config.json`，其 worker 全生命周期峰值包含额外 profile；不能与 #106 在末次计时后、汇总前读取且排除独立 profile/quality 的峰口径混比。旧入口在 `cloud/` 安装可选 benchmark 依赖组并执行：

```powershell
uv sync --group benchmark
uv run --group benchmark python -m tests.diagnosis.benchmarks.run --data-root D:/code/CNN/data
uv run --group benchmark python -m tests.diagnosis.benchmarks.export --input D:/code/CNN/data/real_diagnosis/performance/20261112
```

两套入口均排除导入、加载、预热和序列化的算法计时；受限本地进程的测量不等同于生产整机负载验收。#106 要求生产档 CEEMDAN 中位耗时减半、EMD/EEMD 不超过本平台基线 1.05 倍、OS 峰值零增加，并核对噪声、质量与目标 ECS 整体服务余量；工具的本地成本结论不自动切换生产默认。

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
