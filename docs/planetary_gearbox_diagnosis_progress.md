# 行星齿轮箱故障诊断进展与挑战

> **面向接手此问题的开发者**：本文档记录行星齿轮箱诊断算法的当前状态、已知局限、核心瓶颈及未来实现方向。详细算法理论见 `ALGORITHMS.md` 第 2.7 节。

---

## 1. 问题背景

### 1.1 WTgearbox 数据集

- **路径**: `D:\code\wavelet_study\dataset\WTgearbox\down8192`
- **采样率**: 8192 Hz
- **文件数**: 160 个 `.npy`
- **故障类型**: He(健康), Br(断齿), Mi(缺齿), We(磨损), Rc(裂纹)
- **子类型**: N1/N2(健康), B1/B2(断齿), M1/M2(缺齿), W1/W2(磨损), R1/R2(裂纹)
- **转速**: 20/25/30/35/40/45/50/55 Hz（共8种恒速）
- **通道**: c1, c2（两个加速度计方向）
- **文件命名**: `{Fault}_{Sub}_{Speed}-c{Ch}.npy`

### 1.2 行星齿轮箱参数（WTgearbox 设备配置）

```json
{
  "sun": 28, "ring": 100, "planet": 36,
  "planet_count": 4, "input": 28
}
```

**ring固定、sun输入架构的特征阶次**（相对于太阳轮转频 f_sun）:

| 特征 | 公式 | 数值 | ALGORITHMS.md 章节 |
|------|------|------|-----------------|
| **mesh_order** | `Z_ring × Z_sun / (Z_sun + Z_ring)` | 100×28/128 = **21.875** | 2.7.2 |
| **mesh_freq** | `mesh_order × f_sun` | **175/8 × f_sun** | 2.7.2 |
| **carrier_order** | `Z_sun / (Z_sun + Z_ring)` | 28/128 = **0.21875** | 2.7.2 |
| **sun_fault_order** | `Z_ring / (Z_sun + Z_ring) × N_p` | 100/128 × 4 = **3.125** | 2.7.2 |
| **planet_fault_order** | `Z_ring / (Z_sun + Z_ring)` | 100/128 = **0.78125** | 2.7.2 |

> ⚠️ **关键易错点**: 行星箱 `mesh_order ≠ 齿数`！之前代码用 `input=28`（定轴箱公式），这是错误的。行星箱 mesh_order=21.875（约175/8），边频带间隔是 carrier_order=0.21875（不是1.0）。

---

## 2. 核心瓶颈：频域指标无区分力

### 2.1 实验数据（mesh_order 修复后的实测值）

80 组数据（5故障×8转速×2通道）测试结果——所有频域指标健康和故障范围完全重叠：

| 指标 | 健康(N1/N2)范围 | 故障(Br/Mi/We/Rc)范围 | 区分力 |
|------|----------------|---------------------|--------|
| **SER** | 1.5 ~ 14.4 | 1.5 ~ 10.0 | ❌ 健康范围更大 |
| **CAR** | 3,500 ~ 6.4×10⁹ | 3,500 ~ 8.4×10⁹ | ❌ 完全重叠 |
| **sideband_count** | 全部 = 6 | 全部 = 6 | ❌ |
| **order_kurtosis** | 1 ~ 66,000 | 0.3 ~ 7,000 | ❌ 健康更大 |
| **order_peak_concentration** | 0 ~ 0.4 | 0 ~ 0.4 | ❌ |
| **FM4/M6A/M8A** | 3 ~ 5 | 3 ~ 5 | ❌ (之前测试已确认) |

### 2.2 为什么行星箱频域指标失效

**物理原因**（3条叠加效应，详见 ALGORITHMS.md 2.7.1）:

1. **多行星轮同时啮合**：4个行星轮同时与sun和ring啮合，产生4组调制边频带（间隔=carrier_order），无论健康/故障都存在且幅值相当
2. **内/外啮合同时发生**：每个行星轮同时与sun（外啮合）和ring（内啮合）接触，信号中包含两组mesh频率族
3. **行星架旋转调制**：carrier旋转对所有信号施加低频调制，使频谱呈现复杂结构

**Feng & Zuo (2012)** 的AM-FM模型（ALGORITHMS.md 2.7.1）给出了数学解释：行星箱信号是多个AM-FM分量叠加，即使健康状态下也存在显著边频带结构。

---

## 2.3 全方法 SNR 区分力评估（2026-05-16 更新）

对 WTgearbox 160 个 .npy 文件运行 7 种解调方法，统计各方法对健康/故障的区分力。

### 2.3.1 计算时间

| 方法 | avg | median | max | 标记 |
|------|-----|--------|-----|------|
| narrowband | 0.01s | 0.01s | 0.02s | ✅ 快 |
| fullband | 0.01s | 0.01s | 0.03s | ✅ 快 |
| tsa_envelope | 0.08s | 0.07s | 0.18s | ✅ 快 |
| hp_envelope | 0.01s | 0.01s | 0.02s | ✅ 快 |
| sc_scoh | 0.07s | 0.07s | 0.11s | ✅ 快 |
| msb | 0.01s | 0.01s | 0.01s | ✅ 快 |
| vmd_demod 🔴 | 0.7~1.3s | ~0.9s | ~1.3s | 🔴 **比其他方法慢70~130倍** |

### 2.3.2 SNR 区分力（sun_fault 相关指标）

| 方法 | 主指标 | 区分力 | overlap | 健康 median | 故障 median | 结论 |
|------|--------|--------|---------|-------------|-------------|------|
| narrowband | sun_fault_snr | 1.05 | 0.72 | 134.69 | 141.31 | ❌ 完全重叠 |
| fullband | sun_fault_snr | 1.24 | 0.82 | 9259.73 | 11438.43 | ❌ overlap仍>80% |
| tsa_envelope | sun_fault_snr | 0.85 | 0.89 | 381379 | 322521 | ❌ 健康反而更高 |
| hp_envelope | sun_fault_snr | 1.09 | 0.88 | 12520.63 | 13642.40 | ❌ 完全重叠 |
| sc_scoh | sun_fault_scoh_snr | 1.02 | 0.65 | 7.06 | 7.17 | ❌ 完全重叠 |
| sc_scoh | sun_fault_sc_snr | 1.07 | 0.70 | 0.39 | 0.42 | ❌ 绝对值远<阈值3 |
| msb | msb_sun_fault_snr | 1.29 | 0.81 | 0.07 | 0.09 | ❌ 绝对值远<阈值3 |
| msb | msb_se_snr | 0.61 | 0.63 | 2.55 | 1.56 | ❌ 健康反而更高 |

### 2.3.3 按故障类型细分（sun_fault 指标 median）

| 方法 | 健康(He) | 断齿(Br) | 缺齿(Mi) | 磨损(We) | 裂纹(Rc) |
|------|----------|----------|----------|----------|----------|
| narrowband | 134.69 | 137.79 | 147.68 | 144.00 | 135.87 |
| fullband | 9259.73 | 11158.86 | 16631.80 | 9556.79 | 9621.80 |
| hp_envelope | 12520.63 | 12779.93 | 18509.52 | 11102.72 | 11282.61 |
| sc_scoh | 7.06 | 6.82 | 7.00 | 7.54 | 7.05 |
| msb | 0.07 | 0.06 | 0.05 | 0.10 | 0.14 |

> 所有方法中，健康与故障的值域几乎完全重叠，无任何方法能单独区分。

### 2.3.4 有区分力的指标

| 指标 | 健康 median | 故障 median | 区分力 | 备注 |
|------|-------------|-------------|--------|------|
| **TSA 残差峭度** | 1.19 | 3.95 | **3.31** | ✅ 当前最有效 |
| 包络峭度(narrowband) | 0.88 | 2.90 | 3.28 | ✅ 有效但需门控 |
| 包络峭度(fullband) | 1.80 | 5.11 | 2.84 | ⚠️ 中等 |
| fullband 调制深度 | 0.40 | 0.61 | 1.55 | ⚠️ 区分力不足 |
| hp_envelope 调制深度 | 0.44 | 0.66 | 1.51 | ⚠️ 区分力不足 |

### 2.3.5 显著性检出率

| 方法/指标 | 健康 SNR>3 | 故障 SNR>3 | 健康显著 | 故障显著 |
|-----------|------------|------------|----------|----------|
| narrowband | 100% | 100% | 100% | 100% | ❌ 无区分 |
| msb_sun_fault | 0% | 0% | 0% | 0% | ❌ 全不显著 |
| msb_planet_fault | 0% | 4% | 0% | 4% | ❌ 极低检出 |

### 2.3.6 结论

**7 种解调方法全部无 SNR 区分力**，与第2.1节的频域指标结论一致。行星箱的 AM-FM 调制结构使得健康和故障信号在频域/阶次域的特征完全重叠。

唯一有区分力的仍然是**时域峭度衍生指标**：

- TSA 残差峭度 (区分力=3.31)
- 包络峭度 (区分力=3.28)

---

## 3. 时域峭度——当前唯一有效检出手段

### 3.1 实测数据

| 状态 | 数据 | c1 kurtosis | c2 kurtosis | 备注 |
|------|------|-------------|-------------|------|
| **缺齿(Mi)** | M2_35 | 32.6 / 24.7 | 11.6 / 16.2 | ✅ 明显异常 |
| **断齿(Br)** | B1_45 | ~8.3 | ~6.3 | ⚠️ 与健康重叠 |
| **磨损(We)** | W1_40 | ~8.8 | ~10.1 | ⚠️ 与健康重叠 |
| **裂纹(Rc)** | R1_35 | ~8.3 | ~9.2 | ⚠️ 与健康重叠 |
| **健康(N2)** | N2_各转速 | 3~5 | 4~5 | ✅ 正常 |
| **健康(N1)** | N1_40~55 | 8~22 | 5~8 | ⚠️ 与故障重叠 |

### 3.2 当前检出策略

**三级门控逻辑**（health_score.py / ensemble.py / analyzer.py 三处一致）:

```
kurtosis > 12  →  齿轮故障证据开启
  ↓
health_score 扣分: kurt>12扣25分, >20扣40分
  ↓
ensemble gear_confidence: 有证据时 0.35~0.80, 无证据时 0.0~0.25
  ↓
analyzer fault_probabilities: kurt>12 → "齿轮磨损" 概率 0.3~0.8
```

### 3.3 已知误报

- **He_N1_45-c1** kurt=21.9 → 触发齿轮磨损(fault_prob=0.7)，实际为健康
- **He_N1_55-c1** kurt=14.0 → 触发齿轮磨损(fault_prob=0.45)，实际为健康
- 原因：N1子集的行星齿轮箱在高转速(40~55Hz)下产生非平稳冲击，kurt天然偏高(8~22)

### 3.4 当前效果

| 故障类型 | 检出率 | 误报率 | 说明 |
|---------|--------|--------|------|
| **缺齿(Mi)** | 75% | 0% | c1通道kurt>12可检出，c2通道kurt≈11不够 |
| **断齿(Br)** | 12.5% | — | kurt≈4~8，与健康N2重叠 |
| **磨损(We)** | 12.5% | — | kurt≈8~10，与健康N1重叠 |
| **裂纹(Rc)** | 0% | — | kurt≈4~8，与健康N2重叠 |
| **健康(He)** | — | 12.5% | N1高转速子集误触发(2/16) |

---

## 4. 代码架构

### 4.1 诊断调用链

```
analyzer.py  analyze_device()
  ↓
DiagnosisEngine.analyze_research_ensemble()  ← ensemble.py 主入口
  ↓
  ├─ preprocess()  → wavelet/VMD 去噪
  ├─ analyze_bearing()  → 轴承诊断(若has_bearing)
  ├─ analyze_gear()  → 齿轮诊断(若has_gear)
  └─ _compute_health_score()  → 健康度评分
```

### 4.2 关键文件与职责

| 文件 | 职责 | 行星箱相关修改 |
|------|------|--------------|
| `engine.py` | 调度器：mesh_order/特征阶次计算 | mesh_order用行星公式(21.875), 边频带spacing=carrier_order(0.21875), 添加sun_fault/carrier/planet特征阶次, CPW comb_freq也修复 |
| `gear/__init__.py` | `_evaluate_gear_faults`: 阈值评估 | 行星箱: SER>15/20, CAR>1e10/1e12, sideband≥8/10, order_kurt>50/200 |
| `gear/metrics.py` | SER/FM4/M6A/M8A/边频带计算 | `analyze_sidebands_order` 添加 `spacing` 参数 |
| `health_score.py` | 健康度评分 | `is_gear_device` 分离: 齿轮设备kurt阈值>10/>12/>20, crest>12/>15; 轴承设备保持kurt>5/>8/>10/>20 |
| `ensemble.py` | 多算法集成+置信度 | `_gear_confidence`: 时域证据门控(GEAR_KURT_THRESHOLD=12, GEAR_CREST_THRESHOLD=15) |
| `analyzer.py` | 设备级融合+fault_probabilities | kurt>12 → "齿轮磨损"概率映射(0.3~0.8) |

### 4.3 阈值不一致问题 ⚠️

| 参数 | health_score.py | ensemble.py | 说明 |
|------|----------------|-------------|------|
| `GEAR_CREST_THRESHOLD` | 12.0 | 15.0 | ensemble更严格，crest=12~15区间行为不同 |

> 这是已知的阈值不一致，尚未修复。建议统一为 12.0 或 15.0。

---

## 5. 推荐实现路径

> 详细算法理论见 `ALGORITHMS.md` 第 2.7 节。以下是工程实现优先级。

### 5.1 分级诊断策略（ALGORITHMS.md 2.7.7）

```
Level 1（已有）: kurtosis > 12 / crest > 15 时域门控
      ↓
Level 2（优先实现）: 窄带包络阶次分析
      - 对 mesh_order(21.875) 附近做窄带滤波 + Hilbert包络
      - 对包络做阶次谱，搜索 sun_fault_order(3.125) / planet_fault_order(0.78125)
      - 计算 SNR > 3~5 为显著
      ↓
Level 3（后续）: VMD联合解调
      - K = floor(fs/(2*fmesh)), 建议 K≤5 控制内存
      - 信号截断至5秒
```

**Level 2 是突破当前瓶颈的最佳切入点**——计算量可控（单次Hilbert+FFT），无需新增依赖，可直接在 `engine.py` 的 `analyze_gear` 中实现。

### 5.2 Level 2 实现要点

建议创建 `diagnosis/gear/planetary_demod.py`，核心逻辑：

```python
def planetary_envelope_order_analysis(signal, fs, rot_freq, gear_teeth):
    """行星齿轮箱窄带包络阶次分析"""
    z_sun, z_ring, planet_count = gear_teeth["sun"], gear_teeth["ring"], gear_teeth["planet_count"]
    
    # 特征阶次
    mesh_order = z_ring * z_sun / (z_sun + z_ring)
    sun_fault_order = z_ring / (z_sun + z_ring) * planet_count
    carrier_order = z_sun / (z_sun + z_ring)
    
    # 1. 窄带滤波：mesh_order ± 2阶
    mesh_freq = rot_freq * mesh_order
    band_signal = bandpass_filter(signal, fs, mesh_freq, bandwidth=rot_freq*4)
    
    # 2. Hilbert包络
    envelope = np.abs(hilbert(band_signal))
    envelope = envelope - np.mean(envelope)  # 去DC
    
    # 3. 对包络做阶次谱
    order_axis, order_spectrum = compute_order_spectrum(envelope, fs, rot_freq)
    
    # 4. 搜索特征故障阶次峰值
    sun_amp = order_band_amplitude(order_axis, order_spectrum, sun_fault_order, 0.3)
    planet_amp = order_band_amplitude(order_axis, order_spectrum, planet_fault_order, 0.3)
    carrier_amp = order_band_amplitude(order_axis, order_spectrum, carrier_order, 0.3)
    
    # 5. 计算SNR（相对于背景中位数）
    background = np.median(order_spectrum)
    snr_sun = sun_amp / background
    snr_planet = planet_amp / background
    
    return {
        "sun_fault_snr": snr_sun,
        "planet_fault_snr": snr_planet,
        "carrier_snr": carrier_amp / background,
        "sun_fault_significant": snr_sun > 3,
        "planet_fault_significant": snr_planet > 3,
    }
```

### 5.3 集成到 engine.py

在 `analyze_gear` 方法中，当 `is_planetary=True` 时调用行星箱专用分析：

```python
if is_planetary:
    planetary_result = planetary_envelope_order_analysis(arr, fs, rot_freq, self.gear_teeth)
    result["planetary_demod"] = planetary_result
    # 将 sun_fault/planet_fault 的 SNR 映射到 fault_indicators
```

### 5.4 N1子集误报的缓解策略

He_N1_40~55的kurt=8~22误触发问题，可能的缓解方式：

| 方案 | 思路 | 优劣 |
|------|------|------|
| **多通道交叉验证** | c1和c2都有kurt>12才认定故障 | 简单，但缺齿c2 kurt≈11也会漏检 |
| **旋转谐波优势度门控** | low_freq_ratio>0.55时降低kurt证据权重 | 已实现(rotation_dominant)，但N1_45的low_freq_ratio不高 |
| **转速归一化** | 同转速下与基线比较kurt偏离度 | 需要基线数据，单次检测无法使用 |
| **TSA后kurt** | TSA消除异步成分后再计算kurt | 更准确，但WTgearbox 10秒数据可能不够整周期 |
| **IMF选择性kurt** | VMD分解后选故障IMF的kurt | 避免旋转谐波主导的IMF掩盖冲击IMF |

---

## 6. 数据集快速上手

### 6.1 本地测试命令

```bash
# 激活云端 venv（Windows）
cd /d D:\code\CNN\cloud
. venv\Scripts\activate

# 运行齿轮指标对比测试
PYTHONPATH=D:\code\CNN\cloud python ../tests/diagnosis/test_gear_detail.py

# 运行有效性测试
PYTHONPATH=D:\code\CNN\cloud python ../tests/diagnosis/test_effectiveness.py

# 查看行星箱 mesh_order 验证
PYTHONPATH=D:\code\CNN\cloud python ../tests/diagnosis/test_mesh_order_fix.py
```

### 6.2 服务器部署

```bash
ssh root@8.137.96.104 "cd /opt/CNN && bash deploy.sh"
```

### 6.3 设备-数据对应

| 设备ID | 数据集 | 故障类型 | 有轴承参数 | 有齿轮参数 |
|---------|--------|---------|-----------|-----------|
| WTG-001~003 | CW轴承 | H/I/O | ✅ | ❌(skip_gear) |
| WTG-004~008 | WTgearbox | He/Br/Mi/We/Rc | ❌(skip_bearing) | ✅(行星) |
| WTG-009 | CW+WTgear | 混合 | ✅ | ✅ |
| WTG-010 | — | 离线测试 | — | — |

---

## 7. 历史修复记录

| 版本 | commit | 修复内容 | 效果 |
|------|--------|---------|------|
| **v1(旧)** | — | mesh_order=input=28, 边频带spacing=1, 行星箱阈值偏低 | 健康误报50%+，故障检出靠误驱动的频域指标 |
| **v2** | f3035cc | 行星箱阈值大幅提升(SER>12, CAR>1e15), 健康kurt>5→8→10阶梯 | 健康误报降至12.5%，但SER/CAR检出归零 |
| **v3** | d31ce51 | mesh_order=21.875, spacing=0.21875, sun_fault=3.125, CPW修复 | 频域指标计算正确但仍无区分力；kurt>12是唯一检出路径 |
| **v4** | 5d78479 | 移除重新诊断API的is_online检查 | 离线设备也能对历史数据重新诊断 |

> **结论**: 行星齿轮箱的诊断瓶颈不在代码实现，而在物理机制——行星架构的频域调制效应天然消除了一阶/二阶统计指标的区分力。突破此瓶颈需要转向**窄带包络阶次分析**（分阶次解调），详见 ALGORITHMS.md 2.7.3 和 2.7.7。
