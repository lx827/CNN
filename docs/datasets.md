# Datasets — 原始离线测试数据

本页记录原始来源、身份、采样率和诊断前提。独立入口为 `cloud/tests/diagnosis/real_data/`，只读取原始记录和生成离线报告，不注册设备、不访问业务数据库、不修改生产算法。

数据根默认当前 checkout 的 `data/`，显式 `--data-root` 优先于 `CNN_DATA_ROOT`。独立 worktree 可共享主仓数据目录；源码和提交清单不固定机器盘符。大数据、原文说明和生成报告保留在本地数据根，不提交 Git。

## 来源与首批选样

| 数据身份 | 原始格式与采样率 | 通道角色 | 首批用途 |
|---|---|---|---|
| `ottawa_bearing` | MATLAB，200000 Hz，10 秒 | `Channel_1` 振动；`Channel_2` 编码器原波形 | 健康、内圈、外圈及变速模式个例 |
| `hust_bearing` | 带文本头 `.xls` 实为 TSV，25600 Hz，262144 点 | time、Speed、X/Y/Z | 华中轴承健康/故障、恒速/变速和中等损伤标签 |
| `hust_gearbox` | 带文本头 TXT，25600 Hz，262144 点 | time、speed、X/Y/Z | 同速度载荷配对下健康、断齿、缺齿 |
| `wt_planetary` | MATLAB，48000 Hz | 两振动、编码器及实际文件额外未明通道 | 同标称速度下健康和一种太阳轮故障 |

便携选样清单随代码提交：[轴承清单](../cloud/tests/diagnosis/real_data/manifests/bearing.json)、[齿轮清单](../cloud/tests/diagnosis/real_data/manifests/gear.json)。各条目保留数据身份、相对原始路径、SHA256、真实采样率、标签、故障部位、分组和证据。清单只描述已选样本，不声称覆盖完整数据集。

本地原始材料位于 `DATA_ROOT/raw_sources/<人类原目录名>/`。详细调查保留在 `raw_sources/_bearing_intake/report.txt`、`raw_sources/GEARBOX_INTAKE_20261111.txt` 和 `DATASET_TEST_SELECTION_20261111.md`，它们是本地调查材料。

## 轴承身份与前提

### Ottawa（历史本地名称 CW）

来源为 Huan Huang、Natalie Baddour，University of Ottawa，*Bearing vibration data collected under time-varying rotational speed conditions*，Data in Brief 21 (2018)，DOI `10.1016/j.dib.2018.11.019`，数据身份 `v43hmbwxpm.1`。

原始设计为 H 健康、I 内圈、O 外圈；A 升速、B 降速、C 升后降、D 降后升，各三次采集，共 36 条。每条有自己的转速起止/峰谷，不能给全部记录套同一速度曲线。振动和编码器均为 200 kHz；编码器是电平脉冲，每转脉冲数尚未核实，不能将 `Channel_2` 数值直接作为 Hz。

原论文 Table 1 明确 ER16K 节圆直径 38.52 mm、球径 7.94 mm、9 球，BPFI=5.43fr、BPFO=3.57fr。接触角未在所读表格中给出。reader 保留本来源的几何与特征阶次证据；对象诊断仍需满足速度与完整物理前提。

旧 `CW/down8192_CW/*.npy` 是振动加工格式。三个代表原始 MAT 经 `resample_poly(raw,128,3125)` 与同名 8192 Hz 数组达到浮点舍入误差量级对应，尚未逐个验证全部 36 条。旧数组没有编码器通道。新 reader 不依赖旧 CW 目录；目录是否仍存在不改变新入口契约。

### 华中 HUSTbear

来源为 Chao Zhao、Enrico Zio、Weiming Shen 的 RESS 2024 数据，DOI `10.1016/j.ress.2024.109964`。不要与河内 Hanoi University of Science and Technology 的 HUST practical 混淆；后者为 51.2 kHz、6204–6208 的另一数据集，本入口尚未支持。

华中原始健康码为 H；I/O/B/C 为内圈/外圈/滚动体/内外圈复合故障。`0.5X` 表示中等损伤，**不是负载比例**；无此前缀的故障为严重损伤。原设计为 9 健康状态与 11 工况，包括十种恒速和 `VS_0_40_0Hz`。每条三轴是同次采集。

源说明确认 ER-16K、球径 7.94 mm、9 球，但将 38.52 mm 标为 **Shaft Diameter**；不能把另一来源的节径解释移植为本来源已证实几何。其独立节径与特征阶次依据尚缺。Speed 列为电信号范围，单位与标定未知；文件名标称转频仅是工况标签。变速示意图 0–2 秒时间轴与 10.24 秒记录如何对应也未核实。以上字段保留未知，禁止补入 Ottawa 参数或生成线性速度真值。

## 齿轮身份与前提

### 华中 HUSTgearbox（定轴）

原机械为 Hub City M2，传动比 1.5:1，小轮 18 齿、大轮 27 齿，节圆分别为 1.125 英寸和 1.6875 英寸。它是定轴结构，不能走行星模型。

H/B/M 分别为健康/断齿/缺齿。原始 12 次采集由三状态与**四种速度载荷配对**组成：20 Hz/0.113 Nm、25 Hz/0.226 Nm、30 Hz/0.339 Nm、35 Hz/0.452 Nm。不存在四速度乘四载荷的 16 工况设计；拆成三轴不增加独立采集数。

本地原文本有 8 个 32768 点块，时间每块归零。跨块连续性未证实，reader 在当前块尾截断，首块最多 1.28 秒，不能将跨块拼接称为连续 5 秒。报告同时保留全记录点数与实际窗口。速度列单位、标定和文件名 Hz 是否参考 18 齿小轮仍待证实；`18fr` 只有在 fr 为该小轮机械转频时成立。振动工程单位与具体受损齿轮也不由照片或列名代填。

### WT 行星齿轮箱

来源为本地 WT-行星齿轮数据集，原说明引用 Liu/Cui/Cheng，Measurement Science and Technology 35 (2024) 012002，§6.2、Table 3。原设计为太阳轮健康、断齿、缺齿、齿根裂纹、磨损，八标称转速 20–55 Hz，各状态/速度拆装后采集两次，共 80 个 MAT；拆成两振动通道不是 160 次独立采集。

已证实太阳轮 28 齿、齿圈 100 齿、行星轮 36 齿、4 行星。fr 明确为**太阳轮转频**，啮合为 `175/8 fr`，太阳轮局部事件为 `25/8 fr`。不能把标称 20–55 Hz 当行星架转频。

reader 核对本地实际 MAT 采样与通道结构，额外列保持未知角色，不命名为新的已知传感器。编码器每转脉冲数、测量标定与振动物理单位仍未证实。行星评估还需可比且经验证的健康基线；少量健康/故障记录不能自动产生通用阈值。

## 清单、分组与窗口

manifest 顶层为 `schema_version: 1` 和非空 `samples`。条目至少含 `sample_id`、`dataset_id`、相对数据根的 `source_path`、`fs_hz`、`label`、`fault_types` 和 `group_id`。来源 SHA256、证据、机械参数、工况及未证实前提随条目保存。reader 参数与返回类型以源码 docstring 为准，不支持旧一维 `.npy` 兼容适配。

`sample_id` 标识真实记录，`group_id` 是保守评估分组，例如同速度载荷或拆装系列。报告分别记录真实记录数、分组数和通道数。不同通道和同记录切窗不能作为新的独立采集，也不能随机分到标定集与评估集。原采样率不因窗口缩短而改变；未知辅助信号不降采样为转速。

runner 逐记录、逐通道串行运行，默认 1 秒，可显式请求最多 5 秒。HUST 齿轮受块边界限制可返回更短窗口。轴承调用现有包络 Pipeline，保留统计特征及缺速度/几何的不可判定状态；WT 调用行星 Pipeline 前提门控；HUST 定轴缺小轮参考速度时报告未执行原因。没有新增阈值、估算几何或把标称速度冒充实测转速。

## 当前运行入口

从 `cloud/` 执行，将示例路径替换为实际数据根：

```bash
uv run python -m tests.diagnosis.real_data.run --data-root /path/to/data --window-seconds 1
uv run python -m tests.diagnosis.real_data.run --data-root /path/to/data --sample-id <清单中的sample_id> --window-seconds 5
```

默认读提交的两套清单；`--manifest` 可重复，用相对数据根或绝对路径显式覆盖。`--channel`、`--start-seconds` 可选振动通道与窗口起点。默认报告为 `DATA_ROOT/real_diagnosis/reports/latest.json`，可用 `--output` 指定。

报告包括来源与标签、真实采样率、实际点数/时长、信号质量、Pipeline 是否执行、`evaluation_status`、`diagnosis_conclusion`、coverage、可空 health_score 及不可判定原因。缺源文件、缺显式样本/通道、坏格式均非零退出；未知诊断是有效报告内容，不等于算法验证通过。小样本核实不输出准确率，不声称完成 #78 跨工况效果评估，也不是 #79 性能基准。

测试分层与集中命令见 [测试索引](tests/INDEX.md)。
