# 小波与模态分解契约

> 状态：纯计算、分量选择、质量门控与业务错误边界已分离；#124 小波/VMD 原生模块与默认适配、同公式 EMD 默认筛分接入见 [原生小波与 VMD](native_wavelet_vmd.md)。真实数据诊断效果与目标资源仍需分别验收。
>
> 实现导航：`cloud/app/algorithms/decomposition/`、`cloud/app/algorithms/pipelines/decomposition.py`。各算法族保留专属 adapter，不设统一 `BaseAlgorithm`。

## 数学目的

分解把输入表示为小波系数、频带重构或本征模态。DWT 阈值用于系数收缩；WP 用完整树划分频带；EMD 族依靠局部极值包络筛分；VMD 在频域优化带限模态。原始指标、排序、去噪选择与机械故障评估分别定义；分解成功只说明得到表示。

## 适用与不适用场景

| 方法 | 用途 | 边界 |
|------|------|------|
| DWT | 宽带噪声抑制、细节频带重构 | 小波基、延拓和阈值会改变冲击，不能直接判故障 |
| WP | 完整频带能量、节点选择与包络 | 自然路径不是频率顺序；抽取系数不与原信号前 N 点比较 |
| EMD/EEMD/CEEMDAN | 非平稳探索性分解与敏感 IMF | 端点、模态混叠与未收敛误差影响结果，IMF 不保证有独立物理来源 |
| VMD | 有模态数与频带先验的带限分解 | 模态数/惩罚因子需给定，有限迭代不保证收敛 |

S-G、LMS、ICA 与级联各有前提，单通道扩展不会创造多测点可观测性。VMD AM-FM 等 #75 组合在 [专用研究入口](../composite/INDEX.md) 查看，不参与生产融合或告警。

## 输入、输出与单位

| 对象 | 契约 |
|------|------|
| 输入 | 一维有限数组、正采样率 Hz；幅值保持调用方物理单位或 counts |
| 小波系数 | 第 j 层有效采样率 `fs/2**j`；自然路径与频率序分别保留 |
| 重构、IMF、模态、残差 | 同输入幅值单位；在原采样率和正确时间轴比较 |
| VMD 中心频率 | 输出 Hz；内部 cycles/sample 乘原采样率换算 |
| 有效区间 | 原始输入的半开区间 `[start_index, stop_index)`，不含补零范围 |
| 原始分量指标 | 相关绝对值、Pearson/excess 峭度、归一化包络熵、能量/能量比与中心 Hz |
| 选择 | 索引、指标、排序分数、有效区间、状态与质量；分数不是故障概率 |

能量为采样平方和（输入单位平方），不是已标定物理能量；归一化包络熵的对数底与归一化上界一致。Pearson 高斯基准 3，excess 基准 0，两者不共用阈值。不可定义的相关、熵或峭度返回 `None`。

## 必要前提

- DWT/WP 层数与记录、滤波器长度兼容。WP 频率序按 Gray 对应频带排列；细节重构清除未选近似和细节。
- 小波分量先重构到原时间轴再计算相关和能量，禁止用抽取系数与原信号头部作物理比较。
- EMD 的镜像点和抛物线精化位置/幅值实际参与插值；SD 满足停止时接受本轮更新。EEMD/CEEMDAN 记录种子；当前 CEEMDAN 对应 Torres 2011，不混称 improved-CEEMDAN。
- EMD 族在现有算法族替换接口内使用单 IMF 筛分核；实例持有核，归一化、多 IMF、随机噪声、集成公式与结果状态继续复用 Python 外层。核异常直接传播，初始极值不足与筛分上限保留原有含义。
- `NativeEMDImplementation` 成为默认同公式筛分，支持 PCHIP/cubic 与 SD/Rilling 四种组合；极值、精化、镜像、包络、更新与单 IMF 停止在 C++ 内一次完成。EMD/EEMD/CEEMDAN 外层公式保持原样，独立 emd.sift 0.8.1 家族不混入该默认路径。
- 小波/VMD 默认由原生 adapter 计算；显式 PyWavelets/NumPy 参考实现继续可注入。原生小波复用官方独立 C 内核，并提供不物化全部分量的系数分析与按路径重构；VMD 使用模态连续的单边两轮工作区。详见 [数学、所有权和验证边界](native_wavelet_vmd.md)。
- VMD 奇数/长记录按结果有效区间使用，参考信号同步切片，不补零伪装全长输出。
- 转速估计信号与故障增强信号分离，见 [阶次契约](../order/INDEX.md)。

## Pipeline 组合

```text
族专属分解 → 原时间轴分量与有效区间 → 原始指标
→ 去噪选择或敏感排序 → 收敛质量门控 → 有效重构
→ 包络表示与轴承指标 → 独立故障评估
```

EMD/VMD 去噪 analyze 只分解并提指标，evaluate 消费已有指标选择，可改阈值而不重复分解。EMD 去噪用 excess，VMD 用 Pearson。WP 能量 Pipeline 计算原时间轴能量、占比和熵，select 才选节点；能量熵不直接命名齿轮故障。

敏感分量包络 Pipeline 可消费既有分解，排序/重构后运行 Hilbert、单边谱与包络分析；evaluate 不重算表示。排序权重、去噪门槛、质量门控、故障阈值互不替代。只有所选 IMF 全部收敛或整体 VMD 收敛才接受质量；未选择 IMF 的失败不污染合法选中项。

## 错误与不可判定语义

- 非法维度、非有限值、采样率、层数、模态参数、时间轴错配显式报错。
- 常量/近单调、极值不足、无合法分量或无满足门槛项，返回不可判定/空选择与原因；保留残差，不生成全零正常重构。
- 分解有效不等于质量接受。未收敛选中 IMF/VMD 可保留研究表示，但标记 `approximate`、`quality_status=insufficient`，不得参与有效诊断。
- ndarray 兼容边界对无表示或质量不足抛错，由上层隔离方法失败；不得吞异常并把原信号当作成功去噪。
- 业务去噪统一抛出带实际方法/原因的 `DenoisingError`，HTTP 适配为 422；后台通道保留未知健康状态，不转规则回退成功。旧 preprocessing MED/CPW 数学与重复小波导出删除，消费者直接调用对应算法族。
- 即使质量接受，缺机械几何/转速也只能输出统计表示，不能构造理论故障名称。

## 复杂度与内存

DWT 约 O(N)，WP 随层数保留更多节点；完整全长 WP 分量的结果内存为 O(N·2**level)，轻量系数入口只按需要重构路径。VMD 成本为迭代更新 O(iterations·modes·N) 加输入 FFT 与各模态逆 FFT，不在每次 ADMM 更新中执行 FFT。EMD 随 IMF/筛分轮数增长，集成方法再乘集成次数。结果、参考和重构同时存在会增加内存。生产 2C2G 复用两线程池、逐批串行与业务窗口限制，见 [运行时](../../backend/architecture.md)；本地定向提速不等于目标机器资源验收。

## 参考文献

- Mallat，小波多分辨率；默认原生小波复用 PyWavelets v1.8.0 的独立 C 内核，PyWavelets adapter 保留作显式参考。
- Huang et al. (1998)，EMD；Wu & Huang (2009)，EEMD；Torres et al. (2011)，CEEMDAN。
- Dragomiretskiy & Zosso (2014)，VMD。
- 生产 EMD 族保留仓库内 Python 外层公式，默认筛分为其同公式原生实现。EMD-signal/PyEMD 1.9.0 仅作为可选 benchmark 组中的离线不同公式参照，不作为同语义替换或生产默认，区别见 [性能运行说明](../../benchmarks/diagnosis_performance.md)。
- 用户指定的另一个原生候选以 `emd 0.8.1` 的 `emd.sift` 为参考，版本/源码身份、独立模块和失败边界见 [原生 EMD 契约](native_emd.md)；与上条旧候选的公式与验证预算分别维护，不静默替换生产。
- [理论与历史示例](../wavelet_and_modality_decomposition.md) 不承担当前签名或实现状态。

## 验证向量与验证状态

独立数学审查与定向返修覆盖频率序、时间轴、熵和质量门控；文档轮次不重复算法测试。以下位于 `cloud/tests/diagnosis/algorithms/`：

| 资产 | 向量与反例 |
|------|------------|
| `test_decomposition_wavelet.py` | WP 频率序/采样率、单细节、重构与节点能量 |
| `test_decomposition_emd.py` | 简单 IMF、端点、单调/短信号、SD、残差、种子 |
| `test_emd_sift_contract.py` | 公开族入口的筛分注入、全配置组合、零噪声分支、随机序列、尺度/边界和误差判据负对照 |
| `test_native_emd.py` | 原生四种配置及 EMD/EEMD/CEEMDAN、局部包络/插值与 Rilling、所有权、固定 SHA256 五向量与未收敛质量 |
| `test_decomposition_vmd.py` | 双模态 Hz、返回结构、奇数/长输入有效区间 |
| `test_decomposition_selection.py` | 时间轴、Pearson/excess、零能量、熵、空选择 |
| `test_decomposition_review_counterexamples.py` | 熵归一化、未收敛质量、选中项门控与重评 |
| `test_decomposition_business.py` | 去噪/模态包络消费者、失败隔离与状态 |

真实数据效果需按 [数据集说明](../../datasets.md) 分别建立；测试通过不替代物理有效性和设备校准。

同公式 EMD 原生核的比较使用 [冻结误差契约](../../../cloud/tests/diagnosis/benchmarks/native_emd_contract.json) 与可重建的手写对照信号；局部包络/IMF 及完整模态/残差按输入和参考幅值缩放后分别检查逐点误差和混合 L2 界。L2 使用相对项与绝对误差地板，近零残差仍受同一绝对预算约束。普通对照要求元数据与迭代一致，停止阈值附近的分支差异另作数值与质量核验，不自动放宽预算。默认原生筛分支持 PCHIP/cubic 和 SD/Rilling，并复用当前 Python EMD 族外层；正确性检查不代表性能目标或目标 ECS 资源验收已通过。原生适配、线性带状工作区与依赖归属见 [计算库说明](../../native_compute.md)。
