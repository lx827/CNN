# `mckd.py` — MCKD 解卷积

**对应源码**：`cloud/app/services/diagnosis/mckd.py`

## 函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `mckd_deconvolution` | `mckd_deconvolution(signal, filter_len=30, T=1, M=1, max_iter=30) -> np.ndarray` | MCKD 最大相关峭度解卷积（引入故障周期约束） |
| `mckd_envelope_analysis` | `mckd_envelope_analysis(signal, fs, bearing_params, rot_freq, ...) -> dict` | MCKD + 包络分析 |
