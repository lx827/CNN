# 风机齿轮箱智能故障诊断 — 算法体系全景

> **定位**：本文档串联 5 个子系统，给出每个方法的数学逻辑与交互关系。经典理论细节（故障特征频率公式、TSA 数学推导等）参见 `ALGORITHMS.md`。

---

## 目录

1. [系统全景：数据流与子系统交互](#1-系统全景数据流与子系统交互)
2. [子系统一：信号预处理（11 种方法）](#2-子系统一信号预处理11-种方法)
3. [子系统二：轴承诊断（14 种方法）](#3-子系统二轴承诊断14-种方法)
4. [子系统三：齿轮诊断（6 指标 + 行星专项）](#4-子系统三齿轮诊断6-指标--行星专项)
5. [子系统四：阶次跟踪（3 模式自动切换）](#5-子系统四阶次跟踪3-模式自动切换)
6. [子系统五：集成诊断（弱投票 + 连续衰减评分 + 参数跳过）](#6-子系统五集成诊断弱投票--连续衰减评分--参数跳过)

---

## 1. 系统全景：数据流与子系统交互

```
┌─────────────────────────────────────────────────────────────────────┐
│                        振动信号 x(t)                                 │
├─────────────────────────────────────────────────────────────────────┤
│  [子系统一] 信号预处理                                                │
│  prepare_signal(detrend) → denoise_signal(method)                   │
│  选择: wavelet / VMD / EMD / CEEMDAN / EEMD / WP / S-G / 级联       │
├─────────────────────────────────────────────────────────────────────┤
│  [子系统四] 阶次跟踪（自动估计转频)                                    │
│  恒速/缓变/变速 三模式自适应切换 → rot_freq                          │
├───────────────────────┬─────────────────────────────────────────────┤
│   [子系统二] 轴承诊断  │   [子系统三] 齿轮诊断                         │
│   14 种方法            │   6 指标 + 行星专项                          │
│   产出一组 fault_ind.  │   产出一组 fault_ind.                        │
├───────────────────────┴─────────────────────────────────────────────┤
│  [子系统五] 集成诊断                                                  │
│  ① 弱投票置信度 → bearing_score / gear_score / time_score           │
│  ② D-S 证据融合 → dominant_fault + conflict                         │
│  ③ Sigmoid 连续衰减扣分 → health_score (0~100)                      │
│  ④ 参数驱动跳过：未配轴承参数 → skip_bearing，未配齿轮 → skip_gear    │
└─────────────────────────────────────────────────────────────────────┘
```

**数据说明**：

- 每个去噪方法 × 每个轴承方法 × 每个齿轮方法 的组合独立运行
- 最终的健康度评分 = 所有子结果的综合，非单一方法决定
- 综合故障诊断（前端"策略诊断"/"全算法诊断"）走 `ensemble.py` 的集成路径
- 前端 DataView 各独立分析（FFT/包络/齿轮等）走各自端点的单方法路径

---

## 2. 子系统一：信号预处理（11 种方法）

> 代码入口：`engine.py:140` `preprocess()`  /  `signal_utils.py:157` `denoise_signal()`

所有方法统一接收一个零均值信号（`prepare_signal` 已去直流），返回去噪后信号。

| 方法 | 数学原理 | 核心公式 / 步骤 | 计算代价 |
|------|---------|---------------|---------|
| **wavelet** 小波阈值 | 小波分解 → 噪声在细节系数中表现为小值 → 阈值置零 → 重构 | **噪声估计**：$\sigma = \frac{\text{MAD}(|d_{L-1}|)}{0.6745}$<br>**通用阈值**：$\lambda = \sigma \sqrt{2\ln N}$<br>**软阈值**：$\hat{w} = \text{sgn}(w)\cdot\max(|w|-\lambda, 0)$ | 低 O(N) |
| **vmd** VMD | 变分优化将信号分解为 K 个带限本征模态，保留与原始信号高相关或高峭度的 IMF | **频域更新（维纳滤波形式）**：<br>$\hat{u}_k(\omega) = \frac{\hat{x}(\omega) - \sum_{i\neq k}\hat{u}_i(\omega) - \hat{\lambda}(\omega)/2}{1 + 2\alpha(\omega-\omega_k)^2}$<br>**筛选**：$\text{corr}(IMF_i, x) > 0.3 \lor \text{kurt}(IMF_i) > 3.0$ | 中 O(K·N·iter) |
| **wavelet_vmd** 小波+VMD 级联 | 先小波去宽带噪声 → 再 VMD 分离非平稳成分 | 级联流水线，比单用 VMD 更能保留弱冲击 | 中 |
| **wavelet_lms** 小波+LMS | 先小波去噪 → 再 LMS 自适应消除残留周期噪声 | **LMS**：$e(n) = d(n) - \mathbf{w}^T\mathbf{x}(n)$，$\mathbf{w}(n+1) = \mathbf{w}(n) + \mu e(n)\mathbf{x}(n)$ | 低-中 |
| **emd** EMD | 基于局部特征尺度自适应分解为 IMF，无需预设模态数 | **筛分过程（Sifting）**：<br>$\text{residue} \rightarrow \text{detect extrema} \rightarrow \text{PchipInterpolator}(上包络, 下包络) \rightarrow \text{减去均值包络}$<br>**停止准则**：$ \sum(h_{new}-h)^2 / \sum h^2 < 0.25$ | 中-高 |
| **ceemdan** CEEMDAN | 完备集成 EMD，每层噪声幅值自适应调整，重构误差为零 | **第 k 阶**：$trial = residue + \beta_k \cdot \text{noise\_IMF}_k \cdot \text{std}(residue)$ → 单次筛分 → IMF_k<br>完备性：$x = \sum IMF_k + r_{final}$ | 高 O(M·N²) |
| **eemd** EEMD | 加噪 → EMD → 集成平均消除噪声 | $IMF_k = \frac{1}{M}\sum_{i=1}^{M} EMD(x + \varepsilon_i)[k]$ | 高 |
| **savgol** S-G 平滑 | 滑动窗口内多项式最小二乘拟合，保留信号峰形 | $x_{smooth}[n] = \sum_{m=-w}^{w} c_m \cdot x[n+m]$，系数 $c_m$ 由 Vandermonde 伪逆解得 | 极低 O(N) |
| **wavelet_packet** WP | 小波包完整二叉树分解 → 能量占比 < 5% 的节点置零 | $E_{j,k} = \sum |d_{j,k}[n]|^2$，$p_{j,k} = E_{j,k} / \sum E_{j,m}$ | 低 |
| **ceemdan_wp** CEEMDAN+WP | CEEMDAN 去低频趋势 → WP 筛除非主要能量频带 | 级联两条互补路径 | 高 |

**IMF 筛选通用规则**（EMD/CEEMDAN/EEMD）：排除首 IMF（高频噪声）和末 IMF（低频趋势/残差），保留中间层满足 `corr > 0.35` 或 `kurt > 3.5` 的 IMF。若无满足条件者，回退为峭度最大的中间 IMF 单个重构。

---

## 3. 子系统二：轴承诊断（14 种方法）

> 代码入口：`engine.py:208` `analyze_bearing()`  /  具体实现：`bearing.py`

**共同流程**：带通滤波（选共振频段） → 希尔伯特变换 → 包络提取 → 包络谱 FFT → 故障频率匹配

**14 种方法的本质区别**：如何选择共振频段——这是轴承诊断的核心难题。

| 方法 | 频段选择策略 | 数学核心 | 适用场景 |
|------|-------------|---------|---------|
| **envelope** 标准包络 | 固定频段（Nyquist 25%~75%） | **希尔伯特包络**：$e(t) = |x_f(t) + j\mathcal{H}\{x_f(t)\}|$ | 基线方法 |
| **kurtogram** 快速峭度图 | STFT 各频带峭度：选峭度最高频带 | **谱峭度**：$K = \frac{E[|S(t,f)|^4]}{E[|S(t,f)|^2]^2} - 2$ | 冲击型故障首选 |
| **cpw** CPW 预白化 | 倒频谱域抑制齿轮周期分量 → 峭度图 | **倒频谱陷波**：在 $\tau_k = k/f_{target}$ 处陷波 → 重构 | 齿轮箱内轴承 |
| **med** MED 增强 | FIR 滤波器最大化输出峭度 → 标准包络 | **目标函数**：$\max_f K(\hat{x})$，其中 $\hat{x} = f * x$<br>**迭代求解**：$f_{new} = (Y^TY + \varepsilon I)^{-1} Y^T \cdot (\hat{x}^3 / \|\hat{x}^3\|)$ | 早期弱故障 |
| **mckd** MCKD 增强 | FIR 滤波器最大化相关峭度（引入故障周期T）→ 标准包络 | **相关峭度**：$CK_M(y) = \frac{\sum \prod_{m=0}^{M} y_{i-mT}}{(\sum y_i^2)^{M+1}}$<br>$T = f_s / BPFO$（有参数时），无参数回退 MED | 已知故障频率时精度更高 |
| **teager** TEO 能量算子 | TEO 放大瞬态冲击 → 峭度图 | **离散 TEO**：$\Psi[x_n] = x_n^2 - x_{n-1} \cdot x_{n+1}$ | 低 SNR 冲击 |
| **spectral_kurtosis** 谱峭度重加权 | 多准则复合评分（SK + 冲击度 + SNR）选最优频带 | **评分**：$\text{score} = \max(0, SK-3) \times \ln(1+\text{impulsiveness}) \times \ln(1+\text{SNR})$<br>$\text{impulsiveness} = \max(|band|)/\text{median}(|band|)$ | 比 Kurtogram 更鲁棒 |
| **sc_scoh** 谱相干 | 全频带谱相干矩阵，在循环频率 α 处搜索故障频率 | **谱相干**：$\gamma_x^\alpha(f) = \frac{|\langle X(f-\alpha/2)X^*(f+\alpha/2)\rangle|^2}{\langle PSD(f-\alpha/2)\rangle\langle PSD(f+\alpha/2)\rangle}$ | 理论最严谨，弱故障检出率高 |
| **wp** WP 包络 | 小波包分解 → 选能量最高子带 → 包络 | 小波包逐层二分频带 | 时频联合分析 |
| **dwt** DWT 包络 | 离散小波分解 → 选峭度最高细节层 → 包络 | DWT 仅分解近似子空间 | 同上，更快 |
| **emd_envelope** EMD 包络 | EMD → 选峭度最高 IMF → 包络 | 自适应模态选择 | 变速工况 |
| **ceemdan_envelope** CEEMDAN 包络 | CEEMDAN → 选峭度最高 IMF → 包络 | 比 EMD 抗模态混叠 | 变速工况 |
| **vmd_envelope** VMD 包络 | VMD → 选中心频率接近共振带的 IMF → 包络 | 频域优化分解 | 共振频带明确 |

### 3.1 故障频率匹配（诊断的关键一步）

所有轴承方法在产出包络谱后，调用 `features.py:_compute_bearing_fault_freqs()` 计算 4 类理论故障频率：

| 故障类型 | 精确公式 |
|---------|---------|
| **外圈 BPFO** | $\frac{N}{2} f_r \left(1 - \frac{d}{D}\cos\alpha\right)$ |
| **内圈 BPFI** | $\frac{N}{2} f_r \left(1 + \frac{d}{D}\cos\alpha\right)$ |
| **滚动体 BSF** | $\frac{D}{2d} f_r \left[1 - \left(\frac{d}{D}\cos\alpha\right)^2\right]$ |
| **保持架 FTF** | $\frac{f_r}{2}\left(1 - \frac{d}{D}\cos\alpha\right)$ |

在包络谱的 $\pm 3\%$ 容差带内搜索峰值，计算 SNR（峰值/背景中位数）。SNR > 3 标记为 `significant=True`。

**无轴承参数时**：不计算理论频率，仅提取包络统计指标（包络峭度、峰值 SNR、高频能量比等），依赖集成诊断的统计路径判断是否存在异常冲击。

---

## 4. 子系统三：齿轮诊断（6 指标 + 行星专项）

> 代码入口：`engine.py` `analyze_gear()`  /  指标实现：`gear/metrics.py`  /  行星专项：`gear/planetary_demod.py`

### 4.1 前置步骤：TSA 与信号分解

所有齿轮指标基于**角域时域同步平均（TSA）**的衍生信号：

**Step 1 — 等角度重采样**（同阶次跟踪原理）：
$x(t) \xrightarrow{\text{等角度插值}} x(\theta)$，每转 $samples\_per\_rev$ 点

**Step 2 — 时域同步平均**：
$x_{TSA}(\theta) = \frac{1}{M} \sum_{m=0}^{M-1} x(\theta + m \cdot 2\pi)$

**Step 3 — 衍生信号**：

| 信号 | 公式 | 用途 |
|------|------|------|
| **残余信号** $r(t)$ | $r = x_{order} - x_{TSA}$ | 轴承故障、非同步齿轮成分 |
| **差分信号** $d(t)$ | $d = x_{TSA} - \text{MA}(x_{TSA}, \sim 32\text{样本})$ | 局部齿损伤冲击 |

MA 为卷积移动平均，窗口大小 = 每转采样点数 / 32（取奇数值）。差分信号去除了啮合频率的平滑波动，只保留局部尖峰。

### 4.2 6 种核心指标

| 指标 | 公式 | 物理意义 | 典型阈值 |
|------|------|---------|---------|
| **FM0** | $FM0 = \frac{PP}{\sum_{i=1}^{n} A(i \cdot f_{mesh})}$ | 峰峰值 / 啮合谐波能量和。检测重大故障（齿断裂） | > 2 粗故障 |
| **FM4** | $FM4 = \frac{N \sum (d_i - \bar{d})^4}{[\sum (d_i - \bar{d})^2]^2}$ | 差分信号的归一化峭度。局部故障产生重尾分布 → FM4 > 3 | 3~4 轻微，4~5 中度，>5 严重 |
| **M6A** | $M6A = N^2 \frac{\sum (d_i - \bar{d})^6}{[\sum (d_i - \bar{d})^2]^3}$ | 差分信号 6 阶归一化矩。比 FM4 对稀疏大冲击更敏感（表面磨损） | 无固定阈值 |
| **M8A** | $M8A = N^3 \frac{\sum (d_i - \bar{d})^8}{[\sum (d_i - \bar{d})^2]^4}$ | 差分信号 8 阶归一化矩。对极稀疏高振幅冲击极度敏感 | 无固定阈值 |
| **CAR** | $CAR = \frac{\text{mean}\left[C(\tau = k/f_r)\right]}{\text{median}(|C(\tau)|, \tau > \tau_{bg})}$ | 倒谱中啮合频率周期分量幅值 / 背景。齿面磨损时 CAR 持续上升 | > 1.2 磨损，> 2 严重 |
| **SER** | $SER = \frac{\sum_{i=1}^{6}(A_{mesh - i \cdot f_r} + A_{mesh + i \cdot f_r})}{A_{mesh}}$ | 边频带能量 / 啮合频率能量。调制度越强 SER 越高 | > 1.5 警告，> 3 严重 |

**NA4（趋势监测）**：$NA4 = \frac{E[(r - \bar{r})^4]}{(\text{历史方差均值})^2}$

分母固定为历史基线方差，使 NA4 随损伤扩展**单调上升**（FM4 分母为当前方差，大面积损伤时反而下降）。无历史数据时退化为 FM4。

### 4.3 边频带分析

在啮合频率两侧搜索 $\pm k \cdot f_r$ 边频带（通常取 $k = 1\dots6$），计算：

- **显著边频计数**：边频幅值 > 啮合频率 5% 的边频数量
- **不对称度**：$\frac{|\text{upper\_amp} - \text{lower\_amp}|}{\text{upper\_amp} + \text{lower\_amp}}$，> 0.3 指示单侧齿面损伤

**故障模式 → 边频特征对应**：

| 故障类型 | SER | 边频计数 | 不对称度 |
|---------|-----|---------|---------|
| 健康 | < 1 | 少 | 低 |
| 均匀磨损 | 上升 | 多 | 对称 |
| 偏心 | 中 | 以 1× 为主 | 对称 |
| 局部裂纹/断齿 | 高 | 多，高阶显著 | 常不对称 |

### 4.4 行星齿轮箱专项（`planetary_demod.py`）

行星箱与定轴箱的核心差异：

| 差异 | 定轴箱 | 行星箱 |
|------|--------|--------|
| 边频间隔 | $f_r$（轴转频） | $\text{carrier\_order} = Z_{sun}/(Z_{sun} + Z_{ring})$ |
| 健康边频 | 极少 | 多行星轮同时啮合，天然多边频 |
| 指标阈值 | 低阈值（SER > 1.5） | 高阈值（SER > 8.0，需宽容差） |

**专项方法（5 级分层）**：

| 级别 | 方法 | 原理 |
|------|------|------|
| L1 | 时域门控 | kurt > 10 或 crest > 10 才进入诊断 |
| L2 | 窄带包络阶次 | 啮合阶次 ± 4·carrier_order 带通 → Hilbert → 阶次谱，搜索 sun_fault_order / planet_fault_order |
| L3 | VMD AM-FM 联合解调 | VMD 分解 → 敏感 IMF（中心频率≈mesh_freq）→ 幅值包络 a(t) + 瞬时频率 f_inst(t) → 阶次谱 |
| L4 | 谱相关/谱相干 | $\gamma_x^\alpha(f)$ 搜索 $\alpha \in \{sun\_fault, planet\_fault, carrier\}$ → γ > 0.3 warning |
| L5 | CVS+MED + MSB | 连续振动分离单个行星轮 → MED 锐化冲击 → MSB 提取残余边频带能量 |

**关键认知**：行星箱的 `env_kurt` 仅对磨损和缺齿敏感，对断齿/裂纹几乎无区分力（被多行星轮平均化）。断齿/裂纹依赖 FM4、SER、CAR、TSA 残差峭度等其他指标。

---

## 5. 子系统四：阶次跟踪（3 模式自动切换）

> 代码：`order_tracking.py`  /  API 入口：`data_view/order.py`

**核心问题**：转速变化 → 传统 FFT 频谱模糊化 → 啮合频率变成一团糊。

**解决**：将信号从"等时间采样"转为"等角度采样"，再做 FFT。无论转速如何变化，齿轮啮合始终固定在整数阶。

### 5.1 三种模式

| 模式 | 转速特征 | 算法 |
|------|---------|------|
| **单帧（single）** | 已知转频（前端传入或已有缓存） | $x(\theta) = \text{interp}(t, x(t), \text{等角度时间})$ → FFT |
| **多帧（multi）** | 缓变（CV ≤ 10%） | 分帧（1秒/帧，50%重叠）→ 各帧独立估计转频 → MAD 剔除异常帧 → 各帧独立阶次跟踪 → 插值到公共阶次轴平均 |
| **变速（varying）** | 剧烈变速（CV > 10%） | STFT 逐帧追踪瞬时频率 → 对速度曲线积分得到转角 → 等相位重采样 → FFT |

**转频估计**（多帧模式下每帧独立）：

$$
\hat{f}_r = \arg\max_f \text{Score}(f), \quad f \in [f_{min}, f_{max}]
$$

其中 $\text{Score}(f)$ 为频谱法（在 FFT 谱搜索 f 及其谐波的能量）与包络解调辅助的综合评分。

**异常帧剔除**：$\text{MAD} = \text{median}(|f_i - \text{median}(f)|)$，剔除 $|f_i - \text{median}| > 3.5 \times \text{MAD}$ 的帧。

### 5.2 等角度重采样

给定转频 $f_r$，在时段 $[0, T]$ 内总转数 $R = T \cdot f_r$，每转 $N$ 点，总角域点数 $N_{total} = R \cdot N$。角域时间坐标：

$$
t_k = \frac{k}{N \cdot f_r}, \quad k = 0, 1, \dots, N_{total} - 1
$$

线性插值：$x_{order}[k] = \text{interp}(t_k)$，再对 $x_{order}$ 加窗 → FFT → 阶次谱。

---

## 6. 子系统五：集成诊断（弱投票 + 连续衰减评分 + 参数跳过）

> 代码：`ensemble.py`  /  健康度：`health_score.py` + `health_score_continuous.py`

### 6.1 集成策略总览

三种策略（profile），在计算深度和响应速度之间取舍：

| Profile | 去噪组合数 | 轴承方法数 | 齿轮方法数 | 计算量 | 使用场景 |
|---------|-----------|-----------|-----------|--------|---------|
| **runtime**（默认） | 1 | 4 (env/kurt/cpw/teager) | 1 (ADVANCED) | 低 | DataView 实时计算 |
| **balanced** | 用户选择 + none | 8 | 1 (ADVANCED) | 中 | 策略诊断 |
| **exhaustive** | 全部 10 种 | 全部 13 种 | 2 | 高 | 全算法诊断 / 研究 |

**主循环**（`run_research_ensemble()`）：

```
for each denoise_method:
    proc[x] = preprocess(x, denoise_method)
    time_features = compute_time_features(proc[x])     # 仅取第一组
    rot_freq = estimate_rot_freq(proc[x], fs)
    
    for each bearing_method:
        result = analyze_bearing(proc[x], fs, rot_freq)
        vote = _bearing_confidence(result, time_features)
        record best_bearing_key
    
    for each gear_method:
        result = analyze_gear(proc[x], fs, rot_freq)
        vote = _gear_confidence(result, has_gear_params, time_features)
        record best_gear_key

bearing_score = max(confidence_list) × 0.55 + vote_fraction(≥0.55) × 0.45
gear_score    = max(confidence_list) × 0.65 + vote_fraction(≥0.55) × 0.35
overall       = max(time_score × 0.6, bearing_score, gear_score)
```

### 6.2 弱投票置信度计算

#### 6.2.1 轴承置信度 `_bearing_confidence()`

**前置门控**：所有非时域命中路径必须满足：

$$
\text{impulse\_context} = (\text{kurt} > 5.0) \lor (\text{crest} > CREST\_EVIDENCE\_THRESHOLD = 10.0)
$$

工业振动中峰值因子 7~9 属正常范围，真正的冲击需要 crest > 10 或 kurt > 5。

**命中分类**：

- **param_hit**：包络谱中匹配到理论故障频率（BPFO/BPFI/BSF 等），且 SNR > 3
- **stat_hit**：包络统计指标显著（包络峭度 > 阈值、包络峰值因子异常等）

**置信度阶梯**：

| 条件 | 置信度 | 判定 |
|------|--------|------|
| param_hit ≥ 2 | 0.85 | 异常 |
| param_hit = 1 且 (stat_hit ≥ 1 或 impulse_context) | 0.65 | 异常 |
| stat_hit ≥ 3 且 impulse_context | 0.65 | 异常 |
| stat_hit ≥ 2 且 impulse_context | 0.55 | 异常 |
| stat_hit ≥ 1 且 impulse_context 且 SNR > 12 | 0.45（低频优势降权至 0.28） | 存疑 |
| strongest_snr > 18 且 impulse_context | 0.50 | 存疑 |
| stat_hit ≥ 2（无冲击证据） | 0.35 | 存疑 |

**低频优势降权**：若包络谱低频能量占比 `low_freq_ratio > 0.55`（轴频谐波主导），则置信度从 0.45 降至 0.28——旋转谐波主导时轴承频率匹配可能是巧合。

#### 6.2.2 齿轮置信度 `_gear_confidence()`

**行星箱 vs 定轴箱阈值差异**：

| 阈值 | 定轴箱 | 行星箱 |
|------|--------|--------|
| kurt 时域门控 | > 8 | > 10 或 < 5.5 |
| crest 时域门控 | > 8 | > 10 |
| 频域补偿（无时域冲击时） | critical ≥ 2 或 (critical≥1 & warning≥2) → 强制打开 | 不补偿 |
| 旋转谐波门控 | low_freq_ratio > 0.55 → 阻塞 | 同 |

**有齿轮参数时**（`has_gear_params = True`，即配置了 input 齿数）：

```
若 impulse_context 且 非 rotation_dominant:
    critical ≥ 1 且 total ≥ 2 → 0.80（异常）
    critical ≥ 1 或 warning ≥ 2 → 0.60（异常）
    warning = 1 → 0.35（存疑）
    tsa_evidence → 0.35（存疑）
```

**无齿轮参数时**：仅凭 CAR / 阶次统计指标，最大 confidence = 0.35，用于"仅需检测异常"的场景。

#### 6.2.3 时域置信度 `_time_confidence()`

纯时域冲击证据（不依赖频域/参数匹配）：

| kurt 范围 | crest 范围 |
|-----------|-----------|
| kurt > 20 → 0.85 | crest > 15 → 0.65 |
| kurt > 12 → 0.70 | crest > 10 → 0.45 |
| kurt > 8 → 0.55 | |
| kurt > 5 → 0.35 | |

取 kurt 和 crest 评分中的最大值。

### 6.3 参数驱动跳过逻辑

> 代码：`features.py:369` `has_bearing_params()` / `features.py:386` `has_gear_params()`

```python
has_bearing_params(p)  →  p.n > 0 且 p.d > 0 且 p.D > 0  # 三参数均有效
has_gear_params(gt)    →  gt.input > 0                    # 只需主动轮齿数
```

**诊断矩阵**：

| 配置 | skip_bearing | skip_gear | 行为 |
|------|-------------|-----------|------|
| 只配轴承参数 | False | **True** | 只跑轴承，齿轮 score = 0 |
| 只配齿轮参数 | **True** | False | 只跑齿轮，轴承 score = 0 |
| 都没配 | False | False | 跑轴承统计 + 齿轮无参统计（CAR/阶次峭度），不匹配频率 |
| 都配置 | False | False | 轴承 + 齿轮全跑 |

跳过路径的 ensemble score 强制为 0，不会产生误报。

### 6.4 健康度评分 `_compute_health_score()`

**起点 100 分 → Sigmoid 连续衰减扣分 → 上限扣 75 分（最低 25 分）**

#### 6.4.1 Sigmoid 连续衰减

传统阈值判断的阶梯扣分在边界处会产生不连续跳变（如 kurt 从 4.99→5.01 导致分数突变 15 分）。Sigmoid 平滑过渡解决了这个问题：

$$
\text{deduction} = \text{max\_deduction} \times \frac{1}{1 + e^{-(\text{value} - \text{threshold}) \times \text{slope}}}
$$

`slope = 2.0` 时，过渡带约 ±3 个阈值单位。

**级联扣分**（多个阈值阶梯）：

```
total = Σ sigmoid(value, threshold_i, increment_i, slope)
       where increment_i = max_deduction_i - max_deduction_{i-1}
```

#### 6.4.2 扣分权重体系（20+ 种故障指示器）

| 类别 | 指标 | 权重键 | 默认权重 |
|------|------|--------|---------|
| 时域 | 峭度（4 级：mild/moderate/high/extreme） | kurtosis | 1.0 |
| 时域 | 峰值因子（3 级） | crest_factor | 0.8 |
| 动态基线 | rms_mad_z / kurt_mad_z 漂移 | kurtosis | 1.0 |
| 趋势 | cusum / ewma 漂移 | kurtosis | 1.0 |
| 轴承频率 | 多频命中 / 单频命中 | bpfo | 1.2 |
| 轴承统计 | 统计异常 / 统计提示 | kurtosis | 1.0 |
| 轴承边带 | 边带密度 / 边带不对称 | sideband | 0.9 |
| SC/SCoh | 谱相干循环平稳证据 | scoh_evidence | 0.8 |
| 齿轮 | SER 严重/警告 | ser | 0.9 |
| 齿轮 | 边频带严重/警告 | gear_sideband | 0.8 |
| 齿轮 | FM4 严重/警告 | fm4 | 0.8 |
| 齿轮 | TSA 残差峭度严重/警告 | fm4 | 0.8 |
| 齿轮 | NA4 趋势严重/警告 | na4_nb4 | 1.0 |
| 齿轮 | CAR 严重/警告 | car | 0.7 |
| 齿轮 | 阶次统计严重/警告 | car | 0.7 |
| 齿轮 | 小波包能量熵严重/警告 | wp_entropy | 0.7 |
| D-S | 证据冲突惩罚 | ds_conflict | 8.0 |

**最终得分**：

$$
\text{health\_score} = 100 - \min\left(\sum \text{deduction}_i \times \text{weight}_i,\; 75\right)
$$

#### 6.4.3 扣分门控

| 扣分路径 | 门控条件 |
|---------|---------|
| **轴承频率匹配** | `kurt > 5 或 crest > 10`（时域冲击证据必须存在） |
| **轴承统计指标** | 同上 |
| **动态基线漂移** | 同上（rms_mad_z/kurt_mad_z 单独不算冲击，必须有时域冲击背景） |
| **齿轮（有参数时）** | `kurt > [8~12] 或 crest > [8~12]`，行星箱额外保底 gate=0.5 |
| **齿轮（无参数时）** | 同轴承统计门控 |
| **TSA 残差峭度** | 独立门控，rotation_dominant 时扣分 ×0.3 |
| **NA4/NB4 趋势** | rotation_dominant 时扣分 ×0.3 |
| **SCoh** | 无门控（仅 sc_scoh 方法产出） |

**旋转谐波主导判定**：`low_freq_ratio > 0.55`（包络谱或阶次谱低频能量占比超过 55%）。此时所有齿轮非时域扣分被阻塞或大幅降权——旋转谐波主导时应重点排查轴不对中/不平衡，而非齿轮故障。

#### 6.4.4 D-S 证据融合集成

当 `dominant_probability > 0.4` 且 `uncertainty < 0.3` 时，将 D-S 主导故障类型写入 `fault_label`。当 `conflict > 0.8`（各方法之间高度矛盾）时，扣 8 × ds_conflict 权重且健康度 < 90 时状态从 normal 降为 warning。

#### 6.4.5 状态判定

```
health_score ≥ 85 → normal
health_score ∈ [60, 85)：
    有 critical → warning
    无 critical 但 time_abnormal → warning  
    否则 → normal
health_score < 60：
    有 critical → fault
    否则 → warning
```

`time_abnormal` = kurt > 5 或 crest > 10 或 rms_mad_z > 4 或 cusum_score > 8。

**D-S 高冲突修正**：若 conflict > 0.8 且 status = normal 且 hs < 90 → 降为 warning。

---

## 附录 A：代码文件速查

| 子系统 | 核心文件 |
|--------|---------|
| 信号预处理 | `services/diagnosis/preprocessing.py`, `vmd_denoise.py`, `emd_denoise.py`, `savgol_denoise.py`, `wavelet_packet.py` |
| 轴承诊断 | `services/diagnosis/bearing.py`, `bearing_cyclostationary.py`, `mckd.py`, `bearing_sideband.py` |
| 齿轮诊断 | `services/diagnosis/gear/metrics.py`, `gear/planetary_demod.py` |
| 阶次跟踪 | `services/diagnosis/order_tracking.py` |
| 集成诊断 | `services/diagnosis/ensemble.py` |
| 健康度评分 | `services/diagnosis/health_score.py`, `health_score_continuous.py` |
| 特征提取 | `services/diagnosis/features.py` |
| 诊断引擎调度 | `services/diagnosis/engine.py` |
| 信号工具 | `services/diagnosis/signal_utils.py` |
| API 入口 | `api/data_view/spectrum.py`, `envelope.py`, `order.py`, `cepstrum.py`, `gear.py` |

## 附录 B：相关文档

- **经典算法理论**：`ALGORITHMS.md` — 故障特征频率、包络分析、谱峭度、TSA、倒频谱、CPW 等详细数学推导
- **API 文档**：`docs/api/backend_api.md`
- **前端交互**：`docs/api/frontend_backend_interaction.md`
- **行星箱诊断进展**：`docs/planetary_gearbox_diagnosis_progress.md`
- **小波与模态分解**：`docs/backend/algorithms/wavelet_and_modality_decomposition.md`
