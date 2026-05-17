### 文件: services/diagnosis/__init__.py -> docs/backend/app/services/diagnosis/__init__.md
- **状态**: 完整
- **已覆盖函数/类**: []
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/bearing.py -> docs/backend/app/services/diagnosis/bearing.md
- **状态**: 完整
- **已覆盖函数/类**: ['envelope_analysis', 'fast_kurtogram', 'cpw_envelope_analysis', 'med_envelope_analysis', 'teager_envelope_analysis', 'spectral_kurtosis_envelope_analysis']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/bearing_cyclostationary.py -> docs/backend/app/services/diagnosis/bearing_cyclostationary.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['bearing_sc_scoh_analysis']
- **缺失函数/类**: ['_compute_sc_scoh_bearing(signal:np.ndarray, fs:float, seg_len:int, overlap_ratio:float, alpha_max:Optional[float]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/bearing_sideband.py -> docs/backend/app/services/diagnosis/bearing_sideband.md
- **状态**: 完整
- **已覆盖函数/类**: ['compute_sideband_density', 'evaluate_bearing_sideband_features']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/bss.py -> docs/backend/app/services/diagnosis/bss.md
- **状态**: 完整
- **已覆盖函数/类**: ['fast_ica', 'vmd_ica_separation']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/channel_consensus.py -> docs/backend/app/services/diagnosis/channel_consensus.md
- **状态**: 完整
- **已覆盖函数/类**: ['cross_channel_consensus']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/emd_denoise.py -> docs/backend/app/services/diagnosis/emd_denoise.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['emd_decompose', 'ceemdan_decompose', 'eemd_decompose', 'compute_imf_energy_entropy', 'emd_denoise']
- **缺失函数/类**: ['_find_extrema(signal:np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]', '_refine_extrema_parabolic(signal:np.ndarray, idx:np.ndarray) -> np.ndarray', '_pad_extrema_rilling(signal:np.ndarray, max_idx:np.ndarray, min_idx:np.ndarray, pad_width:int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]', '_compute_envelope_mean(signal:np.ndarray, max_idx:np.ndarray, min_idx:np.ndarray, use_pchip:bool, pad_width:int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]', '_stop_sd(proto_imf:np.ndarray, old:np.ndarray) -> float', '_stop_rilling(upper_env:np.ndarray, lower_env:np.ndarray, sd1:float, sd2:float, tol:float) -> bool', '_excess_kurtosis(x:np.ndarray) -> float']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/engine.py -> docs/backend/app/services/diagnosis/engine.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['DiagnosisStrategy', 'BearingMethod', 'GearMethod', 'DenoiseMethod', 'DiagnosisEngine', 'DiagnosisEngine.__init__', 'DiagnosisEngine.preprocess', 'DiagnosisEngine._estimate_rot_freq', 'DiagnosisEngine.analyze_bearing', 'DiagnosisEngine.analyze_gear', 'DiagnosisEngine.analyze_comprehensive']
- **缺失函数/类**: ['DiagnosisEngine.analyze_research_ensemble(self, signal:np.ndarray, fs:float, rot_freq:Optional[float], profile:str, max_seconds:float) -> Dict[str, Any]', 'DiagnosisEngine.analyze_all_methods(self, signal:np.ndarray, fs:float, rot_freq:Optional[float], skip_bearing:bool, skip_gear:bool) -> Dict[str, Any]', '_evaluate_bearing_faults_statistical(freq_arr:np.ndarray, amp_arr:np.ndarray, rot_freq:float) -> Dict[str, Any]', '_evaluate_bearing_faults(bearing_params:Optional[Dict], env_freq:List[float], env_amp:List[float], rot_freq:float, rot_freq_std:float) -> Dict[str, Any]']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/ensemble.py -> docs/backend/app/services/diagnosis/ensemble.md
- **状态**: 完整
- **已覆盖函数/类**: ['_as_float', '_safe_denoise', '_profile_config', '_has_gear_params', '_has_bearing_params', '_bearing_confidence', '_gear_confidence', '_time_confidence', '_fault_label', 'run_research_ensemble']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/features.py -> docs/backend/app/services/diagnosis/features.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['compute_time_features', '_compute_dynamic_baseline_features', 'compute_fft_features', 'compute_envelope_features', 'remove_dc', 'compute_channel_features', 'compute_fft', 'compute_imf_energy', '_compute_bearing_fault_freqs', '_compute_bearing_fault_orders', '_sign_cusum', '_mann_whitney_cusum', 'compute_nonparam_cusum_features']
- **缺失函数/类**: ['_get_channel_params(device, channel_index, field)']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/fusion/__init__.py -> docs/backend/app/services/diagnosis/fusion/__init__.md
- **状态**: 完整
- **已覆盖函数/类**: []
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/fusion/ds_fusion.py -> docs/backend/app/services/diagnosis/fusion/ds_fusion.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['EvidenceFrame', 'BPA', 'dempster_combination', 'murphy_average_combination', 'build_bpa_from_method', 'build_time_domain_bpa', 'dempster_shafer_fusion']
- **缺失函数/类**: ['EvidenceFrame.__init__(self, fault_types:List[str])', 'EvidenceFrame.all_elements(self) -> List[str]', 'EvidenceFrame.make_singleton_key(self, fault:str) -> FrozenSet[str]', 'EvidenceFrame.make_full_key(self) -> FrozenSet[str]', 'BPA.__init__(self, frame:EvidenceFrame, masses:Dict[FrozenSet[str], float])', 'BPA.get_mass(self, focal:FrozenSet[str]) -> float', '_classify_method(method_key:str) -> str', '_map_hits_to_faults(hits:List[str], method_type:str, fault_types:List[str]) -> List[str]', 'compute_belief(bpa:BPA, focal:FrozenSet[str]) -> float', 'compute_plausibility(bpa:BPA, focal:FrozenSet[str]) -> float']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/gear/__init__.py -> docs/backend/app/services/diagnosis/gear/__init__.md
- **状态**: 完整
- **已覆盖函数/类**: ['compute_fm0', 'compute_er', 'compute_ser', 'analyze_sidebands', '_evaluate_gear_faults']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/gear/metrics.py -> docs/backend/app/services/diagnosis/gear/metrics.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['compute_tsa_residual_order', 'compute_fm4', 'compute_m6a', 'compute_m8a', 'compute_car', 'compute_ser_order', 'analyze_sidebands_order', 'compute_fm0_order', 'compute_na4', 'compute_nb4', 'analyze_sidebands_zoom_fft']
- **缺失函数/类**: ['_order_band_amplitude(order_axis, spectrum, center_order:float, bandwidth:float) -> float']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/gear/msb.py -> docs/backend/app/services/diagnosis/gear/msb.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['msb_residual_sideband_analysis']
- **缺失函数/类**: ['_compute_slice_snr(msb_se_slice:np.ndarray, fc_axis:np.ndarray, target_freq:float, df:float, background:float) -> float', '_get_slice_value(msb_se_slice:np.ndarray, fc_axis:np.ndarray, target_freq:float, df:float) -> float']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/gear/planetary_demod.py -> docs/backend/app/services/diagnosis/gear/planetary_demod.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['planetary_envelope_order_analysis', 'planetary_fullband_envelope_order_analysis', 'planetary_vmd_demod_analysis', 'planetary_tsa_envelope_analysis', 'planetary_hp_envelope_order_analysis', 'planetary_sc_scoh_analysis', 'planetary_msb_analysis', 'evaluate_planetary_demod_results']
- **缺失函数/类**: ['_local_background(oa, os, center, half_bw, side_bw)', '_band_median_background(oa, os, max_order)', '_envelope_order_spectrum(signal:np.ndarray, fs:float, rot_freq:float) -> Tuple[np.ndarray, np.ndarray]', 'planetary_cvs_med_analysis(signal:np.ndarray, fs:float, rot_freq:float, gear_teeth:Dict) -> Dict']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/gear/vmd_demod.py -> docs/backend/app/services/diagnosis/gear/vmd_demod.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['vmd_fixed_axis_demod_analysis']
- **缺失函数/类**: ['_analyze_fixed_axis_sidebands(amp_freq:np.ndarray, amp_spectrum:np.ndarray, freq_freq:np.ndarray, freq_spectrum:np.ndarray, mesh_freq:float, rot_freq:float, fs:float, n_sidebands:int, sideband_bw_hz:float) -> Dict', '_evaluate_fixed_axis_indicators(ser:float, significant_count:int, mesh_energy:float, demod_type:str) -> Dict']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/health_score.py -> docs/backend/app/services/diagnosis/health_score.md
- **状态**: 完整
- **已覆盖函数/类**: ['_compute_health_score', 'get_ds_label', 'is_ds_conflict_high']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/health_score_continuous.py -> docs/backend/app/services/diagnosis/health_score_continuous.md
- **状态**: 完整
- **已覆盖函数/类**: ['sigmoid_deduction', 'multi_threshold_deduction', 'cascade_deduction', 'compute_continuous_deductions']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/lms_filter.py -> docs/backend/app/services/diagnosis/lms_filter.md
- **状态**: 完整
- **已覆盖函数/类**: ['lms_filter', 'nlms_filter', 'vsslms_filter']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/mckd.py -> docs/backend/app/services/diagnosis/mckd.md
- **状态**: 完整
- **已覆盖函数/类**: ['mckd_deconvolution', 'mckd_envelope_analysis']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/modality_bearing.py -> docs/backend/app/services/diagnosis/modality_bearing.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['emd_bearing_analysis', 'ceemdan_bearing_analysis', 'vmd_bearing_analysis']
- **缺失函数/类**: ['_compute_envelope_spectrum(signal:np.ndarray, fs:float, f_low_pass:float, max_freq:float) -> Dict', '_reconstruct_selected_components(components:List[np.ndarray], indices:List[int], target_length:int) -> np.ndarray']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/order_tracking.py -> docs/backend/app/services/diagnosis/order_tracking.md
- **状态**: 完整
- **已覆盖函数/类**: ['_order_tracking', '_compute_order_spectrum', '_compute_order_spectrum_multi_frame', '_compute_order_spectrum_varying_speed']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/preprocessing.py -> docs/backend/app/services/diagnosis/preprocessing.md
- **状态**: 完整
- **已覆盖函数/类**: ['wavelet_denoise', 'cepstrum_pre_whitening', 'minimum_entropy_deconvolution', 'cascade_wavelet_vmd', 'cascade_wavelet_lms', 'joint_denoise']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/probability_calibration.py -> docs/backend/app/services/diagnosis/probability_calibration.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['calibrate_fault_probabilities', 'calibrate_snr_to_prob']
- **缺失函数/类**: ['_sigmoid_prob(value:float, threshold:float, max_prob:float, slope:float) -> float']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/recommendation.py -> docs/backend/app/services/diagnosis/recommendation.md
- **状态**: 完整
- **已覆盖函数/类**: ['_match_suggestion', '_generate_recommendation', '_generate_recommendation_all', '_summarize_all_methods']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/rule_based.py -> docs/backend/app/services/diagnosis/rule_based.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['adaptive_rms_baseline', '_rule_based_analyze', 'compute_envelope_spectrum', '_extract_spectrum_features', '_extract_envelope_features', '_extract_order_features']
- **缺失函数/类**: ['_order_band_energy(order_axis, spectrum, center_order:float, bandwidth:float) -> float', '_feature_severity(value:float, metric:str, rot_freq:float) -> float', '_compute_order_spectrum_simple(sig:np.ndarray, fs:float, rot_freq:float, samples_per_rev:int, max_order:int)', '_band_energy(freq, amp, center:float, bandwidth:float) -> float']
- **类型注解缺失**: ['_rule_based_analyze', 'compute_envelope_spectrum']
- **算法文档链接**: 无

### 文件: services/diagnosis/savgol_denoise.py -> docs/backend/app/services/diagnosis/savgol_denoise.md
- **状态**: 完整
- **已覆盖函数/类**: ['sg_denoise', 'sg_trend_residual']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/sensitive_selector.py -> docs/backend/app/services/diagnosis/sensitive_selector.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['score_components', 'select_top_components', 'select_wp_sensitive_nodes', 'select_emd_sensitive_imfs', 'select_vmd_sensitive_modes']
- **缺失函数/类**: ['compute_correlation(component:np.ndarray, original:np.ndarray) -> float', 'compute_excess_kurtosis(component:np.ndarray) -> float', 'compute_envelope_entropy(component:np.ndarray) -> float', 'compute_energy_ratio(component:np.ndarray, total_energy:float) -> float', 'compute_center_freq(component:np.ndarray, fs:float) -> float', 'compute_freq_match_score(center_freq:float, target_freq:float) -> float', '_normalize(values:List[float]) -> List[float]']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/signal_utils.py -> docs/backend/app/services/diagnosis/signal_utils.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['remove_dc', 'linear_detrend', 'prepare_signal', 'bandpass_filter', 'lowpass_filter', 'highpass_filter', 'compute_fft_spectrum', 'compute_power_spectrum', 'find_peaks_in_spectrum', 'compute_snr', 'kurtosis', 'skewness', 'rms', 'peak_value', 'crest_factor', '_band_energy', 'estimate_rot_freq_envelope', 'estimate_rot_freq_autocorr', 'estimate_rot_freq_spectrum', 'zoom_fft_analysis']
- **缺失函数/类**: ['parabolic_interpolation(freqs, spectrum, idx)', '_order_band_energy(order_axis, spectrum, center_order:float, bandwidth:float) -> float', 'lowpass_filter_complex(signal:np.ndarray, fs:float, f_cut:float, order:int) -> np.ndarray']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/trend_prediction.py -> docs/backend/app/services/diagnosis/trend_prediction.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['holt_winters_forecast', 'kalman_smooth_health_scores']
- **缺失函数/类**: ['_simple_linear_regression(x:np.ndarray, y:np.ndarray) -> tuple']
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/vmd_denoise.py -> docs/backend/app/services/diagnosis/vmd_denoise.md
- **状态**: 完整
- **已覆盖函数/类**: ['_vmd_core', 'vmd_decompose', 'vmd_denoise', 'vmd_select_impact_mode']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/wavelet_bearing.py -> docs/backend/app/services/diagnosis/wavelet_bearing.md
- **状态**: 完整
- **已覆盖函数/类**: ['wavelet_packet_bearing_analysis', 'dwt_bearing_analysis']
- **缺失函数/类**: []
- **类型注解缺失**: []
- **算法文档链接**: 无

### 文件: services/diagnosis/wavelet_packet.py -> docs/backend/app/services/diagnosis/wavelet_packet.md
- **状态**: 部分缺失
- **已覆盖函数/类**: ['wavelet_packet_decompose', 'compute_wavelet_packet_energy_entropy', 'wavelet_packet_denoise', 'compute_mswpee']
- **缺失函数/类**: ['_coarse_grain(signal:np.ndarray, scale:int) -> np.ndarray']
- **类型注解缺失**: []
- **算法文档链接**: 无

---
**统计总结**:
- Python 文件总数: 34
- 函数/类/方法总数: 211
- 已覆盖数: 160
- 缺失数: 51
- 覆盖率: 75.8%
- 文档缺失文件数: 0
