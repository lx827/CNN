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
}

/// 顶层输出报告。
///
/// `speed_hz` 仲裁不可判定（reason 非空）或频率非有限时为 null，
/// 与参照脚本同规则；`peak_rss_kb` 非 Linux 平台为 null。
#[derive(Serialize)]
pub struct OutputReport {
    pub input: InputInfo,
    pub metrics: Metrics,
    pub spectrum: Vec<f64>,
    pub envelope_spectrum: Vec<f64>,
    pub speed_hz: Option<f64>,
    pub timings_ms: Timings,
    pub peak_rss_kb: Option<u64>,
}

#[cfg(test)]
mod tests {
    //! JSON 序列化结构测试：字段名与共享契约严格一致。本模块不触 FFI，
    //! 无 libcnn_compute.so 的环境可运行 `cargo test --lib`。

    use super::{InputInfo, Metrics, OutputReport, Timings};
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
            timings_ms: Timings {
                detrend: 1.0,
                stats: 2.0,
                filter: 3.0,
                spectrum: 4.0,
                envelope: 5.0,
                speed: 6.0,
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
                "envelope_spectrum",
                "input",
                "metrics",
                "peak_rss_kb",
                "spectrum",
                "speed_hz",
                "timings_ms",
            ]
        );
        assert_eq!(keys(&value["input"]), vec!["file", "fs", "n"]);
        assert_eq!(
            keys(&value["metrics"]),
            vec!["crest", "kurtosis", "peak", "rms", "skewness"]
        );
        assert_eq!(
            keys(&value["timings_ms"]),
            vec!["detrend", "envelope", "filter", "spectrum", "speed", "stats"]
        );
        assert_eq!(value["input"]["fs"], json!(10000));
        assert_eq!(value["input"]["n"], json!(50000));
        assert_eq!(value["speed_hz"], json!(25.0));
        assert_eq!(value["metrics"]["crest"], json!(4.0));
        assert!(value["spectrum"].is_array());
    }

    #[test]
    fn speed_hz_与_peak_rss_kb_为_none_时序列化为_null() {
        let value = serde_json::to_value(sample(None, None)).unwrap();
        assert!(value["speed_hz"].is_null());
        assert!(value["peak_rss_kb"].is_null());
    }
}
