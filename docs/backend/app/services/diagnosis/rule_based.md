# `rule_based.py` — 规则诊断（回退）

**对应源码**：`cloud/app/services/diagnosis/rule_based.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `adaptive_rms_baseline` | `adaptive_rms_baseline(rot_freq_hz) -> float` | 自适应 RMS 基线 |
| `_rule_based_analyze` | `_rule_based_analyze(channels_data, sample_rate=25600, device) -> dict` | 规则诊断主入口（崩溃回退） |
| `compute_envelope_spectrum` | `compute_envelope_spectrum(signal, sample_rate=25600, max_freq=1000) -> Tuple` | 包络谱计算 |
| `_extract_spectrum_features` | `_extract_spectrum_features(freq, amp, rot_freq, gear_teeth, bearing_params) -> dict` | 频谱特征提取 |
| `_extract_envelope_features` | `_extract_envelope_features(envelope_freq, envelope_amp, rot_freq, bearing_params) -> dict` | 包络特征提取 |
| `_extract_order_features` | `_extract_order_features(order_axis, spectrum, rot_freq, gear_teeth, bearing_params) -> dict` | 阶次特征提取 |
