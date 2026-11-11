# Tests — 回归测试与评估套件

> 文档链接检查不能替代正确性验证。算法先核对公式、单位、物理前提、手算/解析解、独立参考与负对照，再使用自动回归保护业务与状态；测试项数不证明算法正确。每次修改 `cloud/app/services/diagnosis/` 或 `cloud/app/algorithms/` 后仍须运行相应检查。
>
> 2026-11 布局重构(#45 地图 T3/#48)后,测试随被测物分立各端,顶层 `tests/` 已撤销:
>
> | 位置 | 内容 |
> |------|------|
> | `cloud/tests/` | 后端测试(原 `tests/backend`)+ 诊断测试套件(原 `tests/diagnosis`,含 P0 回归) |
> | `dc24/tests/` | DC24 工具链测试(原 `tests/edge` 中存活的 start/vendor 两件) |
> | `wind-turbine-diagnosis/tests/` | 前端 `.cjs` 测试(原 `tests/frontend`) |
>
> Python 环境统一为 uv workspace(#47):仓库根目录 `uv sync` 一次,所有 Python 测试用 `uv run` 执行;前端测试用 `node --test`(Node ≥18)。

## 本批 #75/#77/#84 业务验收导航（2026-11-11）

| 边界 | 当前入口 | 覆盖 |
|------|----------|------|
| 证据/状态核心 | `cloud/tests/diagnosis/algorithms/test_diagnosis_domain.py` | 依赖去重/冲突、混合对象 coverage、规范状态、单次权重、直接重评不执行算法 |
| 唯一生产流程 | `cloud/tests/test_diagnosis_workflow.py` | SQLite 迁移/幂等、真实 HTTP 缓存/重评/重分析、真实 worker、事务回滚、告警、转频摘要隔离和配置权重 |
| 既有实际消费者 | `test_analysis_worker_json.py`、`test_read_paths.py`、`test_preprocessing_failures.py`、`test_event_loop.py`（cloud/tests） | 新 Domain 读写、JSON、422、协程与生产缓存 |
| 复合算法 | `cloud/tests/diagnosis/algorithms/test_composite_pipelines.py` | 13 个已知解/负对照、实际阶段串联和消融 |
| 复合研究 HTTP | `test_composite_research_api.py`（同算法目录） | 五组合、资源/相位、生产隔离、实际 summary/参数与 heartbeat |
| 全前端 | `wind-turbine-diagnosis/tests/*.test.cjs` | diagnosis_state、research_summary、composite_research、bearing 与实际页面生命周期 |

后端按精确模块或单文件用 uv 运行，不整体 discover；全前端用 `node --test tests/*.test.cjs`。旧规则、连续评分、推荐、概率校准、通道共识及旧投票 helper 测试随重复实现删除，当前由 domain/workflow 业务契约与真实 HTTP 替代，不恢复旧接口兼容测试。

准确证据：本批 P0 7/5/17 各通过；集中后端首次 79 项存在 3 FAIL+2 ERROR 子项，修复后只定向四失败方法+分解 10 项共 14 通过，另 order 4、PUT HTTP 1、权重/重评 1 通过，没有宣称重新全跑 79。前端最终 52/52 与构建通过。#75 沿用核心 13、早期 HTTP 3/SSR 3/构建，以及最后参数 3/summary HTTP 1/SSR 1；未因文档再跑算法。SQLite 实际迁移/业务有证据，MySQL SQL 具备但无实际服务验证；真实效果/性能归 #78/#79。

## 原始真实数据接入（2026-11-11）

独立入口 `cloud/tests/diagnosis/real_data/` 读取提交的轴承/齿轮选样清单及 `DATA_ROOT/raw_sources/` 原始记录。来源与证据边界见 [数据集契约](../datasets.md)。它不兼容旧一维 8192 Hz npy，也不自动迁移历史效果脚本。

集中验证分两步：先 common/reader 合同与原始格式核实，再串行运行一个真实小窗。将数据根替换为自己的目录；独立 worktree 设 `CNN_DATA_ROOT` 共享主仓数据，临时文件随该根目录落盘：

```bash
cd cloud
# 先设置 CNN_DATA_ROOT=/path/to/data（PowerShell 使用 $env:CNN_DATA_ROOT）
uv run python -m unittest tests.diagnosis.real_data.test_common tests.diagnosis.real_data.test_bearing tests.diagnosis.real_data.test_gear -v
uv run python -m tests.diagnosis.real_data.run --data-root /path/to/data --window-seconds 1
```

格式测试使用小型临时文件；真实 reader 测试在本地清单缺失时可跳过，因此只看到 unittest 绿灯不表示真实数据验收完成。显式 runner 使用提交清单，缺数据/样本/通道、坏格式均非零退出。正常报告中的 unknown、coverage=none 和 health_score=null 表示物理前提不足，不应改成正常或 100 分。

窗口最大 5 秒，HUST 齿轮在 1.28 秒块边界截断；按实际时长报告。多通道和切窗不增加独立采集数。首批只核实数据接入、信号质量和现有 Pipeline 前提门控，不输出准确率，不等于完成 #78 效果评估或 #79 性能测量。本次没有修改生产算法，因此不因新增离线 reader 重跑 P0。

## P0 回归(全部合成信号、无数据集依赖;每次修改 `cloud/app/services/diagnosis/` 或 `cloud/app/algorithms/` 后必跑)

```bash
cd cloud
uv run python tests/diagnosis/regression/test_none_params.py
uv run python tests/diagnosis/regression/test_cpw_robustness.py
uv run python tests/diagnosis/regression/test_varying_speed_order.py
```

> 三件均使用合成信号,不需要任何数据集。出图默认关闭:设 `TEST_PLOT=1` 才绘制对比图,产物写入 `cloud/tests/diagnosis/regression/output/`(已 gitignore,不入库)。

扩展测试按目录选:正确性验证 `cloud/tests/diagnosis/foundation/layer1~5/`(如 `layer2/test_order_tracking_correctness.py`)、方法评估 `method_eval/`、行星箱端到端 `planetary/`、效果 `effectiveness/`、引擎回归 `algorithms/`;改 API 路由另加手动调用验证。

## DC24 实际采集(2026-11-05)

- `cloud/tests/test_dc24_acquisition.py`:隔离SQLite认证、任务领取/取消、完整四通道CSV上传下载、无分析模式、FFT/RMS/包络频带及错误归档拒绝。
- `cloud/tests/test_dc24_driver.py`:本机回环TCP仿真DC24,验证采样配置、半包、24位符号、B8停止、取消保存和序号缺口报错;固定断言2026-11-06新IEPE/PASS的实际B2/B5,防止重新发送旧电压模板;不连接实际硬件。
- `cloud/tests/test_dc24_live.py`:原厂12档、长时长/手动参数、拒绝回放示波、不落采样文件、实时数值、变长帧、保存首帧、流式传输、缓存上限、统计缺口和上传完成后才发布停止终态;WS 实时窗口(鉴权拒绝/4404/推送与选项与心跳,2026-11 #51)。
- `wind-turbine-diagnosis/tests/acquisition_lifecycle.test.cjs`:实际Vue setup/watch/卸载,验证不自动回放、示波中保存与停止、长时长/手动、显示与频带开关、目录选择结果和卸载;含 WS 推送路径(打开期间不 REST 轮询、view 绘制、选项上报,2026-11 #51);API/ECharts/WS 为替身,不覆盖像素。
- `wind-turbine-diagnosis/tests/acquisition_navigation.test.cjs`:实际路由守卫与登录组件,验证一键采集入口登录后返回采集页。
- `dc24/tests/test_dc24_start.py`:实际Windows cmd调用批处理的`--check`模式,覆盖真实启动入口的编码/行尾,不启动服务或采集。
- `dc24/tests/test_dc24_vendor.py`:配置原厂 DLL 后,用真实 32 位连接进程和回环模拟采集器核对控制帧、分片接收、四路计数和停止释放。未配置 DLL 时跳过,不连接现场设备。
- `dc24/tests/test_dc24_edge_pi.py`:树莓派驱动(`dc24_edge_pi.py`+`dc24_ffi.py`)回归——窗口缺口/清单重试状态机/心跳字段等纯逻辑单测,加回环集成:加载真实 `dc24_edge_core` cdylib、socket 假设备走完 BA/B8/B2/B5/B7→80帧→B8、假云端复刻 finish-stream 校验并注入 503 重试,断言五件套与云端收件逐字节一致。库定位 `DC24_EDGE_LIB`→`edge/target`→`cargo build` 兜底,无 Rust 工具链时跳过集成部分。

本机 Windows PowerShell,在CNN根目录运行,无需管理员权限,不访问远端或采集现场数据:

```powershell
# uv workspace 环境提供 SQLAlchemy、NumPy、SciPy、FastAPI 等;首次先在仓库根目录 uv sync。
# 后端 DC24 三件(unittest 模块形式,自 cloud/tests 包加载):
cd cloud
uv run python -m unittest tests.test_dc24_acquisition tests.test_dc24_driver tests.test_dc24_live -v
# DC24 工具链三件(直跑文件;start 件会真实调用 start_dc24.bat --check):
cd ../dc24
uv run python tests/test_dc24_start.py -v
uv run python tests/test_dc24_vendor.py -v
uv run python tests/test_dc24_edge_pi.py -v
# Node内置运行器执行采集页状态测试,依赖已有前端包,不启动浏览器或硬件。
cd ../wind-turbine-diagnosis
node --test tests/acquisition_lifecycle.test.cjs tests/acquisition_navigation.test.cjs
```

## 数据集启动回归(2026-10-23)

- `cloud/tests/test_hustbear_registration.py`:真实内存 SQLite 验证独立注册、幂等、CW 保持原样、冲突整批回滚,2 项,不连接业务数据库。
- ~~`tests/edge/test_replay.py`、`tests/edge/test_browser_open.py`、`tests/edge/test_frontend_lifecycle.py`~~:仅覆盖旧 `edge_client.py` 回放启动器,已随旧上云回放链退役(布局重构 #46,连同 `edge/replay.py`),不再迁移。

后端注册事务验证(本机 Windows,仓库根目录):

```powershell
cd cloud
uv run python -m unittest tests.test_hustbear_registration -v
```

**前端监测回归**:在 `wind-turbine-diagnosis/` 目录执行 `node --test tests/monitor_lifecycle.test.cjs`;`--test` 使用 Node.js 自带测试运行器。依赖前端已安装的 `vue` 和 `@vue/compiler-sfc`,无需新增依赖,不访问云端或创建采集任务。使用真实 Vue 生命周期与模拟 API/ECharts,验证首屏默认通道、通道切换、页面返回和异步卸载清理;不覆盖浏览器像素渲染。

**2026-10-21 新增回归**:

| 文件(新位置) | 覆盖 | 依赖 |
|---|---|---|
| `cloud/tests/test_read_paths.py` | 摘要 SQL/顺序、历史 N+1、严格 JSON、缓存、索引迁移、真实 HTTP 读路径(9 项) | uv workspace 后端依赖及 dev 组 httpx;隔离内存 SQLite |
| `cloud/tests/test_event_loop.py` | 慢去噪期间的协程调度(1 项,覆盖 STFT/倒谱/阶次三个端点) | 同上;受控去噪替身,不测去噪数学效果 |
| `cloud/tests/test_analysis_worker_json.py`(2026-10-23) | 实际后台 worker 的 NumPy 结果入库,通道缓存新增/更新,批次已分析标记、健康度、告警输入及严格 JSON 推送(2 项) | 内存 SQLite,算法替身;不访问云端或业务数据库 |
| `wind-turbine-diagnosis/tests/monitor_lifecycle.test.cjs` | 生命周期、推送合并、设备切换竞争、在途刷新、慢轮询(7 项) | 已安装前端依赖 |
| `wind-turbine-diagnosis/tests/dashboard_lifecycle.test.cjs` | 卸载释放、异步卸载、选中对象刷新、critical 显示、推送/轮询串行合并、失败恢复(6 项) | 已安装前端依赖 |
| `wind-turbine-diagnosis/tests/websocket.test.cjs` | 握手幂等、迟到回调、重连去重、单例/工厂端点隔离(5 项) | Node 自带 test/vm;WebSocket 替身 |

后端整组(30 项,本机 Windows):

```powershell
cd cloud
uv run python -m unittest tests.test_analysis_worker_json tests.test_dc24_acquisition tests.test_dc24_driver tests.test_dc24_live tests.test_event_loop tests.test_hustbear_registration tests.test_read_paths -v
```

前端整组(24 项):

```powershell
cd wind-turbine-diagnosis
node --test tests/acquisition_lifecycle.test.cjs tests/acquisition_navigation.test.cjs tests/dashboard_lifecycle.test.cjs tests/monitor_lifecycle.test.cjs tests/websocket.test.cjs
```

> `python -m unittest discover -s cloud/tests` 形式会递归导入 `cloud/tests/diagnosis` 下脚本式评估文件(模块级即执行、部分需数据集),不要对 cloud/tests 整体 discover;按上文模块清单或单文件运行。

测试运行环境和局限见 [架构整顿记录](../架构整顿记录_20261021.md)。

---

## 目录结构

```
cloud/tests/
├── test_read_paths.py                  # 摘要查询、缓存、索引和 HTTP
├── test_event_loop.py                  # 去噪期间事件循环响应
├── test_analysis_worker_json.py        # 后台 worker JSON 入库
├── test_dc24_acquisition.py            # DC24 任务/上传/下载/分析
├── test_dc24_driver.py                 # DC24 协议驱动(回环 TCP)
├── test_dc24_live.py                   # DC24 实时示波与保存
├── test_hustbear_registration.py       # HUSTbear 设备注册事务
└── diagnosis/                          # 诊断测试套件(整体自顶层 tests/diagnosis 迁入)
    ├── __init__.py
    ├── data_paths.py                   # 数据集路径统一入口(parents[3] 定位仓库根)
    ├── real_data/                     # 原始真实来源reader、便携选样清单、串行小窗CLI
    ├── TEST_ARCHITECTURE.md            # 分层正确性测试架构
    ├── regression/                     # [P0] 回归测试 — 每次修改后必跑
    │   ├── test_none_params.py
    │   ├── test_cpw_robustness.py
    │   └── test_varying_speed_order.py
    ├── algorithms/                     # 算法单元/集成测试(含 order Pipeline 与 Engine/API 接入)
    ├── planetary/                      # 行星齿轮箱专项(端到端/解调方法)
    ├── method_eval/                    # 方法级分类评估框架
    ├── evaluation/                     # 多维度评价框架
    ├── effectiveness/                  # 诊断有效性测试
    ├── foundation/                     # [P0+] 分层正确性测试 → 详见 TEST_ARCHITECTURE.md
    │   ├── synthetic_signals.py
    │   └── layer1~5/
    ├── debug/                          # 调试脚本
    └── eval_plots/                     # 评估绘图脚本

dc24/tests/
├── test_dc24_start.py                  # 一键入口批处理冒烟(--check)
└── test_dc24_vendor.py                 # 原厂 DLL 回环(未配置时跳过)

wind-turbine-diagnosis/tests/
├── acquisition_lifecycle.test.cjs      # 采集页生命周期
├── acquisition_navigation.test.cjs     # 采集入口导航守卫
├── monitor_lifecycle.test.cjs          # 监测初始化、请求/轮询调度及卸载
├── dashboard_lifecycle.test.cjs        # 总览刷新、状态与生命周期
└── websocket.test.cjs                  # 连接状态竞争与重连去重
```

---

## 0. 分层正确性测试(详见 `cloud/tests/diagnosis/TEST_ARCHITECTURE.md`)

> **用途**:按依赖层从下往上(Layer 1→5)验证诊断算法全链路,使用合成信号 + 4 个真实数据集。
> **完整文档**:`cloud/tests/diagnosis/TEST_ARCHITECTURE.md` — 含覆盖矩阵、测试列表、运行方式。

---

## 1. 回归测试(P0 — 每次修改后必须运行)

> **⚠️ 重要**:对 `cloud/app/services/diagnosis/` 下任何文件的修改完成后,必须运行以下回归测试。

### 1.1 `test_none_params.py` — None 参数安全

```bash
cd cloud
uv run python tests/diagnosis/regression/test_none_params.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证设备参数为 None 时诊断引擎不崩溃 |
| **测试范围** | 参数门控、无几何统计路径、Engine 各对象方法与未知状态 |
| **数据集** | 不需要(使用合成信号) |
| **通过标准** | 所有 assert 通过,无异常抛出 |

### 1.2 `test_cpw_robustness.py` — CPW 鲁棒性

```bash
cd cloud
uv run python tests/diagnosis/regression/test_cpw_robustness.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 验证 CPW 在非法参数(rot_freq=None/-5/0, 空 comb_frequencies)下不崩溃 |
| **数据集** | 不需要 |
| **通过标准** | 所有边界条件测试通过 |

### 1.3 `test_varying_speed_order.py` — 变速阶次跟踪

```bash
cd cloud
uv run python tests/diagnosis/regression/test_varying_speed_order.py
```

| 项目 | 说明 |
|------|------|
| **目的** | 用公式期望验证恒速/缓变/快速变速转速、相位、角域采样与阶次谱 |
| **数据集** | 不需要（全部独立合成信号） |
| **通过标准** | 已知阶次与近频峰、解析转速积分、三角扫频轨迹、MAD 近零、非法/不可判定、8192/25600 Hz 分辨率、单边幅值和阶次轴语义全部通过 |

### 1.4 一键回归测试

```bash
cd cloud
uv run python tests/diagnosis/regression/test_none_params.py && uv run python tests/diagnosis/regression/test_cpw_robustness.py && uv run python tests/diagnosis/regression/test_varying_speed_order.py && echo "ALL REGRESSION TESTS PASSED"
```

---

## 2. 新增算法测试(`cloud/tests/diagnosis/algorithms/`)

本轮对象化切片最小地图如下。在 `cloud/` 使用 `uv run python tests/diagnosis/algorithms/<文件>`；文档轮次只登记资产，不重复算法测试。以下专项除注明外使用合成信号：

| 边界 | 入口 | 主要证据 |
|------|------|----------|
| 定轴 #71 | `test_fixed_axis_gear.py`、`test_fixed_axis_gear_api.py` | TSA 恒等式、矩/边带手算、历史缺失、重评、Engine/HTTP |
| 高级轴承 #73 | `test_bearing_spectral_kurtosis_advanced.py`、`test_bearing_deconvolution_advanced.py`、`test_bearing_cpw_teo_advanced.py`、`test_bearing_cyclostationary_advanced.py` | 复高斯/SVD/周期目标、梳状先验、TEO 单位、SC 频移与专属评估 |
| 高级轴承业务 | `test_bearing_advanced_business.py`、`test_bearing_advanced_api.py` | 实际 MED 回退、门控、方法隔离、JSON/API |
| 分解 #74 | `test_decomposition_wavelet.py`、`test_decomposition_emd.py`、`test_decomposition_vmd.py`、`test_decomposition_selection.py` | 频率序/时间轴、镜像/停止、有效区间/Hz、熵/零能量 |
| 分解质量/业务 | `test_decomposition_review_counterexamples.py`、`test_decomposition_business.py` | 未收敛选中分量、直接重评、失败状态与消费者 |
| 去噪公共错误 | `cloud/tests/test_preprocessing_failures.py` | 真实 HTTP/worker、未知方法、失败不回退、None 告警、422 对象/参数数组 schema；用 `uv run python -m unittest tests.test_preprocessing_failures -v` |
| 行星 #72 | `../planetary/test_planetary_pipeline.py` | WT 运动学、参考轴、角域 residual、SER、基线与工况 |
| 行星业务/API | `../planetary/test_planetary_business.py`、`../planetary/test_planetary_api.py` | 无基线不伪健康/告警、按通道完整几何、实际 HTTP 四方法与旧标识拒绝 |
| 统一业务 #77/#84 | `test_diagnosis_domain.py` 与 `cloud/tests/test_diagnosis_workflow.py` | 取代旧规则/评分/投票协议，实际新状态、缓存、事务与重评 |

不再调用已删除旧函数证明新实现兼容。真实数据分类效果和性能分别归 #78/#79。

| 文件 | 用途 | 需要数据集 | 运行方式 |
|------|------|-----------|---------|
| `test_bearing_envelope_analysis.py` | 手工谱唯一归属、偏移真峰、有效阴性、超带宽/共享 bin、BPFI 边带融合、真实可观测边带分母、非谐波负对照、低频后缀健康/ensemble 集成、阈值与参数校验 | 无 | `uv run python tests/diagnosis/algorithms/test_bearing_envelope_analysis.py`(在 cloud 目录) |
| `test_bearing_envelope_pipeline.py` | 标准包络单边幅值、实际频带、指标/评估分离、展示不影响诊断、无参统计、未知转频、Engine/ensemble/SC 新契约 | 无 | `uv run python tests/diagnosis/algorithms/test_bearing_envelope_pipeline.py`(在 cloud 目录) |
| `test_order_pipeline.py` | 恒速已知阶次/近频峰、单边幅值、角域轴与 FFT 阶次轴、解析积分与全记录三角扫频、单帧快扫频双阶次、持续越界与近边界有效信号、零 MAD 离群与微变、窄带纯音、短/长边缘与内部越界、slow→fast 与失败不可判定、不同 fs 的 STFT 分辨率、轴承故障调制不冒充轴频、原始估计信号隔离 | 无 | `uv run python tests/diagnosis/algorithms/test_order_pipeline.py`(在 cloud 目录) |
| `test_order_integration.py` | Engine/ensemble 快速变速轴承与齿轮边界；/order 恒速幅值/谱轴、批次记录持久化、通道缓存保护、无记录不伪造健康、快速变速成功及噪声 400 | 无（隔离 SQLite） | `uv run python tests/diagnosis/algorithms/test_order_integration.py`(在 cloud 目录) |
| `test_bearing_envelope_api.py` | 包络 HTTP 新响应、max_freq 生效、隔离 SQLite 与认证替身 | 无 | `uv run python tests/diagnosis/algorithms/test_bearing_envelope_api.py`(在 cloud 目录) |
| `cloud/tests/test_numeric_algorithms.py` | #76 FFT/STFT/倒谱、统计、通用包络与显示抽点的解析向量和边界 | 无 | `uv run python -m unittest tests.test_numeric_algorithms -v`(在 cloud 目录) |
| `cloud/tests/test_numeric_routes.py` | #76 DataView/Monitor 数值归一化、响应字段与路由兼容 | 无（隔离测试环境） | `uv run python -m unittest tests.test_numeric_routes -v`(在 cloud 目录) |
| `test_engine_regressions.py` | 诊断引擎核心回归(无参数/TSA/转频/健康区分) | HUSTbear/CW(可选) | `uv run python tests/diagnosis/algorithms/test_engine_regressions.py`(在 cloud 目录) |
| `test_new_algorithms.py` | EMD/MCKD/小波包/SG 等新算法功能验证 | 无 | 同上 |

---

## 3. 行星齿轮箱专项测试(`cloud/tests/diagnosis/planetary/`)

旧 `test_planetary_e2e.py`、`test_planetary_demod.py` 对应旧 Level 1–5 入口，不能作为新基础 Pipeline 的验收或效果证明；当前入口是 `test_planetary_pipeline.py`。历史数据批评估待参数、基线与数据齐备后按新契约重建。

| 文件 | 用途 | 数据依赖 |
|------|------|----------|
| `test_planetary_pipeline.py` | 当前基础运动学/方法指标/基线评估 | 无，已知物理参数合成信号 |
| `test_planetary_business.py`、`test_planetary_api.py` | 真实 Engine/ensemble 和隔离 SQLite HTTP 消费路径 | 无真实数据依赖 |

```bash
cd cloud
uv run python tests/diagnosis/planetary/test_planetary_pipeline.py
uv run python tests/diagnosis/planetary/test_planetary_business.py
uv run python tests/diagnosis/planetary/test_planetary_api.py
```

前端 `wind-turbine-diagnosis/tests/planetary_contract.test.cjs` 用 `node --test tests/planetary_contract.test.cjs` 验证机械表单保留全部模型字段与只读指标/unknown 语义；不覆盖浏览器像素。

`wind-turbine-diagnosis/tests/error_message.test.cjs` 验证共享格式化和实际 request 拦截器消费 422 对象、旧字符串与参数校验数组；`bearing_contract.test.cjs` 覆盖 DataView/研究的对应读取与新方法标签。用 `node --test tests/error_message.test.cjs tests/bearing_contract.test.cjs`，不代表像素或真实设备效果。

---

## 4. 方法级分类评估框架(`cloud/tests/diagnosis/method_eval/`)

历史 method_eval/evaluation/effectiveness 脚本尚未整体迁移至新 Domain 与无概率协议，下列目录作为历史实验导航保留，不承诺当前命令可直接用于新版本效果验收。#78 需按新对象、机械参数、基线和真实数据重建；本批未借这些历史数字宣称检出效果。

| 文件 | 用途 | 数据集 |
|------|------|--------|
| `main.py` | 主入口,运行全部评估 | — |
| `test_bearing_hustbear.py` | HUSTbear 轴承评估:11种方法+集成,二分类+五分类 | HUSTbear |
| `test_bearing_cw.py` | CW 轴承评估:变速工况下的轴承方法性能 | CW |
| `test_gear_wtgearbox.py` | WTgearbox 齿轮评估:齿轮方法性能 | WTgearbox |
| `test_binary_all.py` | 全部二分类评估(健康 vs 故障) | 三个数据集 |

```bash
cd cloud
uv run python tests/diagnosis/method_eval/test_bearing_hustbear.py
```

---

## 5. 多维度评价框架(`cloud/tests/diagnosis/evaluation/`)

| 文件 | 用途 |
|------|------|
| `main.py` | 主入口,运行全部评估维度 |
| `denoise_eval.py` | 去噪方法对比评估 |
| `bearing_eval.py` | 轴承诊断方法评估 |
| `gear_eval.py` | 齿轮诊断方法评估 |
| `comprehensive_eval.py` | 综合诊断(轴承+齿轮)评估 |
| `robustness_eval.py` | 噪声鲁棒性评估 |
| `classification_metrics_eval.py` | 分类指标(准确率/召回率/F1) |
| `ds_fusion_eval.py` | D-S 证据融合效果评估 |
| `health_trend_eval.py` | 健康度趋势评估 |
| `channel_consensus_eval.py` | 多通道一致性评估 |
| `report_generator.py` | 评估报告生成 |

```bash
cd cloud
uv run python tests/diagnosis/evaluation/main.py
```

---

## 6. 其他测试

### 6.1 有效性测试(`cloud/tests/diagnosis/effectiveness/`)

| 文件 | 用途 |
|------|------|
| `test_effectiveness.py` | 参数驱动跳过逻辑测试:仅轴承/仅齿轮/都有/都无 四种场景 |
| `test_dataset_effectiveness.py` | 数据集本身的诊断可行性评估 |

### 6.2 调试(`cloud/tests/diagnosis/debug/`)

| 文件 | 用途 |
|------|------|
| `debug_cw_fp.py` | CW 健康数据误判原因诊断,逐项打印扣分项 |

---

## 7. 测试运行环境要求

| 数据集 | 路径 | 用途 |
|--------|------|------|
| HUSTbear | `data/HUSTbear/down8192` | 轴承诊断评估 |
| CW | `data/CW/down8192_CW` | 变速轴承诊断评估 |
| WTgearbox | `data/WTgearbox/down8192` | 齿轮诊断评估 |

> 路径均相对仓库根目录,由 `cloud/tests/diagnosis/data_paths.py` 统一解析;可用 `CNN_DATA_ROOT` 指向仓库外数据目录。
> P0 三件回归全部使用合成信号,无需数据集即可运行;数据集仅评估类套件(method_eval/planetary/evaluation 等)需要。
> 2026-11-11 主仓 CW 实际有 36 个变速 `.npy`，数据不随 worktree 自动复制；其他目录须分别确认，禁止把独立 worktree 无目录写成全部数据缺失。真实效果本轮未完成验证。

---

## 8. 何时运行哪些测试

| 修改范围 | 最小测试集 |
|---------|-----------|
| `features.py`, `engine.py`, `ensemble.py` | P0回归 + algorithms/ |
| `algorithms/bearing/`、高级轴承业务适配 | P0 + 对应高级轴承专项 + 业务/API；真实效果另跑 method_eval |
| `algorithms/gear/`、齿轮业务适配 | P0 + 定轴/行星 Pipeline 专项 + 业务/API |
| `domain.py`、`assessment.py`、adapters/融合/存储/流程 | P0 + domain/workflow 实际业务、HTTP/worker/缓存/告警 |
| `algorithms/order/`, `order_tracking.py` | P0 + `test_order_pipeline.py` + `test_order_integration.py` + foundation order/signal_utils |
| 分解/选择与去噪消费者 | P0 + decomposition 专项 + 质量反例/业务 |
| API 路由 (`data_view/`, `ingest.py` 等) | P0回归 + 手动 API 调用验证 |

---

*文档更新:2026-11-08(T9/#54:P0 三件确认全部合成信号化、补 TEST_PLOT 出图开关说明;此前 2026-11-07 测试分立各端 #48、uv workspace #47)*
*维护者:AI Agent(新增测试文件时请务必同步更新)*
