# 诊断性能基准运行与原生接口契约

本页记录 #106 的 Python/原生 EMD 族验收契约，并保留 #79 广义诊断基准的运行说明。两套入口独立，不能混用内存或计时口径。测量结果、JSON/CSV、日志、波形、profile 与数值比较表保存在显式数据根，不提交仓库。数据来源与物理前提见 [datasets](../datasets.md)，通用替换准入规则见 [ADR 0005](../adr/0005-diagnosis-native-benchmark-gate.md)。本页不声明尚未完成的双平台收益或目标 ECS 资源验收结果。

## #106 原生 EMD 双平台验收

入口为 [native_performance.py](../../cloud/tests/diagnosis/benchmarks/native_performance.py)，事前冻结参数与准入规则为 [native_performance_config.json](../../cloud/tests/diagnosis/benchmarks/native_performance_config.json)（冻结提交 `a26fdf3`）。这里只比较项目同公式 Python 与显式原生候选，不引入 PyEMD 参照，不修改生产默认后端。

固定矩阵为五条既有 4096 点向量 × `controlled`/`production` 两档 × EMD/EEMD/CEEMDAN，共 30 项。向量 SHA256、原采样率与旧 campaign 相同；两档分别采用 4/8 个 IMF、50/100 次筛分上限、8/50 次 ensemble，种子为 `20261112`。性能矩阵固定 PCHIP/SD、镜像数 3、SD 阈值 0.2 和噪声尺度 0.2。cubic/Rilling 已由原生候选支持，但其四配置正确性由 `test_native_emd.py` 单独覆盖，不把这 30 项称为四配置性能矩阵。

每个 case 依次执行三个完整计时块：A/B、B/A、A/B，其中 A=Python、B=native。每个后端每块使用全新 worker，预热一次、测量五次；每个后端共 15 个原始样本，按全部 15 次取中位数和线性插值 P95。Windows 和 WSL 必须执行完整 30 项；只有 ECS 模式允许用重复的 `--case` 指定资源验收子集，子集结果不能代表完整矩阵。

| 阶段 | 行为与证据 |
|---|---|
| `prepare` | 从显式 `--source-cache` 复制已有向量并核验 dtype、形状、fs 和 SHA256；创建全新的 `--output`，保存配置、数值契约、用例、源码/扩展哈希、依赖、CPU 与真实构建信息 |
| `check` | 独立 worker 内各后端重复计算，要求同后端数组完全相同；核对跨后端冻结数组预算、模态/残差、迭代、收敛、有效区间、元数据及下游选择/质量状态；数组写入 `check_arrays/` |
| `measure` | 已选 case 的 check 均须有结果，等价失败项排除并保留失败证据；通过项执行全部三个 AB/BA/AB 块，保存逐次耗时、OS 峰值、准备复制和输入/输出规模 |
| `profile` | 各后端另启独立 worker，保存前 40 项 cProfile 热点；其耗时和内存不参与成本门槛 |
| `report` | 核对身份、完整块/样本与已验证元数据，输出 `comparison.json`、CSV 和 Markdown；缺项、失败、噪声或峰值回归均不能形成成本通过结论 |

源码、配置、扩展或环境身份变化必须新建 campaign。重复执行阶段只复用身份一致的已完成 worker，并继续从未启动项；`.started` 已存在而没有结果的中断项禁止覆盖，不能挑快的样本重测。完整比较必须保留全部三块；噪声过大时保留 `inconclusive`，不放宽门槛或删样本。

### Windows 运行

先在仓库根通过显式 Git Bash 的 `vsdev uv sync --frozen --group benchmark` 完成源码构建；构建与测量分开。以下 PowerShell 在 `cloud/` 执行，输出目录每个平台、ISA 和 campaign 独立，使用已安装扩展，避免测量期间同步重建：

```powershell
$sourceCache='D:/code/CNN/data/real_diagnosis/performance/20261112'
$campaign='D:/code/CNN/data/real_diagnosis/native_performance/windows-baseline-20261112'
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance prepare --mode windows --source-cache $sourceCache --output $campaign
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance check --output $campaign
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance measure --output $campaign
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance profile --output $campaign
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance report --output $campaign
```

### Ubuntu/WSL 与目标 ECS

Linux 构建入口为 [native_benchmark_build.sh](../../scripts/native_benchmark_build.sh)，参数为 `SOURCE ARTIFACTS wsl|ecs`。它在独立 systemd transient service/cgroup 中用 `uv sync --frozen` 从源码构建，固定 GCC/G++、baseline ISA、Ninja 单任务；环境、uv 缓存、CMake build 与日志都在显式 ARTIFACTS 中。运行需要可创建 systemd 系统 transient service 的权限以及 cgroup v2；不能把普通 `taskset` 或未读回的环境变量当作资源限制。

构建与测量采用不同目录和阶段。Linux 的 `check`、`measure`、`profile` 会为每个 worker 自行创建受限 transient service，读回 `memory.max`、`memory.swap.max`、`cpu.max`、有效 CPU 与事件计数。`--mode` 只在 `prepare` 指定并写入 campaign，后续读取该快照。以下命令在独立 Linux 源码归档上运行，不共享 Windows `.venv` 或构建目录；归档需要包含根构建/锁文件、native、Python 算法与基准代码、`emd_reference_contract.py` 及源码身份清单。

```bash
source_root=/root/cnn106/source
artifact_root=/root/cnn106/build-wsl
campaign=/root/cnn106/data/native-performance-wsl
source_cache=/root/cnn106/data/real_diagnosis/performance/20261112
bash "$source_root/scripts/native_benchmark_build.sh" "$source_root" "$artifact_root" wsl
export UV_PROJECT_ENVIRONMENT="$artifact_root/env"
cd "$source_root/cloud"
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance prepare --mode wsl --source-cache "$source_cache" --output "$campaign"
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance check --output "$campaign"
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance measure --output "$campaign"
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance profile --output "$campaign"
uv run --no-sync python -m tests.diagnosis.benchmarks.native_performance report --output "$campaign"
```

目标 ECS 使用独立 source、ARTIFACTS 和 campaign，将构建脚本最后参数及 `prepare --mode` 都换为 `ecs`。如只验证指定资源子集，后续四阶段统一附加相同 `--case <case-id>`，例如 `synthetic__short__production__ceemdan`；记录实际选集与未覆盖项。WSL 证据不能代替目标 ECS 整机证据。

| 限制 | Windows | WSL/Linux 本地 | 目标 ECS |
|---|---|---|---|
| CPU | 逻辑 CPU 0、2 | 逻辑 CPU 0、2；CPUQuota=200% | 逻辑 CPU 0、1；CPUQuota=200% |
| 构建 | MSVC/vsdev，独立于计时 | 2 GiB MemoryMax，单任务构建 | 768 MiB MemoryMax，单任务构建 |
| 每个验收 worker | 2 GiB Job 总提交内存上限 | 2 GiB MemoryMax | 512 MiB MemoryMax |
| swap | Job 限制不等于物理 RAM 上限 | MemorySwapMax=0 | MemorySwapMax=0 |
| 启动前余量 | 记录宿主背景活动 | 记录宿主背景活动 | MemAvailable 至少为对应构建/worker 上限加 256 MiB，否则不启动 |

所有数值线程变量在 worker 导入前固定为 1。生产继续保持线程池 `max_workers=2`、`ANALYSIS_SEM=1`；工具不改 `CNN.service`、不部署。ECS 模式以 1 秒间隔记录全机 MemAvailable、swap、CPU 时间及现有 `CNN.service` cgroup 状态，阶段结束另读服务状态。这些是余量观察，不冒称全机真实内存峰。构建日志分别保存 GNU time 与 cgroup 资源证据；GNU time 单进程/子进程高水位不能当作构建进程组聚合峰值。目标权限、构建或整体服务余量证据不可取得时，明确保留未完成验收。

### 冻结的成本、质量和热点口径

计时覆盖完整公开 EMD 族调用，包括 Python 外层多 IMF、RNG、ensemble 聚合及调用内必要转换与输出所有权；排除导入、向量 I/O、预热、指标汇总和 profile。缓存加载后的连续化准备单独记录 `preparation_copy_bytes` 和输入 bytes，输出按数组 `nbytes` 记录。合规连续 float64 在边界借用，单 IMF 内部仍有工作副本；源码推导的线性 scratch 包络与实测数组载荷分开报告，不能声称测得了全部 native malloc 或用它替代 RSS。

每个计时 worker 的 OS RSS 高水位在最后一次调用后、任何指标序列化之前读取：Windows 为 `PeakWorkingSetSize`，Linux 为 `getrusage(RUSAGE_SELF).ru_maxrss`（KiB 转 bytes）。从新 worker 启动开始累计，包含真实导入、输入、预热和输出生命周期；Python 基线不强制导入原生扩展。每后端取三个 worker 峰值的最大值，要求 native 不大于 Python，零容差、不按 MiB 四舍五入。导入后 RSS 与峰值增量仅作诊断；Linux cgroup `memory.peak`（内核支持时）及事件另存，与进程 RSS、Windows Job 提交内存各有边界。独立 check 的质量指标与 profile 不污染计时 worker 峰值；这与下述 #79 旧峰口径不同。

生产档 CEEMDAN 要求 native/Python 中位数比值 ≤0.5；所有 EMD/EEMD 档要求 ≤1.05；受控档 CEEMDAN 时间只报告。每个五样本 worker 的 `1.4826 × MAD / median` 必须 ≤0.05，同后端三个块中位数的 `(max−min)/median` 必须 ≤0.10，任一超出则为 `inconclusive`。15 点 P95 只描述本次样本，不是生产 SLO。

`equivalence_pass` 表示同公式数值与元数据/质量状态一致；`quality_eligible` 与 `diagnosis_evaluable` 另行记录分量质量和可评估性。双方都返回不可用状态仍可能等价，不能因此宣称诊断可用。`local_cost_gate` 仅判断本 campaign 的冻结计算成本；总体采用仍需双平台完整矩阵、质量证据及目标 ECS 源码构建/服务余量，工具保持 `adoption=candidate`，不自动切换默认。等价失败项不得借重构完备性或计时完成豁免。

环境证据保存 CPU、编译器、编译选项、实际 SIMD 与扩展哈希。cProfile 仅看到 C++ binding 的整体调用，不能单独证明其内部各助手的 SIMD 覆盖或融合收益；此类结论应补充独立 native profile/编译证据，原始材料仍留数据根。未测量的候选不写收益，未满足门槛则保留候选和具体原因。

## #79 广义诊断基准运行（旧入口）

旧 `run.py` 是独立离线入口，不访问数据库，不修改生产实现，仍只支持 Windows。它保留 #79 的广义算法比较，与 #106 `native_performance.py` 分开运行和导出。Python 依赖仅由 uv 管理；EMD-signal 与 psutil 位于可选 `benchmark` group，不是生产默认依赖。

在 `cloud/` 中运行，将示例替换为主仓或其他共享原始数据根：

```bash
uv sync --group benchmark
uv run --group benchmark python -m tests.diagnosis.benchmarks.run --data-root /path/to/data
uv run --group benchmark python -m tests.diagnosis.benchmarks.export --input /path/to/data/real_diagnosis/performance/20261112
```

精确参数来自 [config.json](../../cloud/tests/diagnosis/benchmarks/config.json)，入口为 [run.py](../../cloud/tests/diagnosis/benchmarks/run.py)，可选参照为 [pyemd_adapter.py](../../cloud/tests/diagnosis/benchmarks/pyemd_adapter.py)，结果导出为 [export.py](../../cloud/tests/diagnosis/benchmarks/export.py)。修改 frozen config 后必须使用独立 `--output` 保存新 campaign，不能混入旧向量/结果。

数据根按显式 `--data-root`、`CNN_DATA_ROOT`、当前 checkout 的 `data/` 解析。默认 campaign 输出在 `DATA_ROOT/real_diagnosis/performance/20261112/`，可用 `--output` 覆盖；导出默认在该 campaign 的 `export/` 下。始终把输出指向仓库外数据目录，不提交生成结果。失败时用 `--resume --case <case-id>` 只继续目标 case，复用已缓存向量与参数，不重复已完成项。

文件分工：`vectors.json` 保存来源和 float64 字节 SHA256，`vectors/*.npy` 是固定输入，`config.json` 是参数快照，`cases.json` 是矩阵，`cases/*.json` 保存逐次计时、状态、收敛和真实内存峰，`environment.json` 保存环境，`results.json` 汇总，导出目录提供精简 JSON/CSV。源文件 SHA256 来自原采集清单；worker 每次校验缓存向量 SHA256，原始材料验收与算法计时分开。

## #79 固定矩阵

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

## #79 计时、内存与正确性口径

本节仅适用于旧 `run.py`：它要求 Windows，操作系统不满足时明确失败。每项独立进程固定 config 中的两颗逻辑 CPU；Windows Job Object 限制整个 worker 进程组的总提交内存并读回验证。OMP/OpenBLAS/MKL/NumExpr 线程环境在导入数值库前固定。逻辑 CPU 亲和不等于独占物理核心；宿主背景活动要随 campaign 说明。

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

本节保留 #79/#106 的历史接口草案，下表名称不代表现行 ABI。EMD 首批按 [ADR 0006](../adr/0006-native-diagnosis-compute-package.md) 实现 C++ 单 IMF 筛分；#106 仍显式选用 Python 外层、NumPy 噪声与原生筛分，不随业务默认改变。

2026-11-14 云端默认已迁移到 [完整原生业务 EMD](../algorithms/decomposition/native_business_emd.md)，支持 PCHIP/cubic × SD/Rilling 的完整 EMD/EEMD/Torres CEEMDAN。随机生成也在 C++，同种子不保证旧 NumPy 数组相同，因此独立测量脚本为 `scripts/benchmark_emd_family.py`，不能套用 #106 的同噪声逐数组门槛。原生数学公式使用独立同噪声组合核验，确定性 EMD 和局部筛分继续保持原 [冻结预算](../../cloud/tests/diagnosis/benchmarks/native_emd_contract.json)。构建验证、本地成本与生产 ECS 资源验收分别记录；既有固定输入清单保留，不提交生成数组或数值报告。

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
