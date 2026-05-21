# Bug 记录

> 最后更新: 2026-05-21 | 详见 AGENTS.md §14

## 未修复 (1)

| # | 文件 | 描述 |
|---|------|------|
| 11 | `run_all.py`, `ensemble.py`, `engine.py` | Ensemble 五分类准确率 30%，内圈/外圈/复合全部被预测为外圈 |

**Bug #11 详细**（根因分析完成，待修复）：

**现象**：HUSTbear 五分类（健康/球故障/内圈/外圈/复合）Accuracy=30%，混淆矩阵显示内圈/外圈/复合全部预测为"外圈"。

**根因链（由 `tests/diagnosis/eval_plots/diagnose_multiclass.py` 验证）**：

1. **评估脚本标签映射子串匹配 Bug（直接原因）**
   - `run_all.py` 第 310-323 行：
     ```python
     if "bpfo" in fl or "outer" in fl:   # "bpfo" 是 "bpfo_bpfi" 的子串
         pred = "外圈"
     ```
   - `"bpfo"` 在 `"bearing_bpfo_bpfi"` / `"bearing_bpfo_bsf"` 中均为 `True`
   - 导致球故障/内圈/外圈/复合全部被映射为"外圈"

2. **`_fault_label` 拼接逻辑无区分力（直接原因）**
   - `ensemble.py` 第 334-335 行：
     ```python
     return "bearing_" + "_".join(param_hits[:2])
     ```
   - `indicators` 字典插入顺序固定为 `BPFO → BPFI → BSF`
   - 只要 BPFO 被标记，标签永远以 `bearing_BPFO_` 开头
   - 真实故障类型信息丢失

3. **物理参数路径 `significant` 阈值过低（深层原因）**
   - `engine.py` 第 988 行：`significant = snr > 4.5`
   - 诊断统计：健康样本 4/6 被误检；内圈样本 BPFO 被强检（SNR 126.5±60.0，物理异常）
   - 所有故障类型 BPFO/BPFI/BSF 几乎全部被点亮

4. **显著性判定缺乏故障类型间区分机制（本质原因）**
   - 三个故障频率独立判定，无相对强度排序
   - 无主导峰验证（外圈应以 BPFO 为最强峰）
   - 内圈边带验证仅用于 `False → True` 翻转，不参与主决策
   - 谐波族丰富度未参与显著性判定

5. **D-S 证据融合未生效**
   - `get_ds_label` 要求 `dominant_prob > 0.4 and uncertainty < 0.3`
   - 诊断结果：0/30 样本被 D-S 融合覆盖

---

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
