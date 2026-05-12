# 旋转机械故障诊断经典算法体系

> **文档用途**：本文件系统梳理轴承与齿轮故障诊断的核心理论、公式、算法流程及工程参数，
> 作为本项目 `cloud/app/services/analyzer.py`、`signal_generator.py` 及相关模块的算法实现参考。
> 
> **覆盖范围**：
> - 滚动轴承：特征频率、包络分析、谱峭度/快速Kurtogram、倒频谱预白化(CPW)、循环平稳分析、MED、TSA
> - 齿轮：调制模型、TSA、倒频谱、边频带分析、残余信号解调、啮合冲击调制(MIM)、时域指标(FM0/FM4/NA4/NB4/SER)
> - 综合：轴承/齿轮信号分离、抗漂变降噪、决策级鲁棒化、工程部署流程

---

## 目录

1. [滚动轴承故障诊断](#一滚动轴承故障诊断)
   1.1 [故障特征频率](#11-故障特征频率)
   1.2 [包络分析 / 希尔伯特解调](#12-包络分析--希尔伯特解调)
   1.3 [谱峭度与快速谱峭度图 (Fast Kurtogram)](#13-谱峭度与快速谱峭度图)
   1.4 [倒频谱预白化 (CPW)](#14-倒频谱预白化-cpw)
   1.5 [循环平稳分析](#15-循环平稳分析)
   1.6 [最小熵解卷积 (MED)](#16-最小熵解卷积-med)
   1.7 [时域同步平均 (TSA)](#17-时域同步平均-tsa)
   1.8 [轴承故障特征匹配与判别准则](#18-轴承故障特征匹配与判别准则)
2. [齿轮故障诊断](#二齿轮故障诊断)
   2.1 [齿轮振动调制模型](#21-齿轮振动调制模型)
   2.2 [时域同步平均 (TSA) 在齿轮诊断中的应用](#22-时域同步平均-tsa-在齿轮诊断中的应用)
   2.3 [齿轮经典时域故障指标](#23-齿轮经典时域故障指标)
   2.4 [倒频谱分析](#24-倒频谱分析)
   2.5 [边频带分析](#25-边频带分析)
   2.6 [齿轮故障特征匹配与判别准则](#26-齿轮故障特征匹配与判别准则)
3. [轴承与齿轮故障的分离与鉴别诊断](#三轴承与齿轮故障的分离与鉴别诊断)
   3.1 [信号本质差异](#31-信号本质差异)
   3.2 [确定性-随机分离 (DRS / CPW)](#32-确定性-随机分离)
   3.3 [齿轮箱中轴承诊断的标准流程](#33-齿轮箱中轴承诊断的标准流程)
   3.4 [鉴别诊断要点](#34-鉴别诊断要点)
4. [抗漂变与降噪技术体系](#四抗漂变与降噪技术体系)
   4.1 [漂变问题的工程本质](#41-漂变问题的工程本质)
   4.2 [信号级降噪](#42-信号级降噪)
   4.3 [特征级抗漂变](#43-特征级抗漂变)
   4.4 [决策级鲁棒化](#44-决策级鲁棒化)
   4.5 [工程部署完整抗漂变工作流](#45-工程部署完整抗漂变工作流)
5. [关键工程参数速查表](#五关键工程参数速查表)
6. [核心参考文献索引](#六核心参考文献索引)

---

## 一、滚动轴承故障诊断

### 1.1 故障特征频率

#### 1.1.1 精确公式

设轴旋转频率 $f_r = \text{RPM}/60$（Hz），$N$ 为滚动体数，$d$ 为滚动体直径，$D$ 为节圆直径，$\alpha$ 为接触角（深沟球轴承 $\alpha=0^\circ$）：

| 故障位置 | 特征频率公式 | 工程意义 |
|---------|------------|---------|
| **外圈故障 (BPFO)** | $\displaystyle BPFO = \frac{N}{2} f_r \left(1 - \frac{d}{D}\cos\alpha\right)$ | 滚动体经过外圈缺陷点的频率，最易检测 |
| **内圈故障 (BPFI)** | $\displaystyle BPFI = \frac{N}{2} f_r \left(1 + \frac{d}{D}\cos\alpha\right)$ | 缺陷随内圈旋转进出载荷区，产生转频边带 |
| **滚动体故障 (BSF)** | $\displaystyle BSF = \frac{D}{2d} f_r \left[1 - \left(\frac{d}{D}\cos\alpha\right)^2\right]$ | 滚动体自转频率，实际频谱常表现为 $2\times BSF$ |
| **保持架故障 (FTF)** | $\displaystyle FTF = \frac{f_r}{2}\left(1 - \frac{d}{D}\cos\alpha\right) = \frac{BPFO}{N}$ | 亚同步频率，通常为 $0.35\sim0.45 f_r$ |

#### 1.1.2 经验估算（缺乏几何参数时使用）

| 故障类型 | 经验估算 |
|---------|---------|
| 外圈 (BPFO) | $\approx 0.40 \, N \, f_r$ |
| 内圈 (BPFI) | $\approx 0.60 \, N \, f_r$ |
| 滚动体 (BSF) | $\approx 0.42 \, N \, f_r$ |
| 保持架 (FTF) | $\approx 0.38 \, f_r$ |

#### 1.1.3 工程容差

- 实际存在 $1\sim3\%$ 的滑移误差，频谱搜索需设 **$\pm2\sim3\%$ 容差带**
- 若缺乏几何参数，优先使用经验估算并配合制造商数据库

#### 1.1.4 代码实现映射

```python
# 参考实现位置：cloud/app/services/analyzer.py -> _compute_bearing_fault_freqs
def _compute_bearing_fault_freqs(rot_freq: float, bearing_params: dict) -> dict:
    n = bearing_params.get("n", 0)   # 滚动体数 N
    d = bearing_params.get("d", 0)   # 滚动体直径
    D = bearing_params.get("D", 0)   # 节圆直径
    alpha = np.radians(bearing_params.get("alpha", 0))  # 接触角

    cos_a = np.cos(alpha)
    dd = (d / D) * cos_a

    return {
        "BPFO": (n / 2.0) * rot_freq * (1 - dd),
        "BPFI": (n / 2.0) * rot_freq * (1 + dd),
        "BSF":  (D / (2.0 * d)) * rot_freq * (1 - dd ** 2),
        "FTF":  0.5 * rot_freq * (1 - dd),
    }
```

---

### 1.2 包络分析 / 希尔伯特解调

#### 1.2.1 物理原理

轴承局部缺陷产生的冲击激发结构高频共振，该共振信号被故障脉冲序列调幅。包络分析通过解调提取低频调制信号（故障脉冲序列），抑制高频载波。

#### 1.2.2 完整算法流程

**Step 1 — 带通滤波（共振频带选取）**
$$y(t) = \text{BandPass}[x(t); f_c, \Delta f]$$
其中 $(f_c, \Delta f)$ 为共振中心频率与带宽，可通过**谱峭度**或经验选取（通常 $2\sim20$ kHz）。

**Step 2 — 希尔伯特变换构造解析信号**
$$\mathcal{H}[y(t)] = \frac{1}{\pi} \int_{-\infty}^{\infty} \frac{y(\tau)}{t-\tau}\,d\tau$$
$$z(t) = y(t) + j\mathcal{H}[y(t)]$$

**Step 3 — 包络提取**
$$e(t) = |z(t)| = \sqrt{y^2(t) + \mathcal{H}^2[y(t)]}$$

**Step 4 — 低通滤波**
$$e_{LP}(t) = \text{LowPass}[e(t); f_{cut}]$$
截止频率 $f_{cut}$ 应大于最高故障特征频率的 $3\sim5$ 倍（通常取 $500\sim2000$ Hz）。

**Step 5 — FFT 包络谱**
$$E(f) = |\mathcal{F}[e_{LP}(t)]|$$

#### 1.2.3 故障判据

- **外圈故障**：包络谱中出现 $n\times BPFO$ 谐波族（$n=1,2,3,\dots$），至少检测到前 $3\sim5$ 阶
- **内圈故障**：BPFI 两侧出现以轴频 $f_r$ 为间隔的边带 $BPFI \pm k f_r$，同时验证 $n\times BPFI$
- **滚动体故障**：$2\times BSF$ 两侧可能出现保持架频率 FTF 的边带
- **保持架故障**：FTF 及其谐波，常伴随滚动体故障边带

#### 1.2.4 峰值显著性判据

计算峰值与背景噪声的信噪比：
$$SNR_{peak} = \frac{P_{detect}}{\text{Median}[E(f)]}$$
工程阈值：$SNR_{peak} > 3\sim5$（即峰值高于背景中位数 $3\sim5$ 倍）视为显著。

#### 1.2.5 代码实现映射

```python
# 参考实现位置：cloud/app/services/analyzer.py -> compute_envelope_spectrum
from scipy.signal import hilbert
from scipy.fft import rfft, rfftfreq

def compute_envelope_spectrum(signal, sample_rate=25600, max_freq=1000):
    arr = remove_dc(signal)
    # 可选：带通滤波 1kHz~5kHz 共振频带
    analytic_signal = hilbert(arr)
    envelope = np.abs(analytic_signal)
    envelope = envelope - np.mean(envelope)  # 零均值化
    n = len(envelope)
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(n, 1 / sample_rate)
    # 只保留 0~max_freq
    freq_amp = [(f, a) for f, a in zip(xf, yf) if f <= max_freq]
    return [f for f, a in freq_amp], [a for f, a in freq_amp]
```

---

### 1.3 谱峭度与快速谱峭度图

#### 1.3.1 物理意义

谱峭度度量信号各频率分量偏离高斯分布的程度，对瞬态冲击极度敏感。

#### 1.3.2 数学定义

$$K_Y(f) = \frac{S_{4Y}(f)}{S_{2Y}^2(f)} - 2$$

其中 $S_{2nY}(f)$ 为 $2n$ 阶瞬时矩。对于高斯噪声，$K_Y(f)=0$；出现冲击时 $K_Y(f)\gg0$。

#### 1.3.3 Fast Kurtogram 算法流程（Antoni, 2007）

**Step 1 — 构建准解析滤波器组**
- 低通生成滤波器 $h(n)$，截止频率 $f_c = 0.4$
- 二分段低通：$h_0(n) = h(n)\,e^{j\pi n/4}$，带宽 $[0, 1/4]$，中心偏移 $0.125$
- 二分段高通：$h_1(n) = h(n)\,e^{3j\pi n/4}$，带宽 $[1/4, 1/2]$，中心偏移 $0.375$
- 三分段滤波器：$h_1, h_2, h_3$ 覆盖 $[0,1/6], [1/6,1/3], [1/3,1/2]$

**Step 2 — 树状滤波器组分解**
对信号 $x(n)$ 进行 $L$ 层分解，第 $l$ 层产生 $2^l$ 个子带。第 $l$ 层第 $i$ 个系数序列 $c_{l,i}(n)$ 的中心频率与带宽：
$$f_i = (i + 2^{-1})\,2^{-l-1}, \quad \Delta f = 2^{-l-1}$$

**Step 3 — 计算各子带峭度**
对每个子带计算复包络的峭度（或包络方差）：
$$K_{l,i} = \frac{\langle|c_{l,i}|^4\rangle}{\langle|c_{l,i}|^2\rangle^2} - 2$$

**Step 4 — 构建 Kurtogram**
以 $(f_c, \Delta f)$ 为坐标绘制峭度分布图，选取全局最大峭度对应的 $(f_c^*, \Delta f^*)$ 作为最优带通滤波器参数。

**Step 5 — 对最优子带执行包络分析**

#### 1.3.4 工程改进

- **Protrugram**：用包络谱幅值的峭度替代时域峭度，抗非高斯噪声更强
- **MED+SK**：先用最小熵解卷积锐化冲击，再计算谱峭度，提升低信噪比下的检测率

---

### 1.4 倒频谱预白化 (CPW)

#### 1.4.1 核心问题

齿轮啮合频率、轴频等确定性离散频率会掩盖轴承故障的弱冲击成分。

#### 1.4.2 完整数学流程

**Step 1 — FFT**
$$X(f) = \mathcal{F}[x(t)]$$

**Step 2 — 功率谱对数**
$$\ln|X(f)|$$

**Step 3 — 倒频谱变换**
$$C(\tau) = \mathcal{F}^{-1}\{\ln|X(f)|\}$$
$\tau$ 为倒频率（quefrency），单位秒。

**Step 4 — 倒频谱编辑（Cepstral Editing / Comb Lifter）**
识别并编辑确定性分量对应的倒频谱线：
- 齿轮啮合频率族 $\rightarrow$ 对应倒频率 $\tau_{mesh} = 1/f_{mesh}, 2/f_{mesh}, \dots$
- 轴频族 $\rightarrow$ 对应倒频率 $\tau_{shaft} = 1/f_r, 2/f_r, \dots$

编辑操作：
$$C_{edit}(\tau) = \begin{cases} C(\tau), & \tau \notin [\tau_k - T_w/2, \tau_k + T_w/2] \\ \text{interp}[C(\tau)], & \tau \in [\tau_k - T_w/2, \tau_k + T_w/2] \end{cases}$$

其中 $T_w$ 为陷波宽度（通常覆盖整数倍倒频率的窄带），interp 为邻域插值/均值替换。**保留 DC 分量**用于尺度校准。

**Step 5 — 重构幅值谱**
$$\ln|X_{edit}(f)| = \mathcal{F}[C_{edit}(\tau)]$$

**Step 6 — 结合原始相位重构信号**
$$X_{new}(f) = |X_{edit}(f)| \cdot e^{j\arg[X(f)]}$$
$$x_{CPW}(t) = \mathcal{F}^{-1}[X_{new}(f)]$$

**Step 7 — 对 $x_{CPW}(t)$ 执行包络分析**

#### 1.4.3 物理意义

CPW 将各频带能量均衡化（预白化），使原本被强齿轮分量掩盖的轴承冲击成分凸显。Borghesani 等证明 CPW 在变速工况下仍能盲分离确定性齿轮成分与随机轴承成分。

#### 1.4.4 代码实现提示

```python
# 伪代码框架（尚未在项目中实现）
def cepstrum_pre_whitening(signal, sample_rate, mesh_freq, rot_freq):
    X = np.fft.rfft(signal)
    log_mag = np.log(np.abs(X) + 1e-12)
    cepstrum = np.fft.irfft(log_mag)
    
    # 构造 Comb Lifter：去除齿轮/轴频对应的倒频谱线
    # tau_mesh = 1/mesh_freq, tau_shaft = 1/rot_freq
    # 对这些位置设置陷波（用邻域均值替换）
    cepstrum_edited = comb_lifter(cepstrum, mesh_freq, rot_freq, sample_rate)
    
    # 重构
    log_mag_new = np.fft.rfft(cepstrum_edited).real
    X_new = np.exp(log_mag_new) * np.exp(1j * np.angle(X))
    return np.fft.irfft(X_new, n=len(signal))
```

---

### 1.5 循环平稳分析

#### 1.5.1 原理

轴承故障信号具有二阶循环平稳性——其统计特性随轴转角周期变化。

#### 1.5.2 核心工具

**谱相关密度（Spectral Correlation, SC）**：
$$S_x^\alpha(f) = \lim_{T\to\infty} \frac{1}{T} E\left\{X_T\left(f-\frac{\alpha}{2}\right) X_T^*\left(f+\frac{\alpha}{2}\right)\right\}$$
其中 $\alpha$ 为循环频率。

**谱相干（Spectral Coherence）**：
$$\gamma_x^\alpha(f) = \frac{S_x^\alpha(f)}{\sqrt{S_x^0(f-\alpha/2)\,S_x^0(f+\alpha/2)}}$$

#### 1.5.3 诊断逻辑

在循环频率 $\alpha$ 等于故障特征频率（BPFO/BPFI/BSF）处，谱相干出现显著峰值。该方法对随机噪声和确定性干扰具有天然免疫力，是变速工况下的高级诊断手段。

---

### 1.6 最小熵解卷积 (MED)

#### 1.6.1 模型

传感器信号 $y(n) = h(n)*x(n) + e(n)$，其中 $x(n)$ 为故障脉冲，$h(n)$ 为传递路径，$e(n)$ 为噪声。

#### 1.6.2 目标函数

设计 FIR 逆滤波器 $f(n)$，使输出 $\hat{x}(n)=f(n)*y(n)$ 的峭度最大化：
$$\max_f K(\hat{x}) = \frac{\sum(\hat{x}_i-\bar{\hat{x}})^4/N}{(\sum(\hat{x}_i-\bar{\hat{x}})^2/N)^2}$$

#### 1.6.3 迭代算法

1. 初始化滤波器系数 $f^{(0)}$
2. 计算输出 $\hat{x}^{(k)} = f^{(k)} * y$
3. 计算梯度并更新滤波器系数使峭度最大化
4. 迭代至收敛或达到最大迭代次数

#### 1.6.4 工程应用

MED 常用于信号预处理，增强被传递路径衰减的故障冲击，与谱峭度或包络分析级联使用。

---

### 1.7 时域同步平均 (TSA)

#### 1.7.1 原理

以轴转速脉冲为触发，对振动信号按转角周期分段叠加平均。与转速无关的随机噪声和异步成分被抑制，与转速同步的周期性成分（齿轮啮合、轴频谐波）被增强。

#### 1.7.2 公式

$$x_{TSA}(t) = \frac{1}{M}\sum_{m=0}^{M-1} x(t + mT_{rev})$$

其中 $T_{rev}$ 为轴旋转周期，$M$ 为平均段数（通常 $M \geq 50\sim100$ 段）。

#### 1.7.3 轴承诊断中的用途

在齿轮箱中，先用 TSA 提取并移除齿轮啮合的确定性成分，得到**残余信号（Residual Signal）**，再对残余信号进行包络分析检测轴承故障。

---

### 1.8 轴承故障特征匹配与判别准则

#### 1.8.1 包络谱峰值检测算法

**Step 1 — 理论频率计算**：根据轴承几何参数和转速，计算理论 BPFO、BPFI、BSF、FTF

**Step 2 — 容差带设定**：
$$\Delta f = \pm (0.02\sim0.03) \times f_{theory}$$

**Step 3 — 谱峰搜索**：
$$P_{detect} = \max_{f \in [f_{theory}-\Delta f, f_{theory}+\Delta f]} E(f)$$

**Step 4 — 谐波族验证**：
- 外圈：$n\times BPFO$（$n=1,2,3,\dots$）至少检测到前 $3\sim5$ 阶
- 内圈：$BPFI \pm k f_r$ 边带族，同时验证 $n\times BPFI$
- 滚动体：$2\times BSF \pm m\times FTF$ 边带

**Step 5 — 峰值显著性判据**：$SNR_{peak} = P_{detect} / \text{Median}[E(f)] > 3\sim5$

#### 1.8.2 故障类型判别决策树

```
包络谱分析
    │
    ├─ 存在 n×BPFO 谐波族，无明显边带
    │   └─→ 外圈故障（载荷区固定，无转频调制）
    │
    ├─ 存在 BPFI 谐波族，两侧有 k×f_r 边带
    │   └─→ 内圈故障（缺陷随内圈旋转进出载荷区）
    │
    ├─ 存在 2×BSF，两侧有 m×FTF 边带
    │   └─→ 滚动体故障（自转+公转双重调制）
    │
    └─ 存在 FTF 亚同步频率，伴随 BSF 边带
        └─→ 保持架故障（常伴随滚动体磨损）
```

#### 1.8.3 严重度量化指标

| 指标 | 公式/定义 | 意义 |
|-----|----------|------|
| **谐波能量比 (HER)** | $HER = \frac{\sum_{n=1}^{N_h} A(n f_{fault})}{A_{total}}$ | 故障谐波能量占比 |
| **边带调制指数** | $\beta = \frac{A_{sideband}}{A_{carrier}}$ | 内圈/滚动体调制深度 |
| **冲击周期性指标** | $C_I = \frac{|\text{FFT}[e(t)]|_{f_{fault}}}{\text{RMS}[E(f)]}$ | 冲击周期性强度 |

---

## 二、齿轮故障诊断

### 2.1 齿轮振动调制模型

#### 2.1.1 理论基础

健康齿轮振动以啮合频率 $f_{mesh}$ 及其谐波为主。故障齿轮由于齿刚度变化、误差、裂纹等，产生**调幅（AM）**和**调频（FM）**：

$$x(t) = \sum_{k=0}^{K} a_k(t)\cos\left[2\pi k f_{mesh} t + b_k(t) + \theta_k\right]$$

其中：
- 幅值调制：$a_k(t) = A_k\left[1 + \sum_{n=1}^{N} m_{kn}\cos(2\pi n f_{char}t + \phi_{kn})\right]$
- 相位调制：$b_k(t) = \sum_{l=1}^{L} \beta_{kl}\sin(2\pi l f_{char}t + \varphi_{kl})$

$f_{char}$ 为故障齿轮所在轴的转频。

#### 2.1.2 边频带

调制产生以 $m f_{mesh}$ 为中心、间隔为 $k f_{char}$ 的**边频带（Sidebands）**：
$$f_{sb} = m \cdot f_{mesh} \pm k \cdot f_{char}$$

**工程口诀**："啮合频率看幅值，故障诊断看边带"。边频间隔指示故障轴，边频幅值与不对称性指示故障严重程度。

#### 2.1.3 啮合频率计算

$$f_{mesh} = Z \cdot f_r$$

其中 $Z$ 为齿轮齿数，$f_r$ 为轴旋转频率。

---

### 2.2 时域同步平均 (TSA) 在齿轮诊断中的应用

#### 2.2.1 McFadden 经典方法

1. 根据转速脉冲或编码器信号，将振动信号重采样到角域（Order Tracking）
2. 对目标齿轮按齿啮合周期（或轴转周期）进行同步平均
3. 得到仅包含该齿轮啮合成分的平均信号 $x_{gear}(t)$
4. **残余信号**：$r(t) = x(t) - x_{gear}(t)$，包含轴承故障、其他齿轮及随机成分

#### 2.2.2 角域重采样（Order Tracking）

根据转速脉冲或编码器，将时域信号 $x(t)$ 按等角度 $\Delta\theta$ 重采样为 $x(\theta)$。

#### 2.2.3 同步平均公式

$$x_{TSA}(\theta) = \frac{1}{M}\sum_{m=0}^{M-1} x(\theta + m\cdot 2\pi)$$

$M$ 为平均段数（通常 $M \geq 50\sim100$ 段）。

#### 2.2.4 残余信号与差分信号

- **残余信号**：$r(t) = x(t) - x_{TSA}(t)$，包含轴承故障、非同步齿轮成分及随机噪声
- **差分信号**：$d(t) = x_{TSA}(t) - R(t)$，其中 $R(t)$ 为 TSA 信号中的规则啮合分量（啮合频率及其谐波 + 一阶边带）。差分信号用于检测局部齿故障

---

### 2.3 齿轮经典时域故障指标

所有指标均基于 TSA 信号或其衍生信号计算。

#### 2.3.1 FM0 — 粗故障检测（齿断裂/严重磨损）

$$FM0 = \frac{PP}{\sum_{i=1}^{n} A(f_i)}$$

- $PP$：TSA 信号的峰-峰值（$\max(x_{TSA}) - \min(x_{TSA})$）
- $A(f_i)$：啮合频率及其前 $n$ 阶谐波的幅值
- **物理意义**：比较冲击幅值与啮合能量。齿断裂时 $PP$ 剧增而啮合能量变化小，$FM0$ 显著增大
- **典型阈值**：健康状态 $FM0 < 3\sim5$；严重故障 $FM0 > 10\sim20$

#### 2.3.2 FM4 — 局部故障检测（单/双齿点蚀/裂纹）

$$FM4 = \frac{N\sum_{i=1}^{N}(d_i - \bar{d})^4}{\left[\sum_{i=1}^{N}(d_i - \bar{d})^2\right]^2}$$

- $d_i$：差分信号 $d(t)$ 的第 $i$ 个采样点
- $\bar{d}$：差分信号均值
- $N$：采样点数
- **物理意义**：差分信号的归一化峭度。局部故障产生孤立大峰值，使分布尖锐，$FM4 > 3$（高斯基准）。若过多齿损坏，分布反而变平坦，$FM4$ 下降
- **典型阈值**：健康 $\approx 3$；局部故障 $> 5\sim10$

#### 2.3.3 NA4 — 趋势型故障检测（损伤扩展追踪）

$$NA4(M) = \frac{\frac{1}{N}\sum_{i=1}^{N}(r_i - \bar{r})^4}{\left\{\frac{1}{M}\sum_{j=1}^{M}\left[\frac{1}{N}\sum_{k=1}^{N}(r_{kj} - \bar{r}_j)^2\right]\right\}^2}$$

- $r_i$：残余信号第 $i$ 点
- $M$：运行集合中的时间记录总数（历史样本数）
- $j$：第 $j$ 个历史记录
- **物理意义**：准归一化峭度，分母为**历史平均方差**，使 NA4 与系统健康基线对比。随损伤扩展单调上升，适用于趋势监测
- **与 FM4 区别**：FM4 分母为当前记录方差，对大面积损伤不敏感；NA4 分母为历史平均方差，持续响应损伤增长

#### 2.3.4 NB4 — 局部齿损坏（包络域）

$$NB4(M) = \frac{\frac{1}{N}\sum_{i=1}^{N}(E_i - \bar{E})^4}{\left\{\frac{1}{M}\sum_{j=1}^{M}\left[\frac{1}{N}\sum_{k=1}^{N}(E_{kj} - \bar{E}_j)^2\right]\right\}^2}$$

- $E_i$：残余信号经带通滤波（围绕啮合频率/轴频）后的包络信号，$E(t) = |b(t) + j\mathcal{H}[b(t)]|$
- **物理意义**：检测由局部齿损坏引起的瞬态负载波动（反映在包络上）

#### 2.3.5 M6A / M8A — 表面损伤高阶矩

$$M6A = \frac{N^2\sum_{i=1}^{N}(d_i - \bar{d})^6}{\left[\sum_{i=1}^{N}(d_i - \bar{d})^2\right]^3}$$

$$M8A = \frac{N^3\sum_{i=1}^{N}(d_i - \bar{d})^8}{\left[\sum_{i=1}^{N}(d_i - \bar{d})^2\right]^4}$$

- **物理意义**：基于差分信号的 6 阶/8 阶归一化矩，对表面缺陷（剥落、点蚀）比 FM4 更敏感，但更易受噪声干扰产生假报警
- **工程权衡**：高阶矩敏感度高，但需配合低阶指标交叉验证

#### 2.3.6 ER — 能量比（多齿磨损）

$$ER = \frac{\text{RMS}[d(t)]}{\sum_{i=1}^{n_{har}} A(f_{mesh,i}) + \sum_{j=1}^{n_{sb}}(SB_j^+ + SB_j^-)}$$

- 分子：差分信号 RMS 能量
- 分母：规则啮合分量（啮合谐波 + 边带）总能量
- **物理意义**：多齿均匀磨损时，差分信号能量相对啮合能量增加

#### 2.3.7 SER — 边频带能量比（核心频域指标）

$$SER = \frac{\sum_{i=1}^{6}(A_{SB_i}^+ + A_{SB_i}^-)}{A(f_{mesh})}$$

- $A(f_{mesh})$：啮合频率（或其二阶谐波）幅值
- $A_{SB_i}^+, A_{SB_i}^-$：啮合频率两侧前 6 阶边频带幅值
- **物理意义**：边频能量与啮合能量的比值。健康齿轮 $SER < 1$；故障齿轮边频增加，$SER > 1$ 且随劣化单调上升。GE Bently Nevada ADAPT.wind 系统的核心指标

#### 2.3.8 代码实现映射

```python
# 伪代码框架（尚未在项目中完整实现）
def compute_fm0(tsa_signal, mesh_freq, sample_rate):
    pp = np.max(tsa_signal) - np.min(tsa_signal)
    # 计算啮合频率前n阶谐波幅值和
    xf, yf = compute_fft(tsa_signal, sample_rate)
    harmonics_sum = sum(_band_energy(xf, yf, mesh_freq * i, 5.0) for i in range(1, n+1))
    return pp / harmonics_sum

def compute_fm4(differential_signal):
    d = np.array(differential_signal)
    N = len(d)
    d_mean = np.mean(d)
    numerator = N * np.sum((d - d_mean)**4)
    denominator = np.sum((d - d_mean)**2)**2
    return numerator / denominator

def compute_na4(residual_signal, historical_residuals):
    # historical_residuals: list of past residual signal arrays
    r = np.array(residual_signal)
    N = len(r)
    r_mean = np.mean(r)
    numerator = (1/N) * np.sum((r - r_mean)**4)
    
    M = len(historical_residuals)
    variances = []
    for hist in historical_residuals:
        hist_mean = np.mean(hist)
        variances.append((1/len(hist)) * np.sum((hist - hist_mean)**2))
    denom_mean = np.mean(variances)
    return numerator / (denom_mean ** 2)

def compute_ser(freq, amp, mesh_freq, rot_freq):
    # 搜索啮合频率两侧前6阶边频
    total_sideband = 0.0
    for i in range(1, 7):
        sb_low = mesh_freq - i * rot_freq
        sb_high = mesh_freq + i * rot_freq
        total_sideband += _band_energy(freq, amp, sb_low, 2.0)
        total_sideband += _band_energy(freq, amp, sb_high, 2.0)
    mesh_amp = _band_energy(freq, amp, mesh_freq, 5.0)
    return total_sideband / mesh_amp
```

---

### 2.4 倒频谱分析

#### 2.4.1 定义

功率倒频谱：
$$C(\tau) = \mathcal{F}^{-1}\{\ln|X(f)|\}$$

其中 $\tau$ 为倒频率（quefrency），单位为秒。

#### 2.4.2 齿轮诊断优势

1. **边频带族压缩**：频谱中围绕 $f_{mesh}$ 的成簇边带 $f_{mesh} \pm k f_r$，在倒频谱中压缩为单根谱线，位置 $\tau = 1/f_r$
2. **传输路径不敏感**：测点位置和传递路径的影响在倒频谱中表现为相加的慢变分量，与故障相关的周期分量分离
3. **多齿轮分离**：不同轴转频在倒频谱中呈现为不同位置的离散谱线，便于识别多故障源

#### 2.4.3 典型判据

- 倒频谱峰值对应频率 $\approx$ 齿轮轴转频 $\rightarrow$ 该齿轮存在磨损/点蚀/剥落
- 倒频谱峰值对应频率 $\approx$ 轴承内圈转频 $\rightarrow$ 轴承内圈故障

#### 2.4.4 倒频谱幅值比 (CAR) —— 劣化指标

$$CAR = \frac{\text{mean}\left[\sum_{i=1}^{n} C_{peak}^i\right]}{\text{mean}_{\tau \in [\tau_{min}, \tau_{end}]} C_x(\tau)}$$

其中：
$$C_{peak}^i = \max_{\tau \in [1/(i f_r)-\Delta\tau, 1/(i f_r)+\Delta\tau]} C_x(\tau)$$

- 分子：各阶故障特征倒频率对应幅值均值
- 分母：高倒频率（背景）幅值均值
- $\Delta\tau$：倒频谱搜索容差（通常对应 $\pm500$ Hz 容差）
- **判据**：$CAR > 1$ 且持续上升趋势指示齿轮劣化

---

### 2.5 边频带分析

#### 2.5.1 边频带识别算法

**Step 1 — 确定啮合频率**：$f_{mesh} = Z \cdot f_r$

**Step 2 — 高分辨率频谱**：采用 ZOOM-FFT 或细化谱分析，确保频率分辨率 $\Delta f \leq f_r/4$（至少能分辨 4 根边频）

**Step 3 — 边频带搜索**：
$$f_{sb} = f_{mesh} \pm k \cdot f_r, \quad k=1,2,\dots,K$$
通常取前 $K=6$ 阶。

**Step 4 — 边频显著性检验**：
$$\rho_k = \frac{A(f_{mesh} \pm k f_r)}{A(f_{mesh})}$$
若 $\rho_k > 0.05\sim0.1$（即边频幅值超过啮合频率 $5\sim10\%$），视为显著。

#### 2.5.2 故障模式与边频特征对应表

| 故障类型 | 边频带特征 | 频谱/解调表现 |
|---------|----------|-------------|
| **齿形误差** | 边频稀疏、幅值小，以 1× 转频为主 | 啮合频率附近少量边带 |
| **齿轮均匀磨损** | 边频带密集、幅值升高，谐波增多 | 啮合频率及谐波整体抬升 |
| **齿轮偏心** | 强 1× 转频边带，左右基本对称 | $f_{mesh} \pm f_r$ 幅值大 |
| **齿面裂纹/断齿** | 边带宽且高，高阶边频显著，常不对称 | 解调谱出现转频多次谐波 |
| **轴不对中** | 2× 转频边带突出 | $f_{mesh} \pm 2f_r$ 显著 |
| **齿面点蚀** | 边频幅值中等，SER 缓慢上升 | SER 趋势性增加 |

#### 2.5.3 工程方法

- **细化谱分析（ZOOM-FFT）**：提高低频分辨率，精确测定边带间隔
- **边频带能量指标**：计算啮合频率两侧边频带总能量作为故障严重度指标
- **边频带乘积谱（SPS）**：利用边频带的周期性，通过乘积运算增强弱边频

---

### 2.6 齿轮故障特征匹配与判别准则

#### 2.6.1 多指标融合决策矩阵

| 故障阶段 | FM0 | FM4 | NA4 | SER | CAR | 频谱特征 |
|---------|-----|-----|-----|-----|-----|---------|
| **健康** | 低 | $\approx 3$ | 基线 | $<1$ | 基线 | 啮合频率为主，少量边频 |
| **早期点蚀** | 略升 | $>5$ | 上升 | $1\sim2$ | 上升 | 边频增加，1~2 阶为主 |
| **局部裂纹** | 中 | $>10$ | 明显上升 | $2\sim5$ | 明显上升 | 高阶边频显著，解调谱谐波丰富 |
| **断齿** | 极高 | 可能回落 | 极高 | $>5$ | 极高 | 啮合频率幅值剧变，边频极宽 |
| **均匀磨损** | 中 | 低 | 缓慢升 | $>1$ | 缓慢升 | 啮合谐波整体抬升 |

#### 2.6.2 故障定位逻辑

```
TSA + 频谱分析
    │
    ├─ SER < 1, FM0 正常, FM4 ≈ 3
    │   └─→ 健康状态
    │
    ├─ SER > 1, 边频间隔 = f_r1
    │   └─→ 轴1对应齿轮故障
    │
    ├─ SER > 1, 边频间隔 = f_r2
    │   └─→ 轴2对应齿轮故障
    │
    ├─ FM4 > 10, NA4 急剧上升, 边频不对称
    │   └─→ 局部裂纹/断齿（故障齿轮所在轴由边频间隔判定）
    │
    └─ FM0 高, FM4 低, SER 中等
        └─→ 均匀磨损/多齿损坏
```

#### 2.6.3 趋势报警阈值设定

| 指标 | 警告阈值 | 危险阈值 | 趋势判据 |
|-----|---------|---------|---------|
| **SER** | $1.5$ | $3.0$ | 连续 3 次采样上升 |
| **FM4** | $5$ | $10$ | 单次超限即报警 |
| **NA4** | 基线 $+2\sigma$ | 基线 $+3\sigma$ | 相对基线偏移 |
| **CAR** | $1.2$ | $2.0$ | 连续上升趋势 |

---

## 三、轴承与齿轮故障的分离与鉴别诊断

### 3.1 信号本质差异

| 特性 | 齿轮信号 | 轴承信号 |
|-----|---------|---------|
| **周期性** | 确定性，与轴转角严格同步 | 伪周期，受滚动体滑移影响 |
| **频谱性质** | 离散谱（啮合频率 + 边带） | 连续谱 + 离散冲击谱 |
| **统计特性** | 平稳/确定性 | 循环平稳 / 伪循环平稳 |
| **倒频谱表现** | 低倒频率强线谱（谐波族） | 高倒频率随机背景 + 弱周期线谱 |

### 3.2 确定性-随机分离 (DRS / CPW)

#### 3.2.1 核心方法——倒频谱编辑（Cepstral Editing / CPW）

**Step 1 — 计算倒频谱**：$C(\tau) = \mathcal{F}^{-1}\{\ln|X(f)|\}$

**Step 2 — 识别确定性分量**
齿轮和轴频在倒频谱中表现为低倒频率处的**梳状线谱（rahmonics）**：
$$\tau_k = \frac{k}{f_{mesh}}, \quad \tau_m = \frac{m}{f_r}$$

**Step 3 — 梳状陷波提升（Comb Lifter）**
构造倒频域滤波器：
$$L(\tau) = \begin{cases} 0, & \tau \in \bigcup_k [\tau_k - T_w/2, \tau_k + T_w/2] \\ 1, & \text{其他} \end{cases}$$

$$C_{random}(\tau) = C(\tau) \cdot L(\tau)$$

**Step 4 — 重构随机成分**
$$\ln|X_{rand}(f)| = \mathcal{F}[C_{random}(\tau)]$$
$$X_{rand}(f) = |X_{rand}(f)| \cdot e^{j\arg[X(f)]}$$
$$x_{rand}(t) = \mathcal{F}^{-1}[X_{rand}(f)]$$

**结果**：$x_{rand}(t)$ 主要为轴承冲击和随机噪声，齿轮确定性分量被极大抑制。对 $x_{rand}(t)$ 执行包络分析即可诊断轴承。

### 3.3 齿轮箱中轴承诊断的标准流程

```
原始振动信号 x(t)
    │
    ├─ [转速信号] ──→ 角域重采样（Order Tracking）
    │
    ↓
时域同步平均 TSA ──→ 提取齿轮啮合确定性分量 x_gear(t)
    │
    ├─→ 齿轮诊断：对 x_gear(t) 计算 FM0/FM4/NA4/SER
    │
    └─→ 残余信号 r(t) = x(t) - x_gear(t)
            │
            ├─→ 倒频谱预白化 CPW ──→ 消除残余啮合谐波
            │
            └─→ 谱峭度 Fast Kurtogram ──→ 最优带通 (f_c*, Δf*)
                    │
                    └─→ 包络分析 ──→ 包络谱峰值匹配 BPFO/BPFI/BSF/FTF
                            │
                            └─→ 轴承故障定位与严重度评估
```

### 3.4 鉴别诊断要点

1. **若包络谱中出现轴频 $f_r$ 的谐波，但无轴承特征频率**：
   - 可能是齿轮偏心、轴不对中或转子不平衡，**非轴承故障**

2. **若倒频谱中仅见齿轮啮合倒频率 $\tau_{mesh}$，未见轴承特征**：
   - 齿轮系统正常，轴承无显著故障

3. **若 CPW 后谱峭度极高，但包络谱无周期性峰值**：
   - 可能存在随机冲击干扰（如润滑不良、异物进入），需结合温度、油液分析

4. **若同时存在齿轮边频增加和轴承特征频率**：
   - 齿轮箱存在**复合故障**，需分别评估齿轮指标（SER/FM4）和轴承指标（包络谱峰值），优先处理严重度更高者

---

## 四、抗漂变与降噪技术体系

### 4.1 漂变问题的工程本质

| 漂变类型 | 表现形式 | 根因 |
|---------|---------|------|
| **基线漂移** | 健康状态下的振动幅值、温度、电流基线随季节/负载缓慢上移或下移 | 设备老化、润滑状态变化、环境温度、传感器零点漂移 |
| **特征掩蔽** | 故障冲击被强背景噪声（如轮轨噪声、流体噪声、电磁干扰）湮没 | 信噪比过低（SNR < 0 dB），故障特征频带与噪声频带重叠 |
| **分布漂移** | 训练/标定时的特征分布与在线数据分布不一致 | 工况迁移、转速波动、负载变化、测量误差 |
| **阈值失效** | 固定阈值在噪声冲击下频繁触发报警，或故障时无法越过阈值 | 未考虑信号非平稳性和噪声统计特性变化 |

工业现场（如高速列车轴箱、风电齿轮箱、钢厂轧机）常出现 **SNR 低至 −4 dB** 的情况，此时传统包络分析直接失效。

### 4.2 信号级降噪

#### 4.2.1 小波阈值去噪（工程最成熟、实时性最好）

**核心公式**：
- **软阈值**：$\hat{w} = \text{sgn}(w)\cdot\max(|w|-T, 0)$
- **硬阈值**：$\hat{w} = w \cdot \mathbb{I}(|w|>T)$
- **改进非线性阈值**（抑制伪吉布斯振荡）：
  $$\hat{w} = \text{sgn}(w)\cdot\left(|w| - \frac{T}{1+e^{\beta(|w|-T)}}\right)$$

**工程参数选取**：
- **小波基**：轴承/齿轮冲击信号优先选 **db8、sym8、coif5**（紧支撑、正交、高阶消失矩）
- **分解层数**：$L = \lfloor\log_2(N)\rfloor - 2$，通常 $5\sim7$ 层
- **阈值**：$T = \sigma\sqrt{2\ln N}$（通用阈值），其中 $\sigma = \text{Median}(|d_{L-1}|)/0.6745$（鲁棒估计）
- **阈值函数**：强噪声下优先用**软阈值**（避免硬阈值引起的振荡），若信号失真严重改用改进阈值

#### 4.2.2 自适应模态分解降噪（EMD/EEMD/VMD）

**算法流程**：
1. 对含噪信号 $x(t)$ 进行 EMD/EEMD/VMD 分解，得到 IMF 分量 $\{c_1(t), c_2(t), \dots, c_K(t)\}$
2. **IMF 筛选**：计算各 IMF 与原始信号的**互相关系数** $\rho_i$ 和**峭度** $K_i$
3. **重构规则**：保留 $\rho_i > 0.3$ 且 $K_i > 3$ 的 IMF，剔除高频噪声主导分量
4. 重构信号 $x_{den}(t) = \sum_{i \in \mathcal{S}} c_i(t)$

**VMD 参数优化**：
VMD 需预设模态数 $K$ 和惩罚因子 $\alpha$。工程上采用 **K-L 散度** 或 **PSO/GA** 自适应优化：
- 目标函数：最小化重构误差 + 最小化模态混叠
- 优化变量：$(K, \alpha)$，通常 $K \in [3,10]$，$\alpha \in [100, 5000]$

#### 4.2.3 LMS 自适应滤波（强背景噪声实时抑制）

**模型**：$x(n) = s(n) + v(n)$，$s(n)$ 为故障信号，$v(n)$ 为与 $s(n)$ 不相关的宽平稳噪声。

**LMS 更新公式**：
$$e(n) = x(n) - \mathbf{w}^T(n)\mathbf{u}(n)$$
$$\mathbf{w}(n+1) = \mathbf{w}(n) + \mu\, e(n)\, \mathbf{u}(n)$$

其中 $\mathbf{u}(n)$ 为参考噪声输入（可由独立噪声传感器或延迟信号构造），$\mu$ 为步长。

**工程要点**：
- 变步长 LMS（VSSLMS）：$\mu(n) = \alpha\mu(n-1) + \gamma e^2(n)$，兼顾收敛速度与稳态误差
- 归一化 LMS（NLMS）：$\mu$ 按输入功率归一化，防止发散
- 适用于**存在独立参考噪声通道**的场景（如电机轴承诊断中，用机身振动作为参考去除环境噪声）

#### 4.2.4 盲源分离（BSS）——多传感器场景

当多测点信号为故障源与噪声的线性混合 $\mathbf{x}(t) = \mathbf{A}\mathbf{s}(t)$ 时：

**FastICA / JADE 算法**：
1. 中心化和白化：$\mathbf{z} = \mathbf{Q}\mathbf{x}$
2. 估计分离矩阵 $\mathbf{W}$，使各分量独立性最大化（基于峭度或负熵）
3. 分离源信号 $\mathbf{y} = \mathbf{W}\mathbf{z}$
4. 根据频谱特征识别含故障信息的独立分量

**单通道盲分离**（仅有一个传感器时）：
- **EEMD + ICA**：先用 EEMD 将单通道信号扩展为多通道 IMF 矩阵，再执行 ICA
- **相空间重构 + FastICA**：通过延迟嵌入将单通道转为正定多通道问题

**工程价值**：BSS 能从物理上分离噪声源与故障源，而非简单滤除频带，避免损伤故障成分。

#### 4.2.5 联合降噪策略（工程推荐）

| 场景 | 推荐组合 | 作用 |
|-----|---------|------|
| **强高斯白噪声** | 小波阈值 + VMD | 小波去除白噪声，VMD分离非平稳成分 |
| **强脉冲型干扰** | LMS + 中值滤波 | LMS 抑制平稳噪声，中值滤波剔除脉冲 |
| **多传感器可用** | BSS + 小波包 | BSS 分离源信号，小波包精化特征频带 |
| **复合故障+噪声** | XWT + IVMD | 交叉小波相干去除非相干噪声，VMD 精确定位故障模态 |

### 4.3 特征级抗漂变

#### 4.3.1 谱峭度 / Fast Kurtogram（自适应避噪选带）

**核心逻辑**：不人工设定共振频带，而是让算法自动寻找**受噪声污染最小、故障冲击最显著**的频带。

#### 4.3.2 倒频谱预白化（CPW）——消除确定性干扰导致的"假漂变"

齿轮啮合、轴频等确定性分量在频谱中表现为强离散谱线，其幅值随工况波动会造成**虚假的基线漂移**。CPW 将这些分量均衡化（见 1.4 节）。

#### 4.3.3 残差收缩与不对称软阈值（深度学习端）

对于采用深度学习的诊断系统，噪声会导致特征图激活异常：

**多尺度残差收缩块（MASRSB）**：
- **双注意力不对称阈值块**：将特征图正负响应分离，分别计算动态阈值
- **自适应阈值斜率模块**：根据特征图局部方差自动调整收缩斜率
- **物理意义**：强噪声区域特征被收缩至零，弱故障特征被保留并增强

该结构在 SNR = −4 dB 时仍能保持 72.5% 的诊断准确率，相比 ResNet50 提升 12.5% 以上。

### 4.4 决策级鲁棒化

#### 4.4.1 统计过程控制（SPC）——抗漂变的核心理论工具

传统固定阈值无法适应缓慢漂移，必须引入**记忆型控制图**。

##### 4.4.1.1 CUSUM（累积和）控制图——检测缓慢漂移最敏感

**统计量**：
$$C_i^+ = \max\left(0,\; x_i - \mu_0 - K + C_{i-1}^+\right)$$
$$C_i^- = \max\left(0,\; \mu_0 - x_i - K + C_{i-1}^-\right)$$

其中：
- $\mu_0$：健康基线均值（由历史数据估计）
- $K = \delta\sigma/2$：参考值，$\delta$ 为待检测的最小偏移量（通常取 $0.5\sigma \sim 1.0\sigma$）
- 决策规则：若 $C_i^+ > H$ 或 $C_i^- > H$（$H \approx 4\sim5\sigma$），则报警

**为什么抗漂变**：CUSUM 累积微小偏差，对**缓慢劣化导致的趋势性漂移**极度敏感，而 Shewhart 图对此完全失效。

##### 4.4.1.2 EWMA（指数加权移动平均）控制图——平滑随机波动

**统计量**：
$$z_i = \lambda x_i + (1-\lambda)z_{i-1}, \quad 0 < \lambda \leq 1$$

- $\lambda$ 越小（如 $0.05\sim0.2$），对历史记忆越强，越能平滑随机噪声
- 控制限：$UCL/LCL = \mu_0 \pm L\sigma\sqrt{\frac{\lambda}{2-\lambda}[1-(1-\lambda)^{2i}]}$

**工程选择**：
- **EWMA**：适合检测 $0.5\sigma \sim 1.5\sigma$ 的小偏移，对测量误差和自相关数据鲁棒
- **CUSUM**：适合检测持续单向漂移
- **Shewhart + CUSUM/EWMA 组合**：Shewhart 抓突发大故障，CUSUM/EWMA 抓缓慢劣化漂移

##### 4.4.1.3 非参数 CUSUM——不依赖正态假设

工业振动数据往往**非高斯、重尾、偏态**。非参数 CUSUM 基于符号统计或 Mann-Whitney 统计量，不假设分布形式，对异常值和偏态分布更鲁棒。

#### 4.4.2 自适应阈值与动态基线更新

##### 4.4.2.1 滑动窗口基线（Sliding Window Baseline）

**算法**：
1. 维护长度为 $W$（如 $W=1440$ 个点，对应 24 小时）的健康数据环形缓冲区
2. 每采集一个新样本，剔除最旧样本，重新计算窗口内的：
   - 基线：$\mu_{base} = \text{Median}(x_{t-W+1:t})$（用**中位数**而非均值，抗脉冲干扰）
   - 标准差：$\sigma_{base} = 1.4826 \cdot \text{MAD}(x_{t-W+1:t})$（MAD 为绝对中位差）
3. 动态阈值：$Th_{upper} = \mu_{base} + k\cdot\sigma_{base}$，$Th_{lower} = \mu_{base} - k\cdot\sigma_{base}$
4. 报警条件：连续 $N$ 个点（如 $N=3\sim5$）超出阈值带，且持续 $T_{dur}$（如 2 分钟）

**为什么有效**：基线随设备缓慢老化自适应上移，固定阈值不会过早触发；中位数+MAD 对突发噪声不敏感。

##### 4.4.2.2 Holt-Winters 三阶指数平滑（带趋势与季节分量）

$$\hat{y}(t+h) = l(t) + h\cdot b(t) + s(t+h-m(k+1))$$

- $l(t)$：水平分量（基线）
- $b(t)$：趋势分量（漂移速率）
- $s(t)$：季节分量（如日负荷周期）

通过显式建模趋势项 $b(t)$，系统能区分"正常的缓慢劣化趋势"和"异常的加速劣化漂移"。

##### 4.4.2.3 测量误差补偿

当存在显著测量误差时，采用**状态空间模型 + Kalman 滤波**：
$$\mathbf{x}_t = \mathbf{F}\mathbf{x}_{t-1} + \mathbf{w}_t$$
$$\mathbf{y}_t = \mathbf{H}\mathbf{x}_t + \mathbf{v}_t$$

其中 $\mathbf{v}_t$ 为测量误差。Kalman 滤波给出状态的最优估计，有效抑制测量噪声导致的虚假漂移。

#### 4.4.3 多传感器融合与冲突消解

##### 4.4.3.1 方差驱动加权融合

对 $M$ 个传感器，根据各通道实时方差 $\sigma_i^2$ 分配权重：
$$w_i = \frac{1/\sigma_i^2}{\sum_{j=1}^M 1/\sigma_j^2}$$

噪声大的传感器权重自动衰减至接近零，信息丰富的传感器主导决策。

##### 4.4.3.2 D-S 证据理论（决策级融合）

**识别框架** $\Omega = \{F_1, F_2, \dots, F_n, \Theta\}$（$\Theta$ 为未知状态）。

**基本概率分配（BPA）**：每个传感器给出对各故障模式的置信度 $m_i(F_j)$。

**组合规则**（Dempster 组合）：
$$m(A) = \frac{\sum_{B\cap C=A} m_1(B)m_2(C)}{1-K}, \quad K = \sum_{B\cap C=\emptyset} m_1(B)m_2(C)$$

**冲突消解**：当传感器间高度冲突（$K \to 1$）时，经典 D-S 会产生悖论。工程上采用：
- **Murphy 平均法**：先对证据加权平均，再组合
- **Jousselme 距离修正**：根据证据间距离计算可信度，修正 BPA 后再组合
- **Markov 链建模**：利用状态转移规律降低随机冲突证据的影响

**工程价值**：即使单个传感器被强噪声污染导致误判，融合后系统仍能保持高置信度正确决策。

##### 4.4.3.3 投票与一致性检验

- **硬投票**：多个传感器独立诊断，少数服从多数
- **软投票**：加权平均各传感器的故障概率
- **一致性检验**：若传感器间结果差异过大（如 3 个传感器给出 3 种不同故障），系统输出"无法确定"并提示人工介入，避免强行融合产生荒谬结论

### 4.5 工程部署完整抗漂变工作流

```
┌─────────────────────────────────────────────────────────────┐
│  多传感器采集层（振动 + 温度 + 转速 + 电流）                    │
│  ↓                                                          │
│  ① 信号级降噪（并行处理）                                      │
│     ├─ 通道1：小波阈值去噪 / VMD分解                          │
│     ├─ 通道2：LMS自适应滤波（若有参考噪声）                    │
│     └─ 通道3：盲源分离（多通道时）                             │
│  ↓                                                          │
│  ② 特征级抗漂变                                               │
│     ├─ 谱峭度 / Fast Kurtogram → 自适应选带                  │
│     ├─ 倒频谱预白化（CPW）→ 消除工况相关确定性干扰             │
│     └─ 多尺度特征提取（避免单尺度被噪声淹没）                   │
│  ↓                                                          │
│  ③ 单通道独立诊断                                               │
│     ├─ 轴承：包络谱峰值匹配 BPFO/BPFI/BSF                     │
│     └─ 齿轮：TSA + FM4/NA4/SER + 边频带分析                   │
│  ↓                                                          │
│  ④ 决策级鲁棒化                                                │
│     ├─ 动态基线：滑动窗口中位数 + MAD                          │
│     ├─ 趋势检测：CUSUM / EWMA 控制图                          │
│     ├─ 多传感器融合：D-S 证据理论 / 方差加权投票               │
│     └─ 报警策略：连续N点超限 + 持续Tdur时间 + 多源确认         │
│  ↓                                                          │
│  ⑤ 基线自适应更新                                              │
│     ├─ 每周/每月用健康数据重新标定 μ₀, σ₀                     │
│     └─ 工况切换时（如负载变化>20%）触发基线冻结或重新学习       │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、关键工程参数速查表

| 环节 | 方法 | 核心参数 | 推荐值 |
|-----|------|---------|--------|
| **降噪** | 小波去噪 | 小波基 / 层数 / 阈值 | db8 / 5~7层 / $\sigma\sqrt{2\ln N}$ |
| **降噪** | VMD | 模态数 $K$ / 惩罚因子 $\alpha$ | PSO优化，$K\in[3,10]$, $\alpha\in[100,5000]$ |
| **特征** | Fast Kurtogram | 搜索层数 | 4~6层，覆盖 $0\sim f_s/2$ |
| **特征** | CPW | 陷波宽度 $T_w$ | 覆盖 $\pm 2\%$ 倒频率区间 |
| **决策** | CUSUM | 参考值 $K$ / 决策限 $H$ | $K=0.5\sigma$, $H=4\sigma\sim5\sigma$ |
| **决策** | EWMA | 平滑因子 $\lambda$ / 控制限系数 $L$ | $\lambda=0.05\sim0.2$, $L=2.6\sim3.0$ |
| **基线** | 滑动窗口 | 窗口长度 $W$ / 确认点数 $N$ | $W=1000\sim2000$点, $N=3\sim5$ |
| **融合** | D-S 证据 | 冲突阈值 $K_{max}$ | $K>0.8$ 时启用冲突修正机制 |
| **轴承** | 包络分析 | 带通频段 $f_c$ / 低通截止 $f_{cut}$ | $2\sim20$ kHz / $500\sim2000$ Hz |
| **轴承** | 峰值检测 | 容差带 $\Delta f$ | $\pm 2\sim3\%$ 理论频率 |
| **轴承** | 峰值显著性 | SNR 阈值 | $> 3\sim5$ |
| **齿轮** | TSA | 平均段数 $M$ | $\geq 50\sim100$ 段 |
| **齿轮** | SER | 边频阶数 | 前 6 阶 |
| **齿轮** | FM4 报警 | 警告/危险 | $5$ / $10$ |
| **齿轮** | NA4 报警 | 警告/危险 | 基线 $+2\sigma$ / $+3\sigma$ |
| **齿轮** | SER 报警 | 警告/危险 | $1.5$ / $3.0$ |
| **齿轮** | CAR 报警 | 警告/危险 | $1.2$ / $2.0$ |

---

## 六、核心参考文献索引

### 轴承故障诊断经典文献

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Randall & Antoni (2011)** | *Rolling element bearing diagnostics—a tutorial*, MSSP 25(2): 485-520 | 轴承诊断综述教程，涵盖包络分析、谱峭度、循环平稳 | 1.2, 1.3, 1.5 |
| **Antoni (2006)** | *The spectral kurtosis: a useful tool for characterising non-stationary signals*, MSSP 20(2): 282-307 | 谱峭度严格数学定义 | 1.3 |
| **Antoni (2007)** | *Fast computation of the kurtogram for the detection of transient faults*, MSSP 21(1): 108-124 | 快速谱峭度图（Fast Kurtogram） | 1.3 |
| **Randall et al. (2001)** | *The relationship between spectral correlation and envelope analysis...*, MSSP 15(5): 945-962 | 谱相关与包络分析的关系 | 1.5 |
| **Sawalhi et al. (2007)** | *Enhancement of fault detection... using MED combined with spectral kurtosis*, MSSP 21(6): 2616-2633 | MED+SK 联合增强 | 1.6 |
| **Ho & Randall (2000)** | *Optimisation of bearing diagnostic techniques using simulated and actual bearing fault signals*, MSSP 14(5): 763-788 | 模拟与实测信号优化诊断 | 1.2 |
| **Borghesani et al. (2013)** | *Application of cepstrum pre-whitening for the diagnosis of bearing faults under variable speed*, MSSP 36(2): 370-384 | 变速工况倒频谱预白化 | 1.4, 3.2 |
| **McFadden & Smith (1984)** | *Model for the vibration produced by a single point defect in a rolling element bearing*, JSV 96(1): 69-82 | 单点缺陷振动理论模型 | 1.1 |
| **Randall (2017)** | *A history of cepstrum analysis and its application to mechanical problems*, MSSP 97: 3-19 | 倒频谱分析历史与应用 | 2.4 |

### 齿轮故障诊断经典文献

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **McFadden (1987)** | *Examination of a technique for the early detection of failure in gears by signal processing of the time domain average*, MSSP 1(2): 173-183 | TSA 早期故障检测经典方法 | 2.2 |
| **McFadden (1986)** | *Detecting fatigue cracks in gears by amplitude and phase demodulation of the meshing vibration*, J. Vib. Acoust. 108(2): 165-170 | 齿轮啮合振动幅值/相位解调 | 2.2, 2.5 |
| **Wang & McFadden (1995)** | *Decomposition of Gear Motion Signals and Its Application to Gearbox Diagnostics*, J. Vib. Acoust. 117(3A): 363-369 | 齿轮运动信号分解 | 2.2 |
| **Randall (1982)** | *A new method of modeling gear faults*, JSV 83(3): 363-374 | 齿轮故障建模 | 2.1 |
| **Braun (1975)** | *The extraction of periodic waveforms by time domain averaging*, Acustica 23(2): 69-77 | 时域同步平均理论基础 | 2.2 |
| **Antoni & Randall (2002)** | *Differential diagnosis of gear and bearing faults*, ASME J. Vib. Acoust. 124: 165-171 | 齿轮与轴承故障鉴别诊断 | 3.4 |
| **Zakrajsek et al. (1993)** | *An analysis of gear fault detection methods as applied to pitting fatigue failure data*, Proc. MFPT | 多种齿轮故障检测方法对比 | 2.3 |
| **Bonnardot et al. (2005)** | *Use of the acceleration signal of a gearbox in order to perform angular resampling...*, MSSP 19: 766-785 | 角域重采样技术 | 2.2 |
| **汪超等 (2015)** | *基于边频带分析的齿轮故障诊断研究*, 十堰职业技术学院学报 | 边频带与故障模式对应关系 | 2.5 |

### 综合信号处理与高级方法

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Antoni (2009)** | *Cyclostationarity by examples*, MSSP 23: 987-1036 | 循环平稳性教学性综述 | 1.5 |
| **Endo & Randall (2007)** | *Enhancement of autoregressive model-based gear tooth fault detection technique by the use of MED filter*, MSSP 21(2): 906-919 | MED 在齿轮 AR 模型中的应用 | 1.6 |
| **Lei et al. (2013)** | *An improved kurtogram method for fault diagnosis... using WPT*, MSSP 35(1-2): 176-199 | 小波包改进 Kurtogram | 1.3 |
| **Smith et al. (2019)** | *Optimal demodulation-band selection for envelope-based diagnostics: a comparative study...*, MSSP 134: 106303 | 最优解调频带选择对比 | 1.2 |
| **Liu & Wang (2025)** | *CUSUM for autocorrelated data with measurement error* | 测量误差下的 CUSUM 改进 | 4.4.1 |
| **Yuan et al. (2025)** | *Multisensor fault diagnosis via Markov chain and Evidence theory*, EAAI | 高冲突证据下的 D-S 融合 | 4.4.3 |
| **Hanna et al. (GE)** | *Sideband Energy Ratio*, ADAPT.wind | SER 算法与工程应用 | 2.3.7 |
| **NASA CR-2009-00039501** | *Gear Fault Detection Effectiveness* | NA4 开发背景与公式 | 2.3.3 |

---

## 附录：与本项目现有代码的对应关系

| 算法/特征 | 当前实现位置 | 实现状态 | 备注 |
|----------|------------|---------|------|
| 轴承特征频率计算 | `analyzer.py::_compute_bearing_fault_freqs` | ✅ 已实现 | 含 BPFO/BPFI/BSF/FTF |
| 包络谱分析 | `analyzer.py::compute_envelope_spectrum` | ✅ 已实现 | 简化版，未做带通滤波 |
| 阶次谱分析 | `analyzer.py::_compute_order_spectrum_simple` | ✅ 已实现 | 简化阶次跟踪 |
| 频谱特征提取 | `analyzer.py::_extract_spectrum_features` | ✅ 已实现 | 含啮合频率、边带能量 |
| 包络特征提取 | `analyzer.py::_extract_envelope_features` | ✅ 已实现 | 含 BPFO/BPFI/BSF 匹配 |
| 阶次特征提取 | `analyzer.py::_extract_order_features` | ✅ 已实现 | 含齿轮/轴承阶次 |
| 转频估计 | `analyzer.py::_estimate_rot_freq_spectrum` | ✅ 已实现 | 频谱峰值法 + 谐波验证 |
| 时域统计特征 | `analyzer.py::compute_channel_features` | ✅ 已实现 | Peak/RMS/Kurtosis/Crest 等 |
| IMF 能量 | `analyzer.py::compute_imf_energy` | ✅ 已实现 | 用频带能量近似 |
| 规则诊断融合 | `analyzer.py::_rule_based_analyze` | ✅ 已实现 | 多特征加权融合 |
| 神经网络预测 | `nn_predictor.py::predict` | 🔄 预留接口 | 未加载真实模型 |
| 信号生成器 | `signal_generator.py` | ✅ 已实现 | 模拟正常/齿轮磨损/轴承故障/轴不对中 |
| TSA（时域同步平均） | — | ❌ 未实现 | 需编码器/转速脉冲支持 |
| CPW（倒频谱预白化） | — | ❌ 未实现 | 待实现 |
| Fast Kurtogram | — | ❌ 未实现 | 待实现 |
| FM0/FM4/NA4/NB4 | — | ❌ 未实现 | 待实现 |
| SER（边频带能量比） | `analyzer.py` 部分实现 | ⚠️ 部分实现 | 有边带能量计算，未形成 SER 指标 |
| 小波阈值去噪 | — | ❌ 未实现 | 待实现 |
| VMD 分解 | — | ❌ 未实现 | 待实现 |
| CUSUM/EWMA 控制图 | — | ❌ 未实现 | 待实现 |
| D-S 证据融合 | — | ❌ 未实现 | 待实现 |

---

> **维护说明**：本文档为算法理论参考，后续代码实现时应保持理论与实现的一致性。
> 每新增一个算法模块，请在"附录"中更新对应关系。
