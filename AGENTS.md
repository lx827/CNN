# AGENTS.md — 风机齿轮箱智能故障诊断系统

面向 AI Agent 的操作手册:环境、命令、红线、代码导航。人类用户请读 `README.md`。
若仓库根目录存在 `AGENTS.local.md`,先读并遵守其中本机约定(该文件仅存本机,不入库)。

## 1. 环境

| 环境 | OS / Python | 说明 |
|------|------------|------|
| 本地开发 | Windows / 3.13(uv 托管) | 主开发环境 |
| 生产服务器 | Ubuntu 22.04 / 3.13(uv 托管) | 阿里云 ECS,**2核2G** |

生产环境:IP `8.137.96.104`,systemd 服务 `CNN.service`,部署路径 `/opt/CNN`,一键部署 `bash /opt/CNN/deploy.sh`。前端 `vite.config.js` 代理固定指向 `8.137.96.104:8000`,打包后靠 Nginx 反代 — 保持原样。

## 2. Python 环境(uv workspace —— **uv-only,铁律**)

**只允许 uv 命令:`uv sync`、`uv run`、`uv add`、`uv lock`。禁止 `pip`(含 `pip install`/`pip freeze`)、禁止 conda/mamba、禁止手工创建/激活 venv。** 依赖唯一事实源是根 `uv.lock`。

```bash
uv sync                        # 仓库根:安装全部成员(cloud + dc24)
uv run <命令>                   # 在成员目录内运行任何 Python(见 §3)
uv add <包名>                   # 加依赖:在对应成员目录内执行,写入其 pyproject
```

- workspace 定义在根 `pyproject.toml`,成员:`cloud`、`dc24`;Rust 边端 `edge/` 由 cargo 管理,不经 uv
- Python 版本锁定 `.python-version`(3.13),由 uv 自动下载托管,不依赖系统 Python

## 3. 开发命令

```bash
# 后端(http://localhost:8000,API 文档 /docs)
cd cloud && uv sync && uv run python -m app.main

# 前端(http://localhost:3000)
cd wind-turbine-diagnosis && npm install && npm run dev   # build 产出 dist/

# DC24 现场采集(Windows,实机链路)
start_dc24.bat                 # 一键入口(等价:uv run python scripts/dc24_start.py)
```

## 4. 测试

**P0 回归(合成信号,无需数据集)— 修改 `cloud/app/services/diagnosis/` 下任何文件后,三件全绿才算完成:**

```bash
cd cloud
uv run python tests/diagnosis/regression/test_none_params.py
uv run python tests/diagnosis/regression/test_cpw_robustness.py
uv run python tests/diagnosis/regression/test_varying_speed_order.py
```

扩展测试按目录选:正确性验证 `cloud/tests/diagnosis/foundation/layer1~5/`(如 `layer2/test_order_tracking_correctness.py`)、方法评估 `method_eval/`、行星箱端到端 `planetary/`、效果 `effectiveness/`、引擎回归 `algorithms/`;改 API 路由另加手动调用验证。cloud/dc24/前端测试套件及运行方式见 `docs/tests/INDEX.md`。

## 5. 2G 红线(违反即生产 OOM)

- `lifespan.py` 线程池 `max_workers=2` 是内存上限:所有异步计算走现有线程池,新增并发前先算内存账
- 后台分析 `ANALYSIS_SEM = Semaphore(1)`:逐批次串行,排队执行
- DataView 实时计算只处理 5 秒数据(`sample_rate * 5` 截断)

## 6. 配置

- `cloud/.env`(不入库):云端配置,键定义以 `cloud/app/core/config.py` 为准;生产必改 `ADMIN_PASSWORD`、`SECRET_KEY`、`EDGE_API_KEY`。可选键 `CORS_ORIGINS`(逗号分隔跨域白名单,默认含 localhost:3000/4173 与生产 IP)
- `dc24/.env`(不入库):DC24 边端本机配置,由 `dc24/dc24_agent.py` 读取——`DC24_VENDOR_ROOT`(原厂软件目录,配了走 DLL、留空走纯 Python TCP)、`CLOUD_BASE_URL`、`EDGE_API_KEY`,详见 `dc24/README.md`
- `ACQUISITION_DATA_DIR`:可选环境变量,采集任务落盘根目录(默认 `<仓库根>/data/acquisitions`),读取处 `cloud/app/api/acquisition.py`
- 生产部署(`CNN.service`、Nginx、dry-run 演练)见 `docs/部署指南.md`

## 7. 代码导航

```
cloud/                      # 云端后端(uv workspace 成员)
├── app/
│   ├── api/                # 路由:data_view/(频谱+诊断+重新诊断)、devices/、
│   │                       # acquisition(DC24 任务/上传)+ acquisition_live(实时示波+WS)、
│   │                       # ingest、dashboard、alarms、monitor、auth、collect、system
│   ├── core/               # config / websocket / json_utils / memory_log / thresholds
│   ├── services/
│   │   ├── analyzer.py     # 后台分析入口(多通道综合,lifespan worker 调用)
│   │   ├── acquisition_analysis.py / acquisition_live.py   # DC24 原始计数分析 / 示波内存窗口
│   │   ├── diagnosis_queries.py   # 诊断摘要读模型(最新记录统一规则)
│   │   └── diagnosis/      # 诊断算法库
│   │       ├── engine.py   # 调度器:轴承/齿轮/综合分析入口
│   │       ├── ensemble.py # 多算法集成诊断(run_research_ensemble)
│   │       ├── features.py # 特征提取;has_bearing_params/has_gear_params 参数门控
│   │       ├── health_score.py / recommendation.py   # 评分与建议(全项目单一评分源)
│   │       ├── bearing.py / gear/metrics.py / order_tracking.py
│   │       └── preprocessing.py / vmd_denoise.py 等  # 去噪族(wavelet/VMD/MED/MCKD/EMD…)
│   └── lifespan.py         # 线程池 + 后台分析 worker
└── tests/                  # 后端测试 + 诊断测试套件(含 P0 回归)

dc24/                       # DC24 现场采集工具链(uv workspace 成员,Windows)
├── dc24_capture.py         # 协议重组、控制命令、单次采集
├── dc24_agent.py           # 心跳、控制轮询与采集入口(读 dc24/.env)
├── dc24_live.py            # 连续示波、保存与上传
├── dc24_vendor.py / dc24_vendor_bridge.ps1   # 原厂 DLL 校验与 32 位桥接
├── dc24_profiles.json      # 原厂 12 档 B5 命令负载
└── tests/                  # test_dc24_start / test_dc24_vendor

edge/                       # Rust 边端(开发稿,目标树莓派;cargo 管理,不经 uv)
├── src/ tests/ Cargo.toml / Cargo.lock
│   └── ffi.rs              # C ABI 网络接收核心(cdylib dc24_edge_core,树莓派主路线)
├── deploy/dc24-edge.service    # 未安装的 systemd 模板
├── FFI.md                  # FFI 契约(Python 驱动接入文档)
└── README.md               # 开发稿说明(可调配置、验证状态、部署限制)

deploy/                     # 部署资产:cloud/CNN.service(systemd 模板)、
│                           # edge/(交叉编译 Dockerfile + build 脚本;out/ 产物不入库)
scripts/                    # dc24_start.py(一键入口)、dc24_select_directory.py、
│                           # register_hustbear_devices.py、export_openapi.py
wind-turbine-diagnosis/     # Vue3 前端
├── src/api/                # 按域模块(acquisition/monitor/dashboard/data/diagnosis/alarms/devices/…)
├── src/composables/        # useMonitor / useDashboard / useDataView / useSettings 等页面逻辑
├── src/components/<view>/  # 按页面分组(dashboard/monitor/dataview/research/settings/charts)
├── src/views/              # 页面组件(Acquisition/Monitor/Dashboard/DataView/Settings…)
└── tests/                  # *.test.cjs(node --test 运行)
```

逐文件接口:`docs/backend/app/INDEX.md`;服务层函数:`docs/backend/services.md`。

## 8. 数据与数据库

- 数据集 4 套(8192Hz,`.npy`):HUSTbear、CW(轴承)、WTgearbox(行星箱)、HUSTgearbox(定轴箱)。路径、命名规则、机械参数见 **`docs/datasets.md`** — 配置诊断参数、写测试、边端回放都以它为准,不得用其他数据集参数代填
- 表:`devices`、`sensor_data`(batch 1~16 循环覆盖,≥101 永久保留)、`diagnosis`、`alarms`、`collection_tasks`
- 诊断缓存键 `(device, batch, channel, denoise_method)`;重新诊断 `POST /api/data/{device_id}/{batch_index}/reanalyze`、`POST /api/data/{device_id}/reanalyze-all`(逐批串行防 OOM)。字段详情:`docs/backend/app/models.md`

## 9. 编码规范

Python UTF-8 + 中文注释;shell 命令路径用 `/`;改文件用编辑工具,不用 sed。

## 10. 文档即契约(代码改动必须同步文档,不一致会导致前后端调用失败)

| 改动 | 必须同步 |
|------|---------|
| API 端点 | `docs/api/backend_api.md` + `docs/api/frontend_backend_interaction.md` |
| 服务层函数 | `docs/backend/services.md` |
| 前端 API 封装/组件 | `docs/frontend/frontend_api.md` + `frontend_services.md` |
| 增删改 .py 文件 | `docs/backend/app/` 对应 `.md` + `INDEX.md` |

动手前先查对应文档确认契约;文档缺失则改完立即补建。总索引:`docs/INDEX.md`。

## 11. Git 流程

- 新任务:从最新 `origin/main` 建独立任务分支,修改、验证、提交、开 PR;主分支只经 PR 进入
- 提交按逻辑单元拆分(`type(scope): 摘要`),代码/文档/配置分开提交,每个可独立审查回滚
- PR 状态 `MERGED` 且无其后未合入提交 → 删本地+远端任务分支(此清理已预授权);状态不明则保留并说明原因

## 12. 其他约定

- Bug 登记:`docs/Bug登记表.md`,修复后更新
- 现场试验数据(设备1动不平衡、设备2外圈故障、桌面 CSV):先读 `docs/FIELD_DATA_HANDOFF_20261020.md`
- Issue 跟踪(GitHub Issues + `gh`)、triage 标签、域文档(`GLOSSARY.md` + `docs/adr/`):见 `docs/agents/`
- 诊断算法全景:`docs/诊断算法体系全景.md`;理论推导:`docs/算法原理.md`
