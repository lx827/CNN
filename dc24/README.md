# DC24 现场采集工具链（dc24/）

> 按 `GLOSSARY.md` 术语:本目录主体是 **现场采集工具(DC24 工具链)**,运行在 Windows 现场电脑上驱动 DC24 采集卡,是实机验收的现役链路;同时携带树莓派部署形态的 Python 驱动入口 `dc24_edge_pi.py`(设备链路由 `edge/` 的 Rust 核心 cdylib 承担,见下文[树莓派边端驱动](#树莓派边端驱动rust核心--python-驱动)一节)。

## 已打通链路

**现有传感器 → DC24 采集器 → 网线 → Windows 电脑 → CNN 后端 → 网页实时显示与完整数据保存。**

不运行原厂主程序,由自己的程序控制硬件;既支持复用原厂接收 DLL(`JMServer.dll`),也保留不依赖 DLL 的纯 Python TCP 方式。支持原厂 50～100000Hz 全部 12 档、四通道、实时示波、示波中开始/停止保存、完整文件保存与上传。

一键入口:双击仓库根目录 `start_dc24.bat`(检查环境、启动/复用本机前后端与采集代理、打开"真实采集"页)。完整步骤见 [DC24 采集说明](../docs/DC24_ACQUISITION.md),协议细节见 [DC24 实测协议](../docs/DC24_PROTOCOL.md),交接全貌见 [DC24 工作交接说明](../docs/DC24_HANDOFF_20261107.md)。

## 文件结构

```
dc24/
├── dc24_capture.py            # 纯 Python 连接、帧解析、控制指令、单次采集(协议基础,仅标准库)
├── dc24_agent.py              # 认证、心跳、控制轮询与采集入口
├── dc24_live.py               # 持续示波、双接收路径、解码、保存与上传
├── dc24_vendor.py             # 原厂 DLL 校验(SHA-256)
├── dc24_vendor_bridge.ps1     # 32 位 PowerShell/C# 桥接调用 JMServer.dll
├── dc24_profiles.json         # 原厂 12 档完整 B5 命令负载(云端与现场工具共用)
├── dc24_ffi.py                # 树莓派形态:dc24_edge_core 动态库的 ctypes 绑定(仅标准库)
├── dc24_edge_pi.py            # 树莓派形态:云端会话编排、五件套落盘、实时窗口与补传上传
├── tests/                     # 工具链测试(test_dc24_start 入口冒烟 / test_dc24_vendor DLL 回环,
│                              #   未配置原厂 DLL 时跳过;test_dc24_edge_pi 树莓派驱动回归)
└── .env                       # 本机配置(不入库):DC24_VENDOR_ROOT 指向原厂安装目录则走 DLL,留空走 Python TCP
```

## 配置(`.env`)

Python 依赖在根项目 dc24 组，根目录 `uv sync` 默认安装。Windows 首次构建计算包或修改原生源码后，在 Git Bash 执行 `vsdev uv sync`；现有采集入口及工作目录保持原样，见 [计算库构建说明](../docs/native_compute.md)。

| 键 | 说明 |
|----|------|
| `DC24_VENDOR_ROOT` | 原厂软件安装目录绝对路径(含 `dll/JMServer.dll`);配置后实时采集走 DLL,留空走纯 Python TCP |
| `CLOUD_BASE_URL` | 云端地址 fallback(默认 `http://127.0.0.1:8000`) |
| `EDGE_API_KEY` | 边端密钥,须与云端 `cloud/.env` 的 `EDGE_API_KEY` 一致 |

采样率、时长、频带等采集参数由"真实采集"页面下发,不在 `.env` 配置。

## 树莓派边端驱动(Rust 核心 + Python 驱动)

`dc24_edge_pi.py` 是树莓派部署形态的边端入口(对应 `edge/README.md` 的"核心动态库"路线):
设备链路(常驻 TCP 监听、每秒 00 心跳、BA/B8/B2/B5/B7 时序、80 帧解码、首帧序号 0 与连续性
校验)全部由 Rust cdylib `dc24_edge_core` 承担(契约见 [`edge/FFI.md`](../edge/FFI.md)),
`dc24_ffi.py` 用 ctypes 加载并轮询消息,`dc24_edge_pi.py` 负责云端会话循环、心跳、五件套
落盘、实时窗口上传与失败补传。v1 只实现云端下发会话(config.json 的 `mode=cloud`),
本地定时/持续模式不做。

运行方式(树莓派上;Windows 开发机同命令,库文件为 `dc24_edge_core.dll`):

```bash
# 1) 构建 Rust 核心(产物 edge/target/release/libdc24_edge_core.so)
cd edge && cargo build --release && cd ..
# 2) 配置与密钥:config.json 用 edge/config.example.json 的 schema(与核心共用同一份,
#    不得加私有键);密钥从 api_key_env 指定的环境变量读,绝不写入文件
export EDGE_API_KEY=<与云端一致的密钥>
# 3) 启动(在 dc24/ 目录内;--once 完成一个会话后退出,便于联调)
cd dc24 && uv run python dc24_edge_pi.py --config /path/to/config.json
```

行为基线对照 `edge/src/runtime.rs`:实时窗口约最近 2 秒、按绝对样本索引显式保留缺口、
不重发已确认区间;保存任务落盘五件套(`samples.csv`/`counts.i32`/`rx_stream.bin`/
`commands.jsonl`/`metadata.json`,格式与 `dc24_capture.py`/`dc24_live.py` 既有链路一致,
其中 `rx_stream.bin` 由解码样本逐字节可逆重建);上传走 `PUT /jobs/{id}/stream-files/` +
`finish-stream`,失败用 `storage/.uploads/*.json` 本地清单持久化重试;控制/心跳请求短超时
(`http_timeout_seconds`,默认 4s),文件上传长超时(`upload_timeout_seconds`,默认 180s)。
回归测试:`uv run python tests/test_dc24_edge_pi.py -v`(回环假设备+假云端,不需硬件;
找不到库时会尝试 `cargo build`,无 Rust 工具链则跳过集成部分)。

与原 `dc24_agent.py` 的关系:两者共用同一套云端 `/api/acquisition` 契约与五件套格式,
但面向不同部署形态——`dc24_agent.py`/`dc24_live.py` 是 Windows 现场电脑的现役实机链路
(支持原厂 DLL 桥接、回放、目录选择器),继续独立使用;`dc24_edge_pi.py` 面向无桌面树莓派,
设备链路换用 Rust 核心,不依赖 DLL/回放/图形界面,目录选择请求一律回错误并要求页面直接
填写绝对路径。两者不要在同一台机器、同一监听地址上同时运行(与原厂软件亦互斥)。

## 历史说明

旧 `edge_client.py` 数据集回放链(`edge_client.py`/`compressor.py`/`replay.py`,含 `signal_generator.py` 模拟信号)只有上云能力、无采集卡,已随 2026-11 布局重构(#46)退役;数据集说明见 `docs/datasets.md`。树莓派 Rust 边端开发稿见 [`edge/README.md`](../edge/README.md)。
