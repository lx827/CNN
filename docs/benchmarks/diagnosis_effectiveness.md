# 四套原始数据的本地效果实验

入口为 `cloud/tests/diagnosis/real_data/effectiveness.py`，范围是 Ottawa 轴承、HUSTbear 轴承、HUSTgearbox 定轴齿轮与 WT 行星齿轮。它是本地固定实验，不注册设备、不调用 HTTP、不写业务数据库。

## 数据对象与冻结配置

原始记录统一使用 `real_data/common.py` 的 `LoadedRecord`：一次采集包含振动通道、原始采样率、辅助信号和来源元数据。入口复用 `bearing.py` 与 `gear.py` 的原始 reader；辅助编码器/Speed 电信号不直接当作机械 Hz。

样本、原文件 SHA256、标签、采集/拆装组、机械证据、未证实字段与实验条件保存在 [effectiveness.json](../../cloud/tests/diagnosis/real_data/manifests/effectiveness.json)。数据来源契约见 [datasets.md](../datasets.md)。运行时核对源文件哈希，依次读取有限连续窗口并串行分析，不跨 HUST 齿轮的时间归零块拼接。窗口和多通道都不能增加独立采集数。

`current_contract` 实际调用当前 `DiagnosisEngine`，参数只使用本来源可用机械信息及现有模型默认值，速度按产品自动估计，保留 canonical `evaluation_status` 与 `diagnosis_conclusion`。

`conditional_physical_parameters` 单列清单中声明的几何、名义速度和临时健康基线假设。它复用相同对象 Pipeline 与业务评估适配器，不把名义速度冒充实测、不将试验阈值写入产品。Ottawa 未明示的接触角沿用产品模型默认；HUSTbear 节径假设与已证实几何分开记录。WT 使用太阳轮参考轴，N1 健康记录训练临时界限，N2 及故障记录保留为测试；表示改变时训练表示也同步改变。

## 本地命令

在已同步的 uv workspace 中运行。独立 worktree 可以共享主仓 `data`，原始大文件不入库。

```powershell
$env:CNN_DATA_ROOT='D:/code/CNN/data'
cd cloud
uv run python -m tests.diagnosis.real_data.effectiveness --data-root $env:CNN_DATA_ROOT --output D:/code/CNN/data/real_diagnosis/effectiveness/results.json --markdown-output D:/code/CNN/data/real_diagnosis/effectiveness/diagnosis_effectiveness_report.md
uv run python -m unittest tests.diagnosis.real_data.test_effectiveness
```

仅从已有结果重新生成本地报告，不执行算法：

```powershell
uv run python -m tests.diagnosis.real_data.effectiveness --render-results D:/code/CNN/data/real_diagnosis/effectiveness/results.json --markdown-output D:/code/CNN/data/real_diagnosis/effectiveness/diagnosis_effectiveness_report.md
```

JSON、CSV、日志、图片、生成报告及逐记录输出全部留在 `DATA_ROOT/real_diagnosis/effectiveness/`，不提交 Git。仓库只保存源码、冻结清单与手写运行说明。源码参数/签名以 docstring 为准。

## 输出与统计语义

- `records`：逐采集、逐情景结果，含通道 canonical 状态、指标、证据、评分、失败/不可判定原因与记录级结论。
- `observations`：实际样本数、时长、原始采样率、信号统计、估速来源及对象指标，不包含原始振动数组。
- `training`：WT 仅用训练健康记录得到的指标和临时界限，保留训练身份与表示配置。
- `summaries`：记录级检出率、健康误报率、不可判定率、混淆矩阵及故障/速度/负载/长度/严重度/拆装组/噪声信息分组。
- `sensitivity`：运行前固定代表组的方法消融、名义速度敏感性及窗口长度对照，不按结果删改样本。
- `errors`、`environment`、`source_revision`、`runner_sha256`：执行异常与复现依据；长实验每完成一条记录写同目录 `.progress.json`。

训练记录不进入测试分母。检出率分母包含所有测试故障记录；误报率分母包含所有测试健康记录；失败和 unknown 不删除。任一通道异常则记录异常，所有通道均已评估正常才判记录正常，其余判 unknown。异常包括 warning 与 fault，只代表异常检出，不自动定位为某类齿面缺陷。

统计测试验证 unknown 保留分母及多通道不增样本，不重复 reader 或数值算法测试。实验结果不佳时先区分前提不足、覆盖缺口与阈值适用域问题；不得在同一测试标签上调阈值后将该集合重新作为独立效果验收。具体待办登记在 [Bug登记表](../Bug登记表.md)。
