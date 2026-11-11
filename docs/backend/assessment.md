# 证据、评估与诊断状态契约

> 状态：#77/#84 类型化核心已提交；生产编排、缓存/迁移、API 与前端接入仍在实施。本文先定义核心稳定语义，不将未集成接口写成已验证完成。
>
> 核心导航：`cloud/app/services/diagnosis/domain.py`、`adapters.py`、`assessment.py` 与 `fusion/evidence.py`。数学表示与机械前提仍归 [算法契约](../algorithms/INDEX.md)。

## 两维状态与覆盖范围

| 字段 | 合法值 | 责任 |
|------|--------|------|
| `evaluation_status` | evaluated / indeterminate / not_evaluable | 能否形成有效评估 |
| `diagnosis_conclusion` | normal / warning / fault / unknown | 有效证据支持的诊断结论 |
| `health_score` | 有限 0–100 / null | 工程强度分数，不是故障概率 |
| `coverage` | complete / partial / none | 配置对象中有多少形成有效评估 |

`not_evaluable` 表示前提、输入或有效表示不足；`indeterminate` 表示证据或质量不足、结论冲突；`evaluated` 才允许形成显式 normal/warning/fault。前两者结论必须 unknown、健康分必须 null。非法值不静默变成正常或故障，领域结果不再输出旧 `status` 别名。

一个对象不可评估不无条件覆盖另一个对象的有效评估。总体可为 `evaluated + partial`，分数和结论仅覆盖有效对象，局部状态和建议明确未覆盖对象；所有对象都未知时 coverage=none、分数为空。complete 只说明所有配置对象已评估，不意味着所有理论方法都运行或效果已证实。

## Evidence、Evaluation 与 Diagnosis

`Evidence` 表达一个方法实际已经评估的证据：身份、缓存键、真实对象/通道、精确方法、共同依赖、局部评估与结论、可靠度、信号 RMS、物理命题、扣分请求和原因。方法名大小写在唯一边界规范化，未知方法/命题拒绝，不用子串猜测。

有效正常证据必须来自可观测、正能量的有效阴性；空列表、零信号、失败和缺参数不是阴性。normal 不携带故障命题或扣分，warning/fault 必须有明确命题。不可用证据保存原因，但不携带可靠度、故障票或扣分。

`Evaluation` 保留一个对象的全部方法证据、依赖组、融合支持量、冲突与局部结论；未评估方法不隐藏。`Diagnosis` 汇总对象评估、扣分、建议、故障命题和覆盖范围。序列化仅输出 `contract_version=1` 的规范诊断结构，不通过旧状态做双解释。

对象 Pipeline 评估转为 Evidence 的 adapter 仅读评估器已经给出的布尔显著性/warning/critical，不再从原始值补另一阈值。原始无阈值指标、不可评估项、研究组合和缺机械参数不形成物理诊断票；实际 MCKD→MED 回退的证据身份随实际方法保存。

## 共同依赖与融合

```text
对象方法评估 → 标准 Evidence → 同 record/channel/object 的依赖连通组
→ 每组有限支持/内部冲突 → 独立组 D-S 支持量
→ 对象结论 → 总体覆盖与结论 → 一次评分/建议
```

共享任意原始观测或处理依赖的证据形成连通组：A 依赖 x、B 依赖 x/y、C 依赖 y 时三者是一组。不同去噪和包络方法名不证明独立性，共用原始记录不能按方法数量增票。生产证据 family 精确分类为 bearing_envelope、bearing_cyclic、gear_order、planetary、statistics；family 与 dependency 各有责任，family 名不同也不能绕过共同依赖。

组内 normal 与 anomaly 各取最大显式工程可靠度，不累计相似方法数量；保存内部正反冲突。只有独立依赖组进入对象级 `{normal,anomaly}` D-S 框架。BPFO/BPFI 等局部损伤命题可以共存，不把它们硬塞为互斥 D-S 单例。可靠度及融合质量是工程支持量，没有标定集时不称实测故障概率。

跨独立组使用未归一化合取质量累计冲突，再归一保留存活质量；不以最后一步冲突覆盖前序，也不用 Murphy 自我组合伪造独立证据。对象冲突达到策略上限（当前核心为 0.8）时 indeterminate/unknown。无有效证据时保留全集无知，不从时域值猜正常。

研究组合的 `research_only=true` 或 `production_eligible=false` 在生产适配/融合边界拒绝；相关组合的 `evidence_family` 不能作为独立票。各组合仍可保留研究表示，见 [复合研究契约](../algorithms/composite/INDEX.md)。

## 扣分、结论与建议

扣分 code 与权重键在 assessment 的精确表中登记。未知请求或未知权重报错，不统一回退 kurtosis。一个依赖组只取最大加权扣分，不按相似算法数量累加。每条 `Deduction` 保存 code、对象、来源 Evidence、原量、权重键、权重与实际加权值供审计。

冲突扣分原量为冲突系数，只乘 `ds_conflict` 一次（当前默认 8），不先扣 8 分再乘 8。健康分为 `max(0,100−实际加权扣分总和)`，只在形成有效诊断时输出；它不反向决定 normal/warning/fault。总体结论取有效对象的最高严重级别，保留局部未知，避免按分数再重判一次。

建议在同一 assessment 单源产生，明确已评估对象和未覆盖对象。时域 margin 等原始指标的公式来自公共统计模块；设备/通道告警阈值与对象工程阈值是显式策略，不互相覆盖或另算健康度。

## 直接重评与资源边界

`reassess_diagnosis` 只接受 `contract_version=1` 且没有旧 `status` 的规范 Evidence 载荷，直接评估已有证据和新策略，不读原信号、不调用分解/FFT/TSA。旧 JSON 不具有足够无歧义语义时要求重新分析，不能通过猜旧字段升级成健康正常。

profile 决定运行哪些 Pipeline，与证据融合是两层；增加运行方法不自动增加独立支持量。并发、线程池与窗口继续遵守 [2G 运行时](architecture.md)，本轮不进行性能优化或真实数据效果推断。

## 身份、缓存与后续接入边界

`DiagnosisKey=(device_id,batch_index,channel,denoise_method)`；方法 Evidence 必须是真实通道，channel=0 仅表示批次摘要。真实通道号来自记录，不用查询枚举序号或第一有效通道代替；对应机械参数同样按该通道取值。

目标持久化边界是通道缓存与批次摘要分开：手动通道分析不覆盖批次/设备摘要，独立转频写回不命中通道诊断缓存。最新行按 analyzed_at/id 选择，研究结果不进生产 store。轻摘要需要无歧义的两维状态；迁移/旧数据策略、写入形态和公开 HTTP 必须在最终接入源码确认后同步 [持久化](persistence.md) 与 [API](../api/backend_api.md)，本核心文档不提前声称这些接入已经完成。

## 验证状态

typed core 的独立业务向量保护：共享/独立依赖与传递闭包、同源重复不放大、二元 D-S 与可共存部位命题、高冲突、零/空/未知、混合对象 partial、每条扣分权重仅乘一次、规范 Evidence 直接重评不调用算法。最终 worker、真实 HTTP、缓存、告警和前端实际消费者证据在源码集成后统一登记 [测试索引](../tests/INDEX.md)。这些业务验证不修改或证明算法数学、阈值校准与真实检出效果。
