# 信号融合与诊断模块详细文档

> 本文档按文件分组，提取每个函数/类的完整签名、功能说明、参数说明和返回值说明。

---

## 一、盲源分离模块（bss.py）

### fast_ica

```python
def fast_ica(
    X: np.ndarray,
    n_components: Optional[int] = None,
    max_iter: int = 200,
    tol: float = 1e-6,
    whiten: bool = True,
) -> Tuple[np.ndarray, Dict]:
    """
    FastICA 独立成分分析

    基于 Hyvärinen (1999) 的固定点算法，使用 negentropy 近似：
    G(u) = log(cos(a·u))，a ≈ 1.5

    算法流程：
    1. 中心化 + 白化（PCA）
    2. 对每个独立成分，迭代求解分离向量使 negentropy 最大化
    3. Gram-Schmidt 去相关（逐成分估计模式）

    Args:
        X: 输入矩阵 (n_samples, n_features)，每列一个观测通道
        n_components: 要提取的独立成分数，None 则取 min(n_features, 5)
        max_iter: 每成分最大迭代次数
        tol: 收敛容差
        whiten: 是否先白化

    Returns:
        (独立成分矩阵 (n_samples, n_components), 元信息字典)
    """
```

**功能说明：**
FastICA 独立成分分析函数，基于 Hyvärinen (1999) 的固定点算法实现。使用 tanh 函数作为 negentropy 的鲁棒近似，通过逐成分估计（deflation 模式）提取独立成分。算法包含三个主要步骤：数据中心化、PCA 白化降维、FastICA 迭代分离。在迭代过程中使用 Gram-Schmidt 正交化确保各成分之间去相关，并通过 tanh 近似的非线性函数最大化每个成分的 negentropy。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| X | np.ndarray | — | 输入矩阵，形状为 (n_samples, n_features)，每列代表一个观测通道 |
| n_components | Optional[int] | None | 要提取的独立成分数量；为 None 时取 min(n_features, 5) |
| max_iter | int | 200 | 每个独立成分的最大迭代次数 |
| tol | float | 1e-6 | 收敛容差，用于判断分离向量是否已收敛 |
| whiten | bool | True | 是否在 ICA 之前执行 PCA 白化降维 |

**返回值说明：**

返回一个元组 `(S, info)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| S | np.ndarray | 独立成分矩阵，形状为 (n_samples, n_components)，每列为一个独立成分 |
| info | Dict | 元信息字典，包含 `method`（"FastICA"）、`n_components`（成分数）、`kurtoses`（各成分峭度列表）、`correlations`（各成分与原信号的互相关列表）、`whiten`（是否白化） |

---

### vmd_ica_separation

```python
def vmd_ica_separation(
    signal: np.ndarray,
    fs: float,
    K: int = 5,
    alpha: int = 2000,
    max_ica_iter: int = 200,
    ica_tol: float = 1e-6,
) -> Dict:
    """
    单通道 VMD+ICA 盲源分离

    算法流程：
    1. VMD 分解 → 得到 K 个 IMF
    2. 将 IMF 组成多通道矩阵 (N, K)
    3. FastICA 分离 → 得到 K 个独立成分
    4. 按峭度选择含故障信息的独立成分
    5. 重构去噪信号（保留故障成分 + 相关性高的成分）

    Args:
        signal: 输入信号
        fs: 采样率
        K: VMD 分解模态数
        alpha: VMD 惩罚因子
        max_ica_iter: ICA 最大迭代次数
        ica_tol: ICA 收敛容差

    Returns:
        {
            "denoised_signal": np.ndarray,
            "fault_component": np.ndarray,  # 最可能的故障成分
            "n_modes": int,
            "vmd_kurtoses": List[float],
            "ica_kurtoses": List[float],
            "selected_component_index": int,
            "info": Dict,
        }
    """
```

**功能说明：**
单通道 VMD+ICA 盲源分离函数。该函数首先使用 VMD（变分模态分解）将单通道信号分解为多个 IMF（本征模态函数），然后将这些 IMF 作为多通道输入执行 FastICA 独立成分分析，进一步分离噪声源与故障源。接着按各独立成分的峭度值选择最可能的故障成分，并将峭度较高的 ICA 成分进行重构，得到去噪后的信号。函数内置了内存保护机制，信号长度超过 5 秒时会自动截断，以适应 2GB 内存服务器环境。当 VMD 或 ICA 失败时会自动回退到安全输出。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| signal | np.ndarray | — | 输入的单通道振动信号 |
| fs | float | — | 采样率（Hz） |
| K | int | 5 | VMD 分解的模态数（IMF 数量） |
| alpha | int | 2000 | VMD 惩罚因子，控制模态带宽 |
| max_ica_iter | int | 200 | FastICA 的最大迭代次数 |
| ica_tol | float | 1e-6 | FastICA 的收敛容差 |

**返回值说明：**

返回一个字典，包含以下键：

| 键名 | 类型 | 说明 |
|------|------|------|
| denoised_signal | np.ndarray | 重构后的去噪信号，保留故障相关成分 |
| fault_component | np.ndarray | 最可能的故障独立成分（峭度最大） |
| n_modes | int | VMD 实际分解出的模态数 |
| vmd_kurtoses | List[float] | 各 VMD 模态的峭度值列表 |
| ica_kurtoses | List[float] | 各 ICA 独立成分的峭度值列表 |
| selected_component_index | int | 被选中的最佳故障成分索引 |
| selected_indices | List[int] | 用于重构的所有选中成分索引列表 |
| info | Dict | 融合后的元信息字典，包含 ICA 信息和分析方法标识 |
| error | str（可选） | 当 VMD 或 ICA 失败时返回的错误信息 |

---

## 二、LMS 自适应滤波模块（lms_filter.py）

### lms_filter

```python
def lms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.01,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    标准 LMS 自适应滤波

    算法流程：
    1. 构造参考信号 u(n) = x(n - delay)
    2. 初始化滤波器系数 w = 0
    3. 迭代更新：w(n+1) = w(n) + μ·e(n)·u(n)
       其中 e(n) = x(n) - w^T·u(n)

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        step_size: 步长 μ，通常 0.001~0.05
        delay: 参考信号延迟（采样点数），默认 1
        max_iter: 最大迭代次数，None 则等于信号长度

    Returns:
        (滤波后信号, 元信息字典)
    """
```

**功能说明：**
标准 LMS（Least Mean Squares）自适应滤波函数。单通道场景下采用延迟构造法生成参考噪声信号：将原始信号延迟 `delay` 个采样点作为参考输入。滤波器通过迭代更新 FIR 系数，从主通道信号中减去与参考相关的成分，从而保留故障冲击等不相关成分。该算法适用于存在独立参考噪声通道的场景，单通道时通过延迟信号构造虚拟参考。前 `filter_len` 个点由于无法构造完整参考向量，直接保留原信号值。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| signal | np.ndarray | — | 输入的振动信号 |
| filter_len | int | 32 | FIR 滤波器的长度（阶数） |
| step_size | float | 0.01 | 步长 μ，控制收敛速度和稳定性，典型范围 0.001~0.05 |
| delay | int | 1 | 参考信号延迟的采样点数，用于构造虚拟参考噪声 |
| max_iter | Optional[int] | None | 最大迭代次数；为 None 时使用信号长度 |

**返回值说明：**

返回一个元组 `(output, info)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| output | np.ndarray | 滤波后的信号，故障冲击成分得到保留 |
| info | Dict | 元信息字典，包含 `method`（"LMS"）、`filter_len`、`step_size`、`delay`、`kurtosis_before`（滤波前峭度）、`kurtosis_after`（滤波后峭度）、`noise_reduction_ratio`（噪声抑制比）。若信号过短或延迟超过信号长度，则返回包含 `error` 字段的字典 |

---

### nlms_filter

```python
def nlms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    step_size: float = 0.5,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    NLMS（归一化 LMS）自适应滤波

    与标准 LMS 的区别：步长按输入功率归一化，防止发散。
    更新公式：w(n+1) = w(n) + μ / (||u(n)||² + ε) · e(n) · u(n)

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        step_size: 归一化步长 μ，通常 0.1~1.0
        delay: 参考信号延迟
        max_iter: 最大迭代次数

    Returns:
        (滤波后信号, 元信息字典)
    """
```

**功能说明：**
NLMS（Normalized Least Mean Squares，归一化 LMS）自适应滤波函数。与标准 LMS 的核心区别在于步长会根据参考信号向量的功率进行动态归一化，从而有效防止输入信号功率变化导致的发散问题。更新公式中加入了 `ε` 小量防止除零。NLMS 的收敛稳定性显著优于标准 LMS，适合输入信号功率动态变化的场景。单通道下同样采用延迟构造法生成参考信号。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| signal | np.ndarray | — | 输入的振动信号 |
| filter_len | int | 32 | FIR 滤波器的长度（阶数） |
| step_size | float | 0.5 | 归一化步长 μ，典型范围 0.1~1.0 |
| delay | int | 1 | 参考信号延迟的采样点数 |
| max_iter | Optional[int] | None | 最大迭代次数；为 None 时使用信号长度 |

**返回值说明：**

返回一个元组 `(output, info)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| output | np.ndarray | 滤波后的信号 |
| info | Dict | 元信息字典，包含 `method`（"NLMS"）、`filter_len`、`step_size`、`delay`、`kurtosis_before`、`kurtosis_after`、`noise_reduction_ratio`。若信号过短则返回包含 `error` 字段的字典 |

---

### vsslms_filter

```python
def vsslms_filter(
    signal: np.ndarray,
    filter_len: int = 32,
    mu_init: float = 0.01,
    alpha: float = 0.97,
    gamma: float = 5e-5,
    mu_min: float = 1e-6,
    mu_max: float = 0.05,
    delay: int = 1,
    max_iter: Optional[int] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    VSSLMS（变步长 LMS）自适应滤波

    步长随误差自适应调整：
    μ(n) = α·μ(n-1) + γ·e²(n)
    兼顾收敛速度（大误差时步长增大）与稳态误差（小误差时步长减小）。

    Args:
        signal: 输入信号
        filter_len: FIR 滤波器长度
        mu_init: 初始步长
        alpha: 步长记忆系数（0~1），越大则步长变化越慢
        gamma: 步长增长系数
        mu_min: 步长下限
        mu_max: 步长上限
        delay: 参考信号延迟
        max_iter: 最大迭代次数

    Returns:
        (滤波后信号, 元信息字典)
    """
```

**功能说明：**
VSSLMS（Variable Step-Size LMS，变步长 LMS）自适应滤波函数。该算法的核心特点是滤波器步长 `μ(n)` 能够根据当前误差信号的平方进行自适应调整：大误差时自动增大步长以加快收敛，小误差时自动减小步长以降低稳态失调。步长更新公式为 `μ(n) = α·μ(n-1) + γ·e²(n)`，并通过 `mu_min` 和 `mu_max` 进行上下限裁剪。该算法在收敛速度和稳态精度之间取得了更好的平衡。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| signal | np.ndarray | — | 输入的振动信号 |
| filter_len | int | 32 | FIR 滤波器的长度（阶数） |
| mu_init | float | 0.01 | 初始步长 |
| alpha | float | 0.97 | 步长记忆系数（0~1），越大则历史步长权重越高，变化越缓慢 |
| gamma | float | 5e-5 | 步长增长系数，控制误差对步长的影响程度 |
| mu_min | float | 1e-6 | 步长的下限值，防止步长过小导致停滞 |
| mu_max | float | 0.05 | 步长的上限值，防止步长过大导致发散 |
| delay | int | 1 | 参考信号延迟的采样点数 |
| max_iter | Optional[int] | None | 最大迭代次数；为 None 时使用信号长度 |

**返回值说明：**

返回一个元组 `(output, info)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| output | np.ndarray | 滤波后的信号 |
| info | Dict | 元信息字典，包含 `method`（"VSSLMS"）、`filter_len`、`mu_init`、`alpha`、`gamma`、`delay`、`kurtosis_before`、`kurtosis_after`、`noise_reduction_ratio`。若信号过短则返回包含 `error` 字段的字典 |

---

## 三、敏感分量选择模块（sensitive_selector.py）

### compute_correlation

```python
def compute_correlation(component: np.ndarray, original: np.ndarray) -> float:
    """互相关系数"""
```

**功能说明：**
计算分量信号与原始信号之间的互相关系数（Pearson 相关系数的绝对值）。通过对两个信号进行去均值和归一化处理后计算相关性。若任一信号的标准差接近于零（常数信号），则返回 0.0。该指标用于评估分量保留原始信号信息的程度，相关性越高说明分量越忠实于原始信号结构。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| component | np.ndarray | — | 分量信号（如 IMF、小波包节点系数等） |
| original | np.ndarray | — | 原始信号；若长度大于分量，则截取前 len(component) 个点 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 互相关系数的绝对值，范围 [0.0, 1.0] |

---

### compute_excess_kurtosis

```python
def compute_excess_kurtosis(component: np.ndarray) -> float:
    """Excess kurtosis（正态=0）"""
```

**功能说明：**
计算分量信号的 Excess Kurtosis（超额峭度，即峰态减 3）。正态分布的 excess kurtosis 为 0，大于 0 表示信号具有尖峰厚尾特性，通常与冲击型故障相关。该指标对轴承故障中的脉冲冲击非常敏感。若信号长度小于 4 或方差接近零，则返回 0.0。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| component | np.ndarray | — | 分量信号数组 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 超额峭度值；正态分布为 0，冲击型信号通常显著大于 0 |

---

### compute_envelope_entropy

```python
def compute_envelope_entropy(component: np.ndarray) -> float:
    """包络 Shannon 熵（越小 → 周期性越强 → 故障信息越丰富）"""
```

**功能说明：**
计算分量信号的包络 Shannon 熵。首先使用 Hilbert 变换提取信号的包络，然后对包络进行去均值和归一化处理，最后计算 Shannon 熵。熵值越小，表示包络的分布越集中、周期性越强，说明分量中可能含有周期性的故障调制信息。若信号长度小于 8，则返回 10.0（大值以排除选择）。该指标用于区分随机噪声（高熵）和周期性故障成分（低熵）。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| component | np.ndarray | — | 分量信号数组 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 包络 Shannon 熵值（bits）；越小表示周期性越强，故障信息可能越丰富 |

---

### compute_energy_ratio

```python
def compute_energy_ratio(component: np.ndarray, total_energy: float) -> float:
    """能量占比"""
```

**功能说明：**
计算分量信号的能量占原始信号总能量的比例。能量定义为信号平方和。该指标反映了分量在信号整体能量中的贡献程度，能量占比过低的分量可能仅包含噪声，在综合评分中可通过权重进行调节。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| component | np.ndarray | — | 分量信号数组 |
| total_energy | float | — | 原始信号的总能量（平方和） |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 分量能量占总能量之比，范围 [0.0, 1.0] 左右 |

---

### compute_center_freq

```python
def compute_center_freq(component: np.ndarray, fs: float) -> float:
    """分量中心频率（功率谱加权平均）"""
```

**功能说明：**
计算分量信号的中心频率，采用功率谱加权平均方法。对信号进行 FFT 后，以各频率点的功率（幅度平方）作为权重，计算频率的加权平均值。该中心频率反映了分量信号能量集中的频带位置。若信号长度小于 8，则返回 0.0。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| component | np.ndarray | — | 分量信号数组 |
| fs | float | — | 采样率（Hz） |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 功率谱加权平均中心频率（Hz） |

---

### compute_freq_match_score

```python
def compute_freq_match_score(center_freq: float, target_freq: float) -> float:
    """中心频率与目标频率的匹配度（越近越高，返回 0~1）"""
```

**功能说明：**
计算分量中心频率与目标频率（如齿轮啮合频率、轴承共振频率）的匹配度得分。使用相对误差进行度量：当相对误差 `delta < 0.05` 时得分为 1.0；当 `delta > 0.5` 时得分为 0.0；中间区域线性衰减。该指标帮助筛选出中心频率靠近目标故障特征频率的分量。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| center_freq | float | — | 分量的中心频率（Hz） |
| target_freq | float | — | 目标频率（Hz），如啮合频率 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 匹配度得分，范围 [0.0, 1.0]；越接近 1 表示中心频率越靠近目标频率 |

---

### _normalize

```python
def _normalize(values: List[float]) -> List[float]:
    """Min-max 归一化到 [0, 1]，全相同时返回 [0.5]"""
```

**功能说明：**
内部辅助函数，对一组数值进行 Min-Max 归一化，将其线性映射到 [0, 1] 区间。若所有值相同（最大值与最小值之差小于 1e-12），则返回全为 0.5 的列表。该函数用于统一不同量纲指标的量级，便于后续加权综合评分。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| values | List[float] | — | 待归一化的浮点数列表 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | List[float] | 归一化后的列表，每个元素范围 [0.0, 1.0] |

---

### score_components

```python
def score_components(
    components: List[np.ndarray],
    original: np.ndarray,
    fs: float,
    target_freq: float = 0.0,
    mode: str = "bearing",
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    对多个分量（WP节点/IMF/VMD模态）计算综合评分

    Args:
        components: 分量列表
        original: 原始信号
        fs: 采样率
        target_freq: 目标中心频率（啮合频率/共振频率），0=不使用频率匹配
        mode: "bearing" 或 "gear"，决定默认权重
        weights: 自定义权重覆盖默认值

    Returns:
        每个分量的评分详情列表
    """
```

**功能说明：**
对一组信号分量（如小波包节点、EMD IMF、VMD 模态）进行综合评分。首先计算每个分量的五项基础指标：互相关性、超额峭度、包络熵、能量占比、中心频率及频率匹配度。然后对各指标进行 Min-Max 归一化（包络熵取反转，因为越小越好），最后按预设权重加权求和得到综合评分。支持轴承和齿轮两种诊断模式的默认权重配置，也允许用户传入自定义权重。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| components | List[np.ndarray] | — | 信号分量列表，每个元素为一个分量数组 |
| original | np.ndarray | — | 原始信号 |
| fs | float | — | 采样率（Hz） |
| target_freq | float | 0.0 | 目标中心频率（如啮合频率）；为 0 时不使用频率匹配指标 |
| mode | str | "bearing" | 诊断模式，"bearing" 或 "gear"，决定默认权重配置 |
| weights | Optional[Dict[str, float]] | None | 自定义权重字典；为 None 时使用 mode 对应的默认权重 |

**返回值说明：**

返回一个列表，每个元素为一个字典，描述对应分量的评分详情：

| 键名 | 类型 | 说明 |
|------|------|------|
| index | int | 分量索引 |
| score | float | 综合评分（加权求和，归一化后） |
| corr | float | 与原始信号的互相关系数 |
| kurt | float | 超额峭度 |
| env_entropy | float | 包络 Shannon 熵 |
| energy_ratio | float | 能量占比 |
| center_freq | float | 中心频率（Hz） |
| freq_match | float | 频率匹配得分 |

---

### select_top_components

```python
def select_top_components(
    scored: List[Dict],
    top_n: int = 1,
    min_score: float = 0.0,
) -> List[int]:
    """选择评分最高的 top_n 个分量索引（得分 >= min_score）"""
```

**功能说明：**
从已评分的分量列表中选择综合评分最高的前 `top_n` 个分量索引。首先过滤掉得分低于 `min_score` 的分量；若过滤后为空（所有分量都低于阈值），则回退到从全部分量中选择最高评分的。返回按评分降序排列的索引列表。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| scored | List[Dict] | — | 由 `score_components` 返回的评分详情列表 |
| top_n | int | 1 | 要选择的分量数量 |
| min_score | float | 0.0 | 最低可接受评分，低于此值的分量被排除 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | List[int] | 选中分量的索引列表，按评分从高到低排列 |

---

### select_wp_sensitive_nodes

```python
def select_wp_sensitive_nodes(
    wp_coeffs: Dict[str, np.ndarray],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[str], List[Dict]]:
    """
    小波包节点敏感度选择

    Args:
        wp_coeffs: {节点路径: 系数数组}
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率（啮合频率/共振频率）
        top_n: 选择前N个

    Returns:
        (selected_paths, score_details)
    """
```

**功能说明：**
小波包节点敏感度选择便捷函数。将小波包分解后的节点系数字典转换为分量列表，调用 `score_components` 进行综合评分，然后使用 `select_top_components` 选出评分最高的前 `top_n` 个节点，最后将索引映射回节点路径字符串返回。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| wp_coeffs | Dict[str, np.ndarray] | — | 小波包节点系数字典，键为节点路径（如 "aaa"、"aad"），值为系数数组 |
| original | np.ndarray | — | 原始信号 |
| fs | float | — | 采样率（Hz） |
| mode | str | "bearing" | 诊断模式，"bearing" 或 "gear" |
| target_freq | float | 0.0 | 目标频率（Hz） |
| top_n | int | 1 | 选择前 N 个敏感节点 |

**返回值说明：**

返回一个元组 `(selected_paths, score_details)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| selected_paths | List[str] | 被选中的节点路径列表 |
| score_details | List[Dict] | 所有节点的评分详情列表，格式同 `score_components` 返回值 |

---

### select_emd_sensitive_imfs

```python
def select_emd_sensitive_imfs(
    imfs: List[np.ndarray],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[int], List[Dict]]:
    """
    EMD/CEEMDAN IMF 敏感度选择

    自动排除:
    - IMF0（极高频噪声，中心频率 > 0.4*fs）
    - 最后1~2个IMF（低频趋势，中心频率 < 2*rot_freq）

    Args:
        imfs: IMF列表
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率
        top_n: 选择前N个

    Returns:
        (selected_indices, score_details)
    """
```

**功能说明：**
EMD/CEEMDAN IMF 敏感度选择便捷函数。在标准评分的基础上，增加了针对 EMD 特性的自动排除规则：IMF0（第一个分量）若中心频率超过 0.4*fs，则视为极高频噪声，将其评分强制置为 0；最后 1~2 个 IMF 若中心频率过低（小于 max(target_freq*2, 5.0)），则视为低频趋势项，将其评分乘以 0.3 大幅降分（而非完全排除，因为可能含有齿轮信息）。这些规则帮助过滤掉 EMD 分解中常见的噪声层和趋势层。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| imfs | List[np.ndarray] | — | EMD/CEEMDAN 分解得到的 IMF 列表 |
| original | np.ndarray | — | 原始信号 |
| fs | float | — | 采样率（Hz） |
| mode | str | "bearing" | 诊断模式，"bearing" 或 "gear" |
| target_freq | float | 0.0 | 目标频率（Hz），用于低频趋势判断 |
| top_n | int | 1 | 选择前 N 个敏感 IMF |

**返回值说明：**

返回一个元组 `(selected_indices, score_details)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| selected_indices | List[int] | 被选中的 IMF 索引列表 |
| score_details | List[Dict] | 所有 IMF 的评分详情列表（已应用排除规则） |

---

### select_vmd_sensitive_modes

```python
def select_vmd_sensitive_modes(
    modes: List[np.ndarray],
    center_freqs: List[float],
    original: np.ndarray,
    fs: float,
    mode: str = "bearing",
    target_freq: float = 0.0,
    top_n: int = 1,
) -> Tuple[List[int], List[Dict]]:
    """
    VMD 模态敏感度选择

    利用 VMD 已知的中心频率信息增强 freq_match 评分

    Args:
        modes: VMD 模态列表
        center_freqs: 各模态中心频率（Hz）
        original: 原始信号
        fs: 采样率
        mode: "bearing" 或 "gear"
        target_freq: 目标频率
        top_n: 选择前N个

    Returns:
        (selected_indices, score_details)
    """
```

**功能说明：**
VMD 模态敏感度选择便捷函数。VMD 分解已经提供了各模态的精确中心频率信息，该函数利用这一优势，用 VMD 的已知中心频率覆盖通过 FFT 估计的中心频率，从而得到更准确的 `freq_match` 得分。随后根据 `freq_match` 的更新量对综合评分进行局部补偿修正，最后调用 `select_top_components` 选出最佳模态。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| modes | List[np.ndarray] | — | VMD 分解得到的模态列表 |
| center_freqs | List[float] | — | 各模态的已知中心频率列表（Hz），由 VMD 算法输出 |
| original | np.ndarray | — | 原始信号 |
| fs | float | — | 采样率（Hz） |
| mode | str | "bearing" | 诊断模式，"bearing" 或 "gear" |
| target_freq | float | 0.0 | 目标频率（Hz） |
| top_n | int | 1 | 选择前 N 个敏感模态 |

**返回值说明：**

返回一个元组 `(selected_indices, score_details)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| selected_indices | List[int] | 被选中的模态索引列表 |
| score_details | List[Dict] | 所有模态的评分详情列表（已用 VMD 精确中心频率修正） |

---

## 四、多通道一致性投票模块（channel_consensus.py）

### cross_channel_consensus

```python
def cross_channel_consensus(
    channel_results: List[Dict[str, Any]],
    min_channels_for_consensus: int = 2,
) -> Dict[str, Any]:
    """
    跨通道一致性投票

    统计各通道检出的故障类型，通过多数投票确定设备级故障标签。
    一致性高的故障类型获得置信度提升，不一致的故障类型降低权重。

    Args:
        channel_results: 各通道的诊断结果列表
        min_channels_for_consensus: 形成一致性所需的最少通道数

    Returns:
        包含一致性分析结果的字典
    """
```

**功能说明：**
跨通道一致性投票函数，用于多通道传感器诊断场景。遍历各通道的诊断结果，收集轴承故障（BPFO/BPFI/BSF 分别映射为外圈/内圈/滚动体故障）和齿轮故障的检出情况，统计每种故障类型被多少通道检测到。若某故障类型被至少 `min_channels_for_consensus` 个通道同时检出，则视为一致性故障，其置信度获得 10~15% 的提升。若仅有单通道检出某故障（多通道设备下），则降低该故障的设备级健康度扣分权重，并在建议中提示可能为传感器问题或局部噪声。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| channel_results | List[Dict[str, Any]] | — | 各通道的诊断结果列表，每个元素为一个通道的诊断结果字典 |
| min_channels_for_consensus | int | 2 | 形成一致性故障所需的最少通道数 |

**返回值说明：**

返回一个字典，包含以下键：

| 键名 | 类型 | 说明 |
|------|------|------|
| consensus_faults | Dict[str, Dict] | 各故障类型的一致性信息，包含 `channels`（检出通道索引列表）、`count`（检出通道数）、`ratio`（检出比例）、`is_consensus`（是否达到一致性） |
| single_channel_faults | List[str] | 仅单通道检出的故障类型列表 |
| consensus_fault_label | str | 一致性最高的故障标签；无一致性时为 "unknown" |
| consensus_boost | float | 置信度提升系数（≥1.0）；一致故障最多提升约 15% |
| single_channel_penalty | float | 单通道扣分降低系数；无一致性故障时扣减半（0.5） |
| recommendation_hint | str | 建议提示文本；单通道异常时提示检查传感器状态 |

---

## 五、Dempster-Shafer 证据理论融合模块（fusion/ds_fusion.py）

### EvidenceFrame

```python
class EvidenceFrame:
    """D-S 识别框架，包含故障类型集合与 Θ（全集 = 不确定性）。

    Θ 在 D-S 理论中是识别框架的全集 Ω，包含所有可能的假设（故障类型）。
    m(Θ) 表示"不确定属于哪种具体故障，任何故障都有可能"。
    交集运算时 A∩Θ=A（Θ包含所有元素），这是正确融合的关键。
    """

    def __init__(self, fault_types: List[str]):
        ...

    @property
    def all_elements(self) -> List[str]:
        """识别框架的全部元素（故障类型列表）。"""

    def make_singleton_key(self, fault: str) -> FrozenSet[str]:
        """生成单元素焦元键。"""

    def make_full_key(self) -> FrozenSet[str]:
        """Θ 焦元键（全集 = Ω = 所有故障类型的集合）。"""
```

**功能说明：**
D-S 证据理论的识别框架类。识别框架 `Θ`（Theta）是所有可能假设（故障类型）的集合，在代码中用 `frozenset(fault_types)` 表示。该类负责管理故障类型集合，并提供生成单元素焦元键和全集焦元键的方法。使用 `frozenset` 作为键可确保集合运算（交集、子集判断）的正确性，这是 Dempster 组合规则实现的基础。`A ∩ Θ = A` 的自然成立保证了融合时不确定性焦元的正确传播。

**参数说明（__init__）：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| fault_types | List[str] | — | 识别框架中包含的所有故障类型字符串列表 |

**方法说明：**

| 方法名 | 签名 | 说明 |
|--------|------|------|
| all_elements | `@property` → List[str] | 返回去重并排序后的故障类型列表 |
| make_singleton_key | `fault: str` → FrozenSet[str] | 为单个故障类型生成焦元键（单元素 frozenset） |
| make_full_key | `()` → FrozenSet[str] | 生成 Θ（全集）焦元键，包含所有故障类型 |

---

### BPA

```python
class BPA:
    """基本概率分配（Basic Probability Assignment / Mass Function）。

    每个诊断方法的结果映射为 BPA，表示该方法对各故障类型的置信度。
    满足：sum(m(A)) = 1, m(∅) = 0
    """

    def __init__(self, frame: EvidenceFrame, masses: Dict[FrozenSet[str], float]):
        ...

    def get_mass(self, focal: FrozenSet[str]) -> float:
        """获取指定焦元的质量。"""
```

**功能说明：**
基本概率分配（BPA，也称 Mass Function）类。每个诊断方法的结果被映射为一个 BPA 对象，表示该方法对各故障假设（焦元）的置信度分配。BPA 自动执行归一化：排除空集、确保总质量为 1，若总和小于 1 则补全到 Θ，若总和大于 1 则重新归一化。满足 D-S 理论的基本要求：`sum(m(A)) = 1` 且 `m(∅) = 0`。

**参数说明（__init__）：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| frame | EvidenceFrame | — | 所属的识别框架 |
| masses | Dict[FrozenSet[str], float] | — | 初始质量分配字典，键为焦元（frozenset），值为质量 |

**方法说明：**

| 方法名 | 签名 | 说明 |
|--------|------|------|
| get_mass | `focal: FrozenSet[str]` → float | 获取指定焦元的质量；若焦元不存在则返回 0.0 |

---

### dempster_combination

```python
def dempster_combination(bpa1: BPA, bpa2: BPA) -> Tuple[BPA, float]:
    """
    标准 Dempster 组合规则，融合两个 BPA。

    m_12(A) = Σ_{B∩C=A} m1(B)·m2(C) / (1 - K)
    K = Σ_{B∩C=∅} m1(B)·m2(C)  （冲突系数）

    参数:
        bpa1: 第一个 BPA
        bpa2: 第二个 BPA

    返回:
        (融合后的 BPA, 冲突系数 K)
    """
```

**功能说明：**
标准 Dempster 组合规则实现。对两个 BPA 进行融合：遍历两个 BPA 的所有焦元对，计算它们的交集；若交集非空，则将对应的质量乘积累加到新焦元上；若交集为空，则累加到冲突系数 K。最后将非空交集的质量和除以 `(1 - K)` 进行归一化。当 `K >= 1.0`（完全冲突）时，融合结果退化为纯 Θ（全不确定性）。该规则是 D-S 证据理论的核心运算。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| bpa1 | BPA | — | 第一个基本概率分配 |
| bpa2 | BPA | — | 第二个基本概率分配；需与 bpa1 使用同一识别框架 |

**返回值说明：**

返回一个元组 `(fused_bpa, K)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| fused_bpa | BPA | 融合后的基本概率分配 |
| K | float | 冲突系数，范围 [0.0, 1.0]；K 越接近 1 表示两证据冲突越严重 |

---

### murphy_average_combination

```python
def murphy_average_combination(bpas: List[BPA]) -> Tuple[BPA, float]:
    """
    Murphy 平均法：先对所有 BPA 取平均，再与自身反复组合。

    用于高冲突场景（K > 0.8），标准 Dempster 规则会产生不合理结果，
    Murphy 平均法通过平均化降低冲突，再逐次组合。

    步骤：
    1. 计算所有 BPA 的平均 BPA: m_avg(A) = Σ_i m_i(A) / n
    2. 用 m_avg 与 m_avg 组合 n-1 次（等效于与自身反复组合）

    参数:
        bpas: 待融合的 BPA 列表

    返回:
        (融合后的 BPA, 最终冲突系数)
    """
```

**功能说明：**
Murphy 平均修正法，用于解决高冲突场景下标准 Dempster 规则产生的反直觉结果。算法步骤为：首先计算所有 BPA 的算术平均 BPA；然后将平均 BPA 与自身进行 `n-1` 次 Dempster 组合。通过平均化处理，可以有效降低证据之间的冲突程度，使得融合结果更加稳健。当标准融合过程中检测到冲突系数 K > 0.8 时，系统会自动切换到 Murphy 平均法。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| bpas | List[BPA] | — | 待融合的 BPA 列表；空列表时返回纯 Θ |

**返回值说明：**

返回一个元组 `(fused_bpa, final_K)`：

| 返回值 | 类型 | 说明 |
|--------|------|------|
| fused_bpa | BPA | Murphy 平均法融合后的基本概率分配 |
| final_K | float | 融合过程中的最大冲突系数 |

---

### _classify_method

```python
def _classify_method(method_key: str) -> str:
    """判断方法类型：'bearing'、'gear' 或 'unknown'。

    方法键格式如 "none:envelope"、"wavelet:cpw"、"none:advanced" 等。
    """
```

**功能说明：**
内部辅助函数，根据方法键字符串判断诊断方法所属的类型类别。方法键通常采用 "去噪方法:算法名称" 的格式（如 "none:envelope"、"wavelet:cpw"）。函数提取冒号后的算法名部分，检查其是否包含轴承方法关键词（envelope、kurtogram、cpw、med、teager、spectral_kurtosis、bearing）或齿轮方法关键词（standard、advanced、gear），返回对应分类。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| method_key | str | — | 方法标识键字符串，如 "none:envelope" |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | str | 方法类型，"bearing"（轴承方法）、"gear"（齿轮方法）或 "unknown"（未知） |

---

### _map_hits_to_faults

```python
def _map_hits_to_faults(
    hits: List[str],
    method_type: str,
    fault_types: List[str],
) -> List[str]:
    """将诊断指标命中列表映射到故障类型集合中的具体故障。"""
```

**功能说明：**
内部辅助函数，将诊断算法检出的指标名称（如 "bpfo"、"ser"、"fm4" 等）映射到识别框架中的具体故障类型名称（如 "轴承外圈故障"、"齿轮磨损"）。使用预定义的 `BEARING_FAULT_NAMES` 和 `GEAR_FAULT_NAMES` 映射表进行转换，并过滤掉识别框架中不存在的故障类型，去重后返回。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| hits | List[str] | — | 诊断指标命中列表，如 ["bpfo", "bpfi"] |
| method_type | str | — | 方法类型，"bearing" 或 "gear"，决定使用哪个映射表 |
| fault_types | List[str] | — | 当前识别框架中的有效故障类型列表，用于过滤 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | List[str] | 映射后的故障类型名称列表，已去重且均在识别框架中 |

---

### build_bpa_from_method

```python
def build_bpa_from_method(
    method_key: str,
    method_result: Dict[str, Any],
    frame: EvidenceFrame,
) -> BPA:
    """
    从单个诊断方法结果构建 BPA。

    分配逻辑：
    - 轴承方法 confidence > 0.55 → 轴承故障 BPA（根据 hits 分配质量）
    - 轴承方法 confidence 0.2~0.55 → 弱证据 BPA（部分质量给故障，更多给 Θ）
    - 齿轮方法 confidence > 0.55 → 齿轮故障 BPA
    - 齿轮方法 confidence 0.2~0.55 → 弱证据 BPA
    - confidence < 0.2 → Θ 占主导（几乎无信息）
    - 时域证据（kurtosis > 12）→ 冲击型故障 BPA
    """
```

**功能说明：**
从单个诊断方法的结果构建基本概率分配（BPA）。根据方法的置信度 `confidence` 和异常标志 `abnormal`，采用分层分配策略：强证据（confidence > 0.55 且 abnormal）将质量主要分配给具体命中的故障类型或对应类别集合；弱证据（0.2~0.55）分配较少质量给故障，大部分保留给 Θ（不确定性）；极弱证据（< 0.2）几乎将所有质量分配给 Θ。该函数实现了从原始诊断结果到 D-S 证据理论形式的规范化映射。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| method_key | str | — | 方法标识键，如 "none:envelope" |
| method_result | Dict[str, Any] | — | 该方法的结果字典，需包含 `confidence`、`abnormal`、`hits` 等字段 |
| frame | EvidenceFrame | — | 识别框架对象 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | BPA | 构建完成的基本概率分配对象，质量已归一化 |

---

### build_time_domain_bpa

```python
def build_time_domain_bpa(
    time_features: Dict[str, Any],
    frame: EvidenceFrame,
) -> BPA:
    """
    从时域特征构建冲击型故障 BPA。

    当 kurtosis > 12 时，信号中存在明显冲击，
    分配质量到冲击型故障（轴承内圈、齿轮断齿等）。
    """
```

**功能说明：**
从时域特征（峭度、峰值因子）构建冲击型故障的 BPA。采用门控策略：当峭度 kurt > 12 时视为强冲击证据，分配质量到冲击型故障（轴承内圈、外圈、齿轮断齿）；当 5 < kurt ≤ 12 或 crest > 10 时视为中等冲击，微量分配；否则认为无冲击证据，主要分配给 Θ 并少量分配给 "正常" 状态。冲击质量的大小随峭度值动态变化（kurt=12 时约 0.15，kurt=52 时约 0.3）。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| time_features | Dict[str, Any] | — | 时域特征字典，需包含 `kurtosis`（峭度）和 `crest_factor`（峰值因子） |
| frame | EvidenceFrame | — | 识别框架对象 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | BPA | 基于时域冲击特征构建的基本概率分配对象 |

---

### compute_belief

```python
def compute_belief(bpa: BPA, focal: FrozenSet[str]) -> float:
    """
    信念函数 Bel(A) = Σ_{B⊆A} m(B)
    表示对 A 的最低置信度。
    """
```

**功能说明：**
计算 D-S 证据理论中的信念函数 Bel(A)。信念值表示对假设 A 的最低置信度，计算方式为对所有 A 的子集焦元 B 的质量求和。信念函数满足 `Bel(A) ≤ Pl(A)`，构成了对假设 A 置信区间的下限。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| bpa | BPA | — | 基本概率分配对象 |
| focal | FrozenSet[str] | — | 目标焦元 A，用 frozenset 表示 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 信念值 Bel(A)，范围 [0.0, 1.0] |

---

### compute_plausibility

```python
def compute_plausibility(bpa: BPA, focal: FrozenSet[str]) -> float:
    """
    似然函数 Pl(A) = Σ_{B∩A≠∅} m(B)
    表示对 A 的最高可能置信度。
    """
```

**功能说明：**
计算 D-S 证据理论中的似然函数 Pl(A)。似然值表示对假设 A 的最高可能置信度，计算方式为对所有与 A 交集非空的焦元 B 的质量求和。似然函数满足 `Bel(A) ≤ Pl(A)`，构成了对假设 A 置信区间的上限。信念与似然之间的差值 `[Bel(A), Pl(A)]` 反映了关于假设 A 的不确定性程度。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| bpa | BPA | — | 基本概率分配对象 |
| focal | FrozenSet[str] | — | 目标焦元 A，用 frozenset 表示 |

**返回值说明：**

| 返回值 | 类型 | 说明 |
|--------|------|------|
| — | float | 似然值 Pl(A)，范围 [0.0, 1.0] |

---

### dempster_shafer_fusion

```python
def dempster_shafer_fusion(
    method_results: Dict[str, Dict],
    fault_types: List[str] = None,
    time_features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    D-S 证据理论融合：将多种诊断方法的结果融合为综合故障概率分布。

    参数:
        method_results: 各诊断方法的结果字典
        fault_types: 识别框架的故障类型集合，默认使用 DEFAULT_FAULT_TYPES
        time_features: 时域特征字典（可选），用于构建冲击型 BPA

    返回:
        融合结果字典，包含 BPA、信念、似然、冲突系数、主导故障等
    """
```

**功能说明：**
D-S 证据理论融合的主入口函数。将多种诊断方法的结果通过 Dempster-Shafer 证据理论融合为综合故障概率分布。处理流程：1）建立识别框架；2）从各方法结果过滤错误项后构建 BPA，过滤纯 Θ（无信息）的 BPA；3）若有的话，构建时域证据 BPA；4）使用标准 Dempster 规则逐步融合所有 BPA，记录最大冲突系数；5）若最大冲突系数 K > 0.8，自动切换到 Murphy 平均修正法；6）计算各故障类型的 BPA、信念值和似然值；7）确定主导故障类型。空输入或无有效 BPA 时返回纯不确定性（Θ = 1.0）的安全结果。

**参数说明：**

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| method_results | Dict[str, Dict] | — | 各诊断方法的结果字典，键为方法标识（如 "none:envelope"），值为包含 `confidence`、`abnormal`、`hits` 的结果字典 |
| fault_types | List[str] | None | 识别框架的故障类型集合；为 None 时使用模块默认的 `DEFAULT_FAULT_TYPES` |
| time_features | Optional[Dict[str, Any]] | None | 时域特征字典（可选），包含 `kurtosis` 和 `crest_factor`，用于构建冲击型 BPA |

**返回值说明：**

返回一个字典，包含以下键：

| 键名 | 类型 | 说明 |
|------|------|------|
| fused_bpa | Dict[str, float] | 融合后的基本概率分配，键为故障类型（含 "Θ"），值为概率质量 |
| fused_belief | Dict[str, float] | 各故障类型的信念值 Bel |
| fused_plausibility | Dict[str, float] | 各故障类型的似然值 Pl |
| conflict_coefficient | float | 融合过程中的最大冲突系数 K |
| dominant_fault | str | 概率最高的故障类型（排除 "正常"）；若所有故障概率极低则返回 "正常" |
| dominant_probability | float | 主导故障的概率质量 |
| uncertainty | float | Θ（不确定性）的概率质量 |
