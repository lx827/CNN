# O9 模型迁移说明

此目录提供独立可导入的 O9 模型本体，供 CQU 离线训练使用。CQU读取、文件级划分和首轮预处理见[CQU数据准备](../cqu/README.md)，二分类头及已验证的短程训练入口见[训练说明](../cqu/TRAINING.md)；生产推理接入尚未实现。

## 来源与本地适配

- 上游：[`lscatfish/wavelet_study`](https://github.com/lscatfish/wavelet_study)。
- 来源分支：`o9-v1-kk`。
- 固定提交：[`c1fbd5ad5a8afa084cf15f9b294d62be080b7049`](https://github.com/lscatfish/wavelet_study/commit/c1fbd5ad5a8afa084cf15f9b294d62be080b7049)。
- 上游目录：`FaultDiagnosis/DG/o9/`。
- 许可：Apache-2.0，原文保存在 [LICENSE.upstream](LICENSE.upstream)。
- 每份上游文件及本地文件的 SHA-256、具体适配见 [UPSTREAM.json](UPSTREAM.json)。

保留上游参数命名、张量运算和结构。本地只作三处运行适配：`fault_bank.py` 使用包内相对导入；`o9_tools.py` 默认关闭自动 `torch.compile`，以 eager 模式运行，避免依赖额外编译器；移除 `o9.py` 直接执行时启动旧训练器的入口。未迁入旧数据加载器、随机窗口划分、训练调度器和消融实验，导入模型不会启动训练。

另清理了行尾空白，并通过包内 `.gitattributes` 固定来源文件的LF换行，以便在Windows检出后仍可复核哈希。

上游部分注释仍残留“三分支／176维”等旧版本描述；固定提交的实际计算是设备／故障两分支，各64维，解码器输入拼接为128维。本次未按陈旧注释改变模型结构。

## 文件及公共接口

| 文件 | 接口 | 作用 |
|---|---|---|
| `__init__.py` | 导出 `O9MainNet`、`O9Encoder`、`init_weights` | 统一导入入口 |
| `o9.py` | `O9MainNet(n_domains, num_faults, z_d_dim=64, z_f_dim=64, dropout=0.1)` | 组装完整模型 |
| `o9_encoder.py` | `O9Encoder(in_channels=1, hidden_channels=(32,64,128,192,256), z_d_dim=64, z_f_dim=64, dropout=0.1)` | 单通道波形编码、设备及故障分支 |
| `o9_decoder.py` | `O9Decoder(z_d_dim=64, z_f_dim=64, hidden_channels=(128,128,64,32,16,16), dropout=0.1)` | 隐变量重构波形 |
| `fault_bank.py` | `FaultBank(num_faults, feature_dim=64)`、`FaultCombiner(z_f_dim=64, num_faults=8)` | 故障原型相似度、按掩码组合原型 |
| `classifier.py` | `DomainDiscriminator(n_domains, input_dim=64, dropout=0.1)` | 预测来源域；它不是 CQU 故障分类头 |
| `o9_tools.py` | `ChannelLayerNorm`、`GradientReversalLayer`、`TimeAttentionPool`、`EMATracker`、`init_weights(module)` 等原工具 | 归一化、梯度反转、注意力聚合、参数初始化及原工具支持 |

模型的直接依赖只有 PyTorch 和 Python 标准库，无须安装或导入另一个 wavelet 项目。声明的 PyTorch 版本范围见 [requirements.txt](requirements.txt)；本机已验证 Python 3.13.7、PyTorch 2.10.0+cu126。迁移未安装或升级依赖，也未修改后端依赖。

## 输入输出与权重

`O9MainNet.forward(x, sample_z_d=True, use_combiner=False, fault_mask=None)` 接收 `[B,1,4096]` 浮点张量。按旧数据的8192Hz协议，4096点为0.5秒；模型自身不读取CSV、不重采样、不标准化，也不识别通道编号。CQU原始10kHz与四通道的首轮适配由独立的 `training/cqu/` 模块完成。

默认64维分支下返回：

| 键 | 形状／值 | 含义 |
|---|---|---|
| `x_hat` | `[B,1,4096]` | 重构波形 |
| `z_d`、`z_d_mu`、`z_d_logvar` | `[B,128,64]` | 设备分支及其分布参数 |
| `z_f_raw`、`z_f` | `[B,128,64]` | 原始故障分支／选定故障表示 |
| `weights` | `None` 或 `[B,K]` | 仅启用组合器并提供掩码时返回原型组合权重 |

确定性推理须同时调用 `model.eval()` 并显式传入 `sample_z_d=False`；仅 `eval()` 不会关闭上游显式重参数采样。`FaultBank` 输出原型相似度，不是已校准概率。旧五类顺序为健康、轴承内圈、外圈、滚动体、保持架；没有动不平衡，尚不能据此直接给出 CQU 两台设备的二分类结果。

以下是 Python 调用示例，工作目录为仓库根目录。它使用合成张量说明加载方式，不读取现场数据，也不会训练；路径只用于本地权重，不构成仓库运行依赖：

```python
import torch
from training.o9 import O9MainNet

# 仅加载张量及基础元数据，保持原文件不变。
checkpoint = torch.load(
    "o9v1/v3/checkpoint_epoch55.pth",
    map_location="cpu",
    weights_only=True,
)
# 按检查点实际保存的域数、类别数构建，不能把63个输出域误设为60。
model = O9MainNet(
    n_domains=checkpoint["n_domains"],
    num_faults=checkpoint["num_faults"],
)
# 示例采用原EMA参数推理；完整严格加载，不能静默跳过不匹配参数。
model.load_state_dict(checkpoint["ema"], strict=True)
model.eval()
with torch.inference_mode():
    output = model(torch.zeros(1, 1, 4096), sample_z_d=False)
```

从零构建时使用 `model.apply(init_weights)` 初始化，包括上游用 `torch.empty` 创建的原型。新任务微调以后应重新建立训练状态；本目录没有恢复旧优化器或训练轮次的自动逻辑。

## 本轮已验证范围

- 第55轮、Stage2终点及Stage3终点三份权重，各自的 `model` 和 `ema` 共六组均严格加载成功，80个参数张量键及形状完整匹配。
- 三份模型的CPU前向结果有限，输出维度、组合器及域判别器检查通过；显式关闭采样时相同输入结果一致。
- 随机初始化、合成输入反向梯度、参数保存／重载一致性通过；RTX 4060 Laptop上的CUDA前向检查通过。
- 原始权重内容检查前后保持一致。未执行优化器更新、未读取CQU训练数据、未计算CQU识别率。

这些结果说明固定版本模型可在当前项目运行并加载上述权重，不证明复现了旧训练时的精确代码行为，也不说明哪个候选对CQU最好。

## 后续数据与实验约定

已确认的首轮方向是：42份主要候选按完整CSV划分后切片，28份历史故障单独检查；设备1以CH2为主、CH1作对照，设备2以CH3为主；比较随机初始化与第55轮／Stage2终点／Stage3终点初始化。数据准备已固定三折每台8份训练、6份验证、7份外层开发评估，以及8192Hz／4096点／逐窗口标准化协议。各候选使用同一套文件分组，不能在外层评估记录上挑权重或通道。第三步的二分类适配与短程链路验证已完成，微调默认EMA来源；完整训练及外层/历史评估尚未实施。

`o9v1/` 整体被Git忽略，保留本地历史权重、日志、数据索引、分析图及消融产物。新的CQU探索脚本、派生数据和模型结果按本机约定保存在已忽略的 `tmp/cqu/<任务名>/`。模型模块本身无需这些本地文件即可被导入和随机初始化。
