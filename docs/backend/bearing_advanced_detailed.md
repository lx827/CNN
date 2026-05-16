# 轴承高级诊断模块详细文档

> 本文档提取自 `cloud/app/services/diagnosis/` 目录下的 5 个轴承高级诊断模块，包含每个函数/类的完整签名、功能说明、参数说明和返回值说明。

---

## bearing_cyclostationary.py

> 轴承循环平稳分析模块，包含谱相关密度 (SC)、谱相干 (SCoh) 计算及循环频率搜索与故障判定。

---

### `_compute_sc_scoh_bearing`

```python
def _compute_sc_scoh_bearing(
    signal: np.ndarray,
    fs: float,
    seg_len: int = 2048,
    overlap_ratio: float = 0.75,
    alpha_max: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
```

**功能说明**

计算谱相关密度和谱相干的底层函数（轴承与行星箱共用）。

使用分段 FFT 估计法（分段归一化再平均，保证 SCoh ∈ [0,1]）：
- 谱相关密度：`S_x^α(f) = <X(f-α/2) * conj(X(f+α/2))>`（分段平均）
- 谱相干：`γ_x^α(f) = <|S_x^α(f)|> / <sqrt(PSD(f+α/2) * PSD(f-α/2))>`

实际实现中，每段先归一化再平均，最终得到 `scoh = <|X(f-α/2)·conj(X(f+α/2))| / sqrt(PSD_lo·PSD_hi)>`。

非循环频率处相位随机，复数平均后趋零 → SCoh 低；真实循环频率处相位对齐 → SCoh 高。

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `seg_len` | `int` | `2048` | 分段 FFT 长度 |
| `overlap_ratio` | `float` | `0.75` | 分段重叠比例 |
| `alpha_max` | `Optional[float]` | `None` | 最大循环频率 (Hz)，`None` 则取 `fs/4` |

**返回值说明**

返回三元组 `(f_axis, alpha_axis, scoh_matrix)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| `f_axis` | `np.ndarray` | 频率轴 (Hz)，长度为 `n_freq = seg_len//2 + 1` |
| `alpha_axis` | `np.ndarray` | 循环频率轴 (Hz)，仅保留 ≤ `alpha_max` 的部分 |
| `scoh_matrix` | `np.ndarray` | 谱相干矩阵，形状 `(n_alpha, n_freq)`，取值范围 `[0, 1]` |

---

### `bearing_sc_scoh_analysis`

```python
def bearing_sc_scoh_analysis(
    signal: np.ndarray,
    fs: float,
    bearing_params: Optional[Dict] = None,
    rot_freq: Optional[float] = None,
    seg_len: int = 2048,
) -> Dict:
```

**功能说明**

轴承谱相关/谱相干分析入口函数。

在循环频率轴搜索 BPFO/BPFI/BSF/FTF 对应的峰值，判断轴承故障类型。对随机噪声和确定性干扰天然免疫，是变速工况下的高级诊断手段。

工程判据：
- `SCoh > 0.3` 为 warning
- `SCoh > 0.5` 为 critical

分析流程：
1. 估计/获取转频 `rot_freq`
2. 根据轴承几何参数计算故障特征频率（BPFO/BPFI/BSF/FTF）
3. 无参数时，退化为搜索转频附近的估计循环频率
4. 调用 `_compute_sc_scoh_bearing` 计算谱相干
5. 在各故障频率 ± 容差范围内搜索 SCoh 峰值
6. 额外搜索 2×、3× 谐波
7. 返回最可能的故障类型及各项指标

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `bearing_params` | `Optional[Dict]` | `None` | 轴承几何参数，含键 `n`(滚珠数)、`d`(滚珠直径)、`D`(节径)、`alpha`(接触角，度) |
| `rot_freq` | `Optional[float]` | `None` | 轴转频 (Hz)，`None` 时自动从频谱估计 |
| `seg_len` | `int` | `2048` | 分段 FFT 长度 |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `method` | `str` | 固定为 `"bearing_sc_scoh"` |
| `rot_freq_hz` | `float` | 使用的转频 (Hz)，保留 3 位小数 |
| `fault_freqs_hz` | `Dict[str, float]` | 各故障特征频率理论值 (Hz) |
| `fault_indicators` | `Dict[str, Dict]` | 各故障频率的 SCoh 峰值和显著性详情 |
| `sc_max_alpha_hz` | `float` | SCoh 最大峰值对应的循环频率 (Hz) |
| `sc_max_value` | `float` | SCoh 最大峰值 |
| `dominant_fault` | `str` | 最可能的故障类型名称 |

其中 `fault_indicators` 中每个故障条目的结构：

| 键 | 类型 | 说明 |
|----|------|------|
| `theory_hz` | `float` | 理论故障频率 |
| `scoh_peak` | `float` | 该频率附近的 SCoh 峰值 |
| `scoh_snr` | `float` | 峰值与背景中位数的比值 |
| `significant` | `bool` | `scoh_peak > 0.3` 则为显著 |
| `warning` | `bool` | `peak > 0.3 and snr > 3.0` |
| `critical` | `bool` | `peak > 0.5 and snr > 5.0` |

---

## bearing_sideband.py

> 轴承包络谱边频带密度分析模块，针对 BPFI/BPFO/BSF 三种故障类型的谱形态特征进行区分。

---

### `compute_sideband_density`

```python
def compute_sideband_density(
    env_freq: np.ndarray,
    env_amp: np.ndarray,
    fault_freq_hz: float,
    mod_freq_hz: float,
    background: float,
    max_harmonics: int = 5,
    snr_threshold: float = 3.0,
    freq_tolerance: float = 0.0,
    df: float = 1.0,
) -> Dict[str, Any]:
```

**功能说明**

计算指定故障频率周围的边频带密度指标。

边频带密度定义为：在 `fault_freq ± n×mod_freq`（`n = 1, 2, ..., N`）位置，超过 `snr_threshold` 的边带数量占总搜索边带数量的比例。

不同故障类型的边带特征：
- **BPFI（内圈故障）**：包络谱峰值周围常有转频调制边带，边带密度高
- **BPFO（外圈故障）**：谐波更规律，边带较少
- **BSF（滚动体故障）**：频率附近有保持架频率（FTF）调制

同时计算上/下边带不对称性，内圈故障因承载区调制，上下边带幅度通常不对称。

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `env_freq` | `np.ndarray` | — | 包络谱频率轴 (Hz) |
| `env_amp` | `np.ndarray` | — | 包络谱幅值轴 |
| `fault_freq_hz` | `float` | — | 故障特征频率 (BPFO/BPFI/BSF) |
| `mod_freq_hz` | `float` | — | 调制频率（通常为转频 `fr` 或保持架频率 `FTF`） |
| `background` | `float` | — | 包络谱背景水平（中位数） |
| `max_harmonics` | `int` | `5` | 最大搜索谐波阶数（搜索 `±1×` 到 `±N×mod`） |
| `snr_threshold` | `float` | `3.0` | 边带显著性的 SNR 阈值 |
| `freq_tolerance` | `float` | `0.0` | 频率匹配容差 (Hz)，`0` 则自动计算为 `max(fault_freq_hz * 0.05, df * 2)` |
| `df` | `float` | `1.0` | 频率分辨率 (Hz) |

**返回值说明**

返回 `Dict[str, Any]`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `total_searched` | `int` | 搜索的边带总数（含超出频率范围的） |
| `significant_count` | `int` | 超过 SNR 阈值的边带数 |
| `density` | `float` | 边带密度 `(0~1)`，保留 4 位小数 |
| `sideband_details` | `List[Dict]` | 各边带的详细信息列表 |
| `asymmetry` | `float` | 上/下边带不对称性，保留 4 位小数 |
| `upper_count` | `int` | 显著上边带数量 |
| `lower_count` | `int` | 显著下边带数量 |

其中 `sideband_details` 每项结构：

| 键 | 类型 | 说明 |
|----|------|------|
| `order` | `int` | 谐波阶数 `n` |
| `side` | `str` | `"upper"` 或 `"lower"` |
| `theory_hz` | `float` | 理论边带频率 |
| `detected` | `bool` | 是否在频率轴上找到匹配位置 |
| `snr` | `float` | 实际 SNR 值 |
| `significant` | `bool` | 是否超过阈值 |

---

### `evaluate_bearing_sideband_features`

```python
def evaluate_bearing_sideband_features(
    env_freq: List[float],
    env_amp: List[float],
    bearing_params: Optional[Dict],
    rot_freq: float,
) -> Dict[str, Dict]:
```

**功能说明**

评估三种轴承故障类型（BPFO/BPFI/BSF）的边频带密度特征。

返回各故障类型的边带密度、不对称性指标，供故障类型区分使用。

分析流程：
1. 检查参数有效性，无效时返回空字典
2. 根据轴承几何参数计算 BPFO、BPFI、BSF 理论故障频率
3. BPFO/BPFI 使用转频 `rot_freq` 作为调制频率
4. BSF 使用保持架频率 `FTF` 作为调制频率
5. 对每个故障类型调用 `compute_sideband_density` 计算边带密度
6. 附加故障类型判定辅助字段（`high_density`、`low_density`、`high_asymmetry`）

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `env_freq` | `List[float]` | — | 包络谱频率轴 |
| `env_amp` | `List[float]` | — | 包络谱幅值轴 |
| `bearing_params` | `Optional[Dict]` | — | 轴承几何参数，含 `n`、`d`、`D`、`alpha` |
| `rot_freq` | `float` | — | 转频 (Hz) |

**返回值说明**

返回 `Dict[str, Dict]`，键为故障类型名称 `"BPFO"`、`"BPFI"`、`"BSF"`，每个值为：

| 键 | 类型 | 说明 |
|----|------|------|
| `sideband_density` | `float` | 边带密度 |
| `sideband_significant_count` | `int` | 显著边带数 |
| `sideband_asymmetry` | `float` | 不对称性 |
| `high_density` | `bool` | `density >= 0.3`，内圈故障特征 |
| `low_density` | `bool` | `density < 0.15`，外圈故障特征 |
| `high_asymmetry` | `bool` | `asymmetry > 0.3`，内圈故障特征 |

若参数无效或 `env_freq`/`env_amp` 为空，返回 `{}`。

---

## modality_bearing.py

> 模态分解轴承故障诊断模块，基于 EMD/CEEMDAN/VMD 分解的轴承诊断方法。

---

### `_compute_envelope_spectrum`

```python
def _compute_envelope_spectrum(
    signal: np.ndarray,
    fs: float,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
```

**功能说明**

Hilbert 包络 → 低通滤波 → FFT 包络谱的共用底层函数。

流程：
1. 对输入信号执行 Hilbert 变换，得到解析信号
2. 取解析信号幅值作为包络
3. 包络零均值化
4. 若 `f_low_pass < fs/2`，对包络执行低通滤波
5. 对包络做 FFT，得到包络谱
6. 仅保留频率 ≤ `max_freq` 的部分

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入信号（通常为重构后的窄带信号） |
| `fs` | `float` | — | 采样率 (Hz) |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `envelope_freq` | `List[float]` | 包络谱频率轴 (Hz)，仅含 ≤ `max_freq` 的点 |
| `envelope_amp` | `List[float]` | 包络谱幅值轴，与 `envelope_freq` 一一对应 |

---

### `_reconstruct_selected_components`

```python
def _reconstruct_selected_components(
    components: List[np.ndarray],
    indices: List[int],
    target_length: int,
) -> np.ndarray:
```

**功能说明**

从选中的 IMF/模态分量重构窄带信号。

将 `indices` 指定的分量相加得到重构信号。若重构信号长度短于 `target_length`，则在末尾补零；若长于目标长度，则截断。

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `components` | `List[np.ndarray]` | — | IMF/模态分量列表 |
| `indices` | `List[int]` | — | 要选中的分量索引列表 |
| `target_length` | `int` | — | 重构信号的目标长度 |

**返回值说明**

返回 `np.ndarray`，重构后的窄带信号，长度等于 `target_length`。

---

### `emd_bearing_analysis`

```python
def emd_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    max_imfs: int = 8,
    max_sifts: int = 50,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
    use_rilling: bool = False,
) -> Dict:
```

**功能说明**

EMD 敏感 IMF 轴承诊断。

流程：
1. 信号去直流
2. EMD 分解得到 IMF 列表和残余分量
3. 综合评分选择敏感 IMF（排除 IMF1 噪声和末尾趋势项）
4. 重构敏感 IMF 窄带信号
5. Hilbert 包络 → 包络谱

与 `emd_denoise.py` 的区别：
- `emd_denoise.py` 用于降噪（筛去低相关/低峭度 IMF，重构降噪信号）
- 本模块用于诊断（选最敏感 IMF → 包络谱 → 故障频率匹配）

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `max_imfs` | `int` | `8` | 最大 IMF 数 |
| `max_sifts` | `int` | `50` | 单个 IMF 最大筛分次数 |
| `top_n` | `int` | `1` | 选择前 N 个敏感 IMF |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |
| `use_rilling` | `bool` | `False` | 是否使用 Rilling 停止准则 |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `envelope_freq` | `List[float]` | 包络谱频率轴 |
| `envelope_amp` | `List[float]` | 包络谱幅值轴 |
| `method` | `str` | 固定为 `"EMD Sensitive IMF Envelope"` |
| `n_imfs` | `int` | 分解出的 IMF 数量 |
| `selected_imfs` | `List[int]` | 选中的 IMF 索引列表 |
| `imf_scores` | `List[Dict]` | 各 IMF 评分详情 |
| `error` | `str` | （可选）分解失败时的错误信息 |

---

### `ceemdan_bearing_analysis`

```python
def ceemdan_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    max_imfs: int = 8,
    ensemble_size: int = 30,
    noise_std: float = 0.2,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
```

**功能说明**

CEEMDAN 敏感 IMF 轴承诊断。

与 EMD 版的区别：
- CEEMDAN 通过噪声辅助抑制模态混叠，IMF 更纯净
- 分解更完备，噪声鲁棒性更强

注意：`ensemble_size=30` 以减少计算量（默认 50 用于降噪，诊断场景 30 已足够稳定）。

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `max_imfs` | `int` | `8` | 最大 IMF 数 |
| `ensemble_size` | `int` | `30` | CEEMDAN 集成次数（诊断用 30 即可） |
| `noise_std` | `float` | `0.2` | 添加噪声的标准差比例 |
| `top_n` | `int` | `1` | 选择前 N 个敏感 IMF |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |

**返回值说明**

返回格式与 `emd_bearing_analysis` 相同，额外包含：

| 键 | 类型 | 说明 |
|----|------|------|
| `method` | `str` | 固定为 `"CEEMDAN Sensitive IMF Envelope"` |
| `ensemble_size` | `int` | 实际使用的集成次数 |

---

### `vmd_bearing_analysis`

```python
def vmd_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    K: int = 5,
    alpha: float = 2000,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
```

**功能说明**

VMD 敏感模态轴承诊断。

与 EMD 版的区别：
- VMD 在频域自适应分解，模态中心频率由算法确定，频带更清晰
- VMD 精确中心频率可增强 `freq_match` 评分
- `K ≤ 5` 限制以适配 2G 服务器内存

流程：
1. 信号去直流
2. VMD 分解得到模态 `modes` 和中心频率演化矩阵 `omega`
3. 取 `omega` 最后一行作为各模态最终中心频率（需乘以 `fs/2` 转换为 Hz）
4. 利用 VMD 精确中心频率进行敏感模态选择
5. 重构敏感模态 → 包络谱

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `K` | `int` | `5` | 模态数，建议 ≤ 5 |
| `alpha` | `float` | `2000` | VMD 带宽惩罚参数 |
| `top_n` | `int` | `1` | 选择前 N 个敏感模态 |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `envelope_freq` | `List[float]` | 包络谱频率轴 |
| `envelope_amp` | `List[float]` | 包络谱幅值轴 |
| `method` | `str` | 固定为 `"VMD Sensitive Mode Envelope"` |
| `K` | `int` | 使用的模态数 |
| `selected_modes` | `List[int]` | 选中的模态索引列表 |
| `mode_scores` | `List[Dict]` | 各模态评分详情 |
| `mode_center_freqs` | `List[float]` | 各模态中心频率 (Hz)，保留 2 位小数 |
| `error` | `str` | （可选）分解失败时的错误信息 |

---

## wavelet_bearing.py

> 小波类轴承故障诊断模块，基于小波包分解和 DWT 分解的轴承诊断方法，通过敏感分量选择定位共振频带。

---

### `wavelet_packet_bearing_analysis`

```python
def wavelet_packet_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 3,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
    target_freq: float = 0.0,
) -> Dict:
```

**功能说明**

小波包轴承故障诊断。

流程：
1. 小波包完全二叉树分解（`level` 层 → `2^level` 个节点）
2. 计算各节点综合敏感度（相关性 + 峭度 + 包络熵 + 能量占比）
3. 选择最敏感节点（`top_n` 个）
4. 对敏感节点重构窄带信号（非选中节点置零）
5. Hilbert 包络 → 低通滤波 → FFT 包络谱
6. 返回标准格式结果

自动目标频率：若 `target_freq <= 0`，选峭度最高节点的中心频率作为共振频率估计。

各节点频带划分（以 `level=3`、`fs=8192Hz` 为例）：
- 共 8 个节点，每节点带宽 `512 Hz`
- 节点按自然序排列，频率从低到高覆盖 `[0, fs/2]`

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `wavelet` | `str` | `"db8"` | 小波基名称，与去噪模块保持一致 |
| `level` | `int` | `3` | 小波包分解层数（`3` → 8 节点；`4` → 16 节点） |
| `top_n` | `int` | `1` | 选择前 N 个敏感节点 |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |
| `target_freq` | `float` | `0.0` | 目标共振频率 (Hz)，`0` 表示自动检测 |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `envelope_freq` | `List[float]` | 包络谱频率轴 |
| `envelope_amp` | `List[float]` | 包络谱幅值轴 |
| `method` | `str` | 固定为 `"Wavelet Packet Envelope"` |
| `wp_level` | `int` | 小波包分解层数 |
| `wp_wavelet` | `str` | 使用的小波基 |
| `selected_nodes` | `List[str]` | 选中的节点路径列表（如 `"000"`、`"011"`） |
| `node_scores` | `List[Dict]` | 各节点评分详情 |
| `node_center_freqs` | `Dict[str, float]` | 各节点中心频率映射 |
| `target_freq` | `float` | 实际使用的目标共振频率 |
| `n_selected` | `int` | 选中节点数量 |

---

### `dwt_bearing_analysis`

```python
def dwt_bearing_analysis(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "db8",
    level: int = 5,
    top_n: int = 1,
    f_low_pass: float = 2000.0,
    max_freq: float = 1000.0,
) -> Dict:
```

**功能说明**

DWT（离散小波变换）敏感层轴承诊断。

流程：
1. DWT 多层分解 → 各层细节系数 `d_j`
2. 计算各层细节系数的峭度、能量、与原始信号相关性
3. 综合评分（峭度主导 + 相关性 + 能量辅助）选择最优层
4. 重构敏感层窄带信号（非选中层细节系数置零）
5. Hilbert 包络 → 低通滤波 → FFT 包络谱

各层对应频带（`@8192Hz`，`level=5`）：

| 层 | 频带范围 | 典型用途 |
|----|----------|----------|
| `d1` | 2048 ~ 4096 Hz | 极高频噪声 / 结构共振 |
| `d2` | 1024 ~ 2048 Hz | 高频共振（轴承常用） |
| `d3` | 512 ~ 1024 Hz | 中频共振 / 齿轮啮合 |
| `d4` | 256 ~ 512 Hz | 中低频 |
| `d5` | 128 ~ 256 Hz | 低频 / 转频 |

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `wavelet` | `str` | `"db8"` | 小波基名称 |
| `level` | `int` | `5` | DWT 分解层数 |
| `top_n` | `int` | `1` | 选择前 N 个敏感层 |
| `f_low_pass` | `float` | `2000.0` | 包络低通截止频率 (Hz) |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |

**返回值说明**

返回 `Dict`，结构如下：

| 键 | 类型 | 说明 |
|----|------|------|
| `envelope_freq` | `List[float]` | 包络谱频率轴 |
| `envelope_amp` | `List[float]` | 包络谱幅值轴 |
| `method` | `str` | 固定为 `"DWT Sensitive Layer Envelope"` |
| `dwt_level` | `int` | DWT 分解层数 |
| `dwt_wavelet` | `str` | 使用的小波基 |
| `selected_layers` | `List[int]` | 选中的分解层索引列表 |
| `layer_scores` | `List[Dict]` | 各层评分详情 |
| `best_layer` | `Optional[Dict]` | 最优层的完整信息（含频带、峭度、能量、相关性、评分） |

其中 `layer_scores` 每项结构：

| 键 | 类型 | 说明 |
|----|------|------|
| `layer` | `int` | 层号 `j` |
| `freq_range` | `str` | 频带范围字符串，如 `"[1024, 2048]"` |
| `center_freq` | `float` | 中心频率 |
| `kurtosis` | `float` | 该层细节系数峭度 |
| `energy` | `float` | 该层细节系数能量 |
| `corr` | `float` | 与原始信号的绝对相关系数 |
| `score` | `float` | 综合评分 |

---

## mckd.py

> MCKD (Maximum Correlated Kurtosis Deconvolution) 最大相关峭度解卷积模块。与现有 MED 形成互补：MED 最大化全局峭度，MCKD 引入故障周期 T，优化"周期性冲击序列"的检测。

---

### `mckd_deconvolution`

```python
def mckd_deconvolution(
    signal: np.ndarray,
    filter_len: int = 64,
    period_T: int = 100,
    shift_order_M: int = 1,
    max_iter: int = 30,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
```

**功能说明**

最大相关峭度解卷积 (MCKD) 核心算法。

通过迭代优化 FIR 滤波器，使得滤波后信号的**相关峭度**（correlated kurtosis）最大化。与 MED 的区别：
- MED 最大化全局峭度，增强孤立冲击，但可能放大随机大脉冲
- MCKD 引入故障周期 `T`，优化周期性冲击序列的检测，对轴承外圈/内圈故障更敏感

算法参考：McDonald et al. (2012)

迭代流程：
1. 构建 Toeplitz 矩阵 `X0`
2. 初始化滤波器 `f`（冲激函数）
3. 循环迭代：
   - 计算滤波输出 `y = X0 @ f`
   - 计算多移位乘积 `product = prod(y[m*T])`
   - 计算相关峭度 `CK = sum(product) / (y_power)^(M+1)`
   - 若 `|CK - prev_CK| < tol` 则收敛
   - 更新滤波器 `f = solve(R, rhs)` 并归一化
4. 最终用优化后的滤波器对原始信号做卷积

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `filter_len` | `int` | `64` | FIR 滤波器长度 `L`，实际取 `min(filter_len, N//4)` |
| `period_T` | `int` | `100` | 故障冲击周期（采样点数） |
| `shift_order_M` | `int` | `1` | 移位阶数，建议 `1~3` |
| `max_iter` | `int` | `30` | 最大迭代次数 |
| `tol` | `float` | `1e-6` | 收敛容差（相关峭度变化量阈值） |

**返回值说明**

返回三元组 `(滤波后信号, 滤波器系数, 元信息)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| `filtered_signal` | `np.ndarray` | 滤波后的信号，与输入等长（`mode='same'` 卷积） |
| `filter_coeffs` | `np.ndarray` | 优化后的 FIR 滤波器系数，长度 `L`，已归一化 |
| `info` | `Dict` | 元信息字典 |

其中 `info` 结构：

| 键 | 类型 | 说明 |
|----|------|------|
| `method` | `str` | 固定为 `"MCKD"` |
| `period_T` | `int` | 使用的故障周期 |
| `shift_order_M` | `int` | 移位阶数 |
| `filter_len` | `int` | 实际滤波器长度 |
| `correlated_kurtosis` | `float` | 最终相关峭度值，保留 6 位小数 |
| `iterations` | `int` | 实际迭代次数 |
| `error` | `str` | （可选）参数无效时的错误标识 `"invalid_params"` |

**异常处理**

若 `L < 2` 或 `period_T <= 0` 或 `period_T >= N//2`，直接返回原信号副本、单位冲激滤波器 `[1.0]`、`{"error": "invalid_params"}`。

---

### `mckd_envelope_analysis`

```python
def mckd_envelope_analysis(
    signal: np.ndarray,
    fs: float,
    bearing_params: Dict,
    rot_freq: float,
    filter_len: int = 64,
    shift_order_M: int = 1,
    max_freq: float = 1000.0,
) -> Dict:
```

**功能说明**

MCKD + 包络分析的完整诊断流程。

流程：
1. 从 `bearing_params` 提取轴承几何参数 `n`、`d`、`D`、`alpha`
2. 若参数无效（`n <= 0` 或 `d <= 0` 或 `D <= 0`），退化为 MED + 包络分析
3. 计算 BPFO 和 BPFI 理论故障频率
4. 取 `bpfo` 和 `bpfi` 中较大的作为目标频率
5. 由 `period_T = max(3, round(fs / target_freq))` 计算故障周期采样点数
6. 调用 `mckd_deconvolution` 执行 MCKD 滤波
7. 对滤波后信号执行标准包络分析
8. 附加 MCKD 元信息到结果中

**参数说明**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `signal` | `np.ndarray` | — | 输入振动信号 |
| `fs` | `float` | — | 采样率 (Hz) |
| `bearing_params` | `Dict` | — | 轴承几何参数，必须含 `n`、`d`、`D`、`alpha` |
| `rot_freq` | `float` | — | 转频 (Hz)，用于计算故障特征频率 |
| `filter_len` | `int` | `64` | MCKD 滤波器长度 |
| `shift_order_M` | `int` | `1` | MCKD 移位阶数 |
| `max_freq` | `float` | `1000.0` | 包络谱最大显示频率 (Hz) |

**返回值说明**

返回 `Dict`，结构为 `bearing.envelope_analysis()` 的标准输出，额外附加：

| 键 | 类型 | 说明 |
|----|------|------|
| `method` | `str` | `"MCKD + Envelope"` 或 `"MED + Envelope (MCKD fallback: no params)"` |
| `mckd_info` | `Dict` | `mckd_deconvolution` 返回的元信息 |
| `target_fault_freq_hz` | `float` | 用于计算周期的目标故障频率 (Hz)，保留 2 位小数 |

---

*文档生成时间：2026-05-17*
