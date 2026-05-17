# `probability_calibration.py` — 概率校准

**对应源码**：`cloud/app/services/diagnosis/probability_calibration.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `calibrate_fault_probabilities` | `calibrate_fault_probabilities(raw_probs, time_features) -> dict` | 故障概率校准 |
| `calibrate_snr_to_prob` | `calibrate_snr_to_prob(snr, fault_type="generic") -> float` | SNR 转概率 |
