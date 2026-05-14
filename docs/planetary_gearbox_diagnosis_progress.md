# 行星齿轮箱故障诊断进展与挑战

> **面向接手此问题的开发者**：本文档记录行星齿轮箱诊断算法的当前状态、已知局限、核心瓶颈及未来可能方向。

---

## 1. 问题背景

### 1.1 WTgearbox 数据集

- **路径**: `D:\code\wavelet_study\dataset\WTgearbox\down8192`
- **采样率**: 8192 Hz
- **文件数**: 160 个 `.npy`
- **故障类型**: He(健康), Br(断齿), Mi(缺齿), We(磨损), Rc(裂纹)
- **子类型**: N1/N2(健康), B1/B2(断齿), M1/M2(缺齿), W1/W2(磨损), R1/R2(裂纹)
- **转速**: 20/25/30/35/40/45/50/55 Hz（共8种）
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

| 特征 | 公式 | 数值 |
|------|------|------|
| **mesh_order** | `Z_ring × Z_sun / (Z_sun + Z_ring)` | 100×28/128 = **21.875** |
| **mesh_freq** | `mesh_order × f_sun` | **175/8 × f_sun** |
| **carrier_order** | `Z_sun / (Z_sun + Z_ring)` | 28/128 = **0.21875** |
| **sun_fault_order** | `Z_ring / (Z_sun + Z_ring) × planet_count` | 100/128 × 4 = **3.125** |
| **planet_fault_order** | `Z_ring / (Z_sun + Z_ring)` | 100/128 = **0.78125** |

> ⚠️ **关键易错点**: 行星箱 `mesh_order ≠ 齿数`！之前代码用 `input=28`（定轴箱公式 mesh_order=齿数），这是错误的。行星箱 mesh_order = 21.875（约 175/8），边频带间隔是 carrier_order = 0.21875（不是 1.0）。

---

## 2. 核心瓶颈：频域指标无区分力

### 2.1 实验数据（mesh_order 修复后的实测值）

用 5 种故障 × 8 种转速 × 2 通道 = 80 组数据测试，所有频域指标的健康和故障范围完全重叠：

| 指标 | 健康(N1/N2)范围 | 故障(Br/Mi/We/Rc)范围 | 区分力 |
|------|----------------|---------------------|--------|
| **SER** | 1.5 ~ 14.4 | 1.5 ~ 10.0 | ❌ 健康范围更大 |
| **CAR** | 3,500 ~ 6.4×10⁹ | 3,500 ~ 8.4×10⁹ | ❌ 完全重叠 |
| **sideband_count** | 全部 = 6 | 全部 = 6 | ❌ |
| **order_kurtosis** | 1 ~ 66,000 | 0.3 ~ 7,000 | ❌ 健康更大 |
| **order_peak_concentration** | 0 ~ 0.4 | 0 ~ 0.4 | ❌ |
| **FM4/M6A/M8A** | 3 ~ 5 | 3 ~ 5 | ❌ (之前测试已确认) |

### 2.2 为什么行星箱频域指标失效

**物理原因**（3条叠加效应）:

1. **多行星轮同时啮合**：4个行星轮同时与sun和ring啮合，产生4组调制边频带（间隔=carrier_order），这些边频带无论健康/故障都存在且幅值相当
2. **内/外啮合同时发生**：每个行星轮同时与sun（外啮合）和ring（内啮合）接触，信号中包含两组mesh频率族
3. **行星架旋转调制**：carrier旋转对所有信号施加低频调制，使频谱呈现复杂结构

**结果**：定轴齿轮箱的边频带间隔=轴转频（1阶），边频幅值直接反映故障程度。行星箱的边频带间隔=carrier_order（0.21875阶），且边频带天然6个全显著，SER/CAR等指标健康和故障值在同一范围。

---

## 3. 时域峭度——唯一有效检出手段

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
DiagnosisEngine.analyze_research_ensemble()  ← ensemble.py 的主入口
  ↓
  ├─ preprocess()  → wavelet/VMD 去噪
  ├─ analyze_bearing()  → 轴承诊断(若has_bearing)
  ├─ analyze_gear()  → 齿轮诊断(若has_gear)
  └─ _compute_health_score()  → 健康度评分
```

### 4.2 关键文件与职责

| 文件 | 职责 | 行星箱相关修改 |
|------|------|--------------|
| `engine.py` | 调度器：mesh_order/特征阶次计算 | mesh_order用行星公式(21.875), 边频带spacing=carrier_order(0.21875), 添加sun_fault/carrier/planet特征阶次 |
| `gear/__init__.py` | `_evaluate_gear_faults`: 阈值评估 | 行星箱: SER>15/20, CAR>1e10/1e12, sideband≥8/10, order_kurt>50/200 |
| `gear/metrics.py` | SER/FM4/M6A/M8A/边频带计算 | `analyze_sidebands_order` 添加 `spacing` 参数 |
| `health_score.py` | 健康度评分 | `is_gear_device` 分离: 齿轮设备kurt阈值>10/>12/>20, crest>12/>15; 轴承设备保持kurt>5/>8/>10/>20 |
| `ensemble.py` | 多算法集成+置信度 | `_gear_confidence`: 时域证据门控(GEAR_KURT_THRESHOLD=12, GEAR_CREST_THRESHOLD=15) |
| `analyzer.py` | 设备级融合+fault_probabilities | kurt>12 → "齿轮磨损"概率映射(0.3~0.8) |

### 4.3 阈值不一致问题

| 参数 | health_score.py | ensemble.py | 说明 |
|------|----------------|-------------|------|
| `GEAR_CREST_THRESHOLD` | 12.0 | 15.0 | ensemble更严格，crest=12~15区间行为不同 |

> 这是已知的阈值不一致，尚未修复。建议统一为 12.0 或 15.0。

---

## 5. 未来可能方向

### 5.1 行星齿轮箱专用诊断方法（文献方向）

| 方法 | 原理 | 潜力 | 复杂度 |
|------|------|------|--------|
| **行星箱解调分析** | 利用carrier/sun/planet三个特征阶次做分阶次包络解调，而不是围绕mesh_order做边频带 | ★★★★ | 中 |
| **差分信号（行星轮间）** | 比较不同行星轮的TSA信号差异，局部故障会在某个行星轮产生异常 | ★★★★ | 高 |
| **时频域联合分析** | STFT或VMD分解后对各IMF单独计算峭度/包络，避免整段信号被旋转谐波淹没 | ★★★ | 中 |
| **行星箱振动信号分离** | 利用多通道(c1/c2)的信号差异分离sun/ring/planet分量 | ★★★ | 中 |
| **差分-能量指标** | 比较"减去某行星轮TSA"后的残余信号能量变化 | ★★ | 低 |
| **窄带包络+阶次跟踪** | 在mesh_order频带做包络，然后对包络做阶次分析，看sun_fault_order峰值 | ★★★★ | 中 |

### 5.2 最有希望的方向：分阶次包络解调

**核心思路**：行星齿轮箱故障不应围绕mesh_order(21.875)做边频带分析，而是围绕特征故障阶次做包络解调：

1. **太阳轮故障**: 对mesh_order频带(21~22阶)做包络，然后在包络的阶次谱中搜索sun_fault_order=3.125的峰值
2. **行星轮故障**: 对mesh_order频带做包络，在包络阶次谱搜索planet_fault_order=0.78125
3. **carrier异常**: 在原始阶次谱中检查carrier_order=0.21875的幅值异常

**实现建议**:
```python
# 在 engine.py analyze_gear 中添加
if is_planetary and mesh_order:
    # 对 mesh_order 频带做窄带滤波+包络
    band = bandpass_order(order_axis, order_spectrum, mesh_order, bandwidth=2.0)
    envelope = hilbert(band)
    # 对包络做阶次谱分析
    env_order_axis, env_order_spectrum = compute_order_spectrum(envelope, fs, rot_freq)
    # 搜索 sun_fault_order 峰值
    sun_fault_amp = order_band_amplitude(env_order_axis, env_order_spectrum, sun_fault_order, 0.3)
    # 搜索 planet_fault_order 峰值
    planet_fault_amp = order_band_amplitude(env_order_axis, env_order_spectrum, planet_fault_order, 0.3)
```

### 5.3 N1子集误报的缓解策略

He_N1_40~55的kurt=8~22误触发问题，可能的缓解方式：

| 方案 | 思路 | 优劣 |
|------|------|------|
| **多通道交叉验证** | c1和c2都有kurt>12才认定故障 | 简单，但缺齿c2 kurt≈11也会漏检 |
| **旋转谐波优势度门控** | low_freq_ratio>0.55时降低kurt证据权重 | 已实现(rotation_dominant)，但N1_45的low_freq_ratio不高 |
| **转速归一化** | 同转速下与基线比较kurt偏离度 | 需要基线数据，单次检测无法使用 |
| **时域同步平均(TSA)后kurt** | TSA消除异步成分后再计算kurt | 更准确，但需要足够多整周期(≥50)，WTgearbox 10秒数据可能不够 |
| **IMF选择性kurt** | VMD/EMD分解后选故障IMF的kurt | 避免旋转谐波主导的IMF掩盖冲击IMF |

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

| 版本 | 修复内容 | 效果 |
|------|---------|------|
| **v1(旧)** | mesh_order=input=28, 边频带spacing=1, 行星箱阈值偏低 | 健康误报50%+，故障检出靠误驱动的频域指标 |
| **v2(f3035cc)** | 行星箱阈值大幅提升(SER>12, CAR>1e15), 健康kurt>5→8→10阶梯 | 健康误报降至12.5%，但SER/CAR检出归零 |
| **v3(d31ce51)** | mesh_order=21.875, spacing=0.21875, sun_fault=3.125 | 频域指标计算正确但仍无区分力；kurt>12是唯一检出路径 |

> **结论**: 行星齿轮箱的诊断瓶颈不在代码实现，而在物理机制——行星架构的频域调制效应天然消除了一阶/二阶统计指标的区分力。突破此瓶颈需要转向分阶次解调、多通道融合或时频联合分析等专用方法。