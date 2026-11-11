# DC24 网络接收核心 FFI 契约（`dc24_edge_core`）

Rust cdylib 导出的 C ABI，供边端宿主语言（当前为 Python ctypes 驱动 `dc24/dc24_edge_pi.py`）调用。
职责边界：**本库只做设备链路**——常驻监听、每秒 `00` 心跳、BA/B8/B2/B5/B7 时序、`80` 帧解码、
首帧序号 0 与连续性校验、有界消息队列；落盘、后处理、云端上传全部在宿主侧完成。
协议行为依据 [`docs/DC24_PROTOCOL.md`](../docs/DC24_PROTOCOL.md) 的已验证子集，实现见 `src/protocol.rs`、`src/device.rs`、`src/ffi.rs`。

## 构建产物

```sh
cargo build --release
# Linux（树莓派）: libdc24_edge_core.so
# Windows 开发机:  dc24_edge_core.dll
```

C 符号前缀统一为 `dc24_edge_*`（与库文件名无关）。

## 消息结构

```c
typedef struct dc24_msg {
    uint8_t  tag;           /* 偏移0：1=样本块 2=事件 3=链路状态 */
    uint16_t sequence;      /* 偏移2：产生本消息的设备帧号（样本块），其余为0 */
    uint64_t start_sample;  /* 偏移8：本块首样本的会话内绝对索引（样本块），其余为0 */
    size_t   len;           /* data 字节数 */
    const uint8_t* data;    /* 借用指针：有效到下一次 poll / start / close */
} dc24_msg;                 /* repr(C)，自然对齐；宿主结构体须逐字段镜像 */
```

三种 `data` 载荷：

| tag | 载荷 | 语义 |
|---|---|---|
| 1 样本块 | 二进制，长度为 16 的倍数 | 每采样时刻 16 字节：四路小端有符号 int32（数值为有符号 24 位 ADC 计数）。与云端 `POST /api/acquisition/sessions/{id}/frames` 请求体同构，`start_sample` 即查询参数 `start`，`sequence` 即 `sequence` |
| 2 事件 | UTF-8 JSON 行，以 `\n` 结尾 | 设备↔主机控制报文记录（方向/命令/hex/主机时间戳），可直接追加进 `commands.jsonl`；来源为容量 100 的环形缓冲，被裁剪时会全量重发，宿主按行去重由时间戳保证 |
| 3 链路状态 | UTF-8 JSON：`{"state":…,"detail":…}` | 状态序列：`connected → streaming → stopping → stopped`；任何阶段出错为 `failed`（终态）。终态必然可送达（见队列策略） |

## 导出函数

| 函数 | 语义 | 返回 |
|---|---|---|
| `dc24_edge_open(config_json, err, err_len)` | 解析 config.json 全文并绑定常驻监听（进程内每个实例一次；同一地址同时只能有一个监听者，与原厂软件互斥） | 成功=句柄；失败=空指针，错误文本入 `err` |
| `dc24_edge_start(edge, sample_rate, err, err_len)` | 立即返回；内部线程执行 accept+BA 探活与 B8/B2/B5/B7 时序 | 0=已受理；-1=参数/状态错误。采样率必须在 12 档原厂档位内 |
| `dc24_edge_poll(edge, out, timeout_ms)` | 拉取一条消息（阻塞至多 timeout_ms） | 1=取得；0=超时；-1=句柄/出参无效 |
| `dc24_edge_stop(edge, err, err_len)` | 请求停止并等待会话线程收尾（内部完成 B8 与应答，最长约 5～7 秒） | 0=正常；-1=线程异常退出。停止后队列中消息仍可继续 poll |
| `dc24_edge_running(edge)` | 会话线程是否存活 | 1/0；-1=句柄无效 |
| `dc24_edge_info_json()` | 进程级静态 JSON：`version`、`sample_rates`、`channel_count`、`input_configuration`、`transport`、`implementation`、`b2_payload_hex`、`b5_payload_hex_by_rate`、`sample_layout` | 指向静态内存的指针，借用期=进程生命周期，无需释放 |
| `dc24_edge_close(edge)` | 停止会话并释放句柄；之后不得再使用 | 无 |

错误缓冲约定：`err` 为宿主提供的 `char*`，容量 `err_len`；写入按 UTF-8 字符边界截断、NUL 结尾。

## 生命周期示例（Python 伪代码）

```python
lib = ctypes.CDLL("libdc24_edge_core.so")
edge = lib.dc24_edge_open(config_json.encode(), err, len(err))
lib.dc24_edge_start(edge, 10000, err, len(err))
while True:
    if lib.dc24_edge_poll(edge, byref(msg), 250) == 1:
        data = ctypes.string_at(msg.data, msg.len)  # 必须立即拷贝
        ...
lib.dc24_edge_stop(edge, err, len(err))
lib.dc24_edge_close(edge)
```

## 队列与错误策略

- 队列预算 16 MiB（按消息字节计）。宿主消费过慢导致超限时**会话判失败**并推送 `failed` 终态——数据完整性优先，不静默丢样。
- `state`（tag=3）消息不受预算限制：队列满时终态仍可送达。
- 会话内任何协议错误（首帧序号非 0、帧不连续、校验失败、数据超时、设备断开）同样以 `failed` 终态交付，`detail` 为完整错误链。
- 样本索引每次 start 从 0 重新计数；`start_sample` 单调不减，宿主上传实时窗口时以绝对索引显式保留缺口。

## 线程与重入约定

- 同一句柄的所有调用必须在同一线程序列化（或宿主自行加锁）。典型用法：主线程 `open/start/stop/close`，一个消费者线程循环 `poll`。
- `poll` 的 `data` 指针只保证到下一次 `poll`/`start`/`close` 前有效；跨线程共享必须先拷贝。
- `dc24_edge_info_json` 线程安全（内部一次初始化）。

## 配置

复用边端 `config.json` 全 schema（见 `config.rs` / `config.example.json`）。本库只使用其中
`listen_ip`、`device_ip`、`port`、`device_wait_seconds`、`data_timeout_seconds` 字段；
`cloud_url` 等云端字段仅做格式校验（宿主与核心共用同一份部署配置文件）。

## 版本

`dc24_edge_info_json()` 的 `implementation` 字段标识核心版本（当前 `dc24-edge-rust-ffi-0.1.0`），
`version` 与云端边端版本契约对齐（当前 3，见 `docs/DC24_PROTOCOL.md` 第 11 节）。升级 ABI 时同步更新本文件与 `edge/README.md`。
