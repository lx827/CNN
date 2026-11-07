# AGENTS.md — 风机齿轮箱智能故障诊断系统

面向 AI Agent 的操作手册:环境、命令、红线、代码导航。人类用户请读 `README.md`。
若仓库根目录存在 `AGENTS.local.md`,先读并遵守其中本机约定(该文件仅存本机,不入库)。

> **占位说明(2026-11 布局重构,地图 #45)**:`edge/` 已是 Rust 边端(开发稿),DC24 Python 工具链在 `dc24/`,旧 `edge_client.py` 上云回放链已退役(#46);Python 环境已迁 uv workspace(T2/#47,`uv sync`/`uv run`),测试已分立各端(T3/#48:P0 在 `cloud/tests/diagnosis/regression/`)。§2/§3/§6 的 venv 激活与边端命令、§4 的测试路径已失效,现役一键入口为 `start_dc24.bat`;本文相关段落统一改写归 T9,详见重构地图 #45。

## 1. 环境

| 环境 | OS / Python | 说明 |
|------|------------|------|
| 本地开发 | Windows / 3.13 | 主开发环境 |
| 生产服务器 | Ubuntu 22.04 / 3.10 | 阿里云 ECS,**2核2G** |

生产环境:IP `8.137.96.104`,systemd 服务 `CNN.service`,部署路径 `/opt/CNN`,一键部署 `bash /opt/CNN/deploy.sh`。前端 `vite.config.js` 代理固定指向 `8.137.96.104:8000`,打包后靠 Nginx 反代 — 保持原样。

## 2. 虚拟环境(每模块独立 venv,跑任何 Python 前先激活)

```bash
cd cloud && . venv/Scripts/activate     # 后端(Windows 写法,无 source)
cd edge && . venv/Scripts/activate      # 边端
# 服务器 Ubuntu: source venv/bin/activate
```

## 3. 开发命令

```bash
# 后端(http://localhost:8000,API 文档 /docs)
cd cloud && . venv/Scripts/activate
pip install -r requirements.txt         # 首次
python -m app.main

# 前端(http://localhost:3000)
cd wind-turbine-diagnosis && npm install && npm run dev   # build 产出 dist/

# 边端采集客户端
cd edge && . venv/Scripts/activate && python edge_client.py
```

仓库根目录 `start.bat` 一键启动。

## 4. 测试

**P0 回归(合成信号,无需数据集)— 修改 `cloud/app/services/diagnosis/` 下任何文件后,三件全绿才算完成:**

```bash
cd cloud && . venv/Scripts/activate
python ../tests/diagnosis/regression/test_none_params.py
python ../tests/diagnosis/regression/test_cpw_robustness.py
python ../tests/diagnosis/regression/test_varying_speed_order.py
```

扩展测试按目录选:正确性验证 `tests/diagnosis/foundation/layer1~5/`(如 `layer2/test_order_tracking_correctness.py`)、方法评估 `method_eval/`、行星箱端到端 `planetary/`、效果 `effectiveness/`、引擎回归 `algorithms/`;改 API 路由另加手动调用验证。backend/edge/frontend 测试套件及运行方式见 `docs/tests/INDEX.md`。

## 5. 2G 红线(违反即生产 OOM)

- `lifespan.py` 线程池 `max_workers=2` 是内存上限:所有异步计算走现有线程池,新增并发前先算内存账
- 后台分析 `ANALYSIS_SEM = Semaphore(1)`:逐批次串行,排队执行
- DataView 实时计算只处理 5 秒数据(`sample_rate * 5` 截断)

## 6. 配置

键名与默认值以代码为准:`cloud/app/core/config.py`、`edge/edge_client.py`。生产必改 `ADMIN_PASSWORD`、`SECRET_KEY`、`EDGE_API_KEY`(`cloud/.env`)。

## 7. 代码导航

```
cloud/app/
├── api/                  # 路由:data_view/(频谱+诊断+重新诊断)、devices/、ingest、dashboard、alarms…
├── services/
│   ├── analyzer.py       # 后台分析入口(多通道综合,lifespan worker 调用)
│   └── diagnosis/        # 诊断算法库
│       ├── engine.py     # 调度器:轴承/齿轮/综合分析入口
│       ├── ensemble.py   # 多算法集成诊断(run_research_ensemble)
│       ├── features.py   # 特征提取;has_bearing_params/has_gear_params 参数门控
│       ├── health_score.py / recommendation.py   # 评分与建议(全项目单一评分源)
│       ├── bearing.py / gear/metrics.py / order_tracking.py
│       └── preprocessing.py / vmd_denoise.py 等  # 去噪族(wavelet/VMD/MED/MCKD/EMD…)
└── lifespan.py           # 线程池 + 后台分析 worker
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
