# 诊断算法重构交接（2026-11-11）

## 1. 当前状态与暂停点

本轮按用户要求在 **#73 最新秩亏修复提交后暂停**。不要假设 #73 已通过复验，不要直接合并共享集成分支，不要自动开始后续 Issue。

当前刚完成：

- #73 MED/MCKD 数值秩亏修复已提交：`0ad81f34213df1a63ef87c1af775f3229a85ea91`。
- 该提交仅在 #73 任务分支，**尚未 merge 到共享集成分支，尚未由唯一 review 复验**。
- 实现代理报告高级轴承专项 38 项、包络 25 项、P0 三件及独立秩亏/正则化探针通过；这些是实现证据，不替代独立数学复验。
- 当前没有必须继续运行的代理任务。恢复后先处理 #73 该提交的集成与复验，然后暂停时的其他队列保持不变。

## 2. 已合并到 main

| PR | 内容 | Merge commit |
|---|---|---|
| #68 | 标准轴承包络算法、分析、评估与前端垂直切片 | `7dfb39d38928bd610e19ddc54ab3ca54a09b8e3c` |
| #69 | 转速、连续相位与阶次分析 Pipeline | `e967dc8dde11e330410dc19ccffe6e26965d793c` |
| #81 | 云端 FFT/STFT/统计/倒谱、Monitor、DC24 数值路径 | `fe9e52ad54f32d6f261cfc898913d21346a1299d` |
| #82 | 模块化契约文档体系 | `98b8cdb7ef6e28a7d7b7959c2844507aaf550b9a` |
| #85 | 定轴齿轮对象化 Pipeline、业务门控与统一状态展示 | `88ba6efd5740d18c07b87074f08116036e71f937` |

**Issue #71 已随 PR #85 关闭，并已追加关闭评论。** 定轴剩余领域状态拆分和文档分别转 #84、#80，不再属于 #71。

## 3. 已确认的设计与验证共识

- 新建纯计算 `cloud/app/algorithms/`，通用算法只保留一份，业务层调用 Pipeline。
- 高层 Pipeline 按机械对象组织：轴承、定轴齿轮、行星齿轮；不同工况和方法前提不能硬塞同一流程。
- 算法负责计算表示，分析 Pipeline 提取指标，诊断 Pipeline 内调分析 Pipeline 并评估；已有指标可直接重评。
- 显式检查恒速/变速、连续相位、机械参数、历史基线等前提。失败、未知、不可评估不等于健康，也不等于故障；禁止默认 10 Hz 或失败返回 normal。
- 第三方可替换算法保留算法族专属 adapter seam；FFT 直接用 NumPy/SciPy，不做无意义转发封装。
- 参数和结果使用 dataclass、NumPy 数组和明确单位，避免无意义复制及 `ndarray ↔ list` 转换。
- 实验性只属于具体组合流程，不建实验目录或集中注册表；底层算法在正常模块复用。
- 旧实现和旧测试不是正确性基准。按论文、数学定义、参考实现和已知合成信号验证；新 Pipeline 接管后删除旧重复实现。
- **测试通过不代表算法正确。** 算法工作重心是公式、单位、物理前提、手算已知解、独立参考、物理真值合成信号、负对照和反例。自动化测试主要保护业务编排、接口、状态和回归；算法侧已知答案断言只是可执行证据。
- review 报告先说明数学/物理依据、前提和无法证明的限制，再列测试结果；禁止用“多少项全绿”代替算法正确性判断。
- 性能优化、换库和 Rust/C++ 重写后置。`EMD-signal/PyEMD` 仅作为后续移植参照，当前 EMD 是自研实现。

## 4. GitHub Issue 地图

父工单：**#70 诊断算法库与对象化 Pipeline 路线图**  
https://github.com/lx827/CNN/issues/70

| Issue | 内容 | 当前状态 |
|---|---|---|
| #71 | 定轴齿轮 | **已完成，PR #85 已合并，Issue 已关闭** |
| #72 | 行星齿轮 | 未开始 |
| #73 | 高级轴承 | 多轮算法返修中；最新秩亏修复已提交但未集成、未复验；业务接入未开始 |
| #74 | 小波与模态分解 | 已实现并提交，未独立 review、未开 PR |
| #75 | VMD AM-FM 与实验复合流程 | 未开始，依赖相关对象 Pipeline 与 #74 |
| #76 | 云端数值路径 | PR #81 已合并；`rule_based` 统一接入未完成，Issue 开放 |
| #77 | 集成评估与业务编排 | 未开始 |
| #78 | 真实数据集效果基线 | 未开始 |
| #79 | 性能与 Rust/C++ 移植准备 | 未开始 |
| #80 | 模块化文档 | PR #82 已合并；#71/#73/#74 补充与文档 review 未定稿，Issue 开放 |
| #84 | 分离评估状态与诊断结论、统一状态契约 | 新建，关联 #77；不阻塞 #71，尚未开始 |

#84：https://github.com/lx827/CNN/issues/84

**Issue 只追加评论，不反复编辑正文。** 继续 #73 前必须阅读其最新评论。

## 5. 当前分支和提交

### 共享集成分支（不要直接推送或合并到 main）

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-diagnosis-integration`
- 分支：`refactor/diagnosis-integration`
- HEAD：`d3eb8990b84abe6cf2c9f4ccf91268b4c329687f`
- 已同步 `origin/main` 到 PR #85（同步 merge：`b8f8f2a996e14f8db5ce1e23145b9c40967040d5`）。
- 已包含 #71、#73 到提交 `1eae28e`、#74、#76 及文档基线。
- **不包含 #73 最新提交 `0ad81f34213df1a63ef87c1af775f3229a85ea91`。**
- 最近集成无冲突，相关专项、包络、定轴、阶次和 P0 回归通过。
- 未推送、未开 PR、未合并到 main；最后报告工作区干净。

### #73 高级轴承

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-diagnosis-bearing-advanced`
- 分支：`refactor/diagnosis-bearing-advanced`
- 原始提交：`6a02d977fdb8e0c19d7add94ad835a1165a30dc3`
- 第一轮数值返修：`1eae28e9da49356a1e0f50da722212a58408085a`
- 最新秩亏返修：`0ad81f34213df1a63ef87c1af775f3229a85ea91`
- 最后报告工作区干净，无文档或业务接入改动。

内容：谱峭度、MED/MCKD、CPW、TEO、SC/SCoh 纯算法和独立评估。Engine/ensemble/API/前端接入按并行计划有意留到算法审查通过后。

#### 已完成的数学审查与返修

1. 谱峭度使用复高斯背景基准 `E|z|^4/(E|z|^2)^2-2`，实现为明确命名的二叉 IIR 滤波器组，不冒充 Fast Kurtogram；重加权分数和固定阈值仍是工程启发式。
2. MED/MCKD 的孤立冲击与周期相关峭度目标分离，MCKD 留一乘积、延迟输入和 `E/(2B)` 因子经手算和有限差分核对。
3. CPW 仅在调用方明确提供稳定梳状频率时运行；稳定性由调用方前提保证，算法不自动识别滑频。
4. TEO 离散公式、原始负值与多分量交叉项保留；只有 Hilbert 包络输入执行明确标记的工程截负。
5. SC/SCoh 的频移交叉乘积、循环/载波频率轴和专属评估主体核对通过；候选搜索只是理论频率附近局部网格，不是未知循环频率全轴发现。
6. 第一轮修复已处理 SC/SCoh、谱峭度、CPW 的绝对数值下限与幅值尺度问题，非法/超频带候选路由，MED/MCKD 小信号提前停止及 TEO 零能量；这些已经唯一 review 复验通过。

#### 最新秩亏修复（待复验）

反例：`fs=1000`、50 Hz 单谐波 1024 点、`filter_length=16`、`ridge=0`。卷积正规方程秩约为 3/16，普通 `np.linalg.solve` 可能返回有限但不可靠解而不抛异常；旧实现会误报 `computed`，MCKD 甚至可能误报收敛。

最新提交改为：

- 对卷积矩阵 `X` 使用 SVD 直接求解，避免正规方程平方条件数。
- 数值秩标准为 `sigma > eps * max(X.shape) * sigma_max`，不是任意条件数阈值。
- `ridge=0` 且数值列秩不足时，Pipeline 返回 `indeterminate/numerical_deconvolution_failure`、`representation=None`。
- `ridge>0` 时保留明确的 Tikhonov 正则化解，不因原矩阵秩亏而拒绝。
- 实现代理报告单谐波无正则 MED/MCKD 均明确失败，`ridge=1e-8` 可计算，满秩周期冲击对照保持可计算。

恢复后必须由同一个 #73 review 独立检查该求解变换、秩判据、尺度不变性、有效正则化和正常信号，不仅查看新增测试。

### #74 小波与模态分解

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-diagnosis-decomposition`
- 分支：`refactor/diagnosis-decomposition`
- 提交：`d2adc221fc1091b9eb9301f787b7e29eba707c8f`
- 内容：DWT/WP、EMD/EEMD/CEEMDAN、VMD、敏感分量原始指标和 adapter。
- 原实现报告 4 个测试文件 17 项专项通过；已在共享集成分支，但尚未独立 review、未开 PR。
- 后续旧实现接入时需处理既存 `test_emd_denoise.py` 导入不存在的 `_excess_kurtosis`，不能把它算作已通过测试。

### #71 定轴齿轮（已合并，保留现场）

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-diagnosis-fixed-axis-gear`
- 分支：`refactor/diagnosis-fixed-axis-gear`
- 最终任务提交：`e75797819ff131b3a40b80e3010275bd3bd135f6`
- PR #85 已合并，Issue #71 已关闭。
- 统一前端 `diagnosisStatus.js` 已接入 Research、DiagnosisDetail、ComprehensiveSection；未知状态中性兜底。
- 领域状态两维拆分不属于该切片，转 #84。

### #76 云端数值

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-diagnosis-cloud-numeric`
- 分支：`refactor/diagnosis-cloud-numeric`
- 提交：`b7b13042adbe15f3dfd6289fdea1f9fa7f3db530`
- 已通过 PR #81 合并；`rule_based` 统一接入留待后续。

### #80 文档

- 工作区：`D:\code\CNN\.claude\worktrees\refactor-docs-module-contracts`
- 分支：`refactor/docs-module-contracts`
- 提交：`b7a4d1bff28c25c86117c696fe4967f450abf61e`
- 已通过 PR #82 合并。
- #71/#73/#74 的算法文档补充及文档 review 尚未定稿。

**保留所有工作区和分支，不要清理。** 后续集成、复验和返修仍需要使用。

## 6. 协作约束

- 主会话只分派任务和协调分支/PR；除非用户明确要求，不亲自补代码或代替代理跑测试。本次 HANDOFF 由用户明确要求主会话直接重写。
- 使用普通子代理，不指定模型或推理强度，尽量不 fork。
- 每条切片最多一个 review 子代理，串行执行；review 必须实际运行测试、检查退出码和日志中的 `[FAIL]`，但首先要做算法数学/物理审查。
- 实现子代理可提交代码和测试；提交不默认包含文档。
- 共享集成分支由单一集成代理串行 merge 各任务分支，提前发现冲突。
- **禁止 rebase。** 分支同步只用 merge。
- 用户已授权在验证通过后直接开 PR 并 merge，不必等待人工批准；暂停恢复后仍需按该流程完成当前切片，不直接合并共享集成分支。
- 实现代理停止扩写文档；主会话不阅读或判断文档，文档代理负责保留、迁移或删除。
- Issue 进度和验收结果只追加评论。
- 完成当前 review/返修后再开新任务；不要直接开始 #72 等后续算法。

## 7. 恢复后的执行顺序

1. 阅读 #73 最新评论，将 #73 提交 `0ad81f34213df1a63ef87c1af775f3229a85ea91` 用 merge commit 集成到共享分支。
2. 由同一个 #73 review 复验秩亏反例、SVD 求解、数值秩标准、正则化、尺度不变性及此前全部反例。
3. 若算法阶段通过，再单独实施 #73 的 Engine/ensemble/研究 API/前端接入，替换旧重复实现，并进行完整业务 review；通过后才开 PR 合并。
4. 若仍有问题，记录精确反例并返修，不进入业务接入。
5. 串行完成 #74 独立算法 review、必要返修、旧实现接入和完整复验。
6. 后续同步共享分支与最新 main，处理 #76 的 `rule_based` 残余和 #80 文档。
7. 完成当前阶段后再评估 #72、#77/#84 等，不提前扩大范围。

## 8. 验证限制和已知遗留

- 本机缺少 HUSTbear、CW、WTgearbox、HUSTgearbox 等真实数据集，真实诊断效果**未验证**。
- 多个旧测试脚本即使打印 `[FAIL]` 或找不到数据也可能退出 0，必须同时检查退出码和日志，不能只看命令成功。
- 真实数据脚本报告 0 文件时，不得记为通过。
- 算法测试全绿不证明公式、阈值、分类、健康评分或真实工况效果正确；review 必须明确数学依据与未验证限制。
- `test_emd_denoise.py` 的旧 `_excess_kurtosis` 导入待 #74 集成处理。
- `rule_based` 的统一接入未完成。
- `/order` 等残余路径的截断/去噪顺序需在后续统一核对。
- 前端诊断状态展示已统一 adapter，但 `evaluation_status` 与 `diagnosis_conclusion` 的后端领域拆分由 #84 完成。
- 性能、耗时、峰值内存和原生移植均未开始；生产为 2 核 2G，遵守现有线程池和串行分析限制。

## 9. 常用命令和约束

- Python 只允许 `uv run` / `uv sync` / `uv add` / `uv lock`，禁止 pip、conda、手工 venv。
- 修改算法后至少运行 P0 三件：
  - `uv run python tests/diagnosis/regression/test_none_params.py`
  - `uv run python tests/diagnosis/regression/test_cpw_robustness.py`
  - `uv run python tests/diagnosis/regression/test_varying_speed_order.py`
- 新任务从最新 `origin/main` 创建独立 worktree 和任务分支。
- 合并 PR 使用 merge commit：`gh pr merge <number> --merge`。
- 主仓检出可能落后于 `origin/main`，以远端和各任务 worktree 为准。
