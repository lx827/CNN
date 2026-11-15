# ADR 0012:顶层目录按部署形态收编与改名

- 状态:已确认,已实施(PR #154~#157)
- 日期:2026-11-15

## 背景

2026-11-07 ~ 11-15 一周内连续引入 C++ 计算库、drivers 四包拆分、edge/edge-diag 三角换位与本地工作站形态(ADR 0011),根目录膨胀到 20+ 个条目,目录名不表意:`cloud/` 实际同时服务云端与本地工作站、`dc24/` 是采集宿主却被误认为驱动、`drivers/` 看不出是 DC24 采集卡驱动、`edge/` 与 `edge-diag/` 命名不体现"采集 vs 诊断"分工、根 `tests/` 只测计算库却名字泛化。

## 决定

按部署形态收编顶层目录,每个目录归属唯一形态或明确标注共享:

| 旧 | 新 | 形态 |
|---|---|---|
| `cloud/` | `server/` | 分析后端(云端+本地工作站同一套,ADR 0011) |
| `dc24/` | `collector/` | 采集宿主(直连采集卡的机器) |
| `drivers/` | `collector/drivers/` | DC24 驱动四包归属采集器 |
| `edge/` | `edge/acquire/` | 树莓派 Rust 采集传输核心 |
| `edge-diag/` | `edge/diag/` | 树莓派诊断 POC |
| `wind-turbine-diagnosis/` | `web/` | Vue3 前端 |
| `lib/ capi/ bind/ cmake/ cnn_compute/ tests/ examples/ CMakeLists.txt` | `compute/` 下 | 计算库八件套归于一个家(根项目本体) |

三种部署形态各有唯一入口:云端 `deploy.sh`、本地工作站 `start.bat`、树莓派 `deploy/edge/build.sh` + `edge/acquire/deploy/pi/deploy_pi.sh`。`start_dc24.bat` 并入 `start.bat`(原 start.bat 只是转发壳)。

## 不变量

- Python 包名 `cnn_compute`、`dc24-driver*`、模块名 `dc24_capture`/`dc24_agent` 等不变
- uv 依赖组名 `cloud`/`dc24`/`local` 不变(改名收益不抵全库命令与文档的 churn)
- 环境变量 `DC24_*`、DEPLOYMENT_MODE 取值 `cloud`/`local`、前端路由 `/dc24/`、树莓派落盘 `/var/lib/dc24-edge` 不变
- 生产部署根 `/opt/CNN` 不变;deploy.sh 含一次性 `cloud/→server/` 状态迁移(.env 与 turbine.db)

## 理由

命名按"跑在哪台机器上"组织,与 ADR 0011 的三形态模型对齐;收编而非平铺,根目录从 20+ 条目降到 11 个。改名一次性完成并保留 git 历史(git mv),拒绝渐进双名并存。

## 后果

所有相对路径引用(uv sources、scikit-build、cargo manifest、sys.path 定位、文档链接)随 PR 序列同步;`archive/pre-layout-restructure` tag 锚定重组前状态。开发者本地需重新 `uv sync`;生产首次部署自动迁移状态文件。
