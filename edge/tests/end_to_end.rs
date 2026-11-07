//! 在回环地址模拟 DC24 与云端，不访问真实设备或公网服务器。
use dc24_edge::{
    protocol::{self, Frames},
    runtime,
};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tiny_http::{Response, Server, StatusCode};

const SID: &str = "11111111111111111111111111111111";
const JOB: &str = "22222222222222222222222222222222";

#[derive(Default)]
struct Remote {
    files: HashMap<String, Vec<u8>>,
    state: Value,
    finished: bool,
    rejected: bool,
    frames: u64,
    commands: Vec<Vec<u8>>,
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

#[test]
fn device_to_cloud_preserves_counts_files_and_retries_without_memory_backlog() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::current_dir()
        .unwrap()
        .join("target/test-evidence")
        .join(unique.to_string());
    fs::create_dir_all(&root).unwrap();
    let storage = root.join("recordings");
    let server = Server::http("127.0.0.1:0").unwrap();
    let cloud_port = server.server_addr().to_ip().unwrap().port();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let device_port = listener.local_addr().unwrap().port();
    drop(listener);
    let config = root.join("config.json");
    fs::write(&config,serde_json::to_vec(&json!({"cloud_url":format!("http://127.0.0.1:{cloud_port}"),
        "listen_ip":"127.0.0.1","device_ip":"127.0.0.1","port":device_port,"storage":storage,
        "agent_id":"rust-test","min_free_bytes":0,"http_timeout_seconds":1,"upload_timeout_seconds":2,
        "device_wait_seconds":5,"data_timeout_seconds":3})).unwrap()).unwrap();
    let quit = Arc::new(AtomicBool::new(false));
    let remote = Arc::new(Mutex::new(Remote::default()));
    let http = {
        let (q, r, storage) = (quit.clone(), remote.clone(), storage.clone());
        thread::spawn(move || {
            while !q.load(Ordering::Relaxed) {
                let Some(mut req) = server.recv_timeout(Duration::from_millis(100)).unwrap() else {
                    continue;
                };
                assert!(req
                    .headers()
                    .iter()
                    .any(|h| h.field.equiv("X-Edge-Key") && h.value.as_str() == "test-key"));
                let url = req.url().to_owned();
                let method = req.method().as_str().to_owned();
                let mut bytes = Vec::new();
                req.as_reader().read_to_end(&mut bytes).unwrap();
                let mut state = r.lock().unwrap();
                let mut data = Value::Null;
                let mut status = 200;
                if url.ends_with("/control") {
                    data = json!({"session":if state.state["status"]=="stopped"||state.state["status"]=="failed"{Value::Null}else{
                    json!({"id":SID,"sample_rate":1000,"stop_requested":state.finished,
                        "recording":{"id":JOB,"duration":1,"save_directory":storage,"stop_requested":false}})}});
                } else if url.contains("/frames?") {
                    assert_eq!(bytes.len() % 16, 0);
                    for row in bytes.chunks_exact(16) {
                        for (tag, word) in row.chunks_exact(4).enumerate() {
                            assert_eq!(
                                i32::from_le_bytes(word.try_into().unwrap()),
                                [-8388608, 8388607, -1, 12345][tag]
                            );
                        }
                    }
                    state.frames += bytes.len() as u64 / 16;
                } else if url.contains("/state?") {
                    state.state = serde_json::from_slice(&bytes).unwrap();
                } else if method == "PUT" {
                    let name = url
                        .split("/stream-files/")
                        .nth(1)
                        .unwrap()
                        .split('?')
                        .next()
                        .unwrap();
                    if !state.rejected {
                        state.rejected = true;
                        status = 503;
                    } else {
                        state.files.insert(name.into(), bytes);
                    }
                } else if url.contains("/finish-stream?") {
                    assert_eq!(state.files.len(), 5);
                    state.finished = true;
                    data = json!({"status":"completed"});
                } else if url.ends_with(&format!("/jobs/{JOB}")) {
                    data = json!({"status":if state.finished{"completed"}else{"capturing"},"metadata":if state.finished{json!({"complete":true})}else{Value::Null}});
                } else if url.ends_with("/heartbeat") {
                    let beat: Value = serde_json::from_slice(&bytes).unwrap();
                    assert_eq!(beat["source"], "dc24_tcp");
                    assert_eq!(beat["state"]["version"], 3);
                }
                drop(state);
                let body = serde_json::to_vec(&json!({"code":status,"data":data})).unwrap();
                let _ = req.respond(Response::from_data(body).with_status_code(StatusCode(status)));
            }
        })
    };
    let app = {
        let q = quit.clone();
        thread::spawn(move || runtime::run(&config, Some("test-key".into()), q))
    };
    let device = {
        let (q, r) = (quit.clone(), remote.clone());
        thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(5);
            let mut socket = loop {
                match TcpStream::connect(("127.0.0.1", device_port)) {
                    Ok(s) => break s,
                    Err(_) => {
                        assert!(Instant::now() < deadline);
                        thread::sleep(Duration::from_millis(20));
                    }
                }
            };
            socket
                .set_read_timeout(Some(Duration::from_millis(5)))
                .unwrap();
            let mut parser = Frames::default();
            let mut sampling = false;
            let mut sequence = 0u16;
            let mut buf = [0; 4096];
            while !q.load(Ordering::Relaxed) {
                match socket.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        for frame in parser.feed(&buf[..n]).unwrap() {
                            r.lock().unwrap().commands.push(frame.clone());
                            match frame[3] {
                                0xb7 => sampling = true,
                                0xb8 => sampling = false,
                                _ => (),
                            }
                            let ack = protocol::command(
                                frame[3],
                                if frame[3] == 0xba { &[0x55, 0] } else { &[0] },
                            );
                            socket.write_all(&ack).unwrap();
                        }
                    }
                    Err(e)
                        if matches!(
                            e.kind(),
                            std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                        ) =>
                    {
                        ()
                    }
                    Err(_) => break,
                }
                if sampling {
                    let data = data_frame(sequence);
                    sequence = sequence.wrapping_add(1);
                    for part in data.chunks(23) {
                        if socket.write_all(part).is_err() {
                            return;
                        }
                    }
                }
            }
        })
    };
    let deadline = Instant::now() + Duration::from_secs(20);
    let mut completed = false;
    while Instant::now() < deadline {
        {
            let r = remote.lock().unwrap();
            if r.finished && r.state["status"] == "stopped" {
                completed = true;
                break;
            }
        }
        thread::sleep(Duration::from_millis(50));
    }
    quit.store(true, Ordering::Relaxed);
    let app_result = app.join().unwrap();
    let _ = device.join();
    http.join().unwrap();
    app_result.unwrap();
    assert!(completed, "end-to-end session did not finish");
    let state = remote.lock().unwrap();
    assert!(state.rejected && state.frames > 0);
    assert_eq!(state.commands[2], protocol::command(0xb2, &protocol::B2));
    assert_eq!(
        state.commands[3],
        protocol::command(0xb5, &protocol::profile(1000).unwrap())
    );
    assert_eq!(
        state.commands.last().unwrap(),
        &protocol::command(0xb8, &[])
    );
    let path = storage.join(JOB);
    for (name, bytes) in &state.files {
        assert_eq!(fs::read(path.join(name)).unwrap(), *bytes);
    }
    let meta: Value = serde_json::from_slice(&state.files["metadata.json"]).unwrap();
    assert_eq!(meta["complete"], true);
    let count = meta["samples_per_channel"].as_u64().unwrap();
    assert!(count >= 1000 && count % 254 == 0);
    assert_eq!(state.files["counts.i32"].len() as u64, count * 16);
    let text = String::from_utf8(state.files["samples.csv"].clone()).unwrap();
    assert_eq!(text.lines().count() as u64, count + 1);
    for (index, line) in text.lines().skip(1).enumerate() {
        let columns: Vec<_> = line.split(',').collect();
        assert_eq!(columns[0].parse::<usize>().unwrap(), index);
        assert!((columns[1].parse::<f64>().unwrap() - index as f64 / 1000.0).abs() < 1e-9);
        assert_eq!(&columns[2..], &["-8388608", "8388607", "-1", "12345"]);
    }
    let mut parser = Frames::default();
    let mut raw_count = 0;
    for part in state.files["rx_stream.bin"].chunks(1460) {
        for frame in parser.feed(part).unwrap() {
            raw_count += protocol::samples(&frame).unwrap().1.len();
        }
    }
    assert_eq!(raw_count as u64, count);
    assert_eq!(parser.pending(), 0);
    let manifest: Value =
        serde_json::from_slice(&fs::read(storage.join(format!(".uploads/{JOB}.json"))).unwrap())
            .unwrap();
    assert_eq!(manifest["status"], "uploaded");
    println!("EVIDENCE={}", path.display());
}
