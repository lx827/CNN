//! libcnn_compute 的 C ABI 手写绑定；唯一事实源 `capi/include/cnn_compute.h`。
//!
//! 内存契约（头文件 L23-32）：cnn_result 由库分配，本模块 OwnedResult 在
//! Drop 调 cnn_result_free；field.data 借用到 cnn_result_free；复数输出为
//! 交错 double；函数出错返回 NULL，error.message 为 NUL 结尾文本。

// 结构与枚举按头文件完整照抄，未读的成员/变体保留以忠实呈现 ABI。
#![allow(dead_code)]

use anyhow::{anyhow, Context, Result};
use std::ffi::{c_char, c_int, c_void, CString};

/// cnn_error.message 字节数（头文件 char message[512]）。
const MESSAGE_BYTES: usize = 512;

/// 头文件 L49-56 cnn_error_code。
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub enum CnnErrorCode {
    None = 0,
    Argument = 1,
    Domain = 2,
    Range = 3,
    Memory = 4,
    Computation = 5,
}

/// 头文件 L61-68 cnn_field_type。
#[repr(C)]
#[derive(Clone, Copy)]
pub enum CnnFieldType {
    F64 = 0,
    I32 = 1,
    Size = 2,
    U8 = 3,
    Complex = 4,
    Text = 5,
}

/// 头文件 L33-36 cnn_span：只读借用输入。
#[repr(C)]
pub struct CnnSpan {
    pub data: *const f64,
    pub size: usize,
}

/// 头文件 L69-74 cnn_field：name/data 借用到 cnn_result_free。
#[repr(C)]
#[derive(Clone, Copy)]
pub struct CnnField {
    pub name: *const c_char,
    pub field_type: CnnFieldType,
    pub data: *const c_void,
    pub rows: usize,
    pub columns: usize,
}

/// 头文件 L57-60 cnn_error。
#[repr(C)]
pub struct CnnError {
    pub code: CnnErrorCode,
    pub message: [u8; MESSAGE_BYTES],
}

/// 头文件 L48 cnn_result：不透明对象，仅经库函数访问。
#[repr(C)]
pub struct CnnResult {
    _private: [u8; 0],
}

/// 头文件 L245-252 cnn_vmd_options（cnn_vmd 的 NULL 即取 cnn_vmd_defaults）。
#[repr(C)]
#[derive(Clone, Copy)]
pub struct CnnVmdOptions {
    pub modes: c_int,
    pub alpha: f64,
    pub tau: f64,
    pub tolerance: f64,
    pub max_iterations: c_int,
    pub dc: c_int,
    pub max_samples: usize,
    pub initialization: c_int,
    pub seed: u64,
}

extern "C" {
    // 结果生命周期与字段访问（L81、L85）
    fn cnn_result_free(result: *mut CnnResult);
    fn cnn_result_find(
        result: *const CnnResult,
        name: *const c_char,
        field: *mut CnnField,
    ) -> c_int;
    // 管线原语（L93、L107、L108、L117、L145、L146、L321）
    fn cnn_rfft(x: CnnSpan, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_butterworth(
        order: c_int,
        low: f64,
        high: f64,
        fs: f64,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_sosfiltfilt(
        x: CnnSpan,
        sos: CnnSpan,
        padlen: c_int,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_detrend(x: CnnSpan, linear: c_int, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_hilbert_envelope(x: CnnSpan, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_statistics(x: CnnSpan, margin_floor: f64, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_spectrum_speed(
        x: CnnSpan,
        fs: f64,
        low: f64,
        high: f64,
        harmonics: c_int,
        bandwidth: f64,
        smoothing: f64,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    // 二期管线原语（L144、L244、L256、L294、L299、L301、L302、L305）
    fn cnn_cepstrum(x: CnnSpan, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_wavelet_denoise(
        x: CnnSpan,
        wavelet: *const c_char,
        mode: *const c_char,
        level: c_int,
        threshold: *const c_char,
        scale: f64,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_filter_bank_kurtogram(
        x: CnnSpan,
        fs: f64,
        max_level: c_int,
        minimum_frequency: f64,
        order: c_int,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_vmd(
        x: CnnSpan,
        fs: f64,
        options: *const CnnVmdOptions,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_integrate(time: CnnSpan, speed: CnnSpan, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_angle_resample(
        x: CnnSpan,
        phase: CnnSpan,
        samples_per_revolution: c_int,
        error: *mut CnnError,
    ) -> *mut CnnResult;
    fn cnn_amplitude_spectrum(x: CnnSpan, center: c_int, error: *mut CnnError) -> *mut CnnResult;
    fn cnn_tsa(
        x: CnnSpan,
        samples_per_revolution: c_int,
        minimum_revolutions: c_int,
        error: *mut CnnError,
    ) -> *mut CnnResult;
}

fn span(samples: &[f64]) -> CnnSpan {
    CnnSpan {
        data: samples.as_ptr(),
        size: samples.len(),
    }
}

fn fresh_error() -> CnnError {
    CnnError {
        code: CnnErrorCode::None,
        message: [0; MESSAGE_BYTES],
    }
}

fn message(error: &CnnError) -> String {
    let end = error
        .message
        .iter()
        .position(|&byte| byte == 0)
        .unwrap_or(MESSAGE_BYTES);
    String::from_utf8_lossy(&error.message[..end]).into_owned()
}

/// 统一出口：NULL 返回值转 anyhow 错误（携带 cnn_error 文本，头文件 L30）。
fn call(what: &str, result: *mut CnnResult, error: &CnnError) -> Result<OwnedResult> {
    if result.is_null() {
        return Err(anyhow!("{what} 失败: {}", message(error)));
    }
    Ok(OwnedResult(result))
}

/// 拥有 cnn_result 的句柄；字段数据借用至 Drop。
pub struct OwnedResult(*mut CnnResult);

impl OwnedResult {
    /// 按名取字段；find 返回 0 表示无该名称（头文件 L83-85）。
    fn field(&self, name: &str) -> Option<CnnField> {
        let cname = CString::new(name).expect("字段名为内部字面量，不含 NUL");
        let mut field = CnnField {
            name: std::ptr::null(),
            field_type: CnnFieldType::F64,
            data: std::ptr::null(),
            rows: 0,
            columns: 0,
        };
        let found = unsafe { cnn_result_find(self.0, cname.as_ptr(), &mut field) };
        (found != 0).then_some(field)
    }

    /// CNN_F64 字段：行优先数组，长度 rows*columns。
    pub fn f64s(&self, name: &str) -> Result<&[f64]> {
        let field = self
            .field(name)
            .ok_or_else(|| anyhow!("结果缺少字段 {name}"))?;
        // safety: data 借用到 cnn_result_free（头文件 L26），本句柄存活期间有效
        Ok(unsafe {
            std::slice::from_raw_parts(field.data as *const f64, field.rows * field.columns)
        })
    }

    /// CNN_F64 字段的 (rows, columns)；行结构的矩阵字段（bands/modes）配合 f64s。
    pub fn rows_columns(&self, name: &str) -> Result<(usize, usize)> {
        let field = self
            .field(name)
            .ok_or_else(|| anyhow!("结果缺少字段 {name}"))?;
        Ok((field.rows, field.columns))
    }

    /// CNN_TEXT 字段：rows 为字节长度（适配层 text() 以 UTF-8 写入）。
    pub fn text(&self, name: &str) -> Result<&str> {
        let field = self
            .field(name)
            .ok_or_else(|| anyhow!("结果缺少字段 {name}"))?;
        // safety: 同上；文本为 UTF-8
        let bytes = unsafe { std::slice::from_raw_parts(field.data as *const u8, field.rows) };
        std::str::from_utf8(bytes).with_context(|| format!("字段 {name} 不是有效 UTF-8"))
    }

    /// CNN_COMPLEX 字段（交错 double）→ 逐元素幅度。
    /// 仅边界换算：FFT 本体在 C ABI 内完成，与参照脚本对同一复数谱取模一致。
    pub fn complex_magnitude(&self, name: &str) -> Result<Vec<f64>> {
        let field = self
            .field(name)
            .ok_or_else(|| anyhow!("结果缺少字段 {name}"))?;
        let count = field.rows * field.columns; // 复数元素数
                                                // safety: 同上；交错 double 缓冲长度为 2*count（头文件 L27-28）
        let raw = unsafe { std::slice::from_raw_parts(field.data as *const f64, count * 2) };
        Ok(raw
            .chunks_exact(2)
            .map(|pair| (pair[0] * pair[0] + pair[1] * pair[1]).sqrt())
            .collect())
    }
}

impl Drop for OwnedResult {
    fn drop(&mut self) {
        unsafe { cnn_result_free(self.0) }
    }
}

// ---- 安全入口：签名按头文件逐字 ----

/// L117：linear=true 最小二乘直线趋势去除，false 仅去均值。
pub fn detrend(x: &[f64], linear: bool) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_detrend",
        unsafe { cnn_detrend(span(x), c_int::from(linear), &mut error) },
        &error,
    )
}

/// L146：8 项时域统计，字段名 statistics（margin_floor 默认 1e-12）。
pub fn statistics(x: &[f64], margin_floor: f64) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_statistics",
        unsafe { cnn_statistics(span(x), margin_floor, &mut error) },
        &error,
    )
}

/// L107：SOS 设计，字段名 sos，每行 b0,b1,b2,a0,a1,a2。
pub fn butterworth(order: i32, low: f64, high: f64, fs: f64) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_butterworth",
        unsafe { cnn_butterworth(order, low, high, fs, &mut error) },
        &error,
    )
}

/// L108：SOS 零相位双向滤波，padlen<0 用默认规则；字段名 values。
pub fn sosfiltfilt(x: &[f64], sos: &[f64], padlen: i32) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_sosfiltfilt",
        unsafe { cnn_sosfiltfilt(span(x), span(sos), padlen, &mut error) },
        &error,
    )
}

/// L93：半谱复数 FFT（N/2+1 个复数），字段名 values（交错 double）。
pub fn rfft(x: &[f64]) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call("cnn_rfft", unsafe { cnn_rfft(span(x), &mut error) }, &error)
}

/// L145：解析信号取模（Hilbert 包络），字段名 values。
pub fn hilbert_envelope(x: &[f64]) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_hilbert_envelope",
        unsafe { cnn_hilbert_envelope(span(x), &mut error) },
        &error,
    )
}

/// L321：频谱候选仲裁；字段 frequency(CNN_F64)/source/reason(CNN_TEXT)。
#[allow(clippy::too_many_arguments)]
pub fn spectrum_speed(
    x: &[f64],
    fs: f64,
    low: f64,
    high: f64,
    harmonics: i32,
    bandwidth: f64,
    smoothing: f64,
) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_spectrum_speed",
        unsafe {
            cnn_spectrum_speed(
                span(x),
                fs,
                low,
                high,
                harmonics,
                bandwidth,
                smoothing,
                &mut error,
            )
        },
        &error,
    )
}

/// L144：numeric 族实倒谱（周期 Hann、去均值 log 幅度，前 N/2 点），字段名 values。
pub fn cepstrum(x: &[f64]) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_cepstrum",
        unsafe { cnn_cepstrum(span(x), &mut error) },
        &error,
    )
}

/// L244：小波阈值去噪，参数全默认——名称传 NULL（db8/symmetric/soft），
/// level=0 为最大允许层数，scale=1.0（头文件 L238-239 与 pybind denoise 默认一致）。
/// 字段名 values（去噪后信号）。
pub fn wavelet_denoise(x: &[f64]) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_wavelet_denoise",
        unsafe {
            cnn_wavelet_denoise(
                span(x),
                std::ptr::null(),
                std::ptr::null(),
                0,
                std::ptr::null(),
                1.0,
                &mut error,
            )
        },
        &error,
    )
}

/// L294：谱峭度滤波器组；字段名 bands，每行 low_hz,high_hz,level,
/// spectral_kurtosis,impulsiveness,signal_to_background（适配层 L30-34）。
pub fn filter_bank_kurtogram(
    x: &[f64],
    fs: f64,
    max_level: i32,
    minimum_frequency: f64,
    order: i32,
) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_filter_bank_kurtogram",
        unsafe {
            cnn_filter_bank_kurtogram(span(x), fs, max_level, minimum_frequency, order, &mut error)
        },
        &error,
    )
}

/// L256：VMD 分解，options 传 NULL 取 cnn_vmd_defaults（与 pybind decompose
/// 默认一致）。字段 modes 为 K×valid_length 行优先，另有 input_length/
/// valid_length/iterations/converged/status/reason。
pub fn vmd(x: &[f64], fs: f64) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_vmd",
        unsafe { cnn_vmd(span(x), fs, std::ptr::null(), &mut error) },
        &error,
    )
}

/// L299：时间-转速梯形积分，累计转数从零开始；云端 order 管线同源相位入口，
/// 字段名 values（单位：转）。
pub fn integrate(time: &[f64], speed: &[f64]) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_integrate",
        unsafe { cnn_integrate(span(time), span(speed), &mut error) },
        &error,
    )
}

/// L301：累计转数相位上的等角重采样，输出长度 floor(phase.back()*spr+1e-9)，
/// 字段名 values。
pub fn angle_resample(
    x: &[f64],
    phase: &[f64],
    samples_per_revolution: i32,
) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_angle_resample",
        unsafe { cnn_angle_resample(span(x), span(phase), samples_per_revolution, &mut error) },
        &error,
    )
}

/// L302：周期 Hann 单边峰值幅值谱（阶次域同入口），字段名 values。
pub fn amplitude_spectrum(x: &[f64], center: bool) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_amplitude_spectrum",
        unsafe { cnn_amplitude_spectrum(span(x), c_int::from(center), &mut error) },
        &error,
    )
}

/// L305：完整转数算术同步平均，字段 cycle 为单圈平均、repeated 为平铺信号。
pub fn tsa(
    x: &[f64],
    samples_per_revolution: i32,
    minimum_revolutions: i32,
) -> Result<OwnedResult> {
    let mut error = fresh_error();
    call(
        "cnn_tsa",
        unsafe {
            cnn_tsa(
                span(x),
                samples_per_revolution,
                minimum_revolutions,
                &mut error,
            )
        },
        &error,
    )
}
