# 完整 O9 的 CQU 适配与训练

本入口保留O9编码器的设备/故障两分支、解码器、故障原型库、原型组合器和域判别器，用分阶段的多目标训练进行现场适配。[编码器加二分类头](TRAINING.md)保留为简化对照，不能代替完整O9的效果评估。初版只支持短程检查；后续增加完整轮次入口。默认遍历全部训练窗口，只有显式配置`--max-train-batches`才标记`smoke_only: true`。完成训练预算仍不等于完成外层留出评估或证明泛化能力。

当前状态：2026-10-25已完成设备1CH2折0四组实际训练，第五组中途按用户要求停止。36组计划未完成，后续不自动恢复。具体训练量、验证结果和停止位置见[工作日志](../../docs/CQU_O9_WORK_LOG.md)。本文后续“短程验证”的重载结论针对此前12次链路检查，不冒充本轮所有实际训练产物的重新推理审计。

## 用户确认的适配范围

2026-10-25用户明确选择直接继续完整O9适配与短程试运行，并确认以下选择：

- 保留旧五类，新增不平衡。六类顺序固定为`normal / inner_race / outer_race / ball / cage / imbalance`，索引0～5。设备1的二值标签0/1映射到0/5，设备2映射到0/2，不把不平衡映射成其他轴承故障。
- 沿用三个独立设备/通道实验及已固定的整文件三折，分别建立六原型模型，不混合两台数据。每个任务将名义电机200/600/1000rpm定义为三个来源域；它不是实测轴速估计，也不是把三个转速定义为三种故障。
- 从零模型先仅用当前折训练集的正常记录做Stage1，再用该折全部训练记录做Stage2。旧EMA初始化直接开始新的Stage2；不恢复旧优化器/轮数，也不重做源数据集预训练。
- 域对抗按原注释目标修正，主更新中提高来源预测熵，去掉该目标上多余的梯度反转。

微调严格校验完整旧63域/5类模型后，复制编码器、解码器及前五行原型；第六行不平衡原型和整个三域判别器使用新初始化。同种子下，新增参数跨候选一致。候选仍为`scratch / epoch55 / stage2 / stage3`，默认从旧`ema`读取。保留全部六类原型可训练，但当前任务没有另外几类的CQU正例，因此**不保证也未验证旧五类能力不遗忘**；六类输出数量不等于拥有六类现场验证证据。未补入旧源数据，不进行伪标签或原型蒸馏。

## 来源与实际训练行为

模型及损失固定在`o9-v1-kk@c1fbd5ad5a8afa084cf15f9b294d62be080b7049`，来源和文件哈希见[UPSTREAM.json](../o9/UPSTREAM.json)。另一个本机wavelet目录已有更新，不混入其新损失或架构。该固定版本的实际训练入口只有Stage1和Stage2；历史名为Stage3的检查点只是本轮初始化候选，不据名称新增一个训练阶段。

`o9_loss.py`从固定提交迁入，只改包内导入；CQU训练器独立实现数据适配、阶段编排和明确的失败检查，不引入旧工程的随机划窗、源数据加载器、可视化或零样本评估调度。

| 阶段 | 数据/采样 | 主网络损失 | 原型与域判别器 |
|---|---|---|---|
| Stage1 | 当前折训练集正常窗；设备分支用均值、不采样 | 重构、KL、投影正交、设备时序平滑、故障帧一致性、特征方差 | 冻结；不训练域判别器 |
| Stage2 | 当前折正常和故障；设备分支VAE采样 | 上述损失，加原型BCE/对比CE、原型多样性、修正后的域对抗 | 原型解冻，判别器交替更新 |

原损失权重沿用固定版本的实际构造参数：Stage1为重构1、KL`1e-5`、正交0.5、平滑`1e-5`、故障一致性`1e-4`、方差`1e-2`且阈值0.01；Stage2为重构1、KL`1e-5`、正交0.1、平滑`2e-5`、一致性`4e-4`、方差`1e-4`且阈值0.1、原型2/对比项2/温度0.1、多样性0.3、域损失3。重构包括原实现的波形、FFT、包络、多尺度STFT及相关性项，不额外设计新的频带。

Stage2每个批次均更新主网络，每三个批次中的前两个先更新判别器，保留固定版本的实际更新节奏。重构输入在原始故障特征与按训练标签生成的原型特征之间逐步交替；原型监督始终约束原始编码器故障特征。判别器监督只接收不回传编码器的特征，主更新时判别器切换eval并冻结其参数，但保留对输入特征的梯度。域权重只按训练窗计数的倒数计算，归一化均值为1。

主网络/判别器使用新AdamW，学习率分别`1e-4 / 5e-5`、权重衰减`1e-4`。每阶段新建优化器及余弦调度器，模型和EMA延续；EMA覆盖全部模型参数，衰减0.999，主网络更新后同步。梯度范数上限20/10，非有限损失或梯度直接报错。默认batch8、种子42、CPU线程2、DataLoader工作进程0、不丢尾批；硬件显式指定，不静默切换。

当前未使用旧数据增强，输入沿用已确认的8192Hz/4096点/逐窗标准化和`prepared_v2`。因此这是完整模块及主要训练目标的**CQU适配版**，不声称逐步复现历史训练，亦不声称已复制旧数据增强或源域泛化效果。

## 域对抗方向与GPU兼容修正

固定版本原实现先计算负归一化熵，又经GRL反转梯度，导致编码器实际朝降低熵的方向更新；外层和GRL内部还重复施加ramp。经用户确认，本适配版在固定判别器时直接最小化负归一化熵，只在损失外部施加一次0→3的Stage2逐轮ramp。两轮短程试运行依次使用0、3，覆盖启用对抗的路径。单轮Stage2的ramp为0，只能验证无对抗强度的首轮，不能宣称检查过有效对抗。

另发现原STFT的隐式反射补边在CUDA反向不支持PyTorch严格确定性模式。`DeterministicMultiScaleSTFT`用切片、翻转和拼接实现相同反射补边，再以`center=False`计算STFT。补边内容、窗、归一化和帧数保持一致；未关闭确定性检查，也未改变上游源文件。等价前向、CPU梯度及CUDA确定性反向另行验证。原始失败产物保留在本机报告中。

## 验证与保存规则

训练不读取外层留出或28份历史记录。每轮验证完整6份文件/360窗口，使用新CQU EMA、`sample_z_d=False / use_combiner=False`。模型预测只依赖波形；真实标签仅用于计算损失及核对预测，不进入验证前向或原型组合。

每个窗口按故障特征均值与六原型的余弦相似度/0.1计算六类Softmax分数，每份文件平均60窗分数。保存六类预测和混淆矩阵；二分类分数为`1－正常分数`，即其他五类合计，阈值0.5。二分类检出故障不代表识别对了故障子类，必须结合六类预测看。分数未经概率校准。

只在Stage2选`best.pt`：验证文件级二分类平衡准确率最高，同分时取六类窗口交叉熵最低。Stage1分数仅供排查，不用于挑最佳故障模型。所有短程分数只检验数值及选优流程，不报告为正式成绩，也不用于挑选初始化候选。完整轮次分数属于当前采集内的开发验证结果，须同时报告训练预算、误报和漏报，不将验证选优成绩当独立测试成绩。

所有输出写入`tmp/cqu/`下不存在的新目录，保存`run.json`、含每批全部损失的`metrics.jsonl`、逐轮完整验证分数、`last.pt`、`best.pt`和从零训练的`stage1_last.pt`。检查点含完整模型、EMA、两个优化器、两个调度器、阶段/轮次/步数、随机状态及配置/输入身份；成功完成请求预算后才写`summary.json`。本轮验证所有best/last状态可重载，并验证CPU状态重载后的下一次更新其模型、EMA、双优化器和随机状态逐值一致；**尚未提供完整任务续训CLI，也未证明整轮/跨阶段中断续训与连续训练逐参数一致**，不能套用简化版的续训结论。

## 文件与公共接口

| 模块 | 接口 | 作用 |
|---|---|---|
| `full_model.py` | `CLASS_NAMES / FULL_PROTOCOL` | 六类顺序及适配协议 |
| `full_model.py` | `class_ids(binary_labels, experiment)` | 二值现场标签到六类标签 |
| `full_model.py` | `build_full_model(initialization, checkpoint=None, parameters='ema', seed=42)` | 完整旧参数校验与明确的迁移映射 |
| `full_model.py` | `prototype_logits(model, x)` | 无标签的六类余弦分数 |
| `full_model.py` | `DeterministicMultiScaleSTFT` | 等价确定性STFT补边适配 |
| `full_model.py` | `FullObjective(stage, domain_weights)` | 原分项损失、权重及修正后域目标 |
| `full_model.py` | `FullStageTrainer(model, stage, domain_weights, ema, lr_main=1e-4, lr_disc=5e-5)`、`step(x, labels, domains, adversarial_weight)` | 一个阶段的优化状态及单批更新 |
| `full_train.py` | `FullSmokeConfig(experiment, fold, initialization, ...)` | 短程配置，默认S1一轮/S2两轮/每轮两批 |
| `full_train.py` | `FullTrainConfig(experiment, fold, initialization, ...)` | 完整轮次配置，默认S1五轮/S2二十轮，批次上限为None |
| `full_train.py` | `evaluate_full(trainer, dataset, experiment, batch_size, adversarial_weight)` | 新EMA完整记录级验证及分项损失 |
| `full_train.py` | `run_smoke(prepared, output, config, checkpoint=None)`、`main()` | 单个任务的完整短程运行 |
| `full_train.py` | `run_training(prepared, output, config, checkpoint=None)` | 单任务完整或显式限批训练；完整轮次逐轮检查窗口覆盖，记录实际批量、窗口数和平均损失 |

## 本机调用示例

以下示例在本机Windows PowerShell、仓库根目录`E:/A-codehub/CNN`执行，不需管理员、不联网、不安装依赖，只读取现有缓存及旧权重，创建新的本机忽略目录。输出目录必须尚不存在。

```powershell
# 仅为当前PowerShell进程放行环境激活脚本，不更改机器或用户的持久执行策略。
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
# 激活本项目cloud虚拟环境，使后续python使用已验证的PyTorch环境。
. ./cloud/venv/Scripts/Activate.ps1
# 设备1CH2、折0，从零运行S1一轮和S2两轮，每轮最多两批、每批8窗；使用CUDA，结果固定标为短程检查。
python -X utf8 -m training.cqu.full_train --prepared tmp/cqu/o9_data_prep_20261025/prepared_v2 --output tmp/cqu/full_example_scratch --experiment device1_ch2 --fold 0 --init scratch --stage1-epochs 1 --stage2-epochs 2 --max-train-batches 2 --batch-size 8 --device cuda
# 设备2CH3、折0，用旧Stage2的EMA初始化，直接运行新的S2两轮；不恢复旧优化器，参数含义与上条一致。
python -X utf8 -m training.cqu.full_train --prepared tmp/cqu/o9_data_prep_20261025/prepared_v2 --output tmp/cqu/full_example_stage2 --experiment device2_ch3 --fold 0 --init stage2 --checkpoint o9v1/v3/checkpoint_final_s2.pth --parameters ema --stage2-epochs 2 --max-train-batches 2 --batch-size 8 --device cuda
# 检查上条成功摘要：应为complete/smoke_only均true，累计主更新4次、判别器更新3次。
Get-Content -Encoding UTF8 tmp/cqu/full_example_stage2/summary.json
```

`-X utf8`固定Python文本编码，`-m`按包执行入口；`--prepared`指定只读缓存，`--output`指定新结果目录，`--experiment/--fold`固定任务与整文件分组，`--init/--checkpoint/--parameters`选择初始化来源，轮数/批量/批次上限限制短程预算。以上两条示例都显式限批，保留为短程用法；完整训练移除`--max-train-batches`并明确轮数。例如S2二十轮、batch8对应每轮480窗/60批，共1200次主更新，仅读train/validation。实际项目实验预算及完成状态以[工作日志](../../docs/CQU_O9_WORK_LOG.md)为准。旧类保留训练或10kHz输入对照均属于后续实验。
