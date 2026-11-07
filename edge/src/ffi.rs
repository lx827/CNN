//! C ABI 导出层：DC24 网络接收核心。契约文档见 `edge/FFI.md`。
//!
//! 设计边界：本层只负责设备链路（常驻监听、每秒 00 心跳、BA/B8/B2/B5/B7 时序、
//! `80` 帧解码、首帧 0 与序号连续性校验）和有界消息队列；
//! 落盘、后处理、云端上传一律由宿主语言（当前为 Python ctypes 驱动）完成。
//! 宿主通过 `dc24_edge_poll` 拉取消息——不做跨语言回调，ctypes 侧最稳。

use crate::{config::Config, device, protocol};
use anyhow::{ensure, Result};
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    ffi::{c_char, CStr, CString},
    net::TcpListener,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex, MutexGuard, OnceLock,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

/// 消息标签：1=样本块，2=设备/主机事件（JSON 行），3=链路状态（JSON）。
pub const MSG_SAMPLES: u8 = 1;
pub const MSG_EVENT: u8 = 2;
pub const MSG_STATE: u8 = 3;

/// 接收队列字节预算；超过即判会话失败（数据完整性优先，不静默丢样）。
const QUEUE_BUDGET_BYTES: usize = 16 * 1024 * 1024;

/// C 侧消息结构。`data` 为借用指针：有效期从本次 poll 返回起，
/// 到下一次 poll / start / close 止；宿主必须在此之前完成拷贝。
#[repr(C)]
pub struct Message {
    pub tag: u8,
    pub sequence: u16,
    pub start_sample: u64,
    pub len: usize,
    pub data: *const u8,
}

struct Queued {
    tag: u8,
    sequence: u16,
    start: u64,
    bytes: Vec<u8>,
}

#[derive(Default)]
struct Queue {
    items: VecDeque<Queued>,
    bytes: usize,
}
impl Queue {
    /// 链路状态消息不受预算限制：会话失败时队列可能已满，终态必须可送达。
    fn push(&mut self, item: Queued) -> Result<()> {
        if item.tag != MSG_STATE {
            ensure!(
                self.bytes + item.bytes.len() <= QUEUE_BUDGET_BYTES,
                "接收队列超过 {} MiB：宿主消费过慢或链路异常，停止会话",
                QUEUE_BUDGET_BYTES / (1024 * 1024)
            );
        }
        self.bytes += item.bytes.len();
        self.items.push_back(item);
        Ok(())
    }
}

type SharedQueue = Arc<Mutex<Queue>>;

fn lock(queue: &SharedQueue) -> MutexGuard<'_, Queue> {
    queue
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

fn state_message(state: &str, detail: impl std::fmt::Display) -> Queued {
    Queued {
        tag: MSG_STATE,
        sequence: 0,
        start: 0,
        bytes: json!({"state": state, "detail": detail.to_string()})
            .to_string()
            .into_bytes(),
    }
}

fn push_state(queue: &SharedQueue, state: &str, detail: impl std::fmt::Display) {
    let _ = lock(queue).push(state_message(state, detail));
}

/// 设备线程侧的消费端：把 `80` 帧解码为样本块消息，并增量转发事件日志。
struct Sink {
    queue: SharedQueue,
    previous: Option<u16>,
    index: u64,
    events_seen: usize,
    last_data: Instant,
}
impl Sink {
    fn frame(&mut self, frame: &[u8], events: &VecDeque<Value>) -> Result<()> {
        let (sequence, rows) = protocol::samples(frame)?;
        protocol::check_sequence(self.previous, sequence)?;
        self.previous = Some(sequence);
        self.last_data = Instant::now();
        let mut bytes = Vec::with_capacity(rows.len() * 16);
        for row in &rows {
            for value in row {
                bytes.extend(value.to_le_bytes());
            }
        }
        let start = self.index;
        self.index += rows.len() as u64;
        lock(&self.queue).push(Queued {
            tag: MSG_SAMPLES,
            sequence,
            start,
            bytes,
        })?;
        // 事件缓冲是容量 100 的环形队列；发现被裁剪就全量重发，避免漏记关键命令。
        if events.len() < self.events_seen {
            self.events_seen = 0;
        }
        for event in events.iter().skip(self.events_seen) {
            lock(&self.queue).push(Queued {
                tag: MSG_EVENT,
                sequence,
                start,
                bytes: (event.to_string() + "\n").into_bytes(),
            })?;
        }
        self.events_seen = events.len();
        Ok(())
    }
}

/// 与 runtime::session 相同的设备时序（DC24_PROTOCOL 第 5 节），不接触云端与落盘。
fn session_once(
    config: Config,
    listener: TcpListener,
    queue: SharedQueue,
    stop: Arc<AtomicBool>,
    rate: u32,
) -> Result<()> {
    let profile = protocol::profile(rate)?;
    let Some(mut link) = device::Link::connect(&listener, &config, &stop)? else {
        push_state(&queue, "stopped", "等待设备前会话被停止");
        return Ok(());
    };
    push_state(
        &queue,
        "connected",
        format!("设备 {} 已连接", config.device_ip),
    );
    let mut sink = Sink {
        queue: queue.clone(),
        previous: None,
        index: 0,
        events_seen: 0,
        last_data: Instant::now(),
    };
    let capture = (|| -> Result<()> {
        link.exchange(0xb8, &[], true, &mut |f, e| sink.frame(f, e))?;
        link.exchange(0xb2, &protocol::B2, true, &mut |f, e| sink.frame(f, e))?;
        link.exchange(0xb5, &profile, true, &mut |f, e| sink.frame(f, e))?;
        if stop.load(Ordering::Relaxed) {
            return Ok(());
        }
        link.exchange(0xb7, &[0], true, &mut |f, e| sink.frame(f, e))?;
        push_state(&queue, "streaming", rate);
        sink.last_data = Instant::now();
        while !stop.load(Ordering::Relaxed) {
            let frames = link.pump(&mut |f, e| sink.frame(f, e))?;
            ensure!(
                !frames.iter().any(|f| f[3] == 0xb8),
                "设备应答了未请求的停止命令"
            );
            ensure!(
                sink.last_data.elapsed() < Duration::from_secs(config.data_timeout_seconds),
                "设备采样数据超时"
            );
        }
        Ok(())
    })();
    push_state(&queue, "stopping", "会话停止中");
    // 即使采集失败也先尝试停止硬件；只在应答后发布正常终态。
    let stopped = link.exchange(0xb8, &[], true, &mut |f, e| sink.frame(f, e));
    if capture.is_err() || stopped.is_err() {
        let _ = link.send(0xb8, &[]);
    }
    capture?;
    stopped?;
    ensure!(link.pending() == 0, "停止后仍有不完整设备帧");
    push_state(&queue, "stopped", "会话正常结束");
    Ok(())
}

fn run_session(
    config: Config,
    listener: TcpListener,
    queue: SharedQueue,
    stop: Arc<AtomicBool>,
    rate: u32,
) {
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        session_once(config, listener, queue.clone(), stop, rate)
    }));
    match outcome {
        Ok(Ok(())) => (),
        Ok(Err(error)) => push_state(&queue, "failed", format!("{error:#}")),
        Err(panic) => push_state(&queue, "failed", format!("会话线程 panic: {panic:?}")),
    }
}

/// 句柄。同一句柄的所有调用必须在同一线程序列化（或由宿主自行加锁）。
pub struct Edge {
    config: Config,
    listener: TcpListener,
    queue: SharedQueue,
    stop: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
    /// 上一次 poll 借出的消息；保留所有权以维持 data 指针有效。
    borrowed: Option<Queued>,
}

fn write_err(err: *mut c_char, capacity: usize, message: &str) {
    if err.is_null() || capacity == 0 {
        return;
    }
    let bytes = message.as_bytes();
    let mut end = (capacity - 1).min(bytes.len());
    // 退回 UTF-8 字符边界，语义同 str::is_char_boundary：切割点处的字节若是
    // 续字节，说明多字节字符被截半，须整体让出。（手写 bytes[end] 不判 len 会
    // 越界 panic；查 bytes[end-1] 续字节则漏掉"保留首字节、丢弃续字节"的切割。）
    let boundary = |cut: usize| cut == 0 || cut >= bytes.len() || (bytes[cut] & 0xC0) != 0x80;
    while end > 0 && !boundary(end) {
        end -= 1;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), err.cast::<u8>(), end);
        *err.add(end) = 0;
    }
}

/// 用 config.json 全文初始化并绑定常驻监听。失败返回空指针，错误文本写入 err。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_open(
    config_json: *const c_char,
    err: *mut c_char,
    err_len: usize,
) -> *mut Edge {
    let fail = |message: &str| -> *mut Edge {
        write_err(err, err_len, message);
        std::ptr::null_mut()
    };
    if config_json.is_null() {
        return fail("config_json 为空");
    }
    let text = match CStr::from_ptr(config_json).to_str() {
        Ok(text) => text,
        Err(_) => return fail("config_json 不是有效 UTF-8"),
    };
    let config = match Config::from_json(text) {
        Ok(config) => config,
        Err(error) => return fail(&format!("配置无效: {error:#}")),
    };
    let listener = match device::bind_listener(&config) {
        Ok(listener) => listener,
        Err(error) => return fail(&format!("绑定监听失败: {error:#}")),
    };
    Box::into_raw(Box::new(Edge {
        config,
        listener,
        queue: Arc::new(Mutex::new(Queue::default())),
        stop: Arc::new(AtomicBool::new(false)),
        worker: None,
        borrowed: None,
    }))
}

/// 启动一次采集会话（内部线程完成 accept+BA 探活与 BA/B8/B2/B5/B7 时序）。
/// 立即返回；进度与错误通过 dc24_edge_poll 的状态消息交付。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_start(
    edge: *mut Edge,
    sample_rate: u32,
    err: *mut c_char,
    err_len: usize,
) -> i32 {
    let Some(edge) = edge.as_mut() else {
        write_err(err, err_len, "edge 句柄为空");
        return -1;
    };
    if edge
        .worker
        .as_ref()
        .is_some_and(|worker| !worker.is_finished())
    {
        write_err(err, err_len, "已有会话在运行");
        return -1;
    }
    edge.worker = None;
    let _ = edge.borrowed.take(); // 此前 poll 借出的指针即刻失效
    if let Err(error) = protocol::profile(sample_rate) {
        write_err(err, err_len, &format!("{error:#}"));
        return -1;
    }
    let listener = match edge.listener.try_clone() {
        Ok(listener) => listener,
        Err(error) => {
            write_err(err, err_len, &format!("复制监听句柄失败: {error}"));
            return -1;
        }
    };
    edge.stop = Arc::new(AtomicBool::new(false));
    let config = edge.config.clone();
    let queue = edge.queue.clone();
    let stop = edge.stop.clone();
    edge.worker = Some(thread::spawn(move || {
        run_session(config, listener, queue, stop, sample_rate)
    }));
    0
}

/// 请求停止并等待会话线程收尾（内部完成 B8 与应答等待）。最长约 5～7 秒。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_stop(edge: *mut Edge, err: *mut c_char, err_len: usize) -> i32 {
    let Some(edge) = edge.as_mut() else {
        write_err(err, err_len, "edge 句柄为空");
        return -1;
    };
    edge.stop.store(true, Ordering::Relaxed);
    if let Some(worker) = edge.worker.take() {
        if worker.join().is_err() {
            write_err(err, err_len, "会话线程异常退出");
            return -1;
        }
    }
    0
}

/// 拉取一条消息。返回 1=取得消息，0=超时，-1=句柄或出参无效。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_poll(
    edge: *mut Edge,
    out: *mut Message,
    timeout_ms: i32,
) -> i32 {
    let Some(edge) = edge.as_mut() else {
        return -1;
    };
    if out.is_null() {
        return -1;
    }
    let deadline = Instant::now() + Duration::from_millis(timeout_ms.max(0) as u64);
    loop {
        let popped = {
            let mut queue = lock(&edge.queue);
            queue
                .items
                .pop_front()
                .inspect(|item| queue.bytes -= item.bytes.len())
        };
        if let Some(item) = popped {
            let message = Message {
                tag: item.tag,
                sequence: item.sequence,
                start_sample: item.start,
                len: item.bytes.len(),
                data: item.bytes.as_ptr(),
            };
            let _ = edge.borrowed.take();
            edge.borrowed = Some(item);
            *out = message;
            return 1;
        }
        if Instant::now() >= deadline {
            return 0;
        }
        thread::sleep(Duration::from_millis(5));
    }
}

/// 会话线程是否仍在运行（0=否，1=是，-1=句柄无效）。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_running(edge: *const Edge) -> i32 {
    let Some(edge) = edge.as_ref() else {
        return -1;
    };
    edge.worker
        .as_ref()
        .is_some_and(|worker| !worker.is_finished()) as i32
}

/// 停止会话并释放句柄。之后不得再使用该指针。
#[no_mangle]
pub unsafe extern "C" fn dc24_edge_close(edge: *mut Edge) {
    if let Some(edge) = edge.as_mut() {
        edge.stop.store(true, Ordering::Relaxed);
        if let Some(worker) = edge.worker.take() {
            let _ = worker.join();
        }
    }
    if !edge.is_null() {
        drop(Box::from_raw(edge));
    }
}

fn info() -> &'static CString {
    static INFO: OnceLock<CString> = OnceLock::new();
    INFO.get_or_init(|| {
        let profiles: serde_json::Map<String, Value> = protocol::RATES
            .iter()
            .map(|rate| {
                Ok((
                    rate.to_string(),
                    Value::String(protocol::hex(&protocol::profile(*rate)?)),
                ))
            })
            .collect::<Result<_>>()
            .expect("内置档位必然有效");
        let text = json!({
            "version": 3,
            "sample_rates": protocol::RATES,
            "channel_count": 4,
            "input_configuration": protocol::input_configuration(),
            "transport": "rust_tcp",
            "implementation": "dc24-edge-rust-ffi-0.1.0",
            "b2_payload_hex": protocol::hex(&protocol::B2),
            "b5_payload_hex_by_rate": profiles,
            "sample_layout": "每采样时刻16字节：四路小端有符号int32，数值为有符号24位ADC计数",
        })
        .to_string();
        CString::new(text).expect("信息文本不含内部 NUL")
    })
}

/// 返回进程级静态 JSON（借用期=进程生命周期）：心跳元数据与命令负载模板，
/// 供宿主组装云端心跳与记录元数据，保证与 Rust 全量边端上报一致。
#[no_mangle]
pub extern "C" fn dc24_edge_info_json() -> *const c_char {
    info().as_ptr()
}
