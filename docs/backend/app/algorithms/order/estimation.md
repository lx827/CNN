# `estimation.py` — 转频估计

**对应源码**：`cloud/app/algorithms/order/estimation.py`

## 标量候选

- `estimate_spectrum_speed(...) -> ScalarSpeed`：频谱谐波评分、子谐波惩罚、包络/Welch/自相关候选仲裁；只估计转频，不执行故障增强或 VMD/EMD 去噪。
- `estimate_envelope_speed(...) -> ScalarSpeed`：指定载波频带的 Hilbert 包络候选。
- `estimate_autocorrelation_speed(...) -> ScalarSpeed`：归一化自相关滞后峰候选。

候选需要原始频谱支撑。没有有效信号、搜索频带或显著谱峰时返回 `ScalarSpeed.indeterminate`，不返回搜索下限、10 Hz 或其他默认转速。旧 `signal_utils` 仅转换该结果。仲裁使用谐波族、次谐波惩罚、包络/Welch/自相关一致性，不是单纯选择最强 FFT 峰；但轴承故障频率本身不是轴频证据，若信号没有可观测的 1×轴频或其调制证据，不得按 BPFO/标称转频比例反猜转速。

## 连续轨迹

`estimate_stft_speed_trajectory(signal, fs, search, parameters) -> SpeedTrajectoryEstimate`：

1. `resolve_stft_window_samples` 按 `fs/target_frequency_resolution_hz` 计算目标窗长，再受最长窗时长和信号长度约束。默认 8192 Hz 使用 4096 点，25600 Hz 使用 12800 点，物理分辨率均为 2 Hz；不再固定 512。
2. 在搜索频带逐帧找峰，以峰值/全谱背景、峰邻域能量/全谱能量和可靠帧比例共同判定。背景排除峰主瓣，能量分母不使用窄搜索带，因此窄带纯音不会被 bin 中位数误拒，白噪声也不会因偶然峰被接受。抛物线只细化峰位置，不伪称提高物理分辨率。
3. 可靠脊线插值到采样点；前后 STFT 未覆盖区域按边缘可靠点局部线性外推。首尾 bin 不直接等于越界：亚 bin 峰位仍在范围内且边界外侧局部能量不占优时接受；亚 bin 插值越界或外侧能量占优才记为边界风险。持续边界风险、记录内部越界或超过 STFT 半窗的端点越界均返回不可判定。边缘长度检查统一使用逐采样点计数与 `nperseg//2` 采样点上限，只有短边缘外推可截回边界。
4. 无可靠脊线时返回 `status="indeterminate"` 和原因，不生成正常轨迹。

`estimation_signal` 与阶次重采样信号由 Pipeline 分开传入，因此显式选择的故障增强不会无条件改变转速估计。
