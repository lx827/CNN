# 风机齿轮箱智能故障诊断系统

基于振动信号的旋转机械故障诊断系统，覆盖**边端采集 → 云端分析 → 前端展示**的完整链路，用于风机齿轮箱与轴承的状态监测和故障诊断。

## 系统组成

| 模块 | 目录 | 说明 |
|------|------|------|
| 分析后端 | `server/` | FastAPI 服务，负责数据接入、信号分析、诊断、告警与 WebSocket 推送；云端与本地工作站同一套代码（ADR 0011） |
| 前端 | `web/` | Vue 3 + Vite + Element Plus + ECharts 可视化界面 |
| 采集宿主 | `collector/` | 直连 DC24 采集卡的机器上运行；驱动四包在 `collector/drivers/`（Python TCP / Rust FFI / 原厂 DLL 三选一） |
| 边端 | `edge/` | 树莓派：`acquire/` Rust 采集传输核心（主路线），`diag/` 诊断 POC |
| 计算库 | `compute/` | 独立 C++ 数值计算库（pybind11 进 Python、C ABI 供边端），含自身 tests 与消费示例 |
| 文档 | `docs/` | 架构、算法、接口、部署、运维与现场资料 |

**三种部署形态，各有唯一入口：** 云端 = 服务器上 `bash /opt/CNN/deploy.sh`；本地工作站 = 双击根目录 `start.bat`；树莓派边端 = `deploy/edge/build.sh` 交叉编译 + `edge/acquire/deploy/pi/deploy_pi.sh` 安装。

**诊断能力：** 轴承（包络分析、快速谱峭度图、CPW、MED、MCKD、循环平稳等）、齿轮（FM0/FM4/CAR/SER、行星齿轮箱解调等）、阶次跟踪、去噪与多方法集成投票，输出健康度、故障概率与维护建议。

## 快速开始

**DC24 现场实时采集**：双击仓库根目录的 `start.bat` 一次启动本机前后端和真实采集链路，自动打开“真实采集”。支持原厂12档采样率、四通道实时示波、可选频谱/RMS/均值/包络谱、自填时长或手动停止，以及选择现场保存目录。操作见 [DC24采集说明](docs/DC24_ACQUISITION.md)，原理见[从传感器到CSV](docs/DC24_SIGNAL_TO_CSV.md)。旧数据集回放链已于 2026-11 布局重构退役。

## 开发与部署

- 开发命令（根目录单项目，**uv-only**）：仓库根 `uv sync` 构建计算扩展并安装默认依赖组，后端 `cd server && uv run python -m app.main`，前端 `cd web && npm install && npm run dev`；Windows 构建使用 Git Bash 的 `vsdev uv sync`。详见 [计算库构建说明](docs/native_compute.md) 与 [AGENTS.md](AGENTS.md)
- 系统架构与目录结构：见 [系统架构](docs/系统架构.md)
- 算法原理：见 [算法原理](docs/算法原理.md)
- 服务器部署：`bash /opt/CNN/deploy.sh` 一键部署（`--dry-run` 演练零改动，`-s` 跳过前端构建），详见 [部署指南](docs/部署指南.md)
- 日常操作与运维命令：见 [操作手册](docs/操作手册.md)、[服务器命令速查](docs/服务器命令速查.md)
- 全部文档索引：见 [docs/INDEX.md](docs/INDEX.md)

> **接口契约**：后端 OpenAPI 契约入库于 [`docs/api/openapi.json`](docs/api/openapi.json)。修改任何后端路由后，在仓库根执行 `uv run python scripts/export_openapi.py` 刷新并随代码一起提交。

## 目录结构

```
CNN/
├── server/                    # 云端 FastAPI 后端（cloud 依赖组，测试在 server/tests/）
├── web/                       # Vue 3 前端（测试在 web/tests/）
├── edge/                      # Rust 边端：acquire/ 采集（目标树莓派）、diag/ 诊断 CLI（cargo 管理）
├── collector/                 # DC24 共用采集宿主（dc24 依赖组，测试在 collector/tests/）
│   └── drivers/               # 公共 DC24 接口及 Python TCP / 原厂 DLL 独立驱动包
├── compute/lib/               # 纯 C++：core 公共数值模块、emd 算法模块
├── compute/bind/              # pybind11 导出、NumPy 互操作与类型声明生成
├── compute/cnn_compute/       # 独立 Python 计算包
├── deploy/                    # 部署资产：server/CNN.service 模板、edge/ 交叉编译构建
├── scripts/                   # 运维调试脚本（dc24_start、export_openapi 等）
├── data/                      # 数据集（不提交 Git）
├── docs/                      # 项目文档
├── pyproject.toml / uv.lock / .python-version   # 根项目配置、锁文件与 Python 3.13
├── start.bat                  # 本地工作站一键启动(DC24 实机链路)
└── deploy.sh                  # 服务器一键部署（支持 --dry-run / -s）
```

## 许可

本项目采用 [GNU Affero General Public License v3.0](LICENSE)。
