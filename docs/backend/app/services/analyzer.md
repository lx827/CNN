# `analyzer.py` — 综合分析引擎

**对应源码**：`cloud/app/services/analyzer.py`

## 函数

### `_safe_result`

```python
def _safe_result(msg="分析失败", health=100) -> dict
```

- **返回值**：`dict` — 崩溃安全默认结果

### `_params_valid`

```python
def _params_valid(params: Optional[Dict], kind: str) -> bool
```

- **返回值**：`bool`
- **说明**：判断轴承/齿轮参数有效性

### `analyze_device`

```python
def analyze_device(
    channels_data: Dict[str, List[float]],
    sample_rate: int = 25600,
    device = None,
    rot_freq: Optional[float] = None,
    denoise_method: str = ""
) -> dict
```

- **参数**：
  - `channels_data` — 通道数据 `{"ch1": [...], "ch2": [...], ...}`
  - `sample_rate` — 采样率
  - `device` — Device 对象（含齿轮/轴承参数）
  - `rot_freq` — 转频（可选）
  - `denoise_method` — 去噪方法
- **返回值**：`{health_score, status, fault_probabilities, imf_energy, order_analysis, rot_freq}`
- **说明**：综合分析主入口。优先 NN → DiagnosisEngine → rule_based 回退
