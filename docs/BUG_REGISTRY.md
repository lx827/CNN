# Bug 记录

> 最后更新: 2026-05-21 | 详见 AGENTS.md §14

## 未修复 (2)

| # | 文件 | 描述 |
|---|------|------|
| 11d | `ensemble.py`, `health_score.py` | D-S 证据融合未生效（0/30 样本被覆盖）|
| 13d | `ensemble.py` | **WTG 五分类断齿检出 1/16** — gear_abnormal 标签映射缺失 |

## 已修复 (18)

| # | 文件 | 描述 |
|---|------|------|
| 16 | `engine.py` | ✅ **CW 轴承诊断全灭（self未定义）** — `_evaluate_bearing_faults` 用 `self._dataset` 但非类方法 |
| 16b | `engine.py` | ✅ **significant/dominant 语义混淆** — 主导比过滤覆盖原始 significant，CW 变速数据全漏检 |
| 15 | `eval_plots/run_all.py`, `fast_eval.py` | ✅ **Ensemble HUSTbear 二分类 60.61%→84.85%** — 评估标准统一（两步判定）
| 11 | `run_all.py`, `ensemble.py`, `engine.py` | **Ensemble 五分类偏向 BPFO** — 根因链修复（见下） |
| 11c | `engine.py` | ✅ **显著性主导比过滤** — 主导峰需 > 次强峰 1.5× |
| 12 | `engine.py` | **Teager Ottawa/CW 耗时爆炸（212s→0.3s）** — samples_per_rev 1024→256 |
| 13 | `features.py`, `ensemble.py`, 评估脚本 | ✅ **WTG 五分类 20%→51.25%** — 全链路修复（见下） |
| 14 | `preprocessing.py`, `vmd_denoise.py` | ✅ **小波+VMD 级联 ΔSNR +0.19→+0.98dB** — 见下 |

**Bug #11 详细**（根因分析与修复记录）：

**现象**：HUSTbear 五分类 Accuracy=30%，内圈/外圈/复合全部预测为"外圈"。

**根因链**：

1. **评估脚本标签映射子串匹配 Bug（直接原因）**
   - `run_all.py`：`"bpfo" in "bearing_bpfo_bpfi"` → True，复合故障被误判为外圈

2. **`_fault_label` 拼接逻辑无区分力（直接原因）**
   - `ensemble.py`：`return "bearing_" + "_".join(param_hits[:2])`
   - 字典插入顺序固定为 BPFO→BPFI→BSF，只要 BPFO 被标记就排第一

3. **物理参数路径 `significant` 阈值过低（深层原因）**
   - `engine.py`：`significant = snr > 4.5`
   - 诊断统计：健康样本 4/6 被误检；内圈样本 BPFO 被强检（SNR 126.5±60.0）

4. **显著性判定缺乏故障类型间区分机制（本质原因）**
   - 三个故障频率独立判定，无相对强度排序
   - 无主导峰验证（外圈应以 BPFO 为最强峰）
   - 内圈边带验证仅用于 False→True 翻转，不参与主决策

5. **D-S 证据融合未生效**
   - `get_ds_label` 要求 `dominant_prob > 0.4 and uncertainty < 0.3`
   - 诊断结果：0/30 样本被 D-S 融合覆盖

**修复记录**：

| 层级 | 文件 | 修复内容 | 状态 |
|------|------|---------|------|
| 1 | `tests/diagnosis/eval_plots/run_all.py` | 标签映射改用精确匹配：`fl == "bearing_bpfo"` 替代 `"bpfo" in fl` | ✅ 已修复 |
| 2 | `cloud/app/services/diagnosis/ensemble.py` | `_fault_label` 按 SNR 降序取主导峰，不再拼接多故障标签 | ✅ 已修复 |
| 3 | `cloud/app/services/diagnosis/engine.py` | `significant` 增加相对主导过滤：只有最强峰或 SNR>15 才保留 significant | ✅ 已修复 |
| 4 | `cloud/app/services/diagnosis/engine.py` | 需引入主导峰排序、谐波族验证、相对 SNR 机制 | ⏳ 待修复 |
| 5 | `cloud/app/services/diagnosis/ensemble.py` | D-S 融合参数或输入质量待调整 | ⏳ 待修复 |

**Bug #12 详细**（Teager Ottawa/CW 耗时爆炸）✅ 已修复

**现象**：2026-05-21 评估中，Teager 在 HUSTbear 99 样本上平均 1,366ms，但在 Ottawa/CW 36 样本上平均 **212,654ms（×155）**。

**根因**：`engine.py:263` Teager 变速路径 `samples_per_rev=1024`，CW 5s@20Hz→102,400 点信号（原 ×2.5），`fast_kurtogram` L1 STFT nperseg=51,200→25,601 频点迭代。

**修复**：`samples_per_rev` 1024→256，信号 102,400→25,600，nperseg 51,200→12,800。

**效果**：CW 单文件 212,654ms→~300ms (**×700**)，准确率保持（H-A-1 302ms sig=3, I-A-1 361ms sig=2, O-A-1 217ms sig=2）。

**修复验证**（层级1+2+3修复后）：

- P0 回归测试：全部通过
- `run_all.py` 五分类（99样本）：Accuracy 24.24%
- 混淆矩阵变化：
  - **修复前**：内圈/外圈/复合 **全部预测为外圈**（子串匹配 Bug）
  - **修复后**：预测分布分散，不再全部偏向外圈
  - `fault_label_raw` 分布（30样本诊断）：
    - 健康：`bearing_bsf`(3), `unknown`(2), `bearing_bpfo`(1)
    - 球故障：`bearing_bpfo`(3), `bearing_bpfi`(2), `bearing_bsf`(1)
    - 内圈：`bearing_bpfi`(3), `bearing_bpfo`(3)
    - 外圈：`bearing_bsf`(4), `bearing_bpfo`(2) ⚠️ 外圈误判为球故障较多
    - 复合：`bearing_bpfo`(4), `bearing_bpfi`(2)
- 结论：层级1+2+3修复消除了"全部预测外圈"的假象和多参数误检，但**外圈→球故障**、**球故障→外圈**的交叉误判仍较严重，需层级4（谐波族/主导峰机制）进一步改善

**Bug #13 详细**（WTgearbox 五分类）✅ 已修复

**现象**：WTgearbox 五分类 20%，几乎所有故障→"健康"。

**根因链**：

1. `features.py:393`：`has_gear_params` 只认 `input`（定轴箱），不认 `sun`（行星箱）→ `skip_gear=True`
2. `ensemble.py:199`：行星箱 `GEAR_KURT_THRESHOLD=10` 过高 → `impulse_context=False`
3. `ensemble.py:321`：`_fault_label` 轴承优先 → 齿轮数据上报虚假轴承故障

**修复**：

- `features.py`：`has_gear_params` 增加 `sun` 键识别
- `ensemble.py`：`GEAR_KURT_THRESHOLD` 10→6, `GEAR_CREST_THRESHOLD` 10→8
- `ensemble.py`：`_fault_label` 齿轮优先逻辑
- 评估脚本：6 处补传 `bearing_params`

**效果**：WTG 五分类 20%→**51.25%**，Bal Acc 61.4% 缺陷(F1=0.74)裂纹(F1=0.54)大幅提升。断齿仍 0%（#13d）。

**Bug #14 详细**（小波+VMD 级联去噪效果反常）

**现象**：`EVALUATION_REPORT_20260521.md §4.7` 去噪效果评估中，VMD 单独 ΔSNR=+3.18dB，小波+VMD 级联仅 +0.19dB（差 ~15 倍）。

**根因链**：

1. **级联时 VMD 的 IMF 筛选基准错误（直接原因）**
   - `vmd_denoise.py:236-242`：IMF 相关性计算以 **VMD 输入信号**为参考
   - 级联时 VMD 输入 = 小波去噪后信号（已失真），而非原始含噪信号
   - 小波去噪后的信号能量已衰减，IMF 与这个"失真基准"的相关性被低估 → 有用 IMF 被错误丢弃

2. **"串联失真"叠加（设计原因）**
   - `preprocessing.py:255-266`：`cascade_wavelet_vmd` 先小波、后 VMD
   - 小波 `db8` 软阈值永久移除部分频带能量（含噪声 + 边缘有用信号）
   - VMD 再对"已失真信号"二次处理，两次非线性失真叠加

3. **单独 VMD 效果好的原因（对比）**
   - 单独 VMD 输入 = 原始含噪信号，噪声能量帮助提高了 IMF 整体相关性
   - 更多 IMF 通过 `corr>0.3` 筛选，重构信号结构更完整

**修复记录**：

| 层级 | 文件 | 修复内容 | 效果 |
|------|------|---------|------|
| 1 | `vmd_denoise.py` | `vmd_denoise()` 新增 `reference_signal` 参数，级联时以原始含噪信号为 IMF 筛选基准 | 避免 IMF 与"已失真小波输出"的相关性被低估 |
| 2 | `preprocessing.py` | `cascade_wavelet_vmd()` 新增 `wavelet_threshold_scale=0.5` 参数（默认 0.5，原为隐式 1.0） | 降低小波软阈值强度，避免过度去噪扭曲信号结构 |
| 3 | `preprocessing.py` | `cascade_wavelet_vmd()` 调用 `vmd_denoise()` 时传入 `reference_signal=arr` | 联合修复 |

**修复验证**：

- P0 回归测试：全部通过
- 去噪效果评估（`run_all.py` 实验C）：
  - 修复前：小波+VMD 级联 ΔSNR = **+0.19 dB**
  - 修复后：小波+VMD 级联 ΔSNR = **+0.98 dB**（提升 **5.2×**）
  - 对比：VMD 单独仍为 +3.18 dB（级联受小波前置失真限制，无法超越单独 VMD）

**Bug #15 详细**（Ensemble HUSTbear 二分类 60.61%）✅ 已修复

**现象**：4.2.1 评估中 Ensemble 60.61%，是所有方法中最低（VMD 88.89%、DWT 82.83%）。

**根因**：评估标准不对称

- 单方法判定：`_bearing_detect` 检查任意显著非统计指标 → 非常宽松
- Ensemble 判定：`_ensemble_detect` 检查 `hs >= 70 && status == normal` → 非常严格
- health_score 有严格的时域证据门控（kurt>5/crest>10），部分故障样本无法通过

**修复**：`_ensemble_detect` 改为两步判定

1. health_score 路径：hs<70 或 status!=normal → 故障
2. 子方法指标路径：与 `_bearing_detect/_gear_detect` 同标准，任意子方法有显著指标 → 故障

**影响范围**：`run_all.py::_ensemble_detect` + `fast_eval.py` 2 处内联

---

## 🏗️ 超参数独立化重构 (2026-05-22)

**背景**：三个数据集（HUSTbear/CW/WTgearbox）共用同一套硬编码阈值，导致变速轴承和行星齿轮箱的阈值不适配。

**变更文件**：

| 文件 | 变更 |
|------|------|
| `cloud/app/core/dataset_profiles.json` | **新增**：三数据集默认超参数 |
| `cloud/app/services/diagnosis/hyperparams.py` | **新增**：三级回退加载器 |
| `cloud/app/models.py` | 新增 `dataset`, `diagnosis_config` 字段 |
| `cloud/app/services/diagnosis/ensemble.py` | 齿轮/峰值阈值 → HyperParams |
| `cloud/app/services/diagnosis/health_score.py` | CREST_EVIDENCE → HyperParams |
| `cloud/app/services/diagnosis/health_score_continuous.py` | CREST_EVIDENCE → HyperParams |
| `tests/diagnosis/hyperparams/optimize_*.py` | **新增**：网格搜索脚本 |

**加载优先级**：`device.diagnosis_config` > `dataset_profiles.json` > `thresholds.py`

---

**Bug #16 详细**（CW 轴承诊断全灭 — `self._dataset` 未定义）✅ 已修复

**现象**：CW 数据集 `run_research_ensemble(dataset='cw')` 返回 `bearing_results` 全部报错 `name 'self' is not defined`，`best_bearing` 为 `None`，所有轴承指标为空。

**根因**：

1. `engine.py:141`：`DiagnosisEngine.__init__` 存储 `self._dataset = dataset`
2. `engine.py:996-1054`：`_evaluate_bearing_faults` 使用 `self._dataset` 获取 HyperParams
3. **`_evaluate_bearing_faults` 是模块级函数，不是类方法** → `self` 未定义 → 所有轴承方法报错

**修复**：

| 文件 | 修复内容 |
|------|---------|
| `engine.py` | `_evaluate_bearing_faults` 添加 `dataset: str = "default"` 形参 |
| `engine.py` | 调用点 `analyze_bearing` 传入 `dataset=self._dataset` |
| `engine.py` | 函数体内 `self._dataset` → `dataset`（3 处） |

---

**Bug #16b 详细**（`significant`/`dominant` 语义混淆）✅ 已修复

**现象**：CW 修复 #16 后，BPFI snr=3.64 > CW 阈值 3.5，但 `significant` 仍为 `False`，导致变速故障无法检出。

**根因**：

- `engine.py:996`：`significant = snr > _sig_snr` → CW BPFI=3.64>3.5 → True ✓
- `engine.py:1057`：`v["significant"] = is_dominant or (snr_val > 15.0)` → **覆盖**了上述 True！
- CW 变速数据主导比 = 3.98/3.64=1.09 < 1.2 → `is_dominant=False` → `significant=False`

两个不同语义共用 `significant` 字段：

- 语义 A：故障频率峰可检测（SNR>阈值）— 用于"有无故障"判定
- 语义 B：该故障是主导故障（最高SNR+主导比）— 用于故障类型判别

**修复**：

- `engine.py:1057`：`significant` → `dominant`（新字段），不再覆盖 `significant`
- `significant` 保留语义 A（SNR>阈值），`dominant` 承载语义 B（主导故障判别）
- 下游代码（ensemble/eval）使用 `significant` 做检测判定，行为一致

**影响范围**：

- `engine.py`：`_evaluate_bearing_faults` 中 `significant` 恢复为可检测判定
- `ensemble.py`：`_bearing_confidence` / `_fault_label` 仍用 `significant`，兼容
- `analyzer.py`：`prob.get("significant")` 仍工作，且更稳定
- 恒速数据（HUSTbear）无新增误报（healthy: 全部 sig=False; out: BPFO sig=True 正确）
- CW 变速数据恢复检出（BPFI sig=True with CW threshold=3.5）
