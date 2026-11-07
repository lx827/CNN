//! FFI 回环测试：模拟设备走 BA/B8/B2/B5/B7 → 80 帧 → B8 的完整时序，
//! 验证样本块布局、事件转发、终态交付、首帧门槛与队列超限保护。
use dc24_edge_core::ffi::{
    dc24_edge_close, dc24_edge_info_json, dc24_edge_open, dc24_edge_poll, dc24_edge_running,
    dc24_edge_start, dc24_edge_stop, Message, MSG_EVENT, MSG_SAMPLES, MSG_STATE,
};
use dc24_edge_core::protocol::{self, Frames};
use serde_json::{json, Value};
use std::{
    ffi::{c_char, CStr, CString},
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::PathBuf,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

fn free_port() -> u16 {
    let probe = TcpListener::bind("127.0.0.1:0").unwrap();
    probe.local_addr().unwrap().port()
}

fn open_handle(port: u16) -> *mut dc24_edge_core::ffi::Edge {
    let storage = PathBuf::from(std::env::temp_dir()).join(format!(
        "dc24-ffi-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let text = CString::new(
        serde_json::to_string(&json!({
            "cloud_url": "http://127.0.0.1:1",
            "listen_ip": "127.0.0.1",
            "device_ip": "127.0.0.1",
            "port": port,
            "storage": storage,
            "agent_id": "ffi-test",
            "min_free_bytes": 0,
            "device_wait_seconds": 5,
            "data_timeout_seconds": 3,
        }))
        .unwrap(),
    )
    .unwrap();
    let mut err = [0 as c_char; 512];
    let handle = unsafe { dc24_edge_open(text.as_ptr(), err.as_mut_ptr(), err.len()) };
    assert!(!handle.is_null(), "open 失败: {}", cstr_lossy(&err));
    handle
}

fn cstr_lossy(buf: &[c_char]) -> String {
    unsafe { CStr::from_ptr(buf.as_ptr()).to_string_lossy().into_owned() }
}

fn start(handle: *mut dc24_edge_core::ffi::Edge, rate: u32) {
    let mut err = [0 as c_char; 512];
    assert_eq!(
        unsafe { dc24_edge_start(handle, rate, err.as_mut_ptr(), err.len()) },
        0,
        "{}",
        cstr_lossy(&err)
    );
}

fn poll(handle: *mut dc24_edge_core::ffi::Edge, timeout_ms: i32) -> Message {
    let mut message = Message {
        tag: 0,
        sequence: 0,
        start_sample: 0,
        len: 0,
        data: std::ptr::null(),
    };
    assert_eq!(
        unsafe { dc24_edge_poll(handle, &mut message, timeout_ms) },
        1
    );
    message
}

fn bytes(message: &Message) -> Vec<u8> {
    unsafe { std::slice::from_raw_parts(message.data, message.len) }.to_vec()
}

/// 排空队列直到 stopped/failed 终态，返回按序收到的全部状态消息。
fn drain_states(handle: *mut dc24_edge_core::ffi::Edge, deadline: Instant) -> Vec<Value> {
    let mut states = Vec::new();
    while Instant::now() < deadline {
        let message = poll(handle, 500);
        assert!(
            message.tag != MSG_SAMPLES || !bytes(&message).is_empty(),
            "样本块不能为空"
        );
        if message.tag == MSG_STATE {
            let value: Value = serde_json::from_slice(&bytes(&message)).unwrap();
            let terminal = value["state"] == "stopped" || value["state"] == "failed";
            states.push(value);
            if terminal {
                return states;
            }
        }
    }
    panic!("期限内未收到终态: {states:?}");
}

fn data_frame(sequence: u16) -> Vec<u8> {
    let mut body = vec![0x80];
    body.extend(sequence.to_le_bytes());
    for _ in 0..254 {
        for (tag, v) in [-8388608i32, 8388607, -1, 12345].iter().enumerate() {
            body.extend(((v << 8) | tag as i32).to_le_bytes());
        }
    }
    let mut out = vec![0x7e];
    out.extend((body.len() as u16).to_be_bytes());
    out.extend(body);
    out.push(255);
    out
}

/// 模拟设备：拨入 → 应答控制命令 → B7 后持续发 80 帧直到 B8。
fn spawn_device(port: u16, first_sequence: u16, frame_delay_ms: u64) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let mut socket = loop {
            match TcpStream::connect(("127.0.0.1", port)) {
                Ok(socket) => break socket,
                Err(_) => thread::sleep(Duration::from_millis(10)),
            }
        };
        socket
            .set_read_timeout(Some(Duration::from_millis(5)))
            .unwrap();
        let mut parser = Frames::default();
        let mut sampling = false;
        let mut sequence = first_sequence;
        let mut buf = [0; 4096];
        loop {
            match socket.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    for frame in parser.feed(&buf[..n]).unwrap() {
                        match frame[3] {
                            0xb7 => sampling = true,
                            // 配置阶段与收尾都会出现 B8：只应答并停发数据，
                            // 等宿主关闭连接后由 EOF 退出。
                            0xb8 => sampling = false,
                            _ => (),
                        }
                        let payload: &[u8] = if frame[3] == 0xba { &[0x55, 0] } else { &[0] };
                        socket
                            .write_all(&protocol::command(frame[3], payload))
                            .unwrap();
                    }
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                    ) => {}
                Err(_) => break,
            }
            if sampling {
                let data = data_frame(sequence);
                sequence = sequence.wrapping_add(1);
                for part in data.chunks(1024) {
                    if socket.write_all(part).is_err() {
                        return;
                    }
                }
                thread::sleep(Duration::from_millis(frame_delay_ms));
            }
        }
    })
}

#[test]
fn ffi_streams_samples_events_and_stops_cleanly() {
    let port = free_port();
    let handle = open_handle(port);
    let info: Value = serde_json::from_str(
        unsafe { CStr::from_ptr(dc24_edge_info_json()) }
            .to_str()
            .unwrap(),
    )
    .unwrap();
    assert_eq!(info["version"], 3);
    assert_eq!(info["transport"], "rust_tcp");
    assert_eq!(
        info["b5_payload_hex_by_rate"]["10000"],
        "00001c00102700000f000000"
    );

    let device = spawn_device(port, 0, 2);
    start(handle, 1000);
    assert_eq!(unsafe { dc24_edge_running(handle) }, 1);

    let deadline = Instant::now() + Duration::from_secs(10);
    let (mut sample_blocks, mut events, mut last_end) = (0, 0, 0u64);
    let mut early_states: Vec<Value> = Vec::new();
    while sample_blocks < 2 || events < 1 {
        assert!(Instant::now() < deadline, "期限内未收到足够样本/事件");
        let message = poll(handle, 500);
        match message.tag {
            MSG_SAMPLES => {
                assert!(message.start_sample >= last_end, "样本起始索引必须单调不减");
                if last_end == 0 {
                    assert_eq!(message.sequence, 0, "首块必须来自帧号 0");
                }
                last_end = message.start_sample + message.len as u64 / 16;
                let data = bytes(&message);
                assert_eq!(data.len() % 16, 0);
                let mut first = [0i32; 4];
                for (channel, word) in data.chunks_exact(4).take(4).enumerate() {
                    first[channel] = i32::from_le_bytes(word.try_into().unwrap());
                }
                assert_eq!(first, [-8388608, 8388607, -1, 12345]);
                sample_blocks += 1;
            }
            MSG_EVENT => {
                let text = String::from_utf8(bytes(&message)).unwrap();
                assert!(text.ends_with('\n'), "事件行必须以换行结尾");
                let value: Value = serde_json::from_str(text.trim_end()).unwrap();
                assert!(value["direction"].is_string());
                events += 1;
            }
            MSG_STATE => {
                let value: Value = serde_json::from_slice(&bytes(&message)).unwrap();
                assert!(
                    value["state"] != "stopped" && value["state"] != "failed",
                    "早段不应出现终态: {value}"
                );
                early_states.push(value);
            }
            tag => panic!("意外消息标签 {tag}"),
        }
    }

    let mut err = [0 as c_char; 512];
    assert_eq!(
        unsafe { dc24_edge_stop(handle, err.as_mut_ptr(), err.len()) },
        0
    );
    assert_eq!(unsafe { dc24_edge_running(handle) }, 0);
    let mut states = early_states;
    states.extend(drain_states(
        handle,
        Instant::now() + Duration::from_secs(10),
    ));
    assert_eq!(states.last().unwrap()["state"], "stopped");
    assert!(states.iter().any(|s| s["state"] == "connected"));
    assert!(states.iter().any(|s| s["state"] == "streaming"));
    unsafe { dc24_edge_close(handle) };
    device.join().unwrap();
}

#[test]
fn ffi_rejects_nonzero_first_sequence() {
    let port = free_port();
    let handle = open_handle(port);
    let device = spawn_device(port, 5, 2);
    start(handle, 1000);
    let states = drain_states(handle, Instant::now() + Duration::from_secs(10));
    let final_state = states.last().unwrap();
    assert_eq!(final_state["state"], "failed");
    assert!(final_state["detail"].as_str().unwrap().contains("首帧"));
    let mut err = [0 as c_char; 512];
    assert_eq!(
        unsafe { dc24_edge_stop(handle, err.as_mut_ptr(), err.len()) },
        0
    );
    unsafe { dc24_edge_close(handle) };
    device.join().unwrap();
}

#[test]
fn ffi_fails_when_host_stops_consuming() {
    let port = free_port();
    let handle = open_handle(port);
    let device = spawn_device(port, 0, 0);
    start(handle, 1000);
    // 完全不 poll，让队列涨满预算：会话必须判失败而不是无限吃内存。
    let deadline = Instant::now() + Duration::from_secs(60);
    while unsafe { dc24_edge_running(handle) } == 1 {
        assert!(Instant::now() < deadline, "会话未因队列超限而失败");
        thread::sleep(Duration::from_millis(50));
    }
    let states = drain_states(handle, Instant::now() + Duration::from_secs(30));
    let final_state = states.last().unwrap();
    assert_eq!(final_state["state"], "failed");
    assert!(final_state["detail"].as_str().unwrap().contains("接收队列"));
    let mut err = [0 as c_char; 512];
    assert_eq!(
        unsafe { dc24_edge_stop(handle, err.as_mut_ptr(), err.len()) },
        0
    );
    unsafe { dc24_edge_close(handle) };
    device.join().unwrap();
}
