# `nn_predictor.py` — 神经网络预留接口

**对应源码**：`cloud/app/services/nn_predictor.py`

## 函数

### `_load_model`

```python
def _load_model() -> Any
```

- **说明**：延迟加载神经网络模型（当前仅检查文件存在性）

### `_preprocess`

```python
def _preprocess(signal: np.ndarray, sample_rate: int = 1000) -> np.ndarray
```

- **返回值**：`np.ndarray`
- **说明**：截断/填充到 5000 点，Z-score 标准化，float32

### `predict`

```python
def predict(
    channels_data: Dict[str, list],
    sample_rate: int = 1000
) -> Optional[Dict]
```

- **返回值**：`Optional[Dict]` — 未启用或加载失败返回 None
- **说明**：神经网络预测主函数
