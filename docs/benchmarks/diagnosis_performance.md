# 诊断性能基准运行与原生接口契约

本页为 #79 的手写运行说明与接口草案。测量结果、JSON/CSV、日志、波形、profile 与数值比较表保存在显式数据根，不提交仓库。数据来源与物理前提见 [datasets](../datasets.md)，通用替换准入规则见 [ADR 0005](../adr/0005-diagnosis-native-benchmark-gate.md)。

## 运行

基准是独立离线入口，不访问数据库，不修改生产实现。Python 依赖仅由 uv 管理；EMD-signal 与 psutil 位于可选 `benchmark` group，不是生产默认依赖。

在 `cloud/` 中运行，将示例替换为主仓或其他共享原始数据根：

```bash
uv sync --group benchmark
uv run --group benchmark python -m tests.diagnosis.benchmarks.run --data-root /path/to/data
uv run --group benchmark python -m tests.diagnosis.benchmarks.export --input /path/to/data/real_diagnosis/performance/20261112
```

精确参数来自 [config.json](../../cloud/tests/diagnosis/benchmarks/config.json)，入口为 [run.py](../../cloud/tests/diagnosis/benchmarks/run.py)，可选参照为 [pyemd_adapter.py](../../cloud/tests/diagnosis/benchmarks/pyemd_adapter.py)，结果导出为 [export.py](../../cloud/tests/diagnosis/benchmarks/export.py)。修改 frozen config 后必须使用独立 `--output` 保存新 campaign，不能混入旧向量/结果。

数据根按显式 `--data-root`、`CNN_DATA_ROOT`、当前 checkout 的 `data/` 解析。默认 campaign 输出在 `DATA_ROOT/real_diagnosis/performance/20261112/`，可用 `--output` 覆盖；导出默认在该 campaign 的 `export/` 下。始终把输出指向仓库外数据目录，不提交生成结果。失败时用 `--resume --case <case-id>` 只继续目标 case，复用已缓存向量与参数，不重复已完成项。

文件分工：`vectors.json` 保存来源和 float64 字节 SHA256，`vectors/*.npy` 是固定输入，`config.json` 是参数快照，`cases.json` 是矩阵，`cases/*.json` 保存逐次计时、状态、收敛和真实内存峰，`environment.json` 保存环境，`results.json` 汇总，导出目录提供精简 JSON/CSV。源文件 SHA256 来自原采集清单；worker 每次校验缓存向量 SHA256，原始材料验收与算法计时分开。

## 固定矩阵

当前配置选四个公开来源各一条原始采集的单振动轴，以及有已知 30 Hz 真值的合成信号。不拼接不同采集块，不将不同轴当成独立记录，不把 Speed 电压或未知脉冲标定当作 Hz。

| 记录 | 原采样率 | 明确短窗 | 长窗策略 |
|---|---:|---:|---|
| Ottawa `I-A-1` | 200000 Hz | 首 4096 点 | 1 s / 5 s |
| HUSTbear `I_20Hz` | 25600 Hz | 首 4096 点 | 1 s / 5 s |
| HUSTgearbox `B_20_1` | 25600 Hz | 首 4096 点 | 1 s / 5 s 请求，块尾截断 |
| WT `B1_20` | 48000 Hz | 首 4096 点 | 1 s / 5 s |
| 固定种子合成 | 8192 Hz | 首 4096 点 | 1 s / 5 s |

四个真实记录另生成“先取原始 1 秒，再 `resample_poly` 到 8192 Hz”的派生向量，分别保存 fs、点数、派生步骤与哈希。短窗只是明确的计算工作负载，原采样率不变，不能把它解释成完整故障效果窗口。

短窗覆盖 EMD/EEMD/CEEMDAN、三个 PyEMD 参照、VMD、MED、MCKD，以及 CEEMDAN 分解分析→敏感分量→包络→评估组合。长窗与派生 fs 覆盖标量转频、STFT 脊线、SC、MSB、标准完整 Engine。另有合成生产 EMD 参数档、双任务调度实验，以及 bearing/gear 参数齐全且已知 30 Hz 的完整合成 Engine 分支。

合成配置中的轴承/齿轮参数仅属于人为定义试件，不向真实来源补造物理参数。真实信号 MCKD 的固定 40 点周期只是数值核参数，不是 BPFO 真值。完整 Engine 必须报告实际方法、物理前提、分支、对象状态与覆盖；参数缺失分支不能代表参数齐全分支，运行成功也不能替代诊断有效性。

## 计时、内存与正确性口径

当前 harness 要求 Windows，操作系统不满足时明确失败。每项独立进程固定 config 中的两颗逻辑 CPU；Windows Job Object 限制整个 worker 进程组的总提交内存并读回验证。OMP/OpenBLAS/MKL/NumExpr 线程环境在导入数值库前固定。逻辑 CPU 亲和不等于独占物理核心；宿主背景活动要随 campaign 说明。

每项预先设一次预热、五次计时。I/O、导入、预热和指标序列化排除在算法耗时外；profile 为明确额外一次的调用，不混入计时样本。中位数和线性插值 P95 从所有原始样本计算；五次仅支持初步尾部观察，不构成生产 P95 SLO 或稳定置信区间。

RSS 使用操作系统 `PeakWorkingSetSize`，记录独立 worker 全生命周期峰值，同时保存导入后的 RSS 与增量；不把间隔轮询最大值当成真实峰。提交内存上限与 RSS 属于不同计量。峰值包含输入、预热、结果与额外 profile，比较实现时保持此边界一致。

两任务实验分别顺序、两线程、两线程加 Semaphore(1)，报告每次两任务总耗时及任务/s。两线程仅为离线资源比较；生产继续遵守 `max_workers=2`、`ANALYSIS_SEM=1`。进程内存约束不包含 OS、MySQL、Nginx 或其他请求，Windows 两逻辑 CPU/2 GiB Job 实验不能冒称为目标 Ubuntu ECS 全机 2C2G 实测。

结果保留每个算法的状态、残差、目标历史、迭代与收敛。重复数组一致、分解完备性、独立直接 FIR 卷积、已知转频误差、相干量范围是可执行不变量；residual 按差额构造的完备性本身不能证明 IMF 唯一、模态物理正确或诊断效果。近似/未收敛输出保留研究数据，不当成已通过诊断验收。数值 API 未报告的收敛状态记 null，不伪造 True。

基准不覆盖全数据集效果、数据库/HTTP/重新诊断负载、所有方法组合及生产服务器服务总内存。结果详报应逐项声明实际覆盖与未覆盖，再做替换判断。

## EMD-signal 参照语义

适配器只用于基准，显式 `parallel=False`、固定 `noise_seed`，不实现生产默认切换。EEMD 将输入 std 比例换算为库以峰峰值定义的 `noise_width` 并保存换算；不同 RNG 的相同数值种子不保证逐点相同噪声。

PCHIP、镜像数量、IMF/筛分上限可对齐，但 PyEMD 多停止测试不等于仓库 SD/Rilling。PyEMD CEEMDAN 使用局部均值与 `beta_progress=True` 的 improved 形式，与仓库 Torres 2011 形式不同。PyEMD EEMD 返回池可能包含趋势分量，不按列号硬配成等价 IMF；CEEMDAN 最后一行最终残差需从振荡分量分离。报告比较完备性、残差比例、非正交分量能量、频率与峭度指标，并解释差异，不能用逐列误差机械判定哪种方法正确。

官方依据：[v1.9.0 EEMD 文档](https://github.com/laszukdawid/PyEMD/blob/v1.9.0/doc/eemd.rst)、[并行说明](https://github.com/laszukdawid/PyEMD/blob/v1.9.0/doc/speedup.rst)、[EMD 停止实现](https://github.com/laszukdawid/PyEMD/blob/v1.9.0/PyEMD/EMD.py)、[CEEMDAN 实现](https://github.com/laszukdawid/PyEMD/blob/v1.9.0/PyEMD/CEEMDAN.py)。这里 EMD-signal 的导入名为 `PyEMD`，与另一 `emd` 项目分开。

## 原生接口与内存所有权草案

这是后续候选的接口契约，尚未实现 ABI。原生函数粒度以当前 campaign 的热点为准，不先假定 Rust/C++ 或某个库更快。先比较重复分解、固定矩阵求解复用、STFT/FFT 调用次数、数组驻留与窗口顺序，原始证据和采纳决定留在数据根详报。

当前已实现的首个候选是 PCHIP/SD 单 IMF 筛分，经 `NativeEMDImplementation` 显式选择；完整分解 ABI 表仍是后续草案。原生核的包络、单 IMF 和公开 EMD 按既有冻结预算验收，输入准备可能的连续化与原生工作数组需在正式测量中单独核算。[计算库说明](../native_compute.md) 记录实际 Eigen 计算基座、PCHIP 兼容适配与 FP 策略。当前只有正确性与构建验证，没有端到端两倍收益或生产采用结论。

EMD 首批实施已按 [ADR 0006](../adr/0006-native-diagnosis-compute-package.md) 收敛为单 IMF 完整筛分核。当前 Python adapter 通过实例核复用外层算法，仍以 Python 为默认；下表完整分解的原生 ABI 是后续候选，不能视为当前已实现接口。比较前冻结的 [数值契约](../../cloud/tests/diagnosis/benchmarks/native_emd_contract.json) 区分局部与完整分解误差预算；手写对照信号和公开入口断言见 [对照资产](../../cloud/tests/diagnosis/algorithms/emd_reference_contract.py) 与 [筛分替换测试](../../cloud/tests/diagnosis/algorithms/test_emd_sift_contract.py)。既有固定 SHA256 输入和参数身份继续复用，不提交生成数组或数值结果。

| 候选粒度 | 输入与单位 | 输出与工作区 |
|---|---|---|
| `emd_decompose_f64` | 连续 float64、长度、fs Hz、EMD/ensemble 参数、uint64 seed | 行主序 `[mode, sample]`、独立 residual、有效区间、逐模态迭代与收敛；趋势另标 |
| `deconv_prepare_f64` + `deconv_solve_f64` | 归一化规则、FIR 长度、ridge、秩判据；MCKD 周期为点数，目标频率另带 Hz | prepare 拥有固定输入矩阵/分解因子，solve 返回 FIR、目标历史和收敛；上下文只用于同输入/参数 |
| `sc_grid_f64` | 振动、fs Hz、alpha Hz、分段/重叠、显式最大工作区 | 行主序 complex128 SC、float64 coherence、频轴/分辨率/输入尺度；SC 为输入单位²/Hz，相干量无量纲 |
| 转频/阶次候选 | 先复用公共分析；速度 Hz、累计转数、阶次轴各带单位 | 保留不可判定与可靠帧，不回退为假恒速 |

Python 边界检查 dtype、维度、有限值和 C 连续布局。连续 float64 输入只读借用，调用期间保持 Python owner 存活，禁止跨调用保留借用指针或原地修改。非连续切片最多做一次显式 contiguous copy，并将其计入边界输入准备成本；若 API 约定不复制则直接拒绝。先切窗再复制，不悄悄复制整个父记录；有效区间只覆盖实际输入，不补零。

原生结果由单一 owner/capsule 管理。NumPy view 持有 owner，最后一个 view 释放时由原 allocator 销毁；独立短窗不能通过长期 view 挂住整条原记录。scratch 按调用或准备上下文拥有，无共享可写工作区、全局 RNG 或内部线程池，计算继续由既有分析 Semaphore 调度。

跨边界目标：合规输入零次复制，必要转换一次，输出暴露 owner 管理的连续缓冲区且零次额外复制。输入/输出/scratch bytes 与峰值分别报告。超额工作区请求、分配失败、非法参数、非有限输入、数值退化必须有明确状态，不用零数组表示成功。非收敛可携带近似数组与 `non_converged`，诊断门控继续拒绝；异常不跨 FFI 展开。

候选读取同 SHA256 向量，先过既有算法数学与状态检查，再比较完备性、FIR 参考、速度真值、谱指标、随机重复性、有效区间与质量状态。相同公式候选采用事先声明的误差预算，公式不同者单独解释。正确性成立后才比较同参数/线程/窗口成本；目标 Ubuntu 2C2G 的整体服务余量是部署验收条件。未实测候选没有性能结论。
