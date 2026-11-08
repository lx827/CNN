# `resampling.py` — 相位、角域采样与阶次 FFT

**对应源码**：`cloud/app/algorithms/order/resampling.py`

## 函数

- `integrate_speed_trajectory(speed)`：用梯形积分计算累计转数 `r(t)=∫fr(t)dt`；`PhaseTrajectory.phase_rad = 2πr(t)`。
- `resample_constant_speed(signal, fs, speed, samples_per_revolution)`：已知标量转频时以 `t=r/fr` 等角采样，同时返回连续相位。
- `resample_to_phase(signal, phase, samples_per_revolution)`：在 `r[k]=k/samples_per_revolution` 位置线性插值，输出角域采样位置轴和信号。
- `compute_order_spectrum(angle_domain, max_order)`：去均值、周期 Hann、rFFT 和相干增益补偿。

## 幅值与轴契约

非 DC/Nyquist bin：

```text
amplitude[k] = |rfft(centered * periodic_hann)[k]| * 2 / sum(window)
order[k] = k * samples_per_revolution / N
```

DC 和偶数 N 的 Nyquist bin 不乘 2。对整数周期的 `A·sin(2πmθ)`，第 m 阶 bin 返回峰值 A，单位为输入信号单位，`scaling="single_sided_amplitude"`。不再使用 `sqrt(N/sum(window²))` 能量归一化并冒充物理幅值。

角域采样点轴 `k/samples_per_revolution` 与 FFT 阶次轴 `k*samples_per_revolution/N` 分别存放，禁止互相替代。
