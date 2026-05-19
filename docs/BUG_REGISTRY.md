# Bug 记录

> 最后更新: 2026-05-20 | 详见 AGENTS.md §14

## 未修复 (1)

| # | 文件 | 描述 |
|---|------|------|
| 9 | `planetary_demod.py:evaluate_planetary_demod_results` | WTG 健康 `planetary_sun_fault` 误报 warning |

**详细描述**：

- `evaluate_planetary_demod_results` 从窄带解调结果读取 `envelope_kurtosis` 作为 `planetary_sun_fault` 的主判定值
- WTG 健康文件 `He_N1_20-c1.npy` 的窄带 `envelope_kurtosis=2.2`，超过阈值 `2.0` → warning
- 但同文件的 `sun_fault_snr` 和 `sun_modulation_depth` 均正常
- 断齿文件 `Br_B1_20-c1.npy` 反而 `envelope_kurtosis=1.2` < 2.0 → 不报警
- 指标与故障**反相关**，说明 `envelope_kurtosis` 在行星箱健康/故障间的区分力被高估（注释称"区分力 3.28×, 健康 median=0.88"，但实测健康可达 2.2）

**可能解决方法**：

1. 提高 warning 阈值 2.0→3.0（但可能漏检真实故障）
2. 改用 `sun_modulation_depth`（调制深度比）替代 `envelope_kurtosis` 作为主判定——调制深度反映故障阶次相对啮合阶次的能量比，理论上对健康/故障更敏感
3. 增加多文件统计校准：用 WTgearbox 全部 160 文件重新标定阈值
4. 窄带频段选择优化：当前根据 `sun_fault_order` 选频段，但对某些健康文件可能选到非最优频段

## 已修复 (8)

| # | 文件 | 描述 |
|---|------|------|
| 1 | gear/metrics.py | CAR 值 10^12 爆炸 — 背景用 median(abs(cep)) |
| 2 | engine.py, health_score_continuous.py | planet_count=0 — n_planets 键未识别 |
| 3 | health_score_continuous.py | is_gear_device 不认 sun 键 |
| 4 | bearing.py:fast_kurtogram | 无冲击时 fallback 任意宽带 |
| 5 | engine.py:analyze_bearing | Teager 未做角域重采样 |
| 6 | engine.py:_evaluate_bearing_faults | 边带增强缺包络峭度门控 |
| 7 | features.py:compute_fft | remove_dc 未导入 |
| 8 | engine.py:_evaluate_bearing_faults | CW 健康统计误报 — 物理未检出抑制统计 |
