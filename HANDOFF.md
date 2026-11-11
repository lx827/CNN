# 诊断对象化重构交接（2026-11-11）

## 当前交付边界

本轮集中收口 #72/#73/#74/#76/#80，开发分支为 `codex/diagnosis-development`，工作区 `C:/Users/25619/.codex/worktrees/diagnosis-development/CNN`，草稿 PR 为 **#89**。本交接不声明 PR 已合并或生产已部署；合并状态与最终提交以 GitHub/Git 为准。

早前要求在 #73 秩亏提交处暂停、保留共享 integration 的交接状态已被用户后续指令替代。旧 integration 已安全删除，不要按旧记录恢复它或重复开始已经完成的审查。主控负责串行集成，文档由独立实施分支集中维护。

## 已形成的稳定结构

| 层次 | 责任 |
|------|------|
| 纯算法 | 表示、变换、运动学及原始数学量；无 HTTP/ORM/设备缓存 |
| 分析 Pipeline | 按机械对象组合表示与指标，保留单位、有效区间和物理前提 |
| 诊断 Pipeline/评估器 | 调分析并评估；已有分析可以直接重评，不重做分解/FFT/TSA |
| 业务编排 | 设备配置、方法与工况门控、统一评分/建议、资源、缓存、持久化和响应 |

- #71 定轴已随 PR #85 合并。regular/residual/differential 与 nonsynchronous 各有明确含义；无历史 NA4/NB4 不可评估，原始无阈值指标不制造故障票。
- #73 高级轴承数学与业务审查已通过：真实命名二叉滤波器组、复高斯谱峭度；MED/MCKD 目标分离、SVD 数值秩与 ridge；CPW 显式稳定梳状先验；TEO 平方单位与负值策略；SC/SCoh 频移交叉乘积、正确轴与专属评估。MCKD 无目标实际运行 MED 并报告回退。
- #74 分解族使用专属 adapter。WP 频率序/原时间轴、EMD 镜像/停止、VMD Hz/有效区间已修；选择评分、去噪门槛、分解收敛质量和故障阈值分开，未收敛选中模态不能诊断。EMD-signal/PyEMD 1.10.0 只是 Apache-2.0 移植参照，当前仍是仓库自研实现。
- #72 行星固定齿圈运动学、sun/carrier 参考轴、carrier 间隔 SER、基础包络与角域 TSA 专属指标；可比基线缺失时保留 unknown，不借定轴阈值命名损伤。
- #76 基础数值表示已随 PR #81 合并；规则回退现复用对象 Pipeline，方法失败/未知不成为健康票。规则阈值和概率保持一致，嵌套机械参数先做 Mapping 门控。
- #80 按算法族/对象、业务、API、前端和测试边界维护。函数签名只在源码 docstring，不恢复逐文件镜像或已删除的兼容入口。

当前权威入口：[算法](docs/algorithms/INDEX.md)、[业务](docs/backend/diagnosis.md)、[API](docs/api/backend_api.md)、[前后端交互](docs/api/frontend_backend_interaction.md)、[测试](docs/tests/INDEX.md)、[Bug](docs/Bug登记表.md)。

## 验证结论的范围

数学/物理依据、手算已知解、独立参考、物理真值合成信号和反例优先；自动测试主要保护业务编排、状态、API 和回归。测试通过不证明真实设备检出效果，不用测试数量替代算法论证。已完成的独立审查和定向返修不再重开重复 review。

生产仍为 **2C2G**：现有线程池 `max_workers=2`，后台分析 `Semaphore(1)`，逐批串行；DataView 数值入口在慢去噪前执行业务窗口限制。DC24 的未标定 counts 仅用于显示与完整分析数组保存，不进入设备诊断、评分或告警。

本轮不宣称真实数据分类效果、阈值校准、性能达标或生产部署。主仓 CW 实际有 36 个变速 `.npy`；worktree 不自带数据不代表所有数据集缺失。用户后续提供其余数据后，按 `docs/datasets.md` 和 `CNN_DATA_ROOT` 分别验证，不代填其他数据集的机械参数。

## 后续任务

| Issue | 后续范围 |
|------|----------|
| #75 | VMD AM-FM 与完整复合实验流程；独立切片开发，不混入尚未完成的本批交付 |
| #77 | 多方法集成、统一业务评估与不可判定传播 |
| #78 | 各真实数据集与现场数据的分类效果、阈值/基线与负对照 |
| #79 | 2G 性能基准与后续 Rust/C++ 移植准备 |
| #84 | 评估状态、证据质量与诊断结论的领域状态进一步分离 |

#80 可随 #89 中本轮文档与链接检查完成关闭；#72/#73/#74/#76 按整批最终源码/API/验证验收决定。#75/#77/#78/#79/#84 保持开放。

## 工作区与提交约束

文档分支 `codex/diagnosis-contract-docs` 位于 `D:/code/CNN/.claude/worktrees/diagnosis-contract-docs`，稳定族契约首提交 `7ea21cd`。API/OpenAPI/前端与最终交接另按逻辑提交，由主控串行集成；不单独开重复 PR 或 GitHub 评论。

旧 `refactor-diagnosis-cloud-numeric` 中的 5 个已修改和 9 个未跟踪 Markdown 已只读盘点：其中有效的幅值归一化、STFT 轴、倒谱秒/ms、先截断后慢去噪、counts 与完整数组语义已收敛到现有模块契约。原工作区文件完整保留；`refactor-docs-module-contracts` 也不清理。

Python 仅用 uv。MSVC 命令遵守 `vsdev`。本轮文档只运行集中 Markdown 链接/结构检查，不重复算法/业务测试；源码最终集成仍按任务验证证据交付。
