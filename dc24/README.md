# DC24 现场采集工具链（dc24/）

> 按 `GLOSSARY.md` 术语:本目录是 **现场采集工具(DC24 工具链)**,运行在 Windows 现场电脑上驱动 DC24 采集卡,是实机验收的现役链路;不是部署在树莓派上的 Rust 边端(`edge/`)。

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
├── requirements.txt           # Python 依赖
└── .env                       # 本机配置(不入库):DC24_VENDOR_ROOT 指向原厂安装目录则走 DLL,留空走 Python TCP
```

## 配置(`.env`)

| 键 | 说明 |
|----|------|
| `DC24_VENDOR_ROOT` | 原厂软件安装目录绝对路径(含 `dll/JMServer.dll`);配置后实时采集走 DLL,留空走纯 Python TCP |
| `CLOUD_BASE_URL` | 云端地址 fallback(默认 `http://127.0.0.1:8000`) |
| `EDGE_API_KEY` | 边端密钥,须与云端 `cloud/.env` 的 `EDGE_API_KEY` 一致 |

采样率、时长、频带等采集参数由"真实采集"页面下发,不在 `.env` 配置。

## 历史说明

旧 `edge_client.py` 数据集回放链(`edge_client.py`/`compressor.py`/`replay.py`,含 `signal_generator.py` 模拟信号)只有上云能力、无采集卡,已随 2026-11 布局重构(#46)退役;数据集说明见 `docs/datasets.md`。树莓派 Rust 边端开发稿见 [`edge/README.md`](../edge/README.md)。
