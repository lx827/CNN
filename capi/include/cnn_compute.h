#ifndef CNN_COMPUTE_H
#define CNN_COMPUTE_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#if defined(CNN_COMPUTE_C_EXPORTS)
#define CNN_API __declspec(dllexport)
#else
#define CNN_API __declspec(dllimport)
#endif
#define CNN_CALL __cdecl
#else
#define CNN_API __attribute__((visibility("default")))
#define CNN_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* 头和动态库按同一源码版本配套升级；不承诺跨版本结构布局兼容。
 * 所有函数同步执行，不创建线程。span 输入只读借用到调用返回，允许空 span
 * 为 {NULL,0}，非空 span 必须指向其声明长度的连续有效存储。
 * cnn_result 拥有输出；field.data/name 借用到 cnn_result_free，后续调用不覆盖。
 * 所有数组行优先；复数输入显式 {real,imag}，复数输出为交错 double(real,imag)。
 * 不以 cnn_complex* 别名读取复数输出；使用 cnn_field_complex 按值读取。
 * 不暴露 STL/Eigen 或异常。
 * 函数出错返回 NULL，error 可为 NULL；算法正常未收敛由结果字段表达。
 * NULL 参数 options 使用 C++ 默认值；非 NULL 必须完整初始化，可用 defaults。
 */
typedef struct cnn_span {
    const double *data;
    size_t        size;
} cnn_span;
typedef struct cnn_indices {
    const size_t *data;
    size_t        size;
} cnn_indices;
typedef struct cnn_complex {
    double real, imag;
} cnn_complex;
typedef struct cnn_complex_span {
    const cnn_complex *data;
    size_t             size;
} cnn_complex_span;
typedef struct cnn_result cnn_result;
typedef enum cnn_error_code {
    CNN_ERROR_NONE,
    CNN_ERROR_ARGUMENT,
    CNN_ERROR_DOMAIN,
    CNN_ERROR_RANGE,
    CNN_ERROR_MEMORY,
    CNN_ERROR_COMPUTATION
} cnn_error_code;
typedef struct cnn_error {
    cnn_error_code code;
    char           message[512];
} cnn_error;
typedef enum cnn_field_type {
    CNN_F64,
    CNN_I32,
    CNN_SIZE,
    CNN_U8,
    CNN_COMPLEX,
    CNN_TEXT
} cnn_field_type;
typedef struct cnn_field {
    const char    *name;
    cnn_field_type type;
    const void    *data;
    size_t         rows, columns;
} cnn_field;
/* index 是复数元素下标，须小于 rows*columns，field.type 必须为 CNN_COMPLEX。 */
static inline cnn_complex cnn_field_complex(cnn_field field, size_t index) {
    const double *data  = (const double *)field.data;
    cnn_complex   value = { data[2 * index], data[2 * index + 1] };
    return value;
}
CNN_API void CNN_CALL   cnn_result_free(cnn_result *result);
CNN_API size_t CNN_CALL cnn_result_count(const cnn_result *result);
/* index 必须小于 count；find 返回 0 表示没有该名称。field 本身按值拷贝。 */
CNN_API cnn_field CNN_CALL   cnn_result_field(const cnn_result *result, size_t index);
CNN_API int CNN_CALL         cnn_result_find(const cnn_result *result, const char *name, cnn_field *field);
CNN_API const char *CNN_CALL cnn_version(void);
CNN_API cnn_result *CNN_CALL cnn_build_info(cnn_error *error);

/* 基础数组结果名 values；复数结果同名且 type=CNN_COMPLEX。 */
CNN_API cnn_result *CNN_CALL cnn_fft(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_fft_complex(cnn_complex_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_ifft(cnn_complex_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_rfft(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_irfft(cnn_complex_span x, size_t samples, cnn_error *error);
/* 固定 N 的 FFT 计划，每活跃调用独占；execute 复用计划和 C 布局适配缓存。
 * 返回结果仍独立拥有，plan 释放或再次 execute 不影响旧结果。半谱长 N/2+1。
 * 创建时可分配；执行仍分配最终结果和后端 exec 所需 scratch。
 */
typedef struct cnn_fft_plan    cnn_fft_plan;
CNN_API cnn_fft_plan *CNN_CALL cnn_fft_plan_create(size_t samples, cnn_error *error);
CNN_API void CNN_CALL          cnn_fft_plan_free(cnn_fft_plan *plan);
CNN_API cnn_result *CNN_CALL   cnn_fft_plan_forward(cnn_fft_plan *plan, cnn_span x, int half, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_fft_plan_complex(cnn_fft_plan *plan, cnn_complex_span x, int inverse, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_fft_plan_inverse_half(cnn_fft_plan *plan, cnn_complex_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_convolve(cnn_span a, cnn_span b, cnn_error *error);
/* SOS 每行为 b0,b1,b2,a0,a1,a2，共 sections*6 个 double。 */
CNN_API cnn_result *CNN_CALL cnn_butterworth(int order, double low, double high, double fs, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_sosfiltfilt(cnn_span x, cnn_span sos, int padlen, cnn_error *error);
/* 反复过滤时持有一份系数和延拓工作区；工作区只在规模增长时扩容。
 * 每活跃调用独占；返回结果独立，不保存输入借用。
 */
typedef struct cnn_sos_plan    cnn_sos_plan;
CNN_API cnn_sos_plan *CNN_CALL cnn_sos_plan_create(cnn_span sos, int padlen, cnn_error *error);
CNN_API void CNN_CALL          cnn_sos_plan_free(cnn_sos_plan *plan);
CNN_API cnn_result *CNN_CALL   cnn_sos_plan_apply(cnn_sos_plan *plan, cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_hann(size_t n, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_detrend(cnn_span x, int linear, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_savgol(cnn_span x, int window, int order, int derivative, double delta, cnn_error *error);
CNN_API cnn_result *CNN_CALL   cnn_solve_tridiagonal(cnn_span lower, cnn_span diagonal, cnn_span upper, cnn_span rhs, cnn_error *error);
typedef enum cnn_interpolation { CNN_SPLREP,
                                 CNN_PCHIP,
                                 CNN_CUBIC } cnn_interpolation;
CNN_API cnn_result *CNN_CALL cnn_interpolate(cnn_span x, cnn_span y, cnn_span query, cnn_interpolation method, cnn_error *error);
typedef enum cnn_padding { CNN_RILLING_PADDING,
                           CNN_NUMPYPAD } cnn_padding;
typedef struct cnn_envelope_options {
    cnn_interpolation interpolation;
    cnn_padding       padding;
    int               pad_width, parabolic;
} cnn_envelope_options;
CNN_API cnn_envelope_options CNN_CALL cnn_envelope_defaults(void);
CNN_API cnn_result *CNN_CALL          cnn_find_extrema(cnn_span x, int maxima, int parabolic, cnn_error *error);
/* envelope 结果 status 为 valid 或 insufficient_extrema；无效时不提供伪造数组。 */
CNN_API cnn_result *CNN_CALL cnn_extrema_envelopes(cnn_span x, const cnn_envelope_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_upper_envelope(cnn_span x, const cnn_envelope_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_combined_envelope(cnn_span x, const cnn_envelope_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_analytic_signal(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_amplitude_normalise(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_frequency_transform(cnn_span x, double fs, int normalised, int smooth_phase, int smooth_frequency, cnn_error *error);
/* 数值结果沿用 C++ 字段名：spectrum frequency/amplitude/power，STFT time/frequency/amplitude，
 * statistics 按 peak,rms,kurtosis,skewness,margin,shape,impulse,crest 排列。 */
CNN_API cnn_result *CNN_CALL cnn_spectrum(cnn_span x, double fs, int remove_mean, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_stft(cnn_span x, double fs, int window, int overlap, int nfft, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_cepstrum(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_hilbert_envelope(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_statistics(cnn_span x, double margin_floor, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_time_domain(cnn_span x, double fs, int window, int step, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_segmented_rms(cnn_span x, double fs, size_t segment, int remove_mean, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_extrema(cnn_span x, cnn_span y, size_t maximum, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_autocorrelation(cnn_span x, int demean, cnn_error *error);

typedef enum cnn_stop_method { CNN_STOP_SD,
                               CNN_STOP_RILLING,
                               CNN_STOP_ENERGY,
                               CNN_STOP_FIXED } cnn_stop_method;
typedef enum cnn_emd_status { CNN_EMD_SUCCESS,
                              CNN_EMD_INSUFFICIENT_EXTREMA,
                              CNN_EMD_ITERATION_LIMIT,
                              CNN_EMD_NUMERICAL_FAILURE } cnn_emd_status;
typedef struct cnn_imf_options {
    double          env_step_size;
    int             max_iterations;
    double          energy_threshold;
    cnn_stop_method stop_method;
    double          sd_threshold, rilling_threshold[3];
} cnn_imf_options;
typedef struct cnn_emd_options {
    cnn_imf_options      imf;
    cnn_envelope_options envelope;
    int                  max_imfs;
    int                  use_sift_threshold;
    double               sift_threshold;
    int                  use_energy_threshold;
    double               energy_threshold;
    int                  use_rilling_threshold;
    double               rilling_threshold[3];
} cnn_emd_options;
CNN_API cnn_imf_options CNN_CALL cnn_imf_defaults(void);
CNN_API cnn_emd_options CNN_CALL cnn_emd_defaults(void);
/* component.i[Nsamples]，component_count 为分量数；iterations 为实际筛分记录。
 * next_imf 另有 continue_flag；status 对应 cnn_emd_status。集成迭代记录为空。 */
CNN_API cnn_result *CNN_CALL cnn_next_imf(cnn_span x, const cnn_imf_options *imf, const cnn_envelope_options *envelope, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_sift(cnn_span x, const cnn_emd_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_ensemble_sift(cnn_span x, cnn_span noise, const cnn_emd_options *options, int ensembles, double noise_scale, int flip, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_complete_ensemble_sift(cnn_span x, cnn_span noise, const cnn_emd_options *options, int ensembles, double noise_scale, cnn_error *error);
typedef enum cnn_first_mask { CNN_MASK_ZERO_CROSSINGS,
                              CNN_MASK_INSTANTANEOUS_FREQUENCY,
                              CNN_MASK_EXPLICIT } cnn_first_mask;
typedef enum cnn_mask_amplitude { CNN_MASK_ABSOLUTE,
                                  CNN_MASK_RATIO_SIGNAL,
                                  CNN_MASK_RATIO_IMF } cnn_mask_amplitude;
typedef struct cnn_mask_options {
    cnn_imf_options      imf;
    cnn_envelope_options envelope;
    cnn_span             frequencies;
    cnn_first_mask       first_mask;
    double               first_frequency;
    cnn_span             amplitudes;
    cnn_mask_amplitude   amplitude_mode;
    double               step_factor;
    int                  max_imfs, phases;
    double               sift_threshold;
} cnn_mask_options;
/* frequencies 为空时由 first_mask 生成；amplitudes 为空使用默认单值 1。 */
typedef struct cnn_iterated_mask_options {
    cnn_mask_options mask;
    int              max_iterations, averages;
    double           threshold, sample_rate, weight_power;
    int              weighted, exclude_edges;
} cnn_iterated_mask_options;
CNN_API cnn_mask_options CNN_CALL          cnn_mask_defaults(void);
CNN_API cnn_iterated_mask_options CNN_CALL cnn_iterated_mask_defaults(void);
CNN_API cnn_result *CNN_CALL               cnn_next_imf_mask(cnn_span x, double frequency, double amplitude, int phases, const cnn_imf_options *imf, const cnn_envelope_options *envelope, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_mask_frequency(cnn_span x, cnn_first_mask method, double frequency, const cnn_imf_options *imf, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_mask_sift(cnn_span x, const cnn_mask_options *options, cnn_error *error);
/* mask_frequencies：converged=1 时 Hz，否则 cycles/sample；mask_iterations 为实际分解次数。 */
CNN_API cnn_result *CNN_CALL cnn_iterated_mask_sift(cnn_span x, const cnn_iterated_mask_options *options, cnn_error *error);
/* first_layer 含 count 条等长 span；layer.i.component.j/iterations/status 保留真实深度。 */
CNN_API cnn_result *CNN_CALL cnn_sift_second_layer(const cnn_span *first_layer, size_t count, const cnn_emd_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_mask_sift_second_layer(const cnn_span *first_layer, size_t count, cnn_span frequencies, const cnn_mask_options *options, cnn_error *error);

/* 小波 decompose 结果 band.i/lengths/level/packet，内含可继续重构的系数 owner。
 * reconstruct 接收 decompose 返回的 owner；在同步调用结束前不得释放它。
 * wavelet/mode/threshold_mode 为 UTF-8 名称，NULL 使用 db8/symmetric/soft。
 */
CNN_API cnn_result *CNN_CALL cnn_wavelet_decompose(cnn_span x, const char *wavelet, const char *mode, int level, int packet, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_wavelet_reconstruct(const cnn_result *coefficients, const char *wavelet, const char *mode, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_wavelet_components(const cnn_result *coefficients, const char *wavelet, const char *mode, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_wavelet_selected(const cnn_result *coefficients, const char *wavelet, const char *mode, cnn_indices selected, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_wavelet_denoise(cnn_span x, const char *wavelet, const char *mode, int level, const char *threshold_mode, double scale, cnn_error *error);
typedef struct cnn_vmd_options {
    int      modes;
    double   alpha, tau, tolerance;
    int      max_iterations, dc;
    size_t   max_samples;
    int      initialization;
    uint64_t seed;
} cnn_vmd_options;
CNN_API cnn_vmd_options CNN_CALL cnn_vmd_defaults(void);
/* valid_length/input_length/iterations/converged/status/reason 保留截断和质量状态。
 * history 仅暴露 iterations 行；modes 为 K*valid_length。 */
CNN_API cnn_result *CNN_CALL cnn_vmd(cnn_span x, double fs, const cnn_vmd_options *options, cnn_error *error);
typedef struct cnn_deconvolution_options {
    int    filter_length, max_iterations;
    double tolerance, ridge;
} cnn_deconvolution_options;
CNN_API cnn_deconvolution_options CNN_CALL cnn_deconvolution_defaults(void);
CNN_API cnn_result *CNN_CALL               cnn_med(cnn_span x, const cnn_deconvolution_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_mckd(cnn_span x, int period, int shift_order, const cnn_deconvolution_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_normalized_kurtosis(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_correlated_kurtosis(cnn_span x, int period, int shift_order, cnn_error *error);
CNN_API cnn_result *CNN_CALL               cnn_mckd_update(cnn_span matrix, size_t rows, size_t columns, cnn_span filter, int period, int shift_order, double ridge, cnn_error *error);
typedef struct cnn_ica_options {
    int      components, max_iterations;
    double   tolerance;
    uint64_t seed;
} cnn_ica_options;
typedef enum cnn_ica_status { CNN_ICA_CONVERGED,
                              CNN_ICA_ITERATION_LIMIT,
                              CNN_ICA_RANK_DEFICIENT,
                              CNN_ICA_SINGULAR_UPDATE } cnn_ica_status;
CNN_API cnn_ica_options CNN_CALL cnn_ica_defaults(void);
CNN_API cnn_result *CNN_CALL     cnn_fast_ica(cnn_span observations, size_t samples, size_t channels, const cnn_ica_options *options, cnn_error *error);
typedef enum cnn_adaptive_method { CNN_LMS,
                                   CNN_NLMS,
                                   CNN_VARIABLE_STEP } cnn_adaptive_method;
typedef struct cnn_adaptive_options {
    cnn_adaptive_method method;
    int                 filter_length, delay;
    size_t              max_updates;
    double              step_size, alpha, gamma, minimum_step, maximum_step;
} cnn_adaptive_options;
CNN_API cnn_adaptive_options CNN_CALL cnn_adaptive_defaults(void);
CNN_API cnn_result *CNN_CALL          cnn_adaptive_filter(cnn_span x, const cnn_adaptive_options *options, cnn_error *error);

/* 诊断基础运算：复杂量保持复数值；MSB 的 valid 字段保留网格有效性。 */
CNN_API cnn_result *CNN_CALL cnn_teager(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_complex_spectral_kurtosis(cnn_complex_span x, cnn_error *error);
/* bands 每行依次 low_hz,high_hz,level,spectral_kurtosis,impulsiveness,signal_to_background。 */
CNN_API cnn_result *CNN_CALL cnn_filter_bank_kurtogram(cnn_span x, double fs, int max_level, double minimum_frequency, int order, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_cepstral_prewhiten(cnn_span x, double fs, cnn_span comb, double width, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_sc_scoh(cnn_span x, double fs, cnn_span alpha, size_t segment, size_t step, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_modulation_bispectrum(cnn_span x, double fs, cnn_span carriers, cnn_span modulation, size_t segment, size_t step, size_t minimum_segments, cnn_error *error);

CNN_API cnn_result *CNN_CALL cnn_integrate(cnn_span time, cnn_span speed, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_rotation_interpolate(cnn_span x, cnn_span y, cnn_span target, int zero_outside, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_angle_resample(cnn_span x, cnn_span phase, int samples_per_revolution, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_amplitude_spectrum(cnn_span x, int center, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_periodic_components(cnn_span cycle, cnn_span orders, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_tsa_components(cnn_span cycle, cnn_span mesh_orders, cnn_span regular_orders, int revolutions, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_tsa(cnn_span x, int samples_per_revolution, int minimum_revolutions, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_zoom_spectrum(cnn_span x, double fs, double low, double high, int points, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_real_cepstrum(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_amfm(cnn_span x, double fs, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_band_envelope(cnn_span x, double fs, double low, double high, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_window_peaks(cnn_span axis, cnn_span amplitude, cnn_span centers, double half_width, int disjoint, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_band_sum(cnn_span axis, cnn_span values, double center, double half_width, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_local_peak(cnn_span axis, cnn_span amplitude, double center, double half_width, double background_inner, double background_outer, cnn_span exclusions, int median_background, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_car_features(cnn_span axis, cnn_span cepstrum, cnn_span targets, double half_width, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_order_statistics(cnn_span amplitude, cnn_error *error);
typedef struct cnn_ridge_options {
    double peak_to_background, local_energy, reliable_fraction, boundary_fraction;
    int    consecutive_boundaries;
} cnn_ridge_options;
CNN_API cnn_ridge_options CNN_CALL cnn_ridge_defaults(void);
CNN_API cnn_result *CNN_CALL       cnn_speed_ridge(cnn_span x, double fs, double low, double high, int window, int hop, const cnn_ridge_options *options, cnn_error *error);
CNN_API cnn_result *CNN_CALL       cnn_spectrum_speed(cnn_span x, double fs, double low, double high, int harmonics, double bandwidth, double smoothing, cnn_error *error);
CNN_API cnn_result *CNN_CALL       cnn_autocorrelation_speed(cnn_span x, double fs, double low, double high, cnn_error *error);
CNN_API cnn_result *CNN_CALL       cnn_envelope_speed(cnn_span x, double fs, double carrier, double low, double high, double bandwidth, cnn_error *error);
CNN_API cnn_result *CNN_CALL       cnn_cvs(cnn_span x, cnn_span carrier, cnn_span planet, double azimuth, double sensor, double half_width, int samples_per_revolution, cnn_error *error);

CNN_API cnn_result *CNN_CALL cnn_holt(cnn_span x, int steps, double alpha, double beta, double gamma, int period, double initial_trend, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_kalman(cnn_span x, double process_noise, double measurement_noise, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_cusum(cnn_span x, double allowance, double alpha, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_mann_whitney_z(cnn_span x, cnn_span reference, int window, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_regression(cnn_span x, cnn_span y, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_central_moment(cnn_span x, int degree, int scale, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_window_moments(cnn_span x, int window, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_robust_standardize(cnn_span x, cnn_error *error);
CNN_API cnn_result *CNN_CALL cnn_sign_cusum(cnn_span x, double reference, int use_median, cnn_error *error);

#ifdef __cplusplus
}
#endif
#endif
