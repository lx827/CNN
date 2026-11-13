//! 输出 JSON 模型与管线参数常量——共享契约的 Rust 侧表达。
//!
//! JSON 字段名与 `scripts/edge_diag_reference.py` 的输出严格一致
//! （对比脚本 `edge_diag_compare.py` 按字段名逐项比较）；本模块不触
//! FFI，可在无 libcnn_compute.so 的环境单独编译与测试。

use serde::Serialize;

/// 管线参数唯一事实源（与 `scripts/edge_diag_reference.py` 保持一致；
/// 默认值取自 cnn_compute Python 包，与 C ABI 同一 C++ 内核）。
pub mod params {
    /// Butterworth 带通阶数。
    pub const FILTER_ORDER: i32 = 4;
    /// 带通下限 Hz（cnn_butterworth 的 low）。
    pub const BAND_LOW_HZ: f64 = 500.0;
    /// 带通上限 Hz（cnn_butterworth 的 high）。
    pub const BAND_HIGH_HZ: f64 = 3000.0;
    /// sosfiltfilt 延拓长度；-1 为库内 SciPy SOS 默认规则
    /// （cnn_compute.filtering.sosfiltfilt 默认 padlen）。
    pub const FILTFILT_PADLEN: i32 = -1;
    /// cnn_statistics 分母下限保护
    /// （cnn_compute.numeric.statistics 默认 margin_floor）。
    pub const STATS_MARGIN_FLOOR: f64 = 1e-12;
    /// 转频搜索下限 Hz。
    pub const SPEED_LOW_HZ: f64 = 10.0;
    /// 转频搜索上限 Hz。
    pub const SPEED_HIGH_HZ: f64 = 100.0;
    /// 谐波数（cnn_compute.rotation.spectrum_speed 默认 harmonics）。
    pub const SPEED_HARMONICS: i32 = 5;
    /// 仲裁带宽 Hz（cnn_compute.rotation.spectrum_speed 默认 bandwidth）。
    pub const SPEED_BANDWIDTH: f64 = 3.0;
    /// 频谱平滑 Hz（cnn_compute.rotation.spectrum_speed 默认 smoothing）。
    pub const SPEED_SMOOTHING: f64 = 1.5;
    /// 谱峭度滤波器组最大分解层
    /// （cnn_compute.diagnostic.filter_bank_kurtogram 默认 max_level）。
    pub const KURTOGRAM_MAX_LEVEL: i32 = 4;
    /// 谱峭度滤波器组最低频带边限 Hz（同上默认 min_frequency）。
    pub const KURTOGRAM_MIN_FREQUENCY: f64 = 100.0;
    /// 谱峭度滤波器组 Butterworth 阶数（同上默认 filter_order）。
    pub const KURTOGRAM_FILTER_ORDER: i32 = 4;
    /// VMD 输入截断点数上限（契约显式：原始信号前 min(n,51200) 点，
    /// 与 cnn_vmd 默认 max_samples 同值）。
    pub const VMD_MAX_SAMPLES: usize = 51200;
    /// 等角重采样每转点数（契约固定 samples_per_revolution=1024）。
    pub const ORDER_SAMPLES_PER_REVOLUTION: i32 = 1024;
    /// 阶次谱保留的最大阶次（含，即幅值谱 bins 0..=50）。
    pub const ORDER_MAX_ORDER: usize = 50;
    /// TSA 最少完整转数（cnn_compute.rotation.tsa 默认 minimum_revolutions）。
    pub const TSA_MINIMUM_REVOLUTIONS: i32 = 4;
}

/// 输入描述块。
#[derive(Serialize)]
pub struct InputInfo {
    pub file: String,
    pub fs: u32,
    pub n: usize,
}

/// 时域统计五指标（全部取自 cnn_statistics 的 statistics 字段）。
#[derive(Serialize)]
pub struct Metrics {
    pub rms: f64,
    pub peak: f64,
    pub crest: f64,
    pub kurtosis: f64,
    pub skewness: f64,
}

/// 每 stage 耗时（毫秒，std::time::Instant 计时）。
#[derive(Serialize)]
pub struct Timings {
    pub detrend: f64,
    pub stats: f64,
    pub filter: f64,
    pub spectrum: f64,
    pub envelope: f64,
    pub speed: f64,
    pub wavelet: f64,
    pub cepstrum: f64,
    pub kurtogram: f64,
    pub vmd: f64,
    pub order: f64,
    pub tsa: f64,
}

/// 小波阈值去噪摘要：残差 = 原始 − 去噪，两侧 RMS 均经 cnn_statistics。
#[derive(Serialize)]
pub struct WaveletInfo {
    pub residual_rms: f64,
    pub denoised_rms: f64,
}

/// 谱峭度选带摘要：bands 矩阵中谱峭度最大行的 low/high 与该行谱峭度。
#[derive(Serialize)]
pub struct KurtogramInfo {
    pub best_low_hz: f64,
    pub best_high_hz: f64,
    pub max_kurtosis: f64,
}

/// VMD 分解摘要：各模态能量占 K 个模态总能量之比与实际输入点数。
#[derive(Serialize)]
pub struct VmdInfo {
    pub mode_energy_ratio: Vec<f64>,
    pub n_input: usize,
}

/// 顶层输出报告。
///
/// `speed_hz` 仲裁不可判定（reason 非空）或频率非有限时为 null，
/// 与参照脚本同规则；此时 `order_spectrum`/`tsa` 同为 null 且带
/// `order_skip_reason`（其余情况无该键）。`peak_rss_kb` 非 Linux 平台为 null。
#[derive(Serialize)]
pub struct OutputReport {
    pub input: InputInfo,
    pub metrics: Metrics,
    pub spectrum: Vec<f64>,
    pub envelope_spectrum: Vec<f64>,
    pub speed_hz: Option<f64>,
    pub wavelet: WaveletInfo,
    pub cepstrum: Vec<f64>,
    pub kurtogram: KurtogramInfo,
    pub vmd: VmdInfo,
    pub order_spectrum: Option<Vec<f64>>,
    pub tsa: Option<Vec<f64>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub order_skip_reason: Option<&'static str>,
    pub timings_ms: Timings,
    pub peak_rss_kb: Option<u64>,
}

#[cfg(test)]
mod tests {
    //! JSON 序列化结构测试：字段名与共享契约严格一致。本模块不触 FFI，
    //! 无 libcnn_compute.so 的环境可运行 `cargo test --lib`。

    use super::{InputInfo, KurtogramInfo, Metrics, OutputReport, Timings, VmdInfo, WaveletInfo};
    use serde_json::{json, Value};

    fn sample(speed_hz: Option<f64>, peak_rss_kb: Option<u64>) -> OutputReport {
        OutputReport {
            input: InputInfo {
                file: "synth_L50000_fs10000.f64".into(),
                fs: 10000,
                n: 50000,
            },
            metrics: Metrics {
                rms: 0.5,
                peak: 2.0,
                crest: 4.0,
                kurtosis: 3.0,
                skewness: 0.1,
            },
            spectrum: vec![0.0, 1.5],
            envelope_spectrum: vec![2.5],
            speed_hz,
            wavelet: WaveletInfo {
                residual_rms: 0.05,
                denoised_rms: 0.49,
            },
            cepstrum: vec![0.1, 0.2],
            kurtogram: KurtogramInfo {
                best_low_hz: 500.0,
                best_high_hz: 1000.0,
                max_kurtosis: 4.2,
            },
            vmd: VmdInfo {
                mode_energy_ratio: vec![0.6, 0.4],
                n_input: 50000,
            },
            order_spectrum: speed_hz.map(|_| vec![0.3, 0.1]),
            tsa: speed_hz.map(|_| vec![0.2, 0.2, 0.2]),
            order_skip_reason: if speed_hz.is_none() {
                Some("speed_null")
            } else {
                None
            },
            timings_ms: Timings {
                detrend: 1.0,
                stats: 2.0,
                filter: 3.0,
                spectrum: 4.0,
                envelope: 5.0,
                speed: 6.0,
                wavelet: 7.0,
                cepstrum: 8.0,
                kurtogram: 9.0,
                vmd: 10.0,
                order: 11.0,
                tsa: 12.0,
            },
            peak_rss_kb,
        }
    }

    /// serde_json 默认 Map 为 BTreeMap，按键名排序后与契约集合比较。
    fn keys(value: &Value) -> Vec<&str> {
        let mut names: Vec<&str> = value
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        names.sort_unstable();
        names
    }

    #[test]
    fn 顶层与嵌套字段名与共享契约一致() {
        let value = serde_json::to_value(sample(Some(25.0), Some(12345))).unwrap();
        assert_eq!(
            keys(&value),
            vec![
                "cepstrum",
                "envelope_spectrum",
                "input",
                "kurtogram",
                "metrics",
                "order_spectrum",
                "peak_rss_kb",
                "spectrum",
                "speed_hz",
                "timings_ms",
                "tsa",
                "vmd",
                "wavelet",
            ]
        );
        assert_eq!(keys(&value["input"]), vec!["file", "fs", "n"]);
        assert_eq!(
            keys(&value["metrics"]),
            vec!["crest", "kurtosis", "peak", "rms", "skewness"]
        );
        assert_eq!(
            keys(&value["wavelet"]),
            vec!["denoised_rms", "residual_rms"]
        );
        assert_eq!(
            keys(&value["kurtogram"]),
            vec!["best_high_hz", "best_low_hz", "max_kurtosis"]
        );
        assert_eq!(keys(&value["vmd"]), vec!["mode_energy_ratio", "n_input"]);
        assert_eq!(
            keys(&value["timings_ms"]),
            vec![
                "cepstrum",
                "detrend",
                "envelope",
                "filter",
                "kurtogram",
                "order",
                "spectrum",
                "speed",
                "stats",
                "tsa",
                "vmd",
                "wavelet",
            ]
        );
        assert_eq!(value["input"]["fs"], json!(10000));
        assert_eq!(value["input"]["n"], json!(50000));
        assert_eq!(value["speed_hz"], json!(25.0));
        assert_eq!(value["metrics"]["crest"], json!(4.0));
        assert_eq!(value["vmd"]["n_input"], json!(50000));
        assert!(value["spectrum"].is_array());
        assert!(value["cepstrum"].is_array());
        assert!(value["tsa"].is_array());
    }

    #[test]
    fn speed_hz_与_peak_rss_kb_为_none_时序列化为_null() {
        let value = serde_json::to_value(sample(None, None)).unwrap();
        assert!(value["speed_hz"].is_null());
        assert!(value["peak_rss_kb"].is_null());
    }

    #[test]
    fn speed_null_时阶次链置_null_且仅此时携带_order_skip_reason() {
        let skipped = serde_json::to_value(sample(None, None)).unwrap();
        assert!(skipped["order_spectrum"].is_null());
        assert!(skipped["tsa"].is_null());
        assert_eq!(skipped["order_skip_reason"], json!("speed_null"));

        let normal = serde_json::to_value(sample(Some(25.0), None)).unwrap();
        assert!(normal["order_spectrum"].is_array());
        assert!(normal["tsa"].is_array());
        assert!(normal.get("order_skip_reason").is_none());
    }
}
