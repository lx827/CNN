use crate::{
    config::{valid_id, Config},
    protocol,
};
use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{BufWriter, Write},
    path::{Path, PathBuf},
};

pub const FILES: [&str; 5] = [
    "samples.csv",
    "metadata.json",
    "rx_stream.bin",
    "commands.jsonl",
    "counts.i32",
];

#[derive(Clone, Deserialize, Serialize)]
pub struct Manifest {
    pub job: String,
    pub session: String,
    pub agent: String,
    pub path: PathBuf,
    pub status: String,
    pub samples: u64,
}

pub fn atomic_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let temp = path.with_extension("json.part");
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temp)?;
    serde_json::to_writer_pretty(&mut file, value)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    fs::rename(&temp, path)?;
    Ok(())
}

pub fn manifest_path(config: &Config, job: &str) -> PathBuf {
    config.storage.join(".uploads").join(format!("{job}.json"))
}

pub fn free_space(path: &Path, reserve: u64, extra: u64) -> Result<()> {
    ensure!(
        fs2::available_space(path)? >= reserve.saturating_add(extra),
        "磁盘剩余空间不足；停止保存，保留已有文件"
    );
    Ok(())
}

pub struct Recording {
    pub manifest: Manifest,
    pub count: u64,
    pub duration: u64,
    rate: u32,
    frames: u64,
    first: Option<u16>,
    last: Option<u16>,
    config: Config,
    csv: BufWriter<File>,
    raw: BufWriter<File>,
    binary: BufWriter<File>,
    meta: Value,
}

fn create(path: &Path) -> Result<BufWriter<File>> {
    Ok(BufWriter::with_capacity(
        65536,
        OpenOptions::new().write(true).create_new(true).open(path)?,
    ))
}

impl Recording {
    pub fn new(
        config: &Config,
        session: &str,
        rate: u32,
        command: &Value,
        start: u64,
        events: &[Value],
    ) -> Result<Self> {
        let job = command["id"].as_str().context("缺少保存任务 ID")?;
        ensure!(valid_id(job) && valid_id(session), "云端任务或会话 ID 无效");
        let duration = command["duration"]
            .as_u64()
            .context("保存时长必须为非负整数")?;
        let root = PathBuf::from(command["save_directory"].as_str().context("缺少保存目录")?);
        ensure!(root.is_absolute(), "保存目录必须是树莓派上的绝对路径");
        ensure!(
            !manifest_path(config, job).exists(),
            "任务已在本地执行；拒绝覆盖"
        );
        fs::create_dir_all(&root)?;
        free_space(&root, config.min_free_bytes, 1024 * 1024)?;
        let path = root.join(job);
        fs::create_dir(&path).context("保存目录已存在或无法创建；不覆盖数据")?;
        let manifest = Manifest {
            job: job.into(),
            session: session.into(),
            agent: config.agent_id.clone(),
            path: path.clone(),
            status: "recording".into(),
            samples: 0,
        };
        atomic_json(&manifest_path(config, job), &manifest)?;
        let mut csv = create(&path.join("samples.csv"))?;
        csv.write_all(b"sample_index,time_s,ch0_counts,ch1_counts,ch2_counts,ch3_counts\n")?;
        let raw = create(&path.join("rx_stream.bin"))?;
        let binary = create(&path.join("counts.i32"))?;
        let mut log = create(&path.join("commands.jsonl"))?;
        for event in events {
            serde_json::to_writer(&mut log, event)?;
            log.write_all(b"\n")?;
        }
        log.flush()?;
        log.get_ref().sync_all()?;
        let meta = json!({"source":"dc24_tcp","session_id":session,"device_ip":config.device_ip.to_string(),
            "host_ip":config.listen_ip.to_string(),"host_tcp_port":config.port,"sample_rate_hz":rate,
            "requested_duration_s":duration,"value_unit":"signed_24_bit_ADC_counts",
            "physical_scaling":"NOT VERIFIED; no voltage/acceleration conversion applied",
            "channel_tags":[0,1,2,3],"b5_payload_hex":protocol::hex(&protocol::profile(rate)?),
            "b2_payload_hex":protocol::hex(&protocol::B2),"input_configuration":protocol::input_configuration(),
            "session_sample_start":start,"saved_directory":path,"complete":false,"transport":"rust_tcp",
            "time_axis":"relative sample index / sample_rate_hz; not device UTC time",
            "sequence_gaps":[],"implementation":"dc24-edge-rust-0.1.0"});
        atomic_json(&path.join("metadata.json"), &meta)?;
        Ok(Self {
            manifest,
            count: 0,
            duration,
            rate,
            frames: 0,
            first: None,
            last: None,
            config: config.clone(),
            csv,
            raw,
            binary,
            meta,
        })
    }
    pub fn append(&mut self, frame: &[u8], sequence: u16, values: &[[i32; 4]]) -> Result<()> {
        // 在写入前预留一整帧的二进制和 CSV 空间；绝不自动删旧数据。
        free_space(
            &self.manifest.path,
            self.config.min_free_bytes,
            (values.len() * 192 + frame.len()) as u64,
        )?;
        self.raw.write_all(frame)?;
        for (i, row) in values.iter().enumerate() {
            for value in row {
                self.binary.write_all(&value.to_le_bytes())?;
            }
            let index = self.count + i as u64;
            writeln!(
                self.csv,
                "{index},{:.9},{},{},{},{}",
                index as f64 / self.rate as f64,
                row[0],
                row[1],
                row[2],
                row[3]
            )?;
        }
        self.first.get_or_insert(sequence);
        self.last = Some(sequence);
        self.count += values.len() as u64;
        self.frames += 1;
        Ok(())
    }
    pub fn due(&self) -> bool {
        self.duration > 0 && self.count >= self.duration.saturating_mul(self.rate as u64)
    }
    pub fn close(mut self, error: Option<&str>) -> Result<Manifest> {
        for writer in [&mut self.csv, &mut self.raw, &mut self.binary] {
            writer.flush()?;
            writer.get_ref().sync_all()?;
        }
        self.meta["samples_per_channel"] = json!(self.count);
        self.meta["data_frames"] = json!(self.frames);
        self.meta["recorded_sample_duration_s"] = json!(self.count as f64 / self.rate as f64);
        self.meta["first_device_sequence"] = json!(self.first);
        self.meta["last_device_sequence"] = json!(self.last);
        self.meta["complete"] = json!(error.is_none() && self.count > 0);
        self.meta["error"] = json!(error);
        self.meta["end_reason"] = json!(if error.is_some() {
            "error"
        } else {
            "operator_or_requested_duration"
        });
        self.meta["unparsed_tail_bytes"] = json!(0);
        atomic_json(&self.manifest.path.join("metadata.json"), &self.meta)?;
        self.manifest.samples = self.count;
        self.manifest.status = if self.count > 0 {
            "pending"
        } else {
            "interrupted"
        }
        .into();
        atomic_json(
            &manifest_path(&self.config, &self.manifest.job),
            &self.manifest,
        )?;
        Ok(self.manifest)
    }
}

pub fn prepare(config: &Config) -> Result<()> {
    fs::create_dir_all(config.storage.join(".uploads"))?;
    for entry in fs::read_dir(config.storage.join(".uploads"))? {
        let path = entry?.path();
        if path.extension().is_none_or(|e| e != "json") {
            continue;
        }
        let mut m: Manifest = serde_json::from_slice(&fs::read(&path)?)?;
        if m.status == "recording" {
            // 崩溃时不能声称最后一帧/CSV已经完整落盘，保留原件供复核。
            m.status = "interrupted".into();
            atomic_json(&path, &m)?;
            eprintln!("上次进程中断，保留未完成记录，不冒充完整数据: {}", m.job);
        }
    }
    Ok(())
}
