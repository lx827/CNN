# `vmd_denoise.py` — VMD 分解

**对应源码**：`cloud/app/services/diagnosis/vmd_denoise.py`

## 函数

### `_vmd_core`

```python
def _vmd_core(
    f: np.ndarray,
    alpha: float,
    tau: float,
    K: int,
    DC: bool,
    init: str,
    tol: float,
    max_iter: int = 200,
) -> Tuple[np.ndarray, np.ndarray]
```

- **返回值**：`(u, u_hat)`
- **说明**：VMD 核心 ADMM 算法（内存优化版）

### `vmd_decompose`

```python
def vmd_decompose(
    signal: np.ndarray,
    K: int = 5,
    alpha: int = 2000,
    tau: float = 0.0,
    tol: float = 1e-7,
) -> Tuple[np.ndarray, np.ndarray]
```

- **返回值**：`(modes, u_hat)`
- **说明**：VMD 分解入口（信号截断至 51200 点防 OOM）

### `vmd_denoise`

```python
def vmd_denoise(
    signal: np.ndarray,
    K: int = 5,
    alpha: int = 2000,
    corr_threshold: float = 0.3,
    kurt_threshold: float = 3.0,
) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：VMD 降噪（IMF 筛选重构：相关性>0.3 或峭度>3.0）

### `vmd_select_impact_mode`

```python
def vmd_select_impact_mode(
    signal: np.ndarray,
    fs: int,
    K: int = 5,
    alpha: int = 2000,
) -> Tuple[np.ndarray, int]
```

- **返回值**：`(mode, best_idx)`
- **说明**：选择峭度最大的冲击模态
