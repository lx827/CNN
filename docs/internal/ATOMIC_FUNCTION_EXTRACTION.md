# 原子函数提取规范 —— 测试文件不应重写云端逻辑

> 问题类型：架构债务（封装粒度错误）
> 严重程度：中 —— 导致测试与云端逻辑漂移，维护成本倍增

---

## 1. 问题现象

测试文件（`tests/diagnosis/foundation/`）中频繁出现以下模式：

```python
# tests/diagnosis/foundation/layer2/test_bearing_correctness.py

def _find_peak_snr(freqs, amps, target, tol_hz=3.0):
    """在目标频率附近找峰值并计算 SNR"""
    freqs = np.array(freqs)
    amps = np.array(amps)
    mask = np.abs(freqs - target) <= tol_hz
    if not np.any(mask):
        return 0.0, 0.0
    peak_idx = np.argmax(amps[mask])
    peak_amp = amps[mask][peak_idx]
    median_amp = np.median(amps)
    snr = peak_amp / (median_amp + 1e-12)
    return float(freqs[mask][peak_idx]), snr
```

这段代码**完全复制了云端 `signal_utils.py:102-153` 中 `find_peaks_in_spectrum` 的核心逻辑**，只是把它"简化"成了只返回两个标量的版本。

### 违反的铁律

> **SKILL.md / TEST_ARCHITECTURE.md 核心原则**：测试只能 `import` 和调用 `cloud/app/` 下的现有函数，**禁止在测试文件中重写算法逻辑**（如自己写 FFT、自己写峰值检测）。

---

## 2. 根因分析

问题**不在于"云端没有这个算法"**，而在于**封装粒度太粗**。

### 2.1 `find_peaks_in_spectrum` 一次做了三件事

```python
def find_peaks_in_spectrum(freqs, amps, target_freq, tolerance_hz=2.0, n_harmonics=5):
    # 1. 搜索基频峰值 ← 测试只需要这个
    # 2. 搜索谐波族   ← 测试不需要
    # 3. 搜索边带     ← 测试不需要
    return {
        "fundamental": {"freq": ..., "amp": ..., "snr": ...},
        "harmonics": [...],
        "sidebands": [...],
    }
```

测试只想做一件事："在目标频率附近找一个峰值，告诉我频率和 SNR"。但云端没有提供这个**原子函数**，测试被迫自己重写。

### 2.2 同样的逻辑以不同名字重复出现

| 文件 | 本地函数名 | 逻辑 |
|------|-----------|------|
| `test_bearing_correctness.py` | `_find_peak_snr` | `argmax` + `median` → SNR |
| `test_bearing_advanced_correctness.py` | `_find_peak_snr` | 同上 |
| `test_order_tracking_correctness.py` | `_find_order_peak` | 同上，只是把 `freqs` 换成 `order_axis` |
| `signal_utils.py:130` | `find_peaks_in_spectrum` 内部 | 同上 |
| `signal_utils.py:248` | `_detect_impact_frequency` 内部 | 同上 |
| `engine.py:962` | `_estimate_rot_freq` 内部 | 同上 |

**同一套逻辑在项目中至少重写了 6 次**。

---

## 3. 影响范围

### 3.1 已确认的重写实例

| 测试文件 | 本地函数 | 云端对应 | 状态 |
|---------|---------|---------|------|
| `layer2/test_bearing_correctness.py` | `_find_peak_snr` | `find_peaks_in_spectrum` | ✅ 已修复 |
| `layer2/test_bearing_advanced_correctness.py` | `_find_peak_snr` | `find_peaks_in_spectrum` | ✅ 已修复 |
| `layer2/test_order_tracking_correctness.py` | `_find_order_peak` | `_search_peak_in_band` | ✅ 已修复 (2026-05-19) |
| `layer2/test_planetary_demod_correctness.py` | `_make_planetary_signal` | 无独立函数，合成信号生成器 | ⚠️ 边界 case |
| `layer3/test_ensemble_integration.py` | `_healthy_signal`, `_impact_train` | 无独立函数 | ⚠️ 边界 case |
| `layer1/test_modality_bearing_correctness.py` | `_make_bearing_signal` | `synthetic_signals:bearing_outer_race` | ⚠️ 轻微重复 |

### 3.2 云端内联重复模式（应提取为原子函数）

```
模式A: mask 区域内搜索峰值
  np.argmax(arr[mask])
  freqs[mask][np.argmax(...)]
  → 出现位置：signal_utils.py:130, 248, 442, 450, 487, 489
  → 出现位置：engine.py:962
  → 出现位置：test_order_tracking_correctness.py:40

模式B: 中位数背景估计
  background = np.median(amps)
  → 出现位置：signal_utils.py:125, 159
  → 出现位置：engine.py:793, 894
  → 出现位置：bearing_cyclostationary.py:259, 300
  → 出现位置：bearing_sideband.py:157
  → 出现位置：gear/msb.py:234

模式C: SNR = peak / background
  → 和模式B成对出现，每次手动除一遍
```

---

## 4. 修复方案

### 4.1 目标架构：原子函数 + 组合函数

```
Layer 0: 原子函数（不可再分的基本操作）
  ├── _search_peak_in_band(freqs, amps, target, tolerance)
  ├── _estimate_background(spectrum, method="median")
  └── _compute_peak_snr(peak_amp, spectrum, method="median")

Layer 1: 组合函数（调用原子函数组装复杂逻辑）
  ├── find_peaks_in_spectrum(...)     ← 调用 _search_peak_in_band + 谐波搜索 + 边带搜索
  ├── _detect_impact_frequency(...)   ← 调用 _search_peak_in_band
  └── _estimate_rot_freq(...)         ← 调用 _search_peak_in_band
```

### 4.2 具体改动步骤

#### Step 1: 在 `signal_utils.py` 新增三个原子函数

```python
def _search_peak_in_band(freqs, amps, target, tolerance):
    """
    原子函数：在目标值附近的频带内搜索峰值。

    参数:
        freqs: 频率/阶次轴 (np.ndarray)
        amps:  幅值谱 (np.ndarray)
        target: 目标搜索中心值 (float)
        tolerance: 搜索容差 (float)

    返回:
        dict or None: {"freq": float, "amp": float}
                      未找到时返回 None
    """
    freqs = np.asarray(freqs)
    amps = np.asarray(amps)
    mask = np.abs(freqs - target) <= tolerance
    if not np.any(mask):
        return None
    idx = np.argmax(amps[mask])
    abs_idx = np.where(mask)[0][idx]
    return {"freq": float(freqs[abs_idx]), "amp": float(amps[abs_idx])}


def _estimate_background(spectrum, method="median"):
    """
    原子函数：估计频谱背景水平。

    参数:
        spectrum: 频谱幅值数组 (np.ndarray)
        method: "median" | "mean" | "q75"

    返回:
        float: 背景估计值（保证 > 0）
    """
    if method == "median":
        bg = np.median(spectrum)
    elif method == "mean":
        bg = np.mean(spectrum)
    else:
        bg = np.percentile(spectrum, 75)
    return max(bg, 1e-12)


def _compute_peak_snr(peak_amp, spectrum, method="median"):
    """
    原子函数：计算峰值信噪比。

    参数:
        peak_amp: 峰值幅值 (float)
        spectrum: 完整频谱（用于估计背景）(np.ndarray)
        method: 背景估计方法

    返回:
        float: SNR = peak_amp / background
    """
    bg = _estimate_background(spectrum, method)
    return peak_amp / bg
```

#### Step 2: 重构 `find_peaks_in_spectrum` 调用原子函数

```python
def find_peaks_in_spectrum(freqs, amps, target_freq, tolerance_hz=2.0, n_harmonics=5):
    result = {"fundamental": None, "harmonics": [], "sidebands": []}

    # 基频搜索 → 调用原子函数
    peak = _search_peak_in_band(freqs, amps, target_freq, tolerance_hz)
    if peak:
        snr = _compute_peak_snr(peak["amp"], amps)
        result["fundamental"] = {
            "freq": peak["freq"],
            "amp": peak["amp"],
            "snr": snr,
        }

    # 谐波搜索 → 复用原子函数
    for h in range(2, n_harmonics + 1):
        hf = target_freq * h
        if hf > freqs[-1]:
            break
        peak_h = _search_peak_in_band(freqs, amps, hf, tolerance_hz)
        if peak_h:
            result["harmonics"].append({
                "freq": peak_h["freq"],
                "amp": peak_h["amp"],
                "order": h,
            })

    return result
```

#### Step 3: 替换测试文件中的本地重写

**`test_order_tracking_correctness.py` 的替换：**

```python
# 删除本地函数 _find_order_peak

# 替换调用处
# 之前：
#   peak_f, peak_amp = _find_order_peak(order_axis, spectrum, target_order, tol=0.5)

# 之后：
found = _search_peak_in_band(np.array(order_axis), np.array(spectrum), target_order, tolerance=0.5)
peak_f = found["freq"] if found else 0.0
peak_amp = found["amp"] if found else 0.0
```

#### Step 4: 逐步替换云端所有内联的 `np.argmax(arr[mask])`

搜索并替换以下模式：

- `np.argmax(arr[mask])` → `_search_peak_in_band`
- `np.median(amps)` 作为背景 → `_estimate_background`
- `peak_amp / np.median(spectrum)` → `_compute_peak_snr`

出现位置：

- `signal_utils.py:248` (`_detect_impact_frequency`)
- `signal_utils.py:442, 450, 487, 489` (`zoom_fft_analysis` 内部)
- `engine.py:962` (`_estimate_rot_freq`)
- `bearing_cyclostationary.py:259, 300`
- `bearing_sideband.py:157`
- `gear/msb.py:234`

---

## 5. 云端全量扫描结果（2026-05-19）

> 扫描范围：`cloud/app/services/diagnosis/**/*.py`（共 33 个文件）
> 扫描目标：已内联实现但未提取为原子函数的通用逻辑

### 5.1 已修复（2026-05-19）

| 模式 | 原子函数 | 出现位置 | 说明 |
|------|---------|---------|------|
| mask 区域内搜索峰值 | `_search_peak_in_band` | signal_utils.py:130, 248, 442, 450, 487, 489; engine.py:962; order_tracking.py:204; planetary_demod.py:989, 1021 | 统一提取为原子函数 |
| 中位数背景估计 | `_estimate_background` | signal_utils.py:125, 159; engine.py:793, 894; bearing_cyclostationary.py:259, 300; bearing_sideband.py:157; gear/msb.py:234; bearing.py:349, 350 | 统一提取为原子函数 |
| SNR = peak / background | `_compute_peak_snr` | 与背景估计成对出现的位置 | 统一提取为原子函数 |

### 5.2 待修复 —— 函数重复定义

同一套逻辑在**不同文件中各自定义了一份**，违反 DRY 原则。

| 逻辑 | 云端定义A | 云端定义B | 建议 |
|------|----------|----------|------|
| 频带能量计算 | `signal_utils.py:280` `_band_energy` | `rule_based.py:307` `_band_energy` | ✅ 已修复 (2026-05-19) |
| 阶次带能量计算 | `signal_utils.py:290` `_order_band_energy` | `rule_based.py:45` `_order_band_energy` | ✅ 已修复 (2026-05-19) |
| 去直流 | `signal_utils.py:91` `remove_dc` | `features.py:276` `remove_dc` (实际是线性去趋势) | ✅ 已修复 (2026-05-19) — 改为 `prepare_signal(detrend=True)` |
| Excess 峭度 | `emd_denoise.py:605` `_excess_kurtosis` | `sensitive_selector.py:58` `compute_excess_kurtosis` | ⬜ 待修复 |

### 5.3 待修复 —— 内联计算（应调用已有原子函数）

云端**已有原子函数**，但调用方选择内联重写。

| 内联模式 | 出现位置 | 已有原子函数 | 修复方式 |
|---------|---------|-------------|---------|
| `np.sqrt(np.mean(amp_arr ** 2))` | `engine.py:868` `env_rms` | `signal_utils.py:251` `rms()` | ✅ 已修复 (2026-05-19) |
| `peak_amp / env_rms` | `engine.py:867` `env_cf` | `signal_utils.py:261` `crest_factor()` | 改为 `crest_factor(amp_arr)` 或 `peak_value(amp_arr) / rms(amp_arr)` |
| `np.mean((envelope - e_mean) ** 4) / (e_var ** 2 + 1e-12) - 3` | `gear/planetary_demod.py:163, 312, 686, 1629`（共 4 处） | `signal_utils.py:239` `kurtosis(signal, fisher=False)` | 改为 `kurtosis(envelope, fisher=False)` |
| `np.median(np.abs(detail)) / 0.6745` | `preprocessing.py:52` | 应提取为 `_estimate_noise_mad(arr)` | 新增原子函数，两处共用 |
| `np.median(np.abs(arr - smoothed)) / 0.6745` | `savgol_denoise.py:45` | 同上 `_estimate_noise_mad` | 同上 |
| `np.median(arr)` + `1.4826 * np.median(np.abs(arr - median))` | `features.py:111-112` | 应提取为 `_median_mad(arr)` | 新增原子函数，与 order_tracking.py:90-91 共用 |
| `np.std(arr) / np.std(arr - smoothed)` | `savgol_denoise.py:46` `snr_imp` | 无直接对应 | 可提取为 `_snr_by_residual_std(original, denoised)` |

### 5.4 待修复 —— 参数传递不一致

| 问题 | 出现位置 | 说明 |
|------|---------|------|
| `bandpass_filter` 的 `order` 参数不统一 | `gear/planetary_demod.py:153` 用 `order=4`，其他多数用默认 `order=6` | 应统一为常量或配置项 |
| `prepare_signal` 的 `detrend` 参数默认值 | `signal_utils.py:101` 默认 `detrend=False`，但某些调用方期望去趋势 | 文档中明确标注行为 |

### 5.5 合理边界 case（不修复）

以下内联调用属于合理情况，**不纳入修复范围**：

| 模式 | 出现位置 | 不修复理由 |
|------|---------|-----------|
| `np.fft.rfft` / `np.fft.irfft` | `bearing_cyclostationary.py`, `gear/planetary_demod.py`, `vmd_denoise.py`, `preprocessing.py` | 需要复数谱或特殊窗函数，通用封装 `compute_fft_spectrum` 不满足需求 |
| `np.fft.rfftfreq` | `bearing_cyclostationary.py`, `gear/planetary_demod.py` | 与 `compute_fft_spectrum` 配套使用，单独调用属于合理拆分 |
| `np.mean((X_segments * np.conj(X_segments)), axis=0)` | `gear/planetary_demod.py:854` | 循环平稳专用计算，不具备通用性 |

---

## 6. 验收标准

修复完成后，满足以下条件：

- [x] `tests/diagnosis/foundation/` 下**没有任何**测试文件包含 `np.argmax` + `np.median` 组合的本地辅助函数（2026-05-19 已完成）
- [x] `signal_utils.py` 新增 `_search_peak_in_band`、`_estimate_background`、`_compute_peak_snr` 三个原子函数（2026-05-19 已完成）
- [x] `find_peaks_in_spectrum` 内部调用上述原子函数，功能等价（2026-05-19 已完成）
- [x] `test_order_tracking_correctness.py` 的 `_find_order_peak` 已改为委托 `_search_peak_in_band`（2026-05-19 已完成）
- [x] 云端代码中 6 处内联的 `np.argmax(arr[mask])` 模式已替换为原子函数（signal_utils.py ×4, engine.py ×2）（2026-05-19 已完成）
- [x] 所有 P0 回归测试通过（`test_none_params.py`, `test_cpw_robustness.py`, `test_varying_speed_order.py`）（2026-05-19 已完成）
- [x] Layer 1 全部 151 测试通过，通过率不变（2026-05-19 已完成）

---

## 7. 如何避免未来再犯

**审查 checklist（每次新增测试文件时自查）：**

- [ ] 测试文件中是否有 `np.argmax`/`np.median`/`np.fft` 等信号处理原语？
- [ ] 这些原语是否在 `signal_utils.py` 或 `preprocessing.py` 中已有对应函数？
- [ ] 如果云端函数"几乎能用"但返回格式太复杂，应该**提取原子函数**而不是自己重写
- [ ] 测试中的 `def _` 辅助函数是否包含任何数学/信号处理逻辑？如果是，应该移到云端

**判断准则：**

> 如果测试文件中的 `def _xxx` 函数可以被另一个测试文件复用，或者它的逻辑出现在云端任何 `.py` 文件中，那么它**必须**是云端函数，不是测试文件本地函数。
