//! edge-diag CLI：单通道 .f64 信号 → 无参数表示层指标 JSON。
//!
//! 全部数值算法经 libcnn_compute 的 C ABI 完成；Rust 侧只做文件 IO、
//! 调用编排、计时与 JSON 序列化，不实现任何数学。

mod ffi;

use anyhow::{anyhow, bail, ensure, Context, Result};
use edge_diag::{params, InputInfo, Metrics, OutputReport, Timings};
use std::time::Instant;

/// 每 stage 计时（毫秒），写入共享契约的 timings_ms。
fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1e3
}

fn main() -> Result<()> {
    let cli = parse_args()?;
    let fs_hz = f64::from(cli.fs);

    let bytes =
        std::fs::read(&cli.input).with_context(|| format!("读取输入文件 {}", cli.input))?;
    ensure!(
        bytes.len() % 8 == 0,
        "输入 {} 长度 {} 字节，不是 float64（8 字节小端）的整数倍",
        cli.input,
        bytes.len()
    );
    let signal: Vec<f64> = bytes
        .chunks_exact(8)
        .map(|chunk| f64::from_le_bytes(chunk.try_into().expect("chunks_exact(8) 恒为 8 字节")))
        .collect();

    // 1. 线性去趋势（统计与谱的输入）
    let stage = Instant::now();
    let detrended = ffi::detrend(&signal, true)?;
    let detrended = detrended.f64s("values")?;
    let detrend_ms = elapsed_ms(stage);

    // 2. 时域统计：字段序 peak,rms,kurtosis,skewness,margin,shape,impulse,crest
    let stage = Instant::now();
    let statistics = ffi::statistics(detrended, params::STATS_MARGIN_FLOOR)?;
    let statistics = statistics.f64s("statistics")?;
    ensure!(
        statistics.len() == 8,
        "cnn_statistics 返回 {} 项统计量，预期 8 项",
        statistics.len()
    );
    let metrics = Metrics {
        rms: statistics[1],
        peak: statistics[0],
        crest: statistics[7],
        kurtosis: statistics[2],
        skewness: statistics[3],
    };
    let stats_ms = elapsed_ms(stage);

    // 3. Butterworth 带通（SOS 零相位）；契约未标中间信号，作用于原始输入，
    //    与 scripts/edge_diag_reference.py 一致
    let stage = Instant::now();
    let design = ffi::butterworth(
        params::FILTER_ORDER,
        params::BAND_LOW_HZ,
        params::BAND_HIGH_HZ,
        fs_hz,
    )?;
    let sos = design.f64s("sos")?;
    let bandpassed = ffi::sosfiltfilt(&signal, sos, params::FILTFILT_PADLEN)?;
    let bandpassed = bandpassed.f64s("values")?;
    let filter_ms = elapsed_ms(stage);

    // 4. 谱：去趋势后信号 rfft 幅度谱
    let stage = Instant::now();
    let spectrum = ffi::rfft(detrended)?.complex_magnitude("values")?;
    let spectrum_ms = elapsed_ms(stage);

    // 5. 包络谱：带通信号 Hilbert 取模（核内）→ rfft 幅度谱
    let stage = Instant::now();
    let envelope = ffi::hilbert_envelope(bandpassed)?;
    let envelope_spectrum = ffi::rfft(envelope.f64s("values")?)?.complex_magnitude("values")?;
    let envelope_ms = elapsed_ms(stage);

    // 6. 转速：原始输入；reason 非空或频率非有限 → null（与参照脚本同规则）
    let stage = Instant::now();
    let speed = ffi::spectrum_speed(
        &signal,
        fs_hz,
        params::SPEED_LOW_HZ,
        params::SPEED_HIGH_HZ,
        params::SPEED_HARMONICS,
        params::SPEED_BANDWIDTH,
        params::SPEED_SMOOTHING,
    )?;
    let reason = speed.text("reason")?;
    let frequency = speed.f64s("frequency")?[0];
    let speed_hz = (reason.is_empty() && frequency.is_finite()).then_some(frequency);
    let speed_ms = elapsed_ms(stage);

    let report = OutputReport {
        input: InputInfo {
            file: cli.input.clone(),
            fs: cli.fs,
            n: signal.len(),
        },
        metrics,
        spectrum,
        envelope_spectrum,
        speed_hz,
        timings_ms: Timings {
            detrend: detrend_ms,
            stats: stats_ms,
            filter: filter_ms,
            spectrum: spectrum_ms,
            envelope: envelope_ms,
            speed: speed_ms,
        },
        peak_rss_kb: peak_rss_kb(),
    };
    let json = serde_json::to_string(&report)?;
    std::fs::write(&cli.out, json).with_context(|| format!("写出 {}", cli.out))?;
    Ok(())
}

struct Cli {
    input: String,
    fs: u32,
    out: String,
}

/// `edge-diag --input xxx.f64 --fs 10000 --out result.json`，std 手解析。
fn parse_args() -> Result<Cli> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut input: Option<String> = None;
    let mut fs: Option<u32> = None;
    let mut out: Option<String> = None;
    let mut index = 0;
    while index < args.len() {
        let value = args
            .get(index + 1)
            .cloned()
            .ok_or_else(|| anyhow!("参数 {} 缺少取值", args[index]))?;
        match args[index].as_str() {
            "--input" => input = Some(value),
            "--fs" => {
                fs = Some(value.parse().with_context(|| format!("解析 --fs 的值 {value}"))?)
            }
            "--out" => out = Some(value),
            other => bail!(
                "未知参数 {other}；用法: edge-diag --input <file.f64> --fs <Hz> --out <result.json>"
            ),
        }
        index += 2;
    }
    Ok(Cli {
        input: input.ok_or_else(|| anyhow!("缺少 --input"))?,
        fs: fs.ok_or_else(|| anyhow!("缺少 --fs"))?,
        out: out.ok_or_else(|| anyhow!("缺少 --out"))?,
    })
}

/// 结束时读 /proc/self/status 的 VmHWM（kB）；非 Linux 平台按契约输出 null。
#[cfg(target_os = "linux")]
fn peak_rss_kb() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|line| line.starts_with("VmHWM:"))?;
    line.split_whitespace().nth(1)?.parse().ok()
}

#[cfg(not(target_os = "linux"))]
fn peak_rss_kb() -> Option<u64> {
    None
}
