# Bug 记录

> 最后更新: 2026-05-20 | 详见 AGENTS.md §14

## 未修复 (0)

（暂无）

## 已修复 (10)

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
| 9 | `planetary_demod.py` | WTG 健康 `planetary_sun_fault` 误报 — 阈值 2.0→3.0 |
| 10 | `engine.py` | `planetary_fullband_env_kurt` 对非齿轮数据误报 critical |

**Bug #9 详细**：

- `evaluate_planetary_demod_results` 用 `envelope_kurtosis > 2.0` 判定 `planetary_sun_fault.warning`
- WTG 健康 `He_N1_20-c1.npy` 的 `env_kurt=2.2` → 误报
- 分析 10 个 20Hz 文件后发现：`env_kurt` 仅对磨损(4.9~8.0)和缺齿(3.3~5.9)敏感，对断齿(1.2~2.1)和裂纹(1.0~1.3)几乎无区分力
- 行星箱有 4 个行星轮同时啮合，断齿冲击被平均化，裂纹能量太弱
- `sun_modulation_depth` 在健康/故障间完全重叠(35~57)，不可用作门控

**修复**：`warning` 阈值 `2.0 → 3.0`，`planetary_sun_fault` 从"核心指标"降级为"辅助指标"

- 磨损/缺齿仍能检出 ✅
- 健康误报消除 ✅
- 断齿/裂纹由 FM4/SER/CAR 等其他指标负责（符合行星箱诊断文献）

**Bug #10 详细**：

- `planetary_fullband_env_kurt` 用于裂纹检测：健康=6.8~20.1，裂纹=1.8~4.2（越低越严重）
- 缺少合理性门控：非齿轮数据（如 HUSTbear 轴承数据）的全频带包络峭度仅 0.6~0.9
- 轴承数据被误送进行星齿轮分析时，`fek=0.6<3.0` → 直接触发 critical
- 导致 `gear_conf=0.87` → hs=77 → status=warning

**修复**：添加 `fek >= 1.0` 合理性门控（最低合理值为裂纹下限 1.8）

- 非齿轮数据不再误触发 ✅
