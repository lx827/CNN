# Diagnosis Engine — 故障诊断算法库

> 本文档说明 `cloud/app/services/diagnosis/` 模块的算法架构、各子模块职责与使用方式。

---

## 1. 模块概述

诊断算法库是系统的核心分析引擎，负责从振动信号中提取特征、识别故障类型、生成健康度评分和维护建议。支持**有参数诊断**（需要设备配置轴承/齿轮参数）和**无参数统计诊断**（纯信号统计指标）两种模式。

---

## 2. 目录结构

```
diagnosis/
├── __init__.py           # 公共导出：DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod, DiagnosisStrategy
├── engine.py             # DiagnosisEngine 主调度器（轴承/齿轮/综合分析入口）
├── bearing.py            # 轴承诊断算法（包络谱 / Fast Kurtogram / CPW / MED）
├── gear/                 # 齿轮诊断
│   ├── __init__.py       # 齿轮诊断公共接口
│   └── metrics.py        # FM0 / FM4 / CAR / M6A / M8A / SER 指标计算
├── preprocessing.py      # 信号预处理（小波去噪 / CPW / MED）
├── vmd_denoise.py        # VMD 变分模态分解去噪
├── features.py           # 时域/频域/阶次/包络特征提取
├── rule_based.py         # 规则诊断算法（回退方案，纯统计指标）
├── health_score.py       # 综合健康度评分 (0-100)
├── recommendation.py     # 诊断建议生成
├── order_tracking.py     # 阶次跟踪算法（单帧/多帧/变速）【冻结，禁止修改】
└── signal_utils.py       # 通用信号处理辅助函数
```

---

## 3. DiagnosisEngine 主调度器

### 3.1 初始化参数

```python
engine = DiagnosisEngine(
    strategy="standard",           # 诊断策略：standard / advanced / expert
    bearing_method=BearingMethod.ENVELOPE,  # 轴承方法
    gear_method=GearMethod.STANDARD,        # 齿轮方法
    denoise_method=DenoiseMethod.NONE,      # 去噪方法
    bearing_params=None,           # 轴承参数 {n, d, D, alpha}
    gear_teeth=None,               # 齿轮参数 {input, output}
)
```

### 3.2 分析方法

| 方法 | 说明 | 缓存字段 |
|------|------|----------|
| `analyze_bearing(signal, sample_rate)` | 轴承故障诊断 | 间接（通过 analyze_comprehensive） |
| `analyze_gear(signal, sample_rate)` | 齿轮故障诊断 | 间接（通过 analyze_comprehensive） |
| `analyze_comprehensive(signal, sample_rate)` | 综合分析（轴承+齿轮+时域特征+健康度） | `diagnosis.engine_result` |
| `analyze_all_methods(signal, sample_rate)` | 全算法对比（4种轴承+2种齿轮方法） | `diagnosis.full_analysis` |

---

## 4. 轴承诊断（bearing.py）

### 4.1 方法对比

| 方法 | 适用场景 | 特点 |
|------|----------|------|
| **标准包络谱** (`envelope`) | 常规轴承故障检测 | 快速，稳定，适合大多数场景 |
| **Fast Kurtogram** (`kurtogram`) | 自适应频带选择 | 自动寻找最优共振频带，对未知故障敏感 |
| **CPW** (`cpw`) | 强噪声环境下的轴承诊断 | 倒频谱预白化 + 包络，消除传递路径影响 |
| **MED** (`med`) | 脉冲信号增强 | 最小熵解卷积，增强周期性冲击成分 |

### 4.2 故障特征频率计算

当提供 `bearing_params = {n, d, D, alpha}` 时：

- **BPFO**（外圈）：`f_o = (n/2) * f_r * (1 - d/D * cos(alpha))`
- **BPFI**（内圈）：`f_i = (n/2) * f_r * (1 + d/D * cos(alpha))`
- **BSF**（滚动体）：`f_b = (D/(2d)) * f_r * (1 - (d/D * cos(alpha))^2)`
- **FTF**（保持架）：`f_c = (1/2) * f_r * (1 - d/D * cos(alpha))`

当无参数时，回退到**统计诊断模式**：基于包络谱峰值 SNR、峭度、高频能量比等指标判断异常。

---

## 5. 齿轮诊断（gear/）

### 5.1 诊断指标

| 指标 | 说明 | 阈值判定 |
|------|------|----------|
| **FM0** | 零阶傅里叶模量（粗故障检测） | > 阈值提示齿轮面磨损 |
| **FM4** | 四阶矩指标（局部故障检测） | > 阈值提示齿面剥落/点蚀 |
| **CAR** | 倒频谱幅值比 | > 阈值提示齿轮调制故障 |
| **M6A** / **M8A** | 高阶矩指标 | 辅助判断局部故障严重程度 |
| **SER** | 边频带能量比 | > 阈值提示齿轮偏心/不对中 |

### 5.2 有参数 vs 无参数

- **有参数**（提供 `gear_teeth = {input, output}`）：
  - 计算啮合频率 `mesh_freq = rot_freq * input_teeth`
  - 在啮合频率附近搜索边频带，判断调制故障
  
- **无参数**：
  - 计算阶次谱统计特征（峰值集中度、峭度）
  - 基于 CAR 指标和统计阈值判断异常

---

## 6. 信号预处理（preprocessing.py / vmd_denoise.py）

### 6.1 去噪方法

| 方法 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 无预处理 | 信号质量较好时 |
| `wavelet` | 小波阈值去噪 | 去除白噪声，保留冲击特征 |
| `vmd` | 变分模态分解 | 非平稳信号分解，计算量大 |
| `med` | 最小熵解卷积 | 增强周期性冲击 |
| `cpw` | 倒频谱预白化 | 消除传递路径影响 |

### 6.2 CPW 关键修复

- **奇数长度信号处理**：使用 `irfft(..., n=N)` 确保输出长度与输入一致
- **MED 卷积模式**：使用 `mode='same'` 避免输出长度不一致

---

## 7. 健康度评分（health_score.py）

### 7.1 评分逻辑

基础分 100 分，根据各类故障指示器扣分：

| 故障类型 | 条件 | 扣分 |
|----------|------|------|
| 轴承外圈/内圈/滚动体/保持架 | `significant=True` | -15~-20 |
| 轴承统计异常 | `envelope_peak_snr > 5.0` | -8 |
| 齿轮调制 | `gear_modulation significant` | -15 |
| 齿轮局部故障 | `gear_local significant` | -12 |
| 齿轮统计异常 | `order_kurtosis > 5.0` | -6 |
| 时域冲击 | `impulse_factor > 阈值` | -5~-10 |

### 7.2 状态判定

| 健康度 | 状态 |
|--------|------|
| 90-100 | normal |
| 70-89 | warning |
| < 70 | critical |

---

## 8. 诊断建议（recommendation.py）

根据故障指示器生成维护建议：

- **轴承故障** → 建议润滑检查、更换轴承、振动监测
- **齿轮故障** → 建议齿面检查、润滑油分析、对中校正
- **综合异常** → 建议停机检查、全面体检

---

## 9. 阶次跟踪（order_tracking.py）

> ⚠️ **此模块已冻结，禁止修改。**

- `_compute_order_spectrum()`：单帧阶次跟踪（恒定转速）
- `_compute_order_spectrum_multi_frame()`：多帧平均（转速缓变）
- `_compute_order_spectrum_varying_speed()`：变速跟踪（STFT + 等相位重采样）

---

## 10. 使用示例

### 10.1 综合分析（有参数）

```python
from app.services.diagnosis import DiagnosisEngine, BearingMethod, GearMethod, DenoiseMethod

engine = DiagnosisEngine(
    strategy="standard",
    bearing_method=BearingMethod.ENVELOPE,
    gear_method=GearMethod.STANDARD,
    denoise_method=DenoiseMethod.WAVELET,
    bearing_params={"n": 9, "d": 7.94, "D": 39.04, "alpha": 0},
    gear_teeth={"input": 18, "output": 27},
)

result = engine.analyze_comprehensive(signal, sample_rate=25600)
# result: { health_score, status, fault_probabilities, bearing, gear, time_features, recommendation }
```

### 10.2 全算法对比分析

```python
engine = DiagnosisEngine(
    strategy=DiagnosisStrategy.EXPERT,
    denoise_method=DenoiseMethod.NONE,
    bearing_params={...},
    gear_teeth={...},
)

result = engine.analyze_all_methods(signal, sample_rate=25600)
# result: { health_score, status, bearing_methods, gear_methods, comprehensive, recommendation }
```

### 10.3 无参数统计诊断

```python
engine = DiagnosisEngine()  # 不传入 bearing_params / gear_teeth

result = engine.analyze_comprehensive(signal, sample_rate=25600)
# 轴承诊断回退到包络谱统计特征
# 齿轮诊断回退到阶次谱统计特征 + CAR
```

---

## 11. 性能注意事项

- **信号长度截断**：所有分析限制最多 5 秒数据（`sample_rate * 5`）
- **VMD 去噪**：计算量最大，2G 服务器上可能超时，建议仅在 expert 策略下使用
- **全算法分析**：同时运行 6 种方法，最耗时（3~10 秒）
- **线程池限制**：`max_workers=2`，严禁增加
