# `modality_bearing.py` — 模态分解轴承分析

**对应源码**：`cloud/app/services/diagnosis/modality_bearing.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `emd_bearing_analysis` | `emd_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | EMD 敏感 IMF 包络分析 |
| `ceemdan_bearing_analysis` | `ceemdan_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | CEEMDAN 敏感 IMF 包络分析 |
| `vmd_bearing_analysis` | `vmd_bearing_analysis(signal, fs, bearing_params, ...) -> dict` | VMD 敏感模态包络分析 |
