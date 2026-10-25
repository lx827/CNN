# CQU × O9 二分类训练入口

第三步已实现两个设备任务的二分类适配、单次训练入口、记录级验证、保存与恢复。数据与三折规则见[数据准备说明](README.md)，项目流程见[工作日志](../../docs/CQU_O9_WORK_LOG.md)。本模块不接入生产诊断，不自动开展完整候选比较。

本页描述“O9编码器＋新二分类头”的简化迁移对照，不是完整O9训练。后续经用户确认实施的重构、原型库、双分支约束及域训练见[完整O9适配](FULL_TRAINING.md)，两个入口与检查点格式独立，验证结论不可混用。

## 已确认的模型与训练目标

用户于2026-10-25确认：保留固定O9编码器，取故障分支`z_f`，沿时间维平均后接`Linear(64,2)`分类头，只使用未加权交叉熵。输入`[B,1,4096]`，输出`[B,2]`未归一化分数；不使用旧重构、原型或域对抗损失。旧设备投影分支保留以严格加载编码器，但冻结且不参与优化；共享主干、故障投影和新分类头从首步共同训练。

| 实验 | 类别0 | 类别1 | 通道 |
|---|---|---|---|
| `device1_ch2` | normal | imbalance | CH2主实验 |
| `device1_ch1` | normal | imbalance | CH1独立对照 |
| `device2_ch3` | normal | outer_race | CH3主实验 |

每个实验建立独立模型，设备编号不作为分类输入。旧五类没有不平衡，不把旧标签硬映射成新任务。模型使用故障分支确定性输出，验证时`eval()`关闭Dropout，不进行VAE采样。Softmax输出作为分类分数，未完成概率校准。

四种初始化为`scratch`、`epoch55`、`stage2`、`stage3`。从零只指CQU任务编码器及新头随机初始化，不重新跑四个历史源数据集。微调先对完整旧模型严格加载80个张量并检查有限值，然后完整严格复制编码器；仅参数形状兼容不能证明历史运行的函数行为被完全复现。新头统一使用相同种子初始化，旧优化器、调度器和旧epoch不恢复。

微调默认使用旧检查点的`ema`参数，这是用户确认的首轮来源；`--parameters model`可显式选择普通参数，但本轮正式对照不自动扩大到该组。它只改变初始化来源，新CQU训练不另维护EMA。旧检查点的期望轮次分别55、60、100，域数63、旧类别数5；与候选不符即报错，不使用`strict=False`掩盖差异。

## 单次训练规则

每次必须明确实验、折编号、初始化和总轮数。使用同一准备缓存中8份训练文件/480窗口、6份验证文件/360窗口；本入口拒绝加载外层`test`或历史分区进行训练/选优。所有三档转速和两类均已在文件清单中覆盖，窗口不再随机跨集合划分。

默认批量8，AdamW主干学习率`1e-4`、分类头`1e-3`、权重衰减`1e-4`，全局梯度范数裁剪1，固定种子42；这些是起始工程配置，尚未通过正式实验选择。未使用类别重加权、增强、调度器、自动早停或AMP。CPU计算线程2、DataLoader工作进程0、不丢弃尾批，避免Windows多进程启动问题；不更改后端线程池。设备由`--device cpu/cuda`显式指定，CUDA不可用时报错，不静默切换硬件。

验证完整读取6份记录的全部窗口，每份以60个窗口故障分数的均值作为记录分数，阈值固定0.5。混淆矩阵行是真实类别、列是预测类别；保存正常误报、故障漏报、转速和采集阶段。按验证记录级平衡准确率最大选优，同分时按验证窗口交叉熵更小选优。不在外层留出、历史数据或其他折的留出成绩上挑权重或参数。所有结果仍属于当前采集内开发证据。

`--max-train-batches`限制每轮训练批次，存在该参数时输出一律标记`smoke_only: true`，即使指定的上限碰巧覆盖整轮也不当正式实验。短程验证分数只用于检查计算和选优流程，不能据此宣布候选优劣或系统识别率。正式比较应从各自原始初始化重新开始，不从本轮短程权重继续计算正式预算。

## 保存、恢复与可追溯记录

所有输出必须写入仓库`tmp/cqu/`下尚不存在的新目录；旧运行、原始信号和旧权重不覆盖。输出包括：

- `run.json`：北京时间、完整配置、类别、数据协议、训练/验证文件身份、初始化及源哈希、代码哈希、固定O9来源、Git HEAD、软件与硬件信息。
- `metrics.jsonl`：逐轮损失、实际训练批次/窗口、累计优化步数、验证指标、最佳轮次及短程标记。
- `validation_epochNNN.json`：每份验证记录的60个窗口分数、记录均值、标签/预测、转速、采集阶段和混淆矩阵。
- `last.pt`、`best.pt`：CQU模型、优化器、轮次、累计步数、最佳指标、随机及洗牌状态、数据和模型协议。
- `summary.json`：仅成功完成请求预算时写出，包含短程状态和CUDA峰值张量分配量。它不是整机显存占用或部署内存需求。

恢复使用`--resume`加载本项目新任务检查点，不能与旧参数初始化`--checkpoint`同时指定。`--epochs`表示恢复后希望达到的总轮数，必须大于已完成轮数；实验、折、初始化名称、种子、批量、学习率等保持一致，缓存身份及协议也必须一致。恢复在新目录继续写日志，原有历史保留；若没有新的最佳结果，新目录不会重复生成`best.pt`，`summary.json`中的`best_checkpoint_path`指向先前最佳文件，须保留前次运行目录。只验证了同环境CPU恢复与连续训练逐参数完全一致，跨硬件结果不保证位级相同。

异常会明确报错且没有成功摘要，已生成的阶段日志保留用于排查。运行记录中的Git HEAD是执行时已提交的版本，若当时有未提交代码，以同时保存的各源码哈希补充追溯。

## 文件与公共接口

| 模块 | 接口 | 作用 |
|---|---|---|
| `binary.py` | `O9BinaryClassifier()`、`forward(x) -> Tensor` | O9故障分支均值池化与独立二分类头 |
| `binary.py` | `build_classifier(initialization, checkpoint=None, parameters='ema', seed=42) -> (model, metadata)` | 新初始化及完整严格校验旧权重；返回来源信息 |
| `binary.py` | `INITIALIZATIONS`、`MODEL_PROTOCOL` | 候选轮次与本轮模型协议 |
| `train.py` | `TrainConfig(experiment, fold, initialization, epochs, ...)` | 不可变单次运行配置，其余默认值见本节 |
| `train.py` | `WindowDataset(prepared, experiment, fold, split)` | 只接受train/validation，校验文件及60窗口覆盖，返回`(x,label,index)` |
| `train.py` | `seed_training(seed) -> None` | 固定随机性、确定性算法及本进程线程数 |
| `train.py` | `evaluate_validation(model, dataset, batch_size, device) -> dict` | 完整记录级汇总，返回损失、逐记录分数与混淆矩阵 |
| `train.py` | `train(prepared, output, config, checkpoint=None, resume=None) -> dict` | 执行显式预算并返回成功摘要 |
| `train.py` | `main() -> None` | 命令行入口，导入模块不启动训练 |

## 本机命令示例

训练同时依赖[数据准备的NumPy/SciPy](requirements.txt)和[模型的PyTorch](../o9/requirements.txt)，本机cloud虚拟环境已具备，未安装或升级依赖。

以下命令在本机Windows PowerShell、仓库根目录`E:/A-codehub/CNN`执行，读取现有准备缓存。它们各自启动子PowerShell，`-NoProfile`跳过用户配置、`-ExecutionPolicy Bypass`仅允许该子进程运行环境激活脚本；点号激活cloud环境；`-X utf8`固定Python编码、`-m`执行模块，`exit`传播退出状态。不需管理员、不联网、不安装依赖，只新建指定本机忽略目录。输出目录示例须尚不存在。

```powershell
# 从零做设备1 CH2、折0的短程检查：总1轮、每批8窗、最多2批，在CUDA运行；不是正式识别率实验。
powershell -NoProfile -ExecutionPolicy Bypass -Command '. ./cloud/venv/Scripts/Activate.ps1; python -X utf8 -m training.cqu.train --prepared tmp/cqu/o9_data_prep_20261025/prepared_v2 --output tmp/cqu/example_scratch --experiment device1_ch2 --fold 0 --init scratch --epochs 1 --batch-size 8 --max-train-batches 2 --device cuda; exit $LASTEXITCODE'

# 用第55轮EMA初始化设备2 CH3；--checkpoint只读旧权重，--parameters明确选EMA，其余同样限制为短程检查。
powershell -NoProfile -ExecutionPolicy Bypass -Command '. ./cloud/venv/Scripts/Activate.ps1; python -X utf8 -m training.cqu.train --prepared tmp/cqu/o9_data_prep_20261025/prepared_v2 --output tmp/cqu/example_epoch55 --experiment device2_ch3 --fold 0 --init epoch55 --checkpoint o9v1/v3/checkpoint_epoch55.pth --parameters ema --epochs 1 --batch-size 8 --max-train-batches 2 --device cuda; exit $LASTEXITCODE'

# 恢复第一条示例的新任务状态到另一个目录；总轮数变为2，保持原批量、种子和每轮2批限制。
powershell -NoProfile -ExecutionPolicy Bypass -Command '. ./cloud/venv/Scripts/Activate.ps1; python -X utf8 -m training.cqu.train --prepared tmp/cqu/o9_data_prep_20261025/prepared_v2 --output tmp/cqu/example_resume --experiment device1_ch2 --fold 0 --init scratch --resume tmp/cqu/example_scratch/last.pt --epochs 2 --batch-size 8 --max-train-batches 2 --device cuda; exit $LASTEXITCODE'
```

成功时日志的累计优化步数应与预算一致，并写出`summary.json`；可通过`run.json`核对任务、通道、文件身份和`smoke_only`。完整训练预算须另行确定，正式运行应去掉短程上限并明确总轮数；移除上限属于新实验，不能偷偷改变现有短程恢复协议。
