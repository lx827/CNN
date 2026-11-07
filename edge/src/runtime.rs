use crate::{
    cloud::Cloud,
    config::{valid_id, Config, Mode},
    device::Link,
    protocol,
    recording::{self, Manifest, Recording, FILES},
};
use anyhow::{bail, ensure, Context, Result};
use fs2::FileExt;
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    fs::{self, OpenOptions},
    path::Path,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

#[derive(Default)]
struct Window {
    chunks: VecDeque<(u64, Vec<u8>)>,
    end: u64,
}
impl Window {
    fn push(&mut self, rows: &[[i32; 4]], rate: u32) {
        let mut bytes = Vec::with_capacity(rows.len() * 16);
        for row in rows {
            for v in row {
                bytes.extend(v.to_le_bytes());
            }
        }
        self.chunks.push_back((self.end, bytes));
        self.end += rows.len() as u64;
        let cutoff = self.end.saturating_sub(rate as u64 * 2);
        while self
            .chunks
            .front()
            .is_some_and(|(start, b)| start + b.len() as u64 / 16 <= cutoff)
        {
            self.chunks.pop_front();
        }
    }
    fn after(&self, sent: u64) -> Option<(u64, Vec<u8>)> {
        let first = self.chunks.front()?.0.max(sent);
        let mut result = Vec::new();
        for (start, bytes) in &self.chunks {
            let skip = sent.saturating_sub(*start).min(bytes.len() as u64 / 16) as usize * 16;
            result.extend_from_slice(&bytes[skip..]);
        }
        if result.is_empty() {
            None
        } else {
            Some((first, result))
        }
    }
}

struct State {
    control: Value,
    status: String,
    error: Option<String>,
    recording: Value,
    window: Window,
    sequence: u16,
    session: Option<String>,
    last_record: Option<String>,
}
impl Default for State {
    fn default() -> Self {
        Self {
            control: Value::Null,
            status: "idle".into(),
            error: None,
            recording: Value::Null,
            window: Window::default(),
            sequence: 0,
            session: None,
            last_record: None,
        }
    }
}
type Shared = Arc<Mutex<State>>;

fn heartbeat(config: &Config, shared: &Shared) -> Value {
    let s = shared.lock().unwrap();
    json!({"stage":s.status,"hardware_connected":matches!(s.status.as_str(),"configuring"|"streaming"),
        "sample_rates":protocol::RATES,"channel_count":4,"save_directory":config.storage,"version":3,
        "input_configuration":protocol::input_configuration(),"transport":"rust_tcp",
        "implementation":"dc24-edge-rust-0.1.0","session_id":s.session,"error":s.error})
}

fn snapshot(shared: &Shared) -> Value {
    let s = shared.lock().unwrap();
    json!({"status":s.status,"error":s.error,"recording":s.recording})
}

fn update(shared: &Shared, status: &str) {
    shared.lock().unwrap().status = status.into();
}

fn mark_record(shared: &Shared, job: &str, status: &str, count: u64, error: Option<String>) {
    let mut s = shared.lock().unwrap();
    if s.recording.is_null() || s.recording["id"] == job {
        s.recording = json!({"id":job,"status":status,"samples_per_channel":count,"error":error});
    }
}

fn upload_one(config: &Config, cloud: &Cloud, manifest: &mut Manifest) -> Result<()> {
    ensure!(
        manifest.agent == config.agent_id && valid_id(&manifest.job),
        "补传记录不属于当前边端"
    );
    // finish-stream 的成功响应可能丢失，先查询任务，避免重传时卡在409。
    let remote = cloud.get(&format!("/jobs/{}", manifest.job))?;
    if matches!(remote["status"].as_str(), Some("completed" | "failed"))
        && remote["metadata"].is_object()
    {
        manifest.status = "uploaded".into();
    } else {
        cloud.post(
            &format!("/jobs/{}/progress?agent_id={}", manifest.job, cloud.id),
            &json!({"stage":"uploading","samples_per_channel":manifest.samples}),
        )?;
        for name in FILES {
            cloud.upload_file(&manifest.job, name, &manifest.path.join(name))?;
        }
        cloud.post(
            &format!("/jobs/{}/finish-stream?agent_id={}", manifest.job, cloud.id),
            &json!({}),
        )?;
        manifest.status = "uploaded".into();
    }
    recording::atomic_json(&recording::manifest_path(config, &manifest.job), manifest)?;
    Ok(())
}

fn uploader(config: Config, cloud: Cloud, shared: Shared, quit: Arc<AtomicBool>) {
    while !quit.load(Ordering::Relaxed) {
        let result = (|| -> Result<()> {
            for entry in fs::read_dir(config.storage.join(".uploads"))? {
                if quit.load(Ordering::Relaxed) {
                    break;
                }
                let path = entry?.path();
                if path.extension().is_none_or(|e| e != "json") {
                    continue;
                }
                let mut m: Manifest = serde_json::from_slice(&fs::read(&path)?)?;
                if m.status == "interrupted" {
                    match cloud.post(&format!("/jobs/{}/progress?agent_id={}",m.job,cloud.id),
                        &json!({"stage":"failed","message":"边端进程中断；现场文件保留，未冒充完整记录上传"})) {
                        Ok(_)=>{m.status="interrupted_reported".into();recording::atomic_json(&path,&m)?;},
                        Err(e)=>eprintln!("中断记录状态待上报 [{}]: {e}",m.job),
                    }
                    continue;
                }
                if m.status != "pending" {
                    continue;
                }
                match upload_one(&config, &cloud, &mut m) {
                    Ok(()) => {
                        let meta: Value =
                            serde_json::from_slice(&fs::read(m.path.join("metadata.json"))?)?;
                        mark_record(
                            &shared,
                            &m.job,
                            if meta["complete"] == true {
                                "completed"
                            } else {
                                "failed"
                            },
                            m.samples,
                            meta["error"].as_str().map(str::to_owned),
                        );
                        eprintln!("文件上传确认完成: {}", m.job);
                    }
                    Err(e) => eprintln!("文件上传待重试，原件保留 [{}]: {e:#}", m.job),
                }
            }
            Ok(())
        })();
        if let Err(e) = result {
            eprintln!("补传队列检查失败: {e:#}");
        }
        sleep(&quit, Duration::from_secs(2));
    }
}

struct Consumer {
    config: Config,
    shared: Shared,
    recording: Option<Recording>,
    previous: Option<u16>,
    count: u64,
    rate: u32,
    session: String,
    last_data: Instant,
    stop_after_record: bool,
    record_ended: bool,
}
impl Consumer {
    fn close(&mut self, error: Option<&str>) -> Result<()> {
        if let Some(r) = self.recording.take() {
            let job = r.manifest.job.clone();
            let count = r.count;
            mark_record(
                &self.shared,
                &job,
                if count > 0 { "uploading" } else { "failed" },
                count,
                error.map(str::to_owned),
            );
            r.close(error)?;
            self.record_ended = true;
        }
        Ok(())
    }
    fn consume(&mut self, frame: &[u8], events: &VecDeque<Value>) -> Result<()> {
        let (sequence, rows) = protocol::samples(frame)?;
        protocol::check_sequence(self.previous, sequence)?;
        self.previous = Some(sequence);
        self.last_data = Instant::now();
        let command = {
            let mut s = self.shared.lock().unwrap();
            s.sequence = sequence;
            s.window.push(&rows, self.rate);
            s.control.get("recording").cloned().unwrap_or(Value::Null)
        };
        self.control_record(&command, events)?;
        if let Some(r) = self.recording.as_mut() {
            r.append(frame, sequence, &rows)?;
            mark_record(&self.shared, &r.manifest.job, "capturing", r.count, None);
            if r.due() {
                self.close(None)?;
            }
        }
        self.count += rows.len() as u64;
        Ok(())
    }
    fn control_record(&mut self, command: &Value, events: &VecDeque<Value>) -> Result<()> {
        if command["stop_requested"] == true {
            self.close(None)?;
            return Ok(());
        }
        let Some(id) = command["id"].as_str() else {
            return Ok(());
        };
        let seen = self.shared.lock().unwrap().last_record.as_deref() == Some(id);
        if !seen {
            ensure!(
                self.recording.is_none(),
                "云端在当前保存未结束时下发另一任务"
            );
            let r = Recording::new(
                &self.config,
                &self.session,
                self.rate,
                command,
                self.count,
                &events.iter().cloned().collect::<Vec<_>>(),
            )?;
            self.shared.lock().unwrap().last_record = Some(id.into());
            self.recording = Some(r);
        }
        Ok(())
    }
}

fn monitor(
    config: Config,
    cloud: Cloud,
    shared: Shared,
    stop: Arc<AtomicBool>,
    done: Arc<AtomicBool>,
    quit: Arc<AtomicBool>,
    id: String,
) {
    let mut sent = 0;
    let mut last_beat = Instant::now() - Duration::from_secs(2);
    while !done.load(Ordering::Relaxed) && !quit.load(Ordering::Relaxed) {
        // 控制与上传都在设备接收线程之外；HTTP超时不阻塞采集和心跳。
        if last_beat.elapsed() >= Duration::from_secs(1) {
            if let Err(e) = cloud.heartbeat(&heartbeat(&config, &shared)) {
                eprintln!("云端心跳失败: {e}");
            }
            last_beat = Instant::now();
        }
        match cloud.control() {
            Ok(control) => {
                let session = &control["session"];
                if session["id"] != id || session["stop_requested"] == true {
                    stop.store(true, Ordering::Relaxed);
                } else {
                    shared.lock().unwrap().control = session.clone();
                }
                if let Some(picker) = control.get("picker").filter(|p| p["status"] == "pending") {
                    if let Some(pid) = picker["id"].as_str().filter(|v| valid_id(v)) {
                        let _ = cloud.post(
                            &format!("/agents/{}/directory-result", cloud.id),
                            &json!({"id":pid,
                            "error":"无界面边端，请在页面直接填写树莓派绝对保存路径"}),
                        );
                    }
                }
            }
            Err(e) => eprintln!("云端控制暂不可达；继续本地采集，等待恢复: {e}"),
        }
        if let Err(e) = cloud.state(&id, &snapshot(&shared)) {
            eprintln!("状态上报失败: {e}");
        }
        let batch = {
            let s = shared.lock().unwrap();
            s.window
                .after(sent)
                .map(|(start, b)| (start, b, s.sequence))
        };
        if let Some((start, bytes, sequence)) = batch {
            match cloud.frames(&id, start, sequence, &bytes) {
                Ok(()) => sent = start + bytes.len() as u64 / 16,
                Err(e) => eprintln!("实时上传失败；窗口有界，完整保存文件仍保留: {e}"),
            }
        }
        sleep(&done, Duration::from_millis(250));
    }
    stop.store(true, Ordering::Relaxed);
}

fn session(
    config: &Config,
    cloud: &Cloud,
    shared: &Shared,
    quit: &Arc<AtomicBool>,
    control: Value,
    scheduled: bool,
) -> Result<()> {
    let id = control["id"].as_str().context("会话缺少 ID")?.to_owned();
    ensure!(valid_id(&id), "会话 ID 无效");
    let rate = u32::try_from(control["sample_rate"].as_u64().context("会话采样率无效")?)?;
    protocol::profile(rate)?;
    if control["samples_received"].as_u64().unwrap_or(0) > 0
        || matches!(
            control["status"].as_str(),
            Some("streaming" | "configuring" | "stopping")
        )
    {
        let error = "边端进程已重启，旧会话样本索引不能从零重用；请在云端新建会话";
        cloud.state(&id, &json!({"status":"failed","error":error}))?;
        if let Some(job) = control["recording"]["id"].as_str().filter(|v| valid_id(v)) {
            if !recording::manifest_path(config, job).exists() {
                cloud.post(
                    &format!("/jobs/{job}/progress?agent_id={}", cloud.id),
                    &json!({"stage":"failed","message":error}),
                )?;
            }
        }
        bail!(error);
    }
    {
        let mut s = shared.lock().unwrap();
        *s = State::default();
        s.session = Some(id.clone());
        s.control = control;
        s.status = "waiting_device".into();
    }
    let stop = Arc::new(AtomicBool::new(false));
    let done = Arc::new(AtomicBool::new(false));
    let worker = {
        let (c, a, s, t, d, q, i) = (
            config.clone(),
            cloud.clone(),
            shared.clone(),
            stop.clone(),
            done.clone(),
            quit.clone(),
            id.clone(),
        );
        thread::spawn(move || monitor(c, a, s, t, d, q, i))
    };
    let mut consumer = Consumer {
        config: config.clone(),
        shared: shared.clone(),
        recording: None,
        previous: None,
        count: 0,
        rate,
        session: id.clone(),
        last_data: Instant::now(),
        stop_after_record: scheduled && config.mode == Mode::Periodic,
        record_ended: false,
    };
    let result = (|| -> Result<()> {
        let Some(mut link) = Link::accept(config, &stop)? else {
            return Ok(());
        };
        update(shared, "configuring");
        let mut discard = |_: &[u8], _: &VecDeque<Value>| Ok(());
        link.exchange(0xba, &[], false, &mut discard)?;
        link.exchange(0xb8, &[], true, &mut discard)?;
        link.exchange(0xb2, &protocol::B2, true, &mut discard)?;
        link.exchange(0xb5, &protocol::profile(rate)?, true, &mut discard)?;
        if stop.load(Ordering::Relaxed) || quit.load(Ordering::Relaxed) {
            return Ok(());
        }
        let capture = (|| -> Result<()> {
            link.exchange(0xb7, &[0], true, &mut |f, e| consumer.consume(f, e))?;
            update(shared, "streaming");
            consumer.last_data = Instant::now();
            while !stop.load(Ordering::Relaxed) && !quit.load(Ordering::Relaxed) {
                let command = shared.lock().unwrap().control["recording"].clone();
                if command["stop_requested"] == true {
                    consumer.close(None)?;
                }
                if consumer.stop_after_record && consumer.record_ended {
                    break;
                }
                let frames = link.pump(&mut |f, e| consumer.consume(f, e))?;
                ensure!(
                    !frames.iter().any(|f| f[3] == 0xb8),
                    "设备应答了未请求的停止命令"
                );
                ensure!(
                    consumer.last_data.elapsed() < Duration::from_secs(config.data_timeout_seconds),
                    "设备采样数据超时"
                );
            }
            Ok(())
        })();
        update(shared, "stopping");
        // 即使采集/写盘失败也先尝试停止硬件；只在应答后发布正常终态。
        let stopped = link.exchange(0xb8, &[], true, &mut |f, e| consumer.consume(f, e));
        if capture.is_err() || stopped.is_err() {
            let _ = link.send(0xb8, &[]);
        }
        capture?;
        stopped?;
        ensure!(link.pending() == 0, "停止后仍有不完整设备帧");
        Ok(())
    })();
    let error = result.as_ref().err().map(|e| format!("{e:#}"));
    let close = consumer.close(error.as_deref());
    let error = error.or_else(|| close.err().map(|e| format!("保存收尾失败: {e:#}")));
    if let Some(message) = &error {
        let job = shared.lock().unwrap().control["recording"]["id"]
            .as_str()
            .map(str::to_owned);
        if let Some(job) = job.filter(|v| valid_id(v)) {
            let manifest = recording::manifest_path(config, &job);
            if !manifest.exists() {
                mark_record(shared, &job, "failed", 0, Some(message.clone()));
                let _=cloud.post(&format!("/jobs/{job}/progress?agent_id={}",cloud.id),
                    &json!({"stage":"failed","message":message.chars().take(500).collect::<String>()}));
            }
        }
    }
    {
        let mut s = shared.lock().unwrap();
        s.status = if error.is_some() { "failed" } else { "stopped" }.into();
        s.error = error.clone();
    }
    done.store(true, Ordering::Relaxed);
    let _ = worker.join();
    cloud
        .state(&id, &snapshot(shared))
        .unwrap_or_else(|e| eprintln!("会话终态未上报: {e}"));
    if let Some(error) = error {
        bail!(error);
    }
    Ok(())
}

fn sleep(quit: &AtomicBool, duration: Duration) {
    let until = Instant::now() + duration;
    while Instant::now() < until && !quit.load(Ordering::Relaxed) {
        thread::sleep(Duration::from_millis(50));
    }
}

pub fn run(config_path: &Path, key_override: Option<String>, quit: Arc<AtomicBool>) -> Result<()> {
    let initial = Config::load(config_path)?;
    fs::create_dir_all(&initial.storage)?;
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(initial.storage.join(".agent.lock"))?;
    lock.try_lock_exclusive()
        .context("保存目录已有另一个边端进程")?;
    recording::prepare(&initial)?;
    let key = key_override
        .or_else(|| std::env::var(&initial.api_key_env).ok())
        .context("没有设置密钥环境变量")?;
    let cloud = Cloud::new(&initial, key)?;
    let shared = Arc::new(Mutex::new(State::default()));
    let upload = {
        let (c, a, s, q) = (initial.clone(), cloud.clone(), shared.clone(), quit.clone());
        thread::spawn(move || uploader(c, a, s, q))
    };
    let mut next = Instant::now();
    let mut scheduled_once = false;
    while !quit.load(Ordering::Relaxed) {
        let result = (|| -> Result<()> {
            let config = Config::load(config_path)?;
            ensure!(
                config.cloud_url == initial.cloud_url
                    && config.agent_id == initial.agent_id
                    && config.storage == initial.storage
                    && config.api_key_env == initial.api_key_env,
                "云端地址、身份或存储目录变更后请重启服务"
            );
            cloud.heartbeat(&heartbeat(&config, &shared))?;
            let control = cloud.control()?;
            let mut current = control["session"].clone();
            let mut scheduled = false;
            if current.is_null()
                && config.mode != Mode::Cloud
                && Instant::now() >= next
                && (config.mode != Mode::Continuous || !scheduled_once)
            {
                current = cloud.post(
                    "/sessions",
                    &json!({"agent_id":config.agent_id,"sample_rate":config.sample_rate}),
                )?;
                let id = current["id"]
                    .as_str()
                    .filter(|id| valid_id(id))
                    .context("云端未返回有效会话ID")?;
                let duration = if config.mode == Mode::Continuous {
                    0
                } else {
                    config.duration_seconds.unwrap()
                };
                let record = match cloud.post(
                    &format!("/sessions/{id}/record"),
                    &json!({"duration":duration,"save_directory":config.storage}),
                ) {
                    Ok(record) => record,
                    Err(error) => {
                        let _ = cloud.post(&format!("/sessions/{id}/stop"), &json!({}));
                        let _ = cloud.state(
                            id,
                            &json!({"status":"failed","error":"创建保存任务失败，未启动设备"}),
                        );
                        return Err(error);
                    }
                };
                current["recording"] = json!({"id":record["id"],"duration":duration,"save_directory":config.storage,"stop_requested":false});
                scheduled = true;
                scheduled_once = true;
            }
            if !current.is_null() {
                session(&config, &cloud, &shared, &quit, current, scheduled)?;
                // 间隔定义为上一次会话结束后等待；不为追赶计划而重叠采集。
                next = Instant::now() + Duration::from_secs(config.interval_seconds.unwrap_or(1));
            }
            Ok(())
        })();
        if let Err(e) = result {
            eprintln!("边端任务失败，保留数据并等待重试: {e:#}");
        }
        sleep(&quit, Duration::from_secs(1));
    }
    let _ = upload.join();
    FileExt::unlock(&lock)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn window_stays_bounded_and_preserves_absolute_gap() {
        let mut w = Window::default();
        let rows = vec![[1, -1, 8388607, -8388608]; 254];
        for _ in 0..1000 {
            w.push(&rows, 10000);
        }
        let (start, b) = w.after(0).unwrap();
        assert!(start > 0);
        assert!(b.len() <= 20000 * 16 + 254 * 16);
        assert_eq!(start + b.len() as u64 / 16, w.end);
        assert_eq!(&b[..4], &1i32.to_le_bytes());
        assert!(w.after(w.end).is_none());
    }
}
