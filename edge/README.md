# DC24 Rust 边端（开发中）

**这是开发进度交接，不是已验证可部署的发行版。** 截至 2026-11-08：`cargo fmt`、`cargo test`（4 单元 + 1 端到端 + 3 FFI 回环，MSVC 工具链）全部通过。**2026-11-11 更新：ARM64 产物已在 WSL Docker 构建并部署到树莓派 MIC-DT-Pi,与真实 DC24 采集卡完成链路验证**(TCP 接入含断线重连、云端控制会话、2000Hz 实时窗口推流,记录见 [树莓派直连配置](../docs/树莓派直连配置.md));本地频谱、模型推理等其余目标仍未实现。

## 目标与已有代码

在树莓派上控制 DC24、接收四路原始 ADC 计数、本地保存并上传 CNN 后端；异常判断留在云端。本轮没有实现本地 FFT、模型推理或自动异常切换。

实现依据是本交接分支已有的 [DC24 协议](../docs/DC24_PROTOCOL.md) 和 [Python 实机链路交接](../docs/DC24_HANDOFF_20261107.md)。Windows DLL 不参与 Rust 程序运行。当前只实现已验证的四通道 IEPE/AC0.2Hz/PASS 配置，不是完整厂家 SDK。

### 两种部署形态，共用同一核心

| 形态 | 组成 | 状态 |
|---|---|---|
| **核心动态库**（树莓派主路线） | 本 crate 的 cdylib `dc24_edge_core`（Linux 产物 `libdc24_edge_core.so`）+ Python 驱动（`dc24/dc24_edge_pi.py`，负责云端会话/落盘/上传） | FFI 契约见 [FFI.md](FFI.md) |
| **全 Rust 单体** | `main.rs` + `runtime.rs` 二进制，链同一核心（rlib） | 端到端回环测试通过 |

网络核心修复（相对 2026-11-07 版）：监听改为**进程内常驻绑定**（Unix 设 SO_REUSEADDR，避开 TIME_WAIT 占用；accept 后 BA 探活丢弃陈旧 backlog 连接）；**首帧序号必须为 0**（与 Python 基线一致）。

| 文件 | 已写入的内容（仍待实机验证） |
|---|---|
| `src/protocol.rs` | 控制报文、TCP 拆帧、四路有符号24位计数、首帧0+序号连续性检查 |
| `src/device.rs` | 常驻监听绑定、设备连接与 BA 探活、心跳、开始/停止控制 |
| `src/ffi.rs` | C ABI 导出：open/start/poll/stop/close/info，有界消息队列 |
| `src/recording.rs` | CSV、原始采样帧、int32 计数及元数据保存，磁盘空间保护 |
| `src/cloud.rs` | 现有 `/api/acquisition` HTTP 接口及流式文件上传 |
| `src/runtime.rs` | 云端控制、有限实时窗口、调度、持久化补传清单 |
| `FFI.md` | C ABI 契约（宿主语言接入文档） |
| `config.example.json` | 配置样例，无真实云端地址或密钥 |
| `deploy/dc24-edge.service` | 未安装的 systemd 模板；账号和路径需要部署前核实 |
| `tests/end_to_end.rs` | 回环模拟设备和云端，检查计数、文件一致性及上传重试 |
| `tests/ffi.rs` | FFI 回环：样本/事件/终态交付、首帧门槛、队列超限保护 |

原始值保持 ADC counts，不自动换算为 g 或 m/s²，不抽点替代完整保存。文件格式沿用现有真实采集链路：`samples.csv`、`counts.i32`、`rx_stream.bin`、`commands.jsonl`、`metadata.json`。

## 配置与控制约定

- `mode=cloud`：由现有云端会话下发采样率、保存时长及停止指令；不自行开始采样。
- `mode=periodic`：显式配置 `sample_rate`、正数 `duration_seconds` 和 `interval_seconds`；间隔按上一次会话结束后等待计算，不重叠追赶任务。
- `mode=continuous`：显式配置采样率，请求持续保存，直到停止；不按本地异常自动切换模式。
- 示例中的采样率、时长、间隔为 `null`，不替用户确定业务参数。`cloud` 模式允许保留这些空值。
- 文件配置在外层任务循环重新读取；正在进行的会话不会被本地配置文件静默重设。云端地址、边端身份或存储根目录变化需要重启程序。
- 密钥只从 `api_key_env` 指定的环境变量读取，默认变量名 `EDGE_API_KEY`；不要将真实密钥写入样例或提交到 Git。
- 无桌面的树莓派需要在页面填写设备上的绝对保存路径，不依赖 Windows 目录选择窗口。

## 连续上传与恢复的边界

代码沿用已有 CNN 接口：采集中上传有限实时窗口；完整五文件在一次保存任务结束、文件关闭后上传。**尚未实现持续保存期间分段发布完整文件**，不能将实时窗口等同于已可靠上传全部连续原始数据。

实时窗口过期后以绝对样本索引显式保留缺口；本地完整保存与实时上传分开。已完整关闭的文件用本地清单记录重试，不把整份文件装入内存。不会自动删除已保存文件；磁盘空间不足时需要报错并停止保存。实际手机热点带宽、存储写入速度和长期稳定性尚未验证。

进程崩溃时未完成的记录保留并标记中断，不冒充完整文件上传；旧实时会话不能在重启后从零重用样本索引。以上恢复路径仍需执行测试。

服务模板的 `MemoryMax=192M` 是拟设的资源保护上限，**不是程序实测内存占用**，也不代表已经证明适用于1GB树莓派。正式部署前必须核验 ARM64 构建、实际资源占用和停止行为。

## 本地验证方式

以下命令只用于开发验证，**不表示目前已全部通过**。在装好 Rust 工具链的开发电脑终端中、工作目录为本仓库的 `edge/` 时执行；无需管理员权限。首次获取依赖需要网络，构建产物写入忽略的 `target/`。

```sh
# 检查 Rust 源码格式和可解析性；--check 只检查，不改文件。
cargo fmt --all -- --check

# 按已提交的锁文件构建并运行测试；--locked 禁止悄悄更改依赖版本。
cargo test --locked

# 生成本机平台的优化构建；不会自动生成树莓派 ARM64 程序，也不会部署。
cargo build --release --locked
```

运行程序前要替换配置样例的云端占位地址，并设置认证环境变量。即使构建成功，也先使用检查模式，不连接采集器或上传数据：

```sh
# 读取指定配置并做格式、参数校验；--check 禁止启动采集或网络操作。
./target/release/dc24-edge --config config.json --check
```

最后一条的路径形式适用于 Linux/macOS；Windows 构建产物是 `target/release/dc24-edge.exe`（动态库为 `target/release/dc24_edge_core.dll`，Linux 为 `libdc24_edge_core.so`）。Windows 下沿用 MSVC 工具链可正常构建；此前 GNU 工具链在中文绝对路径下的链接问题不再阻塞，记录见 [工作记录](../docs/RUST_EDGE_WORKLOG.md)。

## 下一步

Python 驱动与 FFI 核心的实机联调（先 Windows 开发机 + 模拟设备，再树莓派 ARM64 + 真实 DC24）、真机资源占用与停止行为核验。全 Rust 单体路径已于 2026-11-11 实机部署验证(见上);FFI/Python 驱动路径仍待联调。
