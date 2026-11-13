# edge-diag — 树莓派边端诊断 CLI（POC 算法宿主）

薄 Rust CLI 壳，动态链接 `libcnn_compute.so`，对单通道信号文件计算"无参数
表示层"指标并输出 JSON。数值算法全部经 C ABI（`capi/include/cnn_compute.h`）
完成；Rust 侧不实现任何数学，仅做边界换算与归约：复数输出逐元素取模、
残差逐点相减、模态能量比归一、kurtogram 频带行选取、阶次谱按云端
分辨率动态截取
（与参照脚本在同一 C 输出上的 NumPy 运算一一对应）。

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

二期（步骤 7-12，输入除标注外均为原始信号）：

| 步骤 | C ABI（头文件行号） | 输入信号 | 参数 |
|---|---|---|---|
| 7 小波阈值去噪 | `cnn_wavelet_denoise`（L244） | 原始 | 全默认：wavelet/mode/threshold 传 NULL（db8/symmetric/soft），level=0（最大允许层数），scale=1.0 |
| 8 实倒谱 | `cnn_cepstrum`（L144，numeric 族） | 原始 | 无参数；`values` 数组原样输出 |
| 9 谱峭度选带 | `cnn_filter_bank_kurtogram`（L294） | 原始 + fs | max_level=4，min_frequency=100.0，order=4（pybind `diagnostic.filter_bank_kurtogram` 默认） |
| 10 VMD 分解 | `cnn_vmd`（L256） | 原始前 min(n,51200) 点（契约显式） + fs | options=NULL → `cnn_vmd_defaults`（与 pybind `vmd.decompose` 默认一致） |
| 11 阶次谱 | `cnn_integrate`（L299）→ `cnn_angle_resample`（L301）→ `cnn_amplitude_spectrum`（L302） | 原始 + 一期 speed_hz | spr=1024；按云端 `compute_order_spectrum` 动态截取：resolution=spr/重采样长度，retained=min(谱长, floor(50.0/resolution+1e-9)+1)，取前 retained 个值 |
| 12 TSA | `cnn_tsa`（L305） | 步骤 11 的等角重采样信号 | spr=1024，minimum_revolutions=4（pybind `rotation.tsa` 默认） |

步骤 3/6 作用于原始输入信号：契约未标注中间信号（步骤 2/4/5 显式标注
"去趋势后/带通后"），500 Hz 高通与核内均值处理使趋势差异不进入结果；
与参照脚本 `scripts/edge_diag_reference.py` 的取法一致。默认参数值取自
cnn_compute Python 包（`numeric.statistics`、`filtering.sosfiltfilt`、
`rotation.spectrum_speed`、`diagnostic.filter_bank_kurtogram`、`vmd.decompose`、
`rotation.tsa` 的默认，与 C ABI 同一 C++ 内核）。

### 二期字段映射与边界运算

- `wavelet`：去噪信号取 `cnn_wavelet_denoise` 的 `values`；残差 = 原始 − 去噪
  （逐点相减为边界运算）；`residual_rms`/`denoised_rms` 均为
  `cnn_statistics(x, 1e-12)` 的 statistics[1]（rms=√mean(x²)，同核保证一致）。
- `cepstrum`：`cnn_cepstrum` 的 `values` 数组原样（前 N/2 点）。
- `kurtogram`：C ABI 只返回 `bands` 矩阵（每行 low_hz,high_hz,level,
  spectral_kurtosis,impulsiveness,signal_to_background），无 best 字段；
  `best_low_hz`/`best_high_hz`/`max_kurtosis` = 谱峭度（列 3）最大行的
  列 0/列 1/列 3（行选取为边界运算，与参照脚本同规则）。
- `vmd`：`modes` 为 K×valid_length 行优先；`mode_energy_ratio` = 各行平方和
  除以 K 行平方和总计（能量归一为边界归约）；`n_input` = 实际输入点数
  min(n,51200)。
- `order_spectrum`：连续相位来自 `cnn_integrate`（rotation 族，与云端 order
  管线 `cloud/app/algorithms/order/resampling.py` 的
  `integrate_speed_trajectory` 同一 C++ 入口；梯形积分，单位转）。恒速输入
  下梯形积分与线性相位 phase(t)=2π·f·t 严格等价，**未触发恒速近似降级**。
  等角重采样 spr=1024 后取 `cnn_amplitude_spectrum`（center=1）输出，截取
  逐字对齐云端 `compute_order_spectrum`（cloud/app/algorithms/order/
  resampling.py）：resolution = spr/重采样长度（f64 除法），
  retained = min(谱长, floor(50.0/resolution+1e-9)+1)，输出前 retained 个值。
- `tsa`：`cnn_tsa_components` 签名强制 mesh_orders/regular_orders 齿轮参数，
  不适用；采用同族纯转平均入口 `cnn_tsa`（完整转数算术平均），输出取
  `cycle`（单圈平均波形），无缺口。
- `speed_hz` 为 null 时 `order_spectrum`/`tsa` 均为 null，另加
  `order_skip_reason:"speed_null"`；其余情况无该键。

## 输出契约

```json
{"input":{"file":"signal.f64","fs":10000,"n":50000},
 "metrics":{"rms":0.31,"peak":1.2,"crest":3.9,"kurtosis":3.1,"skewness":0.02},
 "spectrum":[...幅度数组...],
 "envelope_spectrum":[...],
 "speed_hz":25.0,
 "wavelet":{"residual_rms":0.04,"denoised_rms":0.30},
 "cepstrum":[...数组原样...],
 "kurtogram":{"best_low_hz":625.0,"best_high_hz":1250.0,"max_kurtosis":4.8},
 "vmd":{"mode_energy_ratio":[0.5,0.2,0.1,0.1,0.1],"n_input":50000},
 "order_spectrum":[...bins 0..=50...],
 "tsa":[...单圈平均波形...],
 "timings_ms":{"detrend":1.2,"stats":0.8,"filter":25.0,"spectrum":9.1,"envelope":18.3,"speed":40.2,
               "wavelet":12.0,"cepstrum":8.5,"kurtogram":60.0,"vmd":210.0,"order":15.4,"tsa":1.1},
 "peak_rss_kb":12345}
```

- `timings_ms`：每 stage `std::time::Instant` 计时（毫秒）；`order` 覆盖
  相位积分→等角重采样→阶次幅值谱整链，`tsa` 单独计时
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

- 无：一期六步与二期六步原语均已由 C ABI 导出；TSA 用纯转平均入口
  `cnn_tsa` 而非强制齿轮参数的 `cnn_tsa_components`（选择，非缺口），
  阶次链相位用 `cnn_integrate`（云端同源，未走恒速近似降级）。
- 非 Linux 平台 `peak_rss_kb` 为 null（契约允许）。
- 本机（Windows）未做链接与数值验证；数值一致性由参照脚本与
  `edge_diag_compare.py`（rtol=1e-6, atol=1e-8）在 Docker 构建产物上验证。
