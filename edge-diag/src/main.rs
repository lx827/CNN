//! edge-diag CLI：单通道 .f64 信号 → 无参数表示层指标 JSON。
//!
//! 全部数值算法经 libcnn_compute 的 C ABI 完成；Rust 侧只做文件 IO、
//! 调用编排、计时与 JSON 序列化，不实现任何数学。

mod ffi;

use anyhow::{anyhow, bail, ensure, Context, Result};
use edge_diag::{
    params, InputInfo, KurtogramInfo, Metrics, OutputReport, Timings, VmdInfo, WaveletInfo,
};
use std::time::Instant;

/// 每 stage 计时（毫秒），写入共享契约的 timings_ms。
fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1e3
}

fn main() -> Result<()> {
    let cli = parse_args()?;
    let fs_hz = f64::from(cli.fs);

    let bytes = std::fs::read(&cli.input).with_context(|| format!("读取输入文件 {}", cli.input))?;
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

    // 7. 小波阈值去噪：参数全默认（NULL→db8/symmetric/soft，level 0=最大层数，
    //    scale 1.0）；残差=原始−去噪（逐点相减为边界运算），RMS 复用 cnn_statistics
    let stage = Instant::now();
    let denoised = ffi::wavelet_denoise(&signal)?;
    let denoised = denoised.f64s("values")?;
    let residual: Vec<f64> = signal
        .iter()
        .zip(denoised)
        .map(|(raw, clean)| raw - clean)
        .collect();
    let residual_rms =
        ffi::statistics(&residual, params::STATS_MARGIN_FLOOR)?.f64s("statistics")?[1];
    let denoised_rms =
        ffi::statistics(denoised, params::STATS_MARGIN_FLOOR)?.f64s("statistics")?[1];
    let wavelet_ms = elapsed_ms(stage);

    // 8. 实倒谱：numeric 族入口，数组原样输出
    let stage = Instant::now();
    let cepstrum = ffi::cepstrum(&signal)?;
    let cepstrum = cepstrum.f64s("values")?.to_vec();
    let cepstrum_ms = elapsed_ms(stage);

    // 9. 谱峭度选带：bands 每行 low,high,level,sk,impulsiveness,s2b，
    //    取谱峭度（列 3）最大行为 best（行选取为边界运算）
    let stage = Instant::now();
    let kurtogram_result = ffi::filter_bank_kurtogram(
        &signal,
        fs_hz,
        params::KURTOGRAM_MAX_LEVEL,
        params::KURTOGRAM_MIN_FREQUENCY,
        params::KURTOGRAM_FILTER_ORDER,
    )?;
    let bands = kurtogram_result.f64s("bands")?;
    let best = bands
        .chunks_exact(6)
        .max_by(|a, b| a[3].total_cmp(&b[3]))
        .ok_or_else(|| anyhow!("cnn_filter_bank_kurtogram 未返回任何频带"))?;
    let kurtogram = KurtogramInfo {
        best_low_hz: best[0],
        best_high_hz: best[1],
        max_kurtosis: best[3],
    };
    let kurtogram_ms = elapsed_ms(stage);

    // 10. VMD：契约显式输入截断（前 min(n,51200) 点），options=NULL 全默认；
    //     各模态能量占 K 个模态总能量之比（平方和归一，边界归约）
    let stage = Instant::now();
    let n_vmd = signal.len().min(params::VMD_MAX_SAMPLES);
    let vmd_result = ffi::vmd(&signal[..n_vmd], fs_hz)?;
    let (mode_count, mode_length) = vmd_result.rows_columns("modes")?;
    let modes = vmd_result.f64s("modes")?;
    let mut energies = Vec::with_capacity(mode_count);
    for row in 0..mode_count {
        let mode = &modes[row * mode_length..(row + 1) * mode_length];
        energies.push(mode.iter().map(|value| value * value).sum::<f64>());
    }
    let total_energy: f64 = energies.iter().sum();
    let vmd_info = VmdInfo {
        mode_energy_ratio: energies
            .iter()
            .map(|energy| energy / total_energy)
            .collect(),
        n_input: n_vmd,
    };
    let vmd_ms = elapsed_ms(stage);

    // 11. 阶次谱：连续相位用 cnn_integrate（云端 order 管线同源，梯形积分，
    //     单位转）；恒速输入下与线性相位 2π·f·t 严格等价，无降级。
    //     speed_hz 为 null 时本 stage 与 tsa 均为 null
    let stage = Instant::now();
    let (order_spectrum, resampled, order_skip_reason) = match speed_hz {
        None => (None, None, Some("speed_null")),
        Some(speed) => {
            let time: Vec<f64> = (0..signal.len())
                .map(|index| index as f64 / fs_hz)
                .collect();
            let speed_samples = vec![speed; signal.len()];
            let phase = ffi::integrate(&time, &speed_samples)?;
            let resampled = ffi::angle_resample(
                &signal,
                phase.f64s("values")?,
                params::ORDER_SAMPLES_PER_REVOLUTION,
            )?;
            let resampled = resampled.f64s("values")?.to_vec();
            let amplitude = ffi::amplitude_spectrum(&resampled, true)?;
            let spectrum = amplitude.f64s("values")?;
            // 云端 compute_order_spectrum 同公式：resolution = spr/重采样长度
            // （f64 除法），retained = min(谱长, floor(50.0/resolution+1e-9)+1)，
            // 输出前 retained 个值（floor 为 f64 语义）
            let resolution =
                f64::from(params::ORDER_SAMPLES_PER_REVOLUTION) / resampled.len() as f64;
            let retained = ((params::ORDER_MAX_ORDER / resolution + 1e-9).floor() as usize + 1)
                .min(spectrum.len());
            let order_spectrum = spectrum[..retained].to_vec();
            (Some(order_spectrum), Some(resampled), None)
        }
    };
    let order_ms = elapsed_ms(stage);

    // 12. TSA：纯转平均入口 cnn_tsa，作用于阶次重采样后信号，取单圈平均 cycle
    let stage = Instant::now();
    let tsa = match &resampled {
        Some(resampled) => Some(
            ffi::tsa(
                resampled,
                params::ORDER_SAMPLES_PER_REVOLUTION,
                params::TSA_MINIMUM_REVOLUTIONS,
            )?
            .f64s("cycle")?
            .to_vec(),
        ),
        None => None,
    };
    let tsa_ms = elapsed_ms(stage);

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
        wavelet: WaveletInfo {
            residual_rms,
            denoised_rms,
        },
        cepstrum,
        kurtogram,
        vmd: vmd_info,
        order_spectrum,
        tsa,
        order_skip_reason,
        timings_ms: Timings {
            detrend: detrend_ms,
            stats: stats_ms,
            filter: filter_ms,
            spectrum: spectrum_ms,
            envelope: envelope_ms,
            speed: speed_ms,
            wavelet: wavelet_ms,
            cepstrum: cepstrum_ms,
            kurtogram: kurtogram_ms,
            vmd: vmd_ms,
            order: order_ms,
            tsa: tsa_ms,
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
                fs = Some(
                    value
                        .parse()
                        .with_context(|| format!("解析 --fs 的值 {value}"))?,
                )
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
