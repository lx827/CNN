# `core/__init__.py` — 算法数据契约

**对应源码**：`cloud/app/algorithms/core/__init__.py`

## `Spectrum`

```python
Spectrum(
    frequency_hz: NDArray[float64],
    amplitude: NDArray[float64],
    amplitude_unit: str = "input_signal",
    scaling: str = "single_sided_amplitude",
)
```

频率轴和幅值必须是一维、等长、非空、有限值，频率严格递增且等间隔，幅值非负。构造对象只保存数组引用，不复制底层数据。

`truncated(max_frequency_hz)` 仅返回频率切片，供业务层生成展示结果；诊断分析必须先使用完整有效频谱完成，不能把该截断用于改变诊断范围。

## `FrequencyBand`

`FrequencyBand(low_hz, high_hz)` 表示实际执行的频带，提供 `center_hz` 和 `width_hz`。必须满足 `0 < low_hz < high_hz`。

## `SpectralPeak`

`SpectralPeak(frequency_hz, amplitude, snr)` 表示局部谱峰及其相对背景幅值的线性比，`snr` 不是 dB。
