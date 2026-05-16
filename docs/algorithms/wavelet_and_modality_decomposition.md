
## 九、基于小波变换的轴承故障诊断

### 9.1 多分辨率分析与共振频带定位

轴承局部缺陷产生的周期性冲击会激发结构的高频共振。这些共振频率通常分布在 $2\sim20$ kHz 范围内，而故障特征频率（BPFO/BPFI/BSF/FTF）本身很低（通常为几十到几百 Hz）。因此，轴承诊断的关键是**找到被故障脉冲调制的共振频带**，并对其进行解调。

**小波多分辨率分析的频带划分**：

对信号 $x(t)$ 进行 $L$ 层DWT分解，第 $j$ 层细节系数 $d_j$ 对应的频带为：

$$f \in \left[\frac{f_s}{2^{j+1}}, \frac{f_s}{2^j}\right]$$

| 分解层数 $j$ | 频带范围 (@8192Hz) | 频带范围 (@25600Hz) | 典型内容 |
|------------|-------------------|--------------------|---------|
| $d_1$ | $2048\sim4096$ Hz | $6400\sim12800$ Hz | 极高频噪声/结构共振 |
| $d_2$ | $1024\sim2048$ Hz | $3200\sim6400$ Hz | 高频共振（轴承常用） |
| $d_3$ | $512\sim1024$ Hz | $1600\sim3200$ Hz | 中频共振/齿轮啮合 |
| $d_4$ | $256\sim512$ Hz | $800\sim1600$ Hz | 中低频/啮合谐波 |
| $d_5$ | $128\sim256$ Hz | $400\sim800$ Hz | 低频/转频谐波 |
| $a_5$ | $0\sim128$ Hz | $0\sim400$ Hz | 直流+趋势 |

**共振频带定位方法**：

1. **小波系数能量法**：计算各层细节系数的能量
   $$E_j = \sum_k |d_{j,k}|^2$$
   能量异常高的层往往包含共振频带。

2. **小波系数峭度法**：计算各层峭度
   $$\kappa_j = \frac{1}{N_j}\sum_k \left(\frac{d_{j,k} - \mu_j}{\sigma_j}\right)^4$$
   轴承故障冲击使对应频带的峭度显著增大（高斯噪声基准为3）。

3. **综合指标法**：
   $$S_j = w_1 \cdot \frac{E_j}{\max(E)} + w_2 \cdot \frac{\kappa_j}{\max(\kappa)}$$
   选择 $S_j$ 最大的层作为敏感频带。

**确定敏感层后**，对该层细节系数进行重构（即该频带的窄带信号），再执行Hilbert包络分析提取故障特征频率。

---

### 9.2 小波包节点与轴承故障频带对应

小波包分解的第 $j$ 层产生 $2^j$ 个等宽频带，每个节点宽度为 $\Delta f = f_s / 2^{j+1}$。这种均匀的频带划分更适合精确定位轴承共振频带。

**节点频率定位公式**：

第 $j$ 层第 $k$ 个节点（$k = 0, 1, \ldots, 2^j-1$）覆盖的频率范围为：

$$f \in \left[k \cdot \frac{f_s}{2^{j+1}},\; (k+1) \cdot \frac{f_s}{2^{j+1}}\right]$$

**轴承诊断中的小波包节点选择策略**：

**Step 1**：计算所有节点的能量和峭度
$$E_{j,k} = \sum_n |w_{j,k}(n)|^2, \quad \kappa_{j,k} = \text{Kurtosis}(w_{j,k})$$

**Step 2**：构建综合敏感度指标
$$\text{Sen}_{j,k} = \alpha \cdot \frac{E_{j,k}}{\max(E)} + \beta \cdot \frac{\kappa_{j,k}}{\max(\kappa)}$$

**Step 3**：选择 $\text{Sen}_{j,k}$ 最大的 $M$ 个节点（通常 $M=1\sim3$）

**Step 4**：对选中节点重构窄带信号，执行Hilbert包络分析

**Step 5**：在包络谱中搜索 BPFO/BPFI/BSF/FTF 及其谐波

**工程实例**（HUSTbear数据集，$f_s=8192$ Hz，3层小波包分解）：

| 节点 | 频带范围 (Hz) | 内容 | 外圈故障样本表现 |
|------|--------------|------|----------------|
| $(3,0)$ | $0\sim512$ | 低频/转频 | 能量正常 |
| $(3,1)$ | $512\sim1024$ | 中低频 | 能量略增 |
| $(3,2)$ | $1024\sim1536$ | 中频共振 | **能量显著集中，峭度>10** |
| $(3,3)$ | $1536\sim2048$ | 中高频 | **峭度峰值** |
| $(3,4\sim7)$ | $2048\sim4096$ | 高频 | 噪声主导 |

健康轴承样本中，各节点能量分布相对均匀（归一化熵 $0.5\sim0.7$）；外圈故障样本中，$(3,2)$ 和 $(3,3)$ 节点能量显著集中，归一化熵下降至 $0.2\sim0.4$。

---

### 9.3 CWT时频图识别冲击周期性

**Morlet小波时频图（Scalogram）** 可直接揭示轴承冲击的时间-频率分布规律：

$$\text{Scalogram}(a,b) = |W(a,b)|^2$$

**轴承故障在Scalogram中的表现**：

- **外圈故障**：在特定尺度（对应共振频带）上出现等时间间隔的竖直线状能量集中，间隔时间为 $T = 1/BPFO$
- **内圈故障**：同样出现周期性冲击，但由于缺陷进出载荷区，冲击幅值存在以转频 $f_r$ 为周期的调制现象。在Scalogram中表现为冲击强度呈周期性明暗变化
- **滚动体故障**：冲击周期为 $1/(2\times BSF)$，且可能存在保持架频率 $FTF$ 的调制

**冲击周期性定量识别**：

对Scalogram中敏感尺度的时域切片（固定 $a=a^*$，沿 $b$ 方向），计算其自相关函数：

$$R(\tau) = \int \text{Scalogram}(a^*, b) \cdot \text{Scalogram}(a^*, b+\tau) \, db$$

$R(\tau)$ 的峰值位置对应冲击周期。若峰值周期与理论 $1/BPFO$、$1/BPFI$ 或 $1/(2BSF)$ 匹配，则判定对应故障。

**工程简化方法**：对敏感尺度的时域切片直接做FFT，在频域中搜索故障特征频率。该方法等效于对该频带进行窄带滤波+包络分析。

---

### 9.4 小波去噪后包络分析完整流程

```
原始振动信号 x(t)
    │
    ↓
小波阈值去噪（db8, 5~7层, soft阈值）
    │
    ↓
小波包分解（3~4层）或DWT细节系数分析
    │
    ├─→ 计算各节点/各层能量 E_j,k 和峭度 κ_j,k
    │
    ↓
选择敏感节点/层（综合指标最大）
    │
    ↓
重构敏感频带窄带信号 y(t)
    │
    ↓
Hilbert变换 → 包络 e(t) = |y(t) + jH[y(t)]|
    │
    ↓
低通滤波（截止频率 > 3×最高故障频率）
    │
    ↓
FFT包络谱 E(f)
    │
    ↓
峰值搜索与故障频率匹配
    ├─→ 计算理论 BPFO/BPFI/BSF/FTF
    ├─→ 设定 ±2~3% 容差带
    ├─→ 搜索容差带内最大峰值
    └─→ 谐波族验证（至少3~5阶）
    │
    ↓
故障类型判定与严重度评估
```

**代码实现映射**：

```python
# 基于小波包的轴承故障诊断伪代码
def wavelet_bearing_diagnosis(signal, fs, bearing_params, rot_freq):
    import pywt
    from scipy.signal import hilbert
    from scipy.fft import rfft, rfftfreq
    
    # Step 1: 小波包分解
    level = 3
    wp = pywt.WaveletPacket(data=signal, wavelet='db8', mode='symmetric')
    nodes = wp.get_level(level, order='natural')
    
    # Step 2: 计算各节点敏感指标
    scores = []
    for node in nodes:
        coeff = np.array(node.data)
        energy = np.sum(coeff**2)
        kurt = np.mean(((coeff - np.mean(coeff)) / np.std(coeff))**4)
        scores.append(0.5 * energy / max(energies) + 0.5 * kurt / max(kurts))
    
    # Step 3: 选择最敏感节点并重构
    best_idx = np.argmax(scores)
    best_node = nodes[best_idx]
    y = best_node.reconstruct(update=False)[:len(signal)]
    
    # Step 4: Hilbert包络分析
    envelope = np.abs(hilbert(y))
    envelope = envelope - np.mean(envelope)
    
    # Step 5: FFT包络谱
    yf = np.abs(rfft(envelope))
    xf = rfftfreq(len(envelope), 1/fs)
    
    # Step 6: 故障频率匹配
    freqs = _compute_bearing_fault_freqs(rot_freq, bearing_params)
    results = {}
    for fault_type, f_fault in freqs.items():
        detected_harmonics = 0
        for n in range(1, 6):
            f_target = n * f_fault
            if f_target > xf[-1]:
                break
            idx = np.argmin(np.abs(xf - f_target))
            peak = yf[idx]
            # 容差带 ±3%
            band = (xf > f_target * 0.97) & (xf < f_target * 1.03)
            if peak > 3 * np.median(yf[band]):
                detected_harmonics += 1
        results[fault_type] = detected_harmonics
    
    return results
```

---

### 9.5 故障判别准则与阈值

**峰值显著性判据**：

$$SNR_{peak} = \frac{P_{detect}}{\text{Median}[E(f)]}$$

工程阈值：$SNR_{peak} > 3\sim5$ 视为显著。

**谐波族验证要求**：

| 故障类型 | 包络谱特征 | 最低可检测谐波数 |
|---------|----------|----------------|
| **外圈故障** | $n \times BPFO$ 等间距谐波族 | 前3阶 |
| **内圈故障** | $n \times BPFI$ 谐波 + 两侧 $k \times f_r$ 边带 | 前2阶谐波+边带 |
| **滚动体故障** | $2n \times BSF$ 谐波 + $m \times FTF$ 边带 | 前2阶 |
| **保持架故障** | $n \times FTF$ 亚同步频率 | 前2阶 |

**多尺度验证**：若多个小波包节点同时指向同一故障类型，诊断置信度显著提升。

---

## 十、基于小波变换的齿轮故障诊断

### 10.1 啮合频率在小波域的分布

齿轮振动以啮合频率 $f_{mesh} = Z \cdot f_r$ 及其谐波为主。在小波域中，啮合频率分量主要分布在特定的分解层或节点中。

**DWT分解层与啮合频率对应**（$f_s = 8192$ Hz）：

| 分解层 | 频带范围 | 40Hz转速啮合频率位置 |
|--------|---------|-------------------|
| $d_3$ | $512\sim1024$ Hz | $f_{mesh}=1120$ Hz（28齿@40Hz）在此层上边界附近 |
| $d_4$ | $256\sim512$ Hz | 一阶啮合谐波 $2f_{mesh}$ 若存在，可能在此层 |
| $d_5$ | $128\sim256$ Hz | 转频 $f_r=40$ Hz 及其谐波在此层 |

**WTgearbox数据集实例**（$f_s=8192$ Hz，太阳轮28齿，$f_{mesh}=175/8 \cdot f_r$）：

| 转速 | $f_{mesh}$ | 对应3层节点 | 对应4层节点 |
|------|-----------|------------|-----------|
| 20 Hz | 437.5 Hz | $(3,0)$: $0\sim512$ | $(4,1)$: $512\sim1024$ 之外，偏 $(4,0)$ 高端 |
| 40 Hz | 875 Hz | $(3,1)$: $512\sim1024$ | $(4,1)$: $512\sim1024$ 与 $(4,2)$: $1024\sim1536$ 边界 |
| 55 Hz | 1203 Hz | $(3,2)$: $1024\sim1536$ | $(4,2)$: $1024\sim1536$ |

**关键点**：随着转速变化，啮合频率在小波域中"跳跃"于不同节点之间。固定节点分析在变速工况下会失效，需配合阶次跟踪或CWT。

---

### 10.2 边频带的小波包节点识别

齿轮故障产生的边频带位于 $f_{mesh} \pm k \cdot f_r$ 处。在小波包域中，这些边频带往往分散在相邻节点中。

**边频带节点定位方法**：

对于第 $j$ 层小波包分解，节点宽度为 $\Delta f = f_s / 2^{j+1}$。边频带 $f_{mesh} \pm k \cdot f_r$ 所在的节点索引为：

$$k_{node} = \left\lfloor \frac{f_{mesh} \pm k \cdot f_r}{\Delta f} \right\rfloor = \left\lfloor \frac{(f_{mesh} \pm k \cdot f_r) \cdot 2^{j+1}}{f_s} \right\rfloor$$

**以WTgearbox 40Hz工况为例**（$f_{mesh}=875$ Hz，$f_r=40$ Hz，3层分解，$\Delta f=512$ Hz）：

| 边频带 | 频率 | 所在节点 |
|--------|------|---------|
| $f_{mesh}$ | 875 Hz | $(3,1)$: $512\sim1024$ |
| $f_{mesh} - f_r$ | 835 Hz | $(3,1)$: $512\sim1024$ |
| $f_{mesh} + f_r$ | 915 Hz | $(3,1)$: $512\sim1024$ |
| $f_{mesh} - 2f_r$ | 795 Hz | $(3,1)$: $512\sim1024$ |
| $f_{mesh} + 6f_r$ | 1115 Hz | $(3,2)$: $1024\sim1536$ |

可见，低阶边频带（前6阶）往往集中在啮合频率所在的同一节点或相邻节点中。4层分解（$\Delta f=256$ Hz）可更精细地分离各边频带。

**故障判定策略**：

1. 定位啮合频率所在节点 $k_{mesh}$
2. 计算该节点及左右相邻节点的能量占比变化
3. 健康齿轮：能量集中在 $k_{mesh}$，相邻节点能量低
4. 故障齿轮：$k_{mesh}$ 节点能量向相邻节点"泄漏"，边频带节点能量升高

---

### 10.3 基于小波包能量重分布的故障判定

**健康齿轮的能量分布特征**：

- 能量高度集中于啮合频率及其谐波所在的少数节点
- 归一化能量熵 $H_{norm} \in [0.30, 0.55]$
- 啮合频带集中度 $> 0.15$（啮合频带节点能量占总能量15%以上）

**故障齿轮的能量分布变化**：

| 故障类型 | 能量分布变化 | 熵值变化 | 典型节点表现 |
|---------|------------|---------|------------|
| **齿形误差/偏心** | 边频能量增加，分布略分散 | 略升 $0.50\sim0.65$ | 啮合节点两侧节点能量升高 |
| **均匀磨损** | 多阶谐波能量同时增加 | 中等上升 $0.55\sim0.70$ | 多个谐波节点能量同时升高 |
| **局部裂纹/断齿** | 冲击使高频能量显著增加 | 显著上升 $>0.70$ | 高频节点能量异常，啮合节点能量剧变 |

**多尺度小波包能量熵 (MSWPEE)**：

为增强对早期微弱故障的敏感性，采用多尺度粗粒化处理：

1. 对原始序列进行粗粒化（尺度因子 $\tau = 1, 2, 3, \ldots$）：
   $$y_j^{(\tau)} = \frac{1}{\tau}\sum_{i=(j-1)\tau+1}^{j\tau} x_i$$

2. 对各粗粒化序列进行 $j$ 层小波包分解，计算能量熵 $H^{(\tau)}$

3. 构建多尺度特征向量：$\mathbf{F}_{MSWPEE} = [H^{(1)}, H^{(2)}, H^{(3)}, \ldots]$

粗粒化处理可抑制高频随机噪声，凸显故障引起的低频调制特征。

---

### 10.4 小波去噪+TSA联合分析流程

齿轮诊断中，小波去噪不仅用于降噪，还可与TSA（时域同步平均）联合使用：

```
原始振动信号 x(t)
    │
    ↓
小波阈值去噪（去除高频随机噪声，保留啮合频率及边频）
    │
    ↓
时域同步平均 TSA（基于估计转频等角度重采样）
    │
    ├─→ 规则啮合分量：x_gear(t) = TSA信号中的啮合频率及其谐波
    │
    └─→ 残余信号：r(t) = x_TSA(t) - x_gear(t)
            │
            ↓
    差分信号：d(t) = x_TSA(t) - R(t)
    （R(t)为规则啮合分量+一阶边带）
            │
            ↓
    故障指标计算：
    ├─→ FM0 = PP / sum(A(f_mesh_i))     [粗故障]
    ├─→ FM4 = N·Σ(d_i - d̄)^4 / [Σ(d_i - d̄)^2]^2   [局部故障]
    ├─→ SER = Σ(A_SB_i) / A(f_mesh)     [边频能量比]
    └─→ 小波包能量熵 H_norm              [频带重分布]
            │
            ↓
    多指标融合决策
```

**小波去噪在此流程中的作用**：

1. **预处理阶段**：在去噪后的信号上执行TSA，可减少随机噪声对同步平均的干扰，提高TSA信噪比
2. **残余信号分析**：对TSA后的残余信号再次进行小波包分解，分析其中是否含有轴承故障特征（见第9章）
3. **差分信号增强**：小波去噪可抑制差分信号中的虚假尖峰，使FM4/FM0指标更稳定

**代码实现映射**：

```python
# 参考实现位置：cloud/app/services/diagnosis/gear/metrics.py
# 小波去噪 → TSA → 齿轮指标 的联合流程

def wavelet_gear_analysis(signal, fs, rot_freq, gear_teeth):
    from scipy.signal import hilbert
    
    # Step 1: 小波去噪
    denoised = wavelet_denoise(signal, wavelet="db8", threshold_mode="soft")
    
    # Step 2: TSA（基于估计转频等角度重采样）
    tsa_signal, residual, differential = compute_tsa_residual(
        denoised, fs, rot_freq
    )
    
    # Step 3: 计算啮合频率及频谱
    mesh_freq = gear_teeth * rot_freq
    xf, yf = compute_fft(tsa_signal, fs)
    
    # Step 4: 齿轮指标
    fm0 = compute_fm0(tsa_signal, mesh_freq, xf, yf)
    fm4 = compute_fm4(differential)
    ser = compute_ser(xf, yf, mesh_freq, rot_freq)
    
    # Step 5: 小波包能量熵
    wp_result = compute_wavelet_packet_energy_entropy(
        denoised, fs, level=3, gear_mesh_freq=mesh_freq
    )
    
    return {
        "fm0": fm0,
        "fm4": fm4,
        "ser": ser,
        "wp_entropy": wp_result["normalized_entropy"],
        "mesh_concentration": wp_result["mesh_band_concentration"]
    }
```

---

## 十一、基于EMD/VMD的轴承故障诊断

### 11.1 轴承冲击在IMF域的分布规律

轴承故障产生的周期性冲击在EMD/VMD分解后，通常具有以下分布特征：

**EMD分解的IMF分布**：

| IMF层 | 典型频率范围 | 轴承故障内容 |
|------|------------|------------|
| IMF1 | 最高频 | 高频结构共振+噪声。健康轴承以噪声为主；故障轴承含共振衰减振荡 |
| IMF2~IMF3 | 中高频 | **轴承共振频带主要分布层**。故障冲击的调制载波集中于此 |
| IMF4~IMF5 | 中低频 | 可能包含轴承故障特征频率的低次谐波+转频成分 |
| IMF6+ | 低频 | 转频及其谐波、齿轮啮合频率、趋势项 |
| 残差 | 极低频 | 直流偏移、慢变趋势 |

**VMD分解的模态分布**：

与EMD不同，VMD的模态中心频率由算法自适应确定，且频带划分更清晰：

| 模态 | 典型中心频率 | 内容 |
|------|------------|------|
| $u_1$ | $0.3\sim0.5 \cdot f_s$ | 高频噪声+结构共振 |
| $u_2$ | $0.1\sim0.3 \cdot f_s$ | **轴承主要共振频带** |
| $u_3$ | $0.03\sim0.1 \cdot f_s$ | 啮合频率/中频成分 |
| $u_4$ | $0.01\sim0.03 \cdot f_s$ | 转频及其谐波 |
| $u_5+$ | $< 0.01 \cdot f_s$ | 低频趋势 |

**物理规律总结**：

- 轴承局部缺陷冲击的**载波频率**（结构共振）通常落在EMD的IMF2~IMF3或VMD的$u_2$模态中
- **调制包络**（故障特征频率）频率很低，在所有IMF/模态中以振幅调制的形式存在
- 对含载波的IMF/模态做Hilbert包络，即可提取故障特征频率

---

### 11.2 敏感IMF选择策略

轴承诊断中，敏感IMF选择是关键步骤。常用以下指标：

**1. 互相关系数**：

$$\rho_i = \frac{\sum_t c_i(t) \cdot x(t)}{\sqrt{\sum_t c_i^2(t) \cdot \sum_t x^2(t)}}$$

- 反映IMF与原始信号的整体相关性
- 但高相关性不一定代表含故障信息（可能是低频趋势或噪声）

**2. 峭度 (Kurtosis)**：

$$K_i = \frac{\frac{1}{N}\sum_{t=1}^{N}(c_i(t) - \bar{c}_i)^4}{\left(\frac{1}{N}\sum_{t=1}^{N}(c_i(t) - \bar{c}_i)^2\right)^2}$$

- 对冲击极度敏感。健康轴承IMF的峭度≈3（高斯分布）
- 故障轴承含冲击的IMF峭度显著增大（$>5\sim20$）
- **注意**：IMF1（高频噪声）的峭度也可能很高，需结合相关性排除

**3. 包络熵 (Envelope Entropy)**：

对IMF $c_i(t)$ 做Hilbert包络 $e_i(t) = |c_i(t) + jH[c_i(t)]|$，计算：

$$H_{env,i} = -\sum_{t} p_t \ln p_t, \quad p_t = \frac{e_i(t)}{\sum_\tau e_i(\tau)}$$

- 包络熵越小，说明包络信号的周期性越强，故障信息越丰富
- 健康轴承各IMF包络熵较大（无明显周期性）
- 故障轴承敏感IMF的包络熵显著减小

**4. 综合选择指标**：

$$\text{Score}_i = w_1 \cdot \rho_i + w_2 \cdot \frac{K_i}{\max_j K_j} + w_3 \cdot \left(1 - \frac{H_{env,i}}{\max_j H_{env,j}}\right)$$

推荐权重：$w_1 = 0.3, w_2 = 0.5, w_3 = 0.2$（峭度为主导指标）。

**5. 频域验证法**：

计算IMF的功率谱，检查其中心频率是否落在轴承已知共振频带（如 $2\sim8$ kHz）内：

$$f_{center,i} = \frac{\int f \cdot |\hat{c}_i(f)|^2 df}{\int |\hat{c}_i(f)|^2 df}$$

若 $f_{center,i} \in [2000, 8000]$ Hz，则该IMF极可能为轴承共振模态。

---

### 11.3 基于IMF的包络谱分析

**完整分析流程**：

```
原始信号 x(t)
    │
    ↓
EMD/VMD分解 → {c_1, c_2, ..., c_K}
    │
    ↓
敏感IMF选择（综合指标 Score_i 最大）
    │
    ↓
取敏感IMF c_s(t)
    │
    ↓
Hilbert包络：e_s(t) = |c_s(t) + jH[c_s(t)]|
    │
    ↓
去除直流分量：e_s(t) = e_s(t) - mean(e_s(t))
    │
    ↓
FFT包络谱：E_s(f) = |FFT[e_s(t)]|
    │
    ↓
故障频率匹配：
    ├─→ BPFO = (N/2)·f_r·(1 - d/D·cosα)
    ├─→ BPFI = (N/2)·f_r·(1 + d/D·cosα)
    ├─→ BSF = (D/2d)·f_r·[1 - (d/D·cosα)^2]
    └─→ FTF = (f_r/2)·(1 - d/D·cosα)
    │
    ↓
峰值显著性检验：SNR_peak = P_detect / Median[E_s(f)] > 3~5
    │
    ↓
谐波族验证（至少3阶）→ 故障类型判定
```

**多IMF联合分析**：

不要仅依赖单一IMF。对前 $M$ 个敏感IMF分别做包络分析，然后：

1. **投票法**：若多个IMF同时检测到同一故障频率，置信度提升
2. **谱平均法**：对各IMF的包络谱加权平均，抑制随机噪声
   $$E_{avg}(f) = \frac{1}{M}\sum_{m=1}^{M} w_m \cdot E_m(f)$$
   其中权重 $w_m \propto \text{Score}_m$

**工程实例**（HUSTbear外圈故障，$f_s=8192$ Hz）：

| IMF | 中心频率(Hz) | 峭度 | 包络熵 | 包络谱峰值频率 | 判定 |
|-----|------------|------|--------|--------------|------|
| IMF1 | ~3500 | 12.5 | 2.1 | 噪声为主，无明显周期 | 噪声主导 |
| **IMF2** | **~1800** | **28.3** | **0.85** | **95.2 Hz (BPFO)** | **敏感IMF** |
| IMF3 | ~800 | 8.7 | 1.5 | 95.2 Hz (弱) | 次敏感 |
| IMF4 | ~300 | 4.2 | 2.8 | 无明显峰值 | 含转频 |
| IMF5 | ~80 | 3.1 | 3.5 | 无明显峰值 | 趋势 |

BPFO理论值：约 $3.57 \times 40$ Hz $= 142.8$ Hz（恒速工况）。变速工况下需用阶次跟踪转换到阶次域。

---

### 11.4 基于IMF能量熵的故障严重度评估

**能量集中度指标**：

$$EC = \frac{\max_i E_i}{\sum_j E_j}$$

- 健康轴承：能量分散在多个IMF，$EC \approx 0.15\sim0.25$
- 故障轴承：能量向敏感IMF集中，$EC > 0.30\sim0.50$

**IMF能量熵与故障严重度的关系**：

$$H_{IMF} = -\sum_{i=1}^{n} p_i \log_2 p_i$$

| 状态 | $H_{IMF}$ 范围 | 物理意义 |
|------|--------------|---------|
| 健康 | $2.5\sim3.5$ | 能量分布相对均匀 |
| 早期故障 | $1.8\sim2.5$ | 能量开始向故障频带集中 |
| 明显故障 | $1.2\sim1.8$ | 能量高度集中于1~2个IMF |
| 严重故障 | $<1.2$ | 能量几乎集中于单一IMF |

**趋势追踪**：连续监测 $H_{IMF}$ 的变化趋势，比单次测量更可靠。若 $H_{IMF}$ 呈持续下降趋势，即使绝对值仍在"健康"范围内，也预示故障正在发展。

---

## 十二、基于EMD/VMD的齿轮故障诊断

### 12.1 齿轮啮合分量在IMF域的分布

齿轮振动信号以啮合频率 $f_{mesh}$ 及其谐波为主。在EMD/VMD分解后，这些确定性分量有明确的分布规律：

**EMD分解中的齿轮分量**：

| IMF层 | 典型内容 | 齿轮故障表现 |
|------|---------|------------|
| IMF1 | 高频噪声/冲击 | 断齿/裂纹时含啮合冲击 |
| IMF2~IMF3 | **啮合频率基波及低阶谐波** | 边频带调制主要在此层 |
| IMF4 | 转频及其谐波 | 轴不对中、偏心时增强 |
| IMF5+ | 低频趋势/直流 | 通常无齿轮信息 |
| 残差 | 极慢趋势 | 温度漂移等 |

**VMD分解中的齿轮分量**：

VMD的频域自适应特性使其对齿轮啮合分量的分离更清晰：

| 模态 | 中心频率 | 内容 |
|------|---------|------|
| $u_1$ | $> 2f_{mesh}$ | 高频噪声、啮合高阶谐波 |
| $u_2$ | $\approx f_{mesh}$ | **啮合频率基波**（齿轮诊断核心） |
| $u_3$ | $\approx f_{mesh}/2$ 或 $2f_r$ | 啮合二阶谐波或转频谐波 |
| $u_4$ | $\approx f_r$ | 转频及其低阶谐波 |
| $u_5+$ | $< f_r$ | 低频趋势 |

**关键观察**：啮合频率 $f_{mesh}$ 在VMD中通常表现为一个独立的模态 $u_k$，其中心频率 $\omega_k \approx f_{mesh}$。这比EMD更清晰，因为EMD的模态混叠可能导致啮合频率分散到多个IMF中。

---

### 12.2 基于VMD的啮合分量提取与边频分析

VMD在齿轮诊断中的核心优势是能**精确分离啮合频率分量**，避免传统FFT中边频带被主啮合峰掩盖的问题。

**算法流程**：

**Step 1：VMD分解**

选择模态数 $K$ 使得啮合频率谐波能被充分分离：
$$K = \min\left(K_{max}, \left\lfloor \frac{f_s}{2 f_{mesh}} \right\rfloor\right)$$

对于WTgearbox（$f_s=8192$ Hz，$f_{mesh}=437.5\sim1203$ Hz）：
- 20Hz转速：$K \approx \lfloor 8192 / 875 \rfloor = 9$
- 55Hz转速：$K \approx \lfloor 8192 / 2406 \rfloor = 3$

**2GB服务器限制**：$K_{max} = 5$，因此高转速下VMD只能分离前2~3阶啮合谐波。

**Step 2：敏感模态选择**

选择中心频率最接近 $f_{mesh}$ 的模态：
$$k^* = \arg\min_k |\omega_k - f_{mesh}|$$

**Step 3：幅值解调**

对敏感模态 $u_{k^*}(t)$ 执行Hilbert包络：
$$a(t) = |u_{k^*}(t) + jH[u_{k^*}(t)]|$$

包络 $a(t)$ 包含故障齿轮所在轴的转频调制信息。

**Step 4：包络谱分析**

对 $a(t)$ 做FFT，在包络谱中搜索：
- 边频带：$f = n \cdot f_r$（$n=1,2,3,\dots$）
- 边频带幅值不对称性指示故障类型（见 `ALGORITHMS.md` 2.5.2）

**Step 5：边频显著性检验**

$$\rho_n = \frac{A(n \cdot f_r)}{A_{DC}}$$

其中 $A_{DC}$ 为包络谱零频幅值（包络均值）。若 $\rho_n > 0.05\sim0.1$，视为显著。

---

### 12.3 EMD残余信号与差分信号分析

EMD分解为齿轮诊断提供了另一种分析路径——基于残余信号和差分信号的经典指标。

**残余信号 (Residual Signal)**：

$$r(t) = x(t) - \sum_{i \in \mathcal{G}} c_i(t)$$

其中 $\mathcal{G}$ 为包含齿轮啮合主要IMF的索引集（通常为IMF2~IMF4）。

残余信号 $r(t)$ 包含：
- 轴承故障冲击
- 非同步齿轮成分
- 随机噪声

对 $r(t)$ 进行包络分析，可检测轴承故障（见第11章）。

**差分信号 (Differential Signal)**：

$$d(t) = x_{TSA}(t) - R(t)$$

其中 $x_{TSA}(t)$ 为TSA后的齿轮信号，$R(t)$ 为规则啮合分量（啮合频率及其谐波 + 一阶边带）。

差分信号 $d(t)$ 的特性：
- 健康齿轮：接近随机噪声，峭度 $\approx 3$
- 局部故障（点蚀、裂纹）：含孤立大峰值，峭度 $> 5\sim10$
- 大面积损伤：峰值增多但分布趋于均匀，峭度可能回落

**基于EMD的差分信号改进**：

传统差分信号通过频域滤波构造，可能引入相位失真。基于EMD的改进方法：

1. 对TSA信号进行EMD分解
2. 识别并剔除包含啮合频率及其谐波的IMF（通过频域验证）
3. 剩余IMF之和即为EMD-based差分信号

**优势**：EMD-based差分信号无滤波器相位失真，更适合计算FM4/M6A/M8A等高阶矩指标。

---

### 12.4 行星齿轮箱VMD幅频联合解调

行星齿轮箱的振动信号具有复杂的多重AM-FM调制结构，传统FFT边频带分析失效。VMD幅频联合解调是本项目的核心高级方法（参见 `ALGORITHMS.md` 2.7.3）。

**行星齿轮箱特征阶次**（WTgearbox参数：sun=28, ring=100, planet=36, $N_p=4$）：

| 特征阶次 | 公式 | 数值 |
|---------|------|------|
| mesh_order | $Z_{ring} \cdot Z_{sun} / (Z_{sun} + Z_{ring})$ | 21.875 |
| carrier_order | $Z_{sun} / (Z_{sun} + Z_{ring})$ | 0.21875 |
| sun_fault_order | $Z_{ring} / (Z_{sun} + Z_{ring}) \cdot N_p$ | 3.125 |
| planet_fault_order | $Z_{ring} / (Z_{sun} + Z_{ring})$ | 0.78125 |

**VMD幅频联合解调流程**：

**Step 1：VMD分解**

$$K = \min\left(5, \left\lfloor \frac{f_s}{2 f_{mesh}} \right\rfloor\right)$$

对于WTgearbox（$f_{mesh}=175/8 \cdot f_r$），$f_s=8192$ Hz：
- $f_r = 20$ Hz → $f_{mesh} = 437.5$ Hz → $K = 5$
- $f_r = 55$ Hz → $f_{mesh} = 1203$ Hz → $K = 3$

**Step 2：敏感IMF选择**

选择中心频率最接近 $f_{mesh}$ 的IMF：
$$k^* = \arg\min_k |\omega_k - f_{mesh}|$$

若多个IMF满足，优先选择中心频率更高的IMF（齿轮故障冲击呈高频特征）。

**Step 3：经验AM-FM分解**

对敏感IMF $u_{k^*}(t)$ 执行Hilbert变换：
$$a(t) = |u_{k^*}(t) + jH[u_{k^*}(t)]|$$
$$c(t) = \frac{u_{k^*}(t)}{a(t)}$$

其中 $a(t)$ 为幅值包络，$c(t)$ 为载波信号。

**Step 4：幅值解调谱**

对 $a(t)$ 做FFT：
$$A(f) = |\text{FFT}[a(t)]|$$

在 $A(f)$ 中搜索 sun_fault_order、planet_fault_order、carrier_order 及其谐波。

**Step 5：频率解调谱**

计算载波 $c(t)$ 的瞬时频率：
$$f_{inst}(t) = \frac{1}{2\pi} \frac{d}{dt}\arctan\frac{H[c(t)]}{c(t)}$$

对 $f_{inst}(t)$ 做FFT：
$$F(f) = |\text{FFT}[f_{inst}(t) - \bar{f}_{inst}]|$$

在 $F(f)$ 中搜索故障特征阶次。

**Step 6：故障判定**

| 故障位置 | 幅值解调谱特征 | 频率解调谱特征 |
|---------|--------------|--------------|
| **太阳轮故障** | sun_fault_order (3.125) 及其谐波突出，伴 1/3 分数谐波 | 纯净的 sun_fault_order 峰值 |
| **行星轮故障** | planet_fault_order (0.78125) 及其谐波 | planet_fault_order 峰值 |
| **齿圈故障** | carrier_order (0.21875) 相关调制 | carrier_order 相关 |

**峰值显著性阈值**：

$$SNR = \frac{A(f_{fault})}{\text{Median}[A(f)]}$$

- 警告阈值：$SNR > 3$
- 危险阈值：$SNR > 5$

---

## 十三、敏感分量与敏感频带选择策略

### 13.1 综合评价指标设计

无论是小波包节点还是IMF，敏感分量选择都需要综合考虑多个指标：

**通用综合评分函数**：

$$\text{Score}(s) = \sum_{m=1}^{M} w_m \cdot \frac{I_m(s) - \min_i I_m(i)}{\max_i I_m(i) - \min_i I_m(i)}$$

其中 $s$ 为待评估的分量（节点或IMF），$I_m$ 为第 $m$ 个指标，$w_m$ 为权重。

**常用指标集**：

| 指标 | 符号 | 轴承诊断权重 | 齿轮诊断权重 | 说明 |
|------|------|------------|------------|------|
| 互相关系数 | $\rho$ | 0.30 | 0.20 | 与原始信号的整体相关性 |
| 峭度 | $K$ | 0.45 | 0.30 | 对冲击敏感度 |
| 包络熵 | $H_{env}$ | 0.15 | 0.10 | 周期性度量（越小越好） |
| 能量占比 | $E/ E_{total}$ | 0.05 | 0.25 | 能量集中度 |
| 中心频率匹配度 | $\Delta f_{center}$ | 0.05 | 0.15 | 与目标频带的频率距离 |

**轴承诊断权重设计理由**：峭度为主导（0.45），因为轴承故障以冲击为特征；相关性为辅（0.30），排除纯噪声分量。

**齿轮诊断权重设计理由**：能量占比和中心频率匹配度权重较高，因为齿轮故障以啮合频率能量变化和边频带产生为特征。

---

### 13.2 轴承诊断的IMF/频带筛选规则

**规则1 — 排除高频噪声层**：

EMD的IMF1或VMD的最高频模态通常以噪声为主，即使峭度很高，也应谨慎使用。判定标准：
- 中心频率 $> 0.4 f_s$：极可能为噪声主导
- 与原始信号相关性 $\rho < 0.1$：几乎无信息

**规则2 — 排除低频趋势层**：

EMD的最后1~2个IMF或VMD的最低频模态为趋势项，无故障信息：
- 中心频率 $< 2 f_r$（低于2倍转频）：趋势/漂移
- 峭度 $< 3.5$：无冲击特征

**规则3 — 共振频带优先**：

轴承结构共振频带通常在 $2\sim8$ kHz（取决于轴承尺寸和安装结构）。优先选择中心频率落在此范围的IMF/频带。

**规则4 — 多分量一致性验证**：

若多个IMF/频带同时指向同一故障类型，诊断置信度提升。定义一致性指数：

$$CI = \frac{\#\{i: \text{IMF}_i \text{ 检测到故障 } F\}}{\#\{\text{总IMF数}\}}$$

$CI > 0.3$（即超过30%的IMF检测到同一故障）视为高置信度。

---

### 13.3 齿轮诊断的IMF/频带筛选规则

**规则1 — 啮合频率匹配优先**：

齿轮诊断的核心是啮合频率分量。优先选择中心频率最接近 $f_{mesh}$ 的IMF/频带：

$$\Delta f = |f_{center} - f_{mesh}| / f_{mesh}$$

$\Delta f < 10\%$ 视为匹配。

**规则2 — 边频带验证**：

对候选IMF/频带执行包络分析，检查是否存在以转频 $f_r$ 为间隔的边频带。边频带的存在是齿轮故障的关键证据。

**规则3 — 健康啮合参考对比**：

若存在同设备健康历史数据，对比当前IMF能量分布与健康状态的差异：

$$\Delta E_i = \frac{E_i^{current} - E_i^{healthy}}{E_i^{healthy}}$$

$\Delta E_i > 2$（即当前能量为健康的3倍以上）视为显著变化。

**规则4 — 行星齿轮箱特殊处理**：

行星齿轮箱健康状态下也有显著边频带（多行星轮同时啮合导致）。不能简单用"边频存在=故障"判定，需关注：
- 边频带幅值的变化趋势
- 残余边频带（residual sidebands）与标准边频带的比值
- VMD解调谱中故障特征阶次的SNR

---

### 13.4 自适应参数调整策略

**信噪比自适应**：

根据信号估计SNR自动调整分析参数：

| 估计SNR | 降噪策略 | 分解参数 | 阈值策略 |
|---------|---------|---------|---------|
| $> 10$ dB | 轻度小波去噪 | 标准参数 | 保守阈值 |
| $0\sim10$ dB | 标准小波去噪 | 标准参数 | 标准阈值 |
| $-5\sim0$ dB | 小波+VMD级联 | K增加1~2 | 积极阈值 |
| $< -5$ dB | 联合降噪+多次平均 | CEEMDAN替代EMD | 最积极阈值 |

**转速自适应**：

- 恒速工况：固定频带分析，小波包节点/IMF直接对应固定频率
- 变速工况：必须先做阶次跟踪（Order Tracking），将时域信号重采样到角域，再进行小波/EMD/VMD分析。此时故障特征为**阶次**而非频率

**负载自适应**：

重载下齿轮啮合能量增强，可能掩盖轴承故障特征。此时：
1. 先用CPW（倒频谱预白化）均衡啮合能量
2. 再用小波/VMD分析残余信号
3. 提高轴承故障检测的峭度阈值（重载下正常冲击也增多）

---

## 十四、多方法融合与工程决策

### 14.1 级联降噪策略

单一降噪方法各有适用场景，级联使用可互补增强：

**小波+VMD级联**（`preprocessing.py::cascade_wavelet_vmd`）：

```
原始信号 x(t)
    │
    ↓
小波阈值去噪（去除高频白噪声，保留中频特征）
    │
    ↓
VMD分解（将去噪后信号分解为K个窄带模态）
    │
    ↓
IMF筛选（相关>0.3 或 峭度>3.0）
    │
    ↓
重构信号 x_denoised(t)
```

**适用场景**：强高斯白噪声背景下的轴承弱故障检测。小波去除白噪声，VMD分离非平稳故障模态。

**小波+LMS级联**（`preprocessing.py::cascade_wavelet_lms`）：

```
原始信号 x(t)
    │
    ↓
小波阈值去噪（粗降噪）
    │
    ↓
LMS自适应滤波（以延迟信号为参考，进一步抑制相关噪声）
    │
    ↓
重构信号 x_denoised(t)
```

**适用场景**：存在周期性干扰（如电机电磁噪声、泵浦脉动）的场景。

**CEEMDAN+小波包级联**：

```
原始信号 x(t)
    │
    ↓
CEEMDAN分解（抑制模态混叠）
    │
    ↓
IMF筛选（保留信息IMF）
    │
    ↓
小波包分解（对选中IMF进一步频带细分）
    │
    ↓
能量熵+峭度分析
```

**适用场景**：复合故障（齿轮+轴承同时故障）的精细分离。

---

### 14.2 分阶段诊断决策树

**第一阶段 — 时域证据门控**（本项目已有）：

```
原始信号时域分析
    │
    ├─→ kurtosis > 12 或 crest > 15
    │       └─→ 存在明显冲击证据，进入第二阶段
    │
    └─→ kurtosis < 5 且 crest < 10
            └─→ 无明显冲击，输出"健康"或"微弱异常"
```

**第二阶段 — 分解+敏感分量选择**：

```
小波去噪 / VMD / CEEMDAN 分解
    │
    ↓
敏感分量选择（综合指标）
    │
    ├─→ 若中心频率 ≈ 啮合频率 → 齿轮分析分支
    │       └─→ 包络分析 → 边频带检测 → SER/FM4
    │
    └─→ 若中心频率在共振频带 → 轴承分析分支
            └─→ 包络分析 → BPFO/BPFI/BSF/FTF匹配
```

**第三阶段 — 多方法交叉验证**：

```
轴承分支交叉验证：
    ├─→ 小波包方法检测到 BPFO
    ├─→ VMD敏感IMF包络谱检测到 BPFO
    ├─→ CEEMDAN边际谱检测到 BPFO
    └─→ 3/3一致 → 高置信度"外圈故障"

齿轮分支交叉验证：
    ├─→ SER > 3.0
    ├─→ FM4 > 10
    ├─→ 小波包能量熵 > 0.70
    └─→ 3/3一致 → 高置信度"局部裂纹/断齿"
```

---

### 14.3 多方法投票融合

本项目 `ensemble.py` 采用的多去噪策略投票：

**去噪方法池**：
$$\mathcal{D} = \{\text{none}, \text{wavelet}, \text{vmd}, \text{wavelet\_vmd}, \text{wavelet\_lms}, \text{emd}, \text{ceemdan}, \text{savgol}\}$$

**对每个去噪方法** $d \in \mathcal{D}$：
1. 用方法 $d$ 预处理信号
2. 执行轴承诊断（包络谱匹配）
3. 执行齿轮诊断（SER/FM4/边频分析）

**投票规则**：

$$\text{Vote}(F) = \sum_{d \in \mathcal{D}} \mathbb{I}(\text{方法 } d \text{ 检测到故障 } F) \cdot w_d$$

其中 $w_d$ 为方法权重（根据历史准确率动态调整）。

**置信度计算**：

$$\text{Confidence}(F) = \frac{\text{Vote}(F)}{\sum_{F'} \text{Vote}(F')}$$

**决策阈值**：
- $\text{Confidence} > 0.6$：输出该故障类型
- $0.3 < \text{Confidence} < 0.6$：输出"疑似"+建议进一步分析
- $\text{Confidence} < 0.3$：输出"无法确定"

**D-S证据理论融合**（`diagnosis/fusion/ds_fusion.py`）：

当各方法结果冲突较大时，采用Dempster-Shafer证据理论进行决策级融合。高冲突（$K > 0.8$）时自动切换为Murphy平均法，避免经典D-S的悖论。

---

## 十五、与项目现有代码的对应关系

| 算法/特征 | 当前实现位置 | 实现状态 | 备注 |
|----------|------------|---------|------|
| 小波阈值去噪 | `diagnosis/preprocessing.py::wavelet_denoise` | ✅ 已实现 | db8默认，支持soft/hard/improved阈值 |
| 小波+VMD级联 | `diagnosis/preprocessing.py::cascade_wavelet_vmd` | ✅ 已实现 | 两阶段级联降噪 |
| 小波+LMS级联 | `diagnosis/preprocessing.py::cascade_wavelet_lms` | ✅ 已实现 | 小波→LMS自适应滤波 |
| 联合降噪入口 | `diagnosis/preprocessing.py::joint_denoise` | ✅ 已实现 | WAVELET_VMD/WAVELET_LMS统一接口 |
| VMD分解 | `diagnosis/vmd_denoise.py::_vmd_core` | ✅ 已实现 | 内存优化版ADMM，O(T·K)内存 |
| VMD降噪 | `diagnosis/vmd_denoise.py::vmd_denoise` | ✅ 已实现 | IMF筛选（相关+峭度）重构 |
| VMD敏感模态选择 | `diagnosis/vmd_denoise.py::vmd_select_impact_mode` | ✅ 已实现 | 基于峭度+包络熵选择 |
| EMD分解 | `diagnosis/emd_denoise.py::emd_decompose` | ✅ 已实现 | Rilling边界+Pchip插值+抛物线极值精化 |
| CEEMDAN分解 | `diagnosis/emd_denoise.py::ceemdan_decompose` | ✅ 已实现 | Torres 2011标准算法，噪声IMF分层 |
| EMD/CEEMDAN降噪 | `diagnosis/emd_denoise.py::emd_denoise` | ✅ 已实现 | 相关/峭度筛选+回退策略 |
| 小波包分解 | `diagnosis/wavelet_packet.py::wavelet_packet_decompose` | ✅ 已实现 | PyWavelets WaveletPacket |
| 小波包能量熵 | `diagnosis/wavelet_packet.py::compute_wavelet_packet_energy_entropy` | ✅ 已实现 | Shannon熵+归一化+啮合频带集中度 |
| 小波包降噪 | `diagnosis/wavelet_packet.py::wavelet_packet_denoise` | ✅ 已实现 | 能量阈值节点筛选 |
| Savitzky-Golay平滑 | `diagnosis/savgol_denoise.py::sg_denoise` | ✅ 已实现 | 与wavelet互补，O(N)复杂度 |
| VMD+ICA盲源分离 | `diagnosis/bss.py::vmd_ica_separation` | ✅ 已实现 | 单通道扩展为多通道，峭度最大选故障分量 |
| 轴承包络谱分析 | `diagnosis/bearing.py::envelope_analysis` | ✅ 已实现 | 带通+Hilbert+低通+包络谱，BPFO/BPFI/BSF匹配 |
| 轴承快速Kurtogram | `diagnosis/bearing.py::fast_kurtogram` | ✅ 已实现 | 多尺度STFT近似Antoni滤波器组 |
| 轴承CPW分析 | `diagnosis/preprocessing.py::cepstrum_pre_whitening` | ✅ 已实现 | 倒频谱编辑+包络分析 |
| 轴承MED分析 | `diagnosis/preprocessing.py::med_filter` | ✅ 已实现 | 最小熵解卷积+包络 |
| 齿轮FM0/FM4/M6A/M8A | `diagnosis/gear/metrics.py` | ✅ 已实现 | 基于TSA/残差/差分信号 |
| 齿轮SER | `diagnosis/gear/metrics.py::compute_ser_order` | ✅ 已实现 | 基于阶次谱的边频带能量比 |
| 齿轮NA4/NB4 | `diagnosis/gear/metrics.py` | ✅ 已实现 | 历史方差归一化，无历史退化为FM4 |
| 齿轮小波包能量熵 | `diagnosis/wavelet_packet.py` | ✅ 已实现 | 行星箱与定轴箱不同阈值 |
| 行星箱VMD解调 | `diagnosis/gear/planetary_demod.py::planetary_vmd_demod_analysis` | ✅ 已实现 | 幅频联合解调，K≤5，exhaustive模式 |
| 行星箱窄带包络阶次 | `diagnosis/gear/planetary_demod.py::planetary_envelope_order_analysis` | ✅ 已实现 | mesh_order附近窄带滤波+Hilbert+阶次谱 |
| 多算法集成诊断 | `diagnosis/ensemble.py::run_research_ensemble` | ✅ 已实现 | 多去噪+多方法投票，D-S证据融合 |

---

## 十六、核心参考文献索引

### 小波变换与去噪

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Mallat (1989)** | _A theory for multiresolution signal decomposition: the wavelet representation_, IEEE Trans. PAMI 11(7): 674-693 | 多分辨率分析理论，Mallat快速算法 | 1.2 |
| **Daubechies (1992)** | _Ten Lectures on Wavelets_, SIAM | 紧支撑正交小波系统理论 | 1.3 |
| **Donoho & Johnstone (1994)** | _Ideal spatial adaptation by wavelet shrinkage_, Biometrika 81(3): 425-455 | 小波阈值去噪理论框架（VisuShrink） | 2.1, 2.3 |
| **Donoho & Johnstone (1995)** | _Adapting to unknown smoothness via wavelet shrinkage_, JASA 90(432): 1200-1224 | SURE阈值与自适应阈值 | 2.3 |
| **Mallat & Hwang (1992)** | _Singularity detection and processing with wavelets_, IEEE Trans. IT 38(2): 617-643 | 模极大值去噪与信号重构 | 2.4 |
| **Chang et al. (2000)** | _Adaptive wavelet thresholding for image denoising and compression_, IEEE Trans. IP 9(9): 1532-1546 | BayesShrink自适应阈值 | 2.3 |

### EMD/EEMD/CEEMDAN

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Huang et al. (1998)** | _The empirical mode decomposition and the Hilbert spectrum for nonlinear and non-stationary time series analysis_, Proc. R. Soc. Lond. A 454: 903-995 | EMD原始论文，Hilbert-Huang变换 | 4, 8.2 |
| **Wu & Huang (2009)** | _Ensemble empirical mode decomposition: a noise-assisted data analysis method_, Adv. Adapt. Data Anal. 1(1): 1-41 | EEMD算法，噪声辅助解决模态混叠 | 5 |
| **Torres et al. (2011)** | _A complete ensemble empirical mode decomposition with adaptive noise_, IEEE ICASSP | CEEMDAN完备算法，自适应噪声幅值 | 6 |
| **Rilling et al. (2003)** | _On empirical mode decomposition and its algorithms_, IEEE-EURASIP Workshop | EMD双阈值停止准则 | 4.3 |

### VMD变分模态分解

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Dragomiretskiy & Zosso (2014)** | _Variational Mode Decomposition_, IEEE Trans. SP 62(3): 531-544 | VMD原始论文，变分框架+ADMM求解 | 7 |
| **Zhang et al. (2015)** | _Application of VMD to incipient fault detection of rolling bearings_, Measurement 91: 202-209 | VMD在轴承早期故障诊断中的应用 | 7, 9.1, 11 |
| **Wang et al. (2015)** | _Research on VMD and its application in detecting rub-impact fault_, MSSP 60-61: 243-251 | VMD参数选择方法 | 7.4 |

### 故障诊断应用

| 作者/年份 | 文献 | 核心贡献 | 适用章节 |
|----------|------|---------|---------|
| **Lei et al. (2013)** | _An improved kurtogram method for fault diagnosis using WPT_, MSSP 35(1-2): 176-199 | 小波包改进Kurtogram | 3, 9.1 |
| **Yan & Gao (2007)** | _A comparative study of WPT and EMD for mechanical fault diagnosis_, MSSP 21(2): 680-693 | EMD与小波包在故障诊断中的对比 | 3, 4 |
| **Liu et al. (2016)** | _Application of EMD-EEMD-CEEMDAN in fault diagnosis of rolling bearings_, J. Mech. Sci. Technol. 30(10): 4527-4537 | EMD系列方法在轴承诊断中的系统对比 | 4, 5, 6, 11 |
| **Feng, Zhang & Zuo (2017)** | _Planetary Gearbox Fault diagnosis via Joint Amplitude and Frequency Demodulation Based on VMD_, Appl. Sci. 7(8): 775 | VMD幅频联合解调用于行星齿轮箱 | 7, 12.4 |
| **Randall & Antoni (2011)** | _Rolling element bearing diagnostics—a tutorial_, MSSP 25(2): 485-520 | 轴承诊断综述，包络分析与谱峭度 | 9, 11 |
| **McFadden (1987)** | _Examination of a technique for the early detection of failure in gears by signal processing of the time domain average_, MSSP 1(2): 173-183 | TSA早期故障检测经典方法 | 10.4, 12.3 |
| **Zakrajsek et al. (1993)** | _An analysis of gear fault detection methods as applied to pitting fatigue failure data_, Proc. MFPT | 多种齿轮故障检测方法对比 | 10, 12 |

---

> **维护说明**：本文档为小波变换与模态分解方法的专用算法理论参考，与 `ALGORITHMS.md` 形成互补关系。
> `ALGORITHMS.md` 侧重轴承/齿轮诊断的整体算法体系，本文档专注于：
> (1) 信号分解与降噪方法的理论细节；(2) 分解结果与故障特征之间的映射关系；(3) 敏感分量选择的工程策略；(4) 多方法融合的决策逻辑。
> 每新增或修改一个分解/去噪/诊断模块，请同时更新本文档和 `ALGORITHMS.md` 中的对应关系表。
