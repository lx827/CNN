# `preprocessing.py` — 预处理与降噪

**对应源码**：`cloud/app/services/diagnosis/preprocessing.py`

## 函数

### `wavelet_denoise`

```python
def wavelet_denoise(
    signal: np.ndarray,
    wavelet: str = "db8",
    level: Optional[int] = None,
    threshold_mode: Literal["soft", "hard", "improved"] = "soft",
    threshold_scale: float = 1.0,
) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：小波阈值去噪（soft/hard/improved 三种模式，σ 鲁棒估计）

### `cepstrum_pre_whitening`

```python
def cepstrum_pre_whitening(
    signal: np.ndarray,
    fs: float,
    comb_frequencies: Optional[list] = None,
    notch_width_ratio: float = 0.02,
) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：CPW 倒频谱预白化，消除齿轮啮合/轴频等确定性干扰

### `minimum_entropy_deconvolution`

```python
def minimum_entropy_deconvolution(
    signal: np.ndarray,
    filter_len: int = 64,
    max_iter: int = 30,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray]
```

- **返回值**：`(滤波后信号, 滤波器系数)`
- **说明**：MED 最小熵解卷积，使输出峭度最大化

### `cascade_wavelet_vmd`

```python
def cascade_wavelet_vmd(
    signal: np.ndarray,
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    vmd_K: int = 5,
    vmd_alpha: int = 2000,
    vmd_corr_threshold: float = 0.3,
    vmd_kurt_threshold: float = 3.0,
) -> Tuple[np.ndarray, Dict]
```

- **返回值**：`(去噪信号, 元信息)`
- **说明**：小波+VMD 级联降噪（推荐强高斯噪声场景）

### `cascade_wavelet_lms`

```python
def cascade_wavelet_lms(
    signal: np.ndarray,
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    lms_filter_len: int = 32,
    lms_step_size: float = 0.01,
    lms_delay: int = 1,
) -> Tuple[np.ndarray, Dict]
```

- **返回值**：`(去噪信号, 元信息)`
- **说明**：小波+LMS 级联降噪

### `joint_denoise`

```python
def joint_denoise(
    signal: np.ndarray,
    strategy: Literal["wavelet_vmd", "wavelet_lms", "wavelet", "vmd", "ceemdan_wp", "eemd"] = "wavelet_vmd",
    wavelet: str = "db8",
    wavelet_level: Optional[int] = None,
    wavelet_mode: Literal["soft", "hard", "improved"] = "soft",
    vmd_K: int = 5,
    vmd_alpha: int = 2000,
    lms_filter_len: int = 32,
    lms_step_size: float = 0.01,
) -> Tuple[np.ndarray, Dict]
```

- **返回值**：`(去噪信号, 元信息)`
- **说明**：联合降噪统一入口
