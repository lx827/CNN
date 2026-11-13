# edge-diag — 树莓派边端诊断 CLI（POC 算法宿主）

薄 Rust CLI 壳，动态链接 `libcnn_compute.so`，对单通道信号文件计算"无参数
表示层"指标并输出 JSON。数值算法全部经 C ABI（`capi/include/cnn_compute.h`）
完成；Rust 侧不实现任何数学，仅对 C 复数输出做逐元素取模的边界换算。

## 用法

```bash
edge-diag --input signal.f64 --fs 10000 --out result.json
```

- 输入：单通道 float64 小端裸二进制（`.f64`），采样率由 `--fs`（Hz）给出
- 输出：紧凑单行 JSON（`serde_json::to_string`）

## 分析管线与参数（与 scripts/edge_diag_reference.py 保持一致）

| 步骤 | C ABI（头文件行号） | 输入信号 | 参数 |
|---|---|---|---|
| 1 线性去趋势 | `cnn_detrend`（L117） | 原始 | linear=1 |
| 2 时域统计 | `cnn_statistics`（L146） | 去趋势后 | margin_floor=1e-12；字段序 peak,rms,kurtosis,skewness,margin,shape,impulse,crest，取 peak/rms/crest/kurtosis/skewness |
| 3 Butterworth 带通（SOS 零相位） | `cnn_butterworth`（L107）+ `cnn_sosfiltfilt`（L108） | 原始 | order=4，通带 [500,3000] Hz，padlen=-1（库内 SciPy SOS 默认规则） |
| 4 rfft 幅度谱 | `cnn_rfft`（L93） | 去趋势后 | 交错复数输出 → 逐元素取模 |
| 5 包络谱 | `cnn_hilbert_envelope`（L145）→ `cnn_rfft` | 带通后（原始信号滤波） | Hilbert 取模在 C 核内 |
| 6 转速 | `cnn_spectrum_speed`（L321） | 原始 | low=10.0, high=100.0, harmonics=5, bandwidth=3.0, smoothing=1.5 |

步骤 3/6 作用于原始输入信号：契约未标注中间信号（步骤 2/4/5 显式标注
"去趋势后/带通后"），500 Hz 高通与核内均值处理使趋势差异不进入结果；
与参照脚本 `scripts/edge_diag_reference.py` 的取法一致。默认参数值取自
cnn_compute Python 包（`numeric.statistics`、`filtering.sosfiltfilt`、
`rotation.spectrum_speed` 的默认，与 C ABI 同一 C++ 内核）。

## 输出契约

```json
{"input":{"file":"signal.f64","fs":10000,"n":50000},
 "metrics":{"rms":0.31,"peak":1.2,"crest":3.9,"kurtosis":3.1,"skewness":0.02},
 "spectrum":[...幅度数组...],
 "envelope_spectrum":[...],
 "speed_hz":25.0,
 "timings_ms":{"detrend":1.2,"stats":0.8,"filter":25.0,"spectrum":9.1,"envelope":18.3,"speed":40.2},
 "peak_rss_kb":12345}
```

- `timings_ms`：每 stage `std::time::Instant` 计时（毫秒）
- `speed_hz`：`cnn_spectrum_speed` 的 frequency 字段；仲裁不可判定（reason
  非空）或频率非有限时输出 null——与参照脚本同规则，对比脚本按双方 null 跳过
- `peak_rss_kb`：结束时读 `/proc/self/status` 的 `VmHWM`（kB）；非 Linux 平台为 null

## 构建与测试

- 交叉构建在 Docker 内进行（`edge-diag/build/`，独立工单）；本仓库本机
  **不做链接验证**（主机无 aarch64 `libcnn_compute.so`）
- `build.rs` 在设置了环境变量 `EDGE_DIAG_LIB` 时注入
  `rustc-link-lib=dylib=cnn_compute` 与该目录的搜索路径（Docker 构建时设）；
  未设置时不注入链接指令
- 无 `.so` 的主机可运行 `cargo check`（类型检查）与
  `cargo test --lib`（JSON 结构测试，位于 `src/lib.rs` 测试模块，不触
  FFI）；完整 `cargo test` 与运行需设置 `EDGE_DIAG_LIB` 并存在对应平台的
  `libcnn_compute.so`

## 已知缺口

- 无：契约管线六步原语均已由 C ABI 导出，没有因未导出而置 null 的 stage。
- 非 Linux 平台 `peak_rss_kb` 为 null（契约允许）。
- 本机（Windows）未做链接与数值验证；数值一致性由参照脚本与
  `edge_diag_compare.py`（rtol=1e-6, atol=1e-8）在 Docker 构建产物上验证。
