# 定轴与行星齿轮契约

> 定轴 #71 已随 PR #85 合并；行星 #72 纯计算与公共业务切片已集成至开发分支/草稿 PR #89。公共接入以 [诊断编排](../../backend/diagnosis.md) 和 [API](../../api/backend_api.md) 为准，未声明真实数据分类效果。
>
> 实现导航：`algorithms/gear/fixed_axis/`、`gear/planetary/`、`mechanics/planetary.py` 与 `algorithms/pipelines/gear/`（均相对 `cloud/app/`）。

## 数学目的

定轴围绕啮合阶次、转频边带、同步平均（TSA）、高阶矩和倒谱提取局部/分布性异常证据。行星还存在行星架调制与多传递路径，须先建立运动学和参考轴；定轴 1 阶边带与阈值不能直接套用。算法提供表示，分析提指标，评估只消费已有指标，业务负责机械配置、资源与融合。

## 适用与不适用场景

- 定轴阶次谱接收合法阶次分析，精确 TSA 还需要可靠恒速与足够完整转数；逐帧平均谱不提供同步相位。
- 行星当前只支持固定齿圈、同模数简单均布行星排，参考轴明确为 sun 或 carrier；不支持浮动齿圈、复合排或行星轮自转 TSA。
- 行星解调只接受明确恒速。单独 `/order` 有快速变速补偿不表示 TSA/解调已支持该工况；不能以轨迹中位数绕过限制。
- 健康行星天然多边带。高 SER/CAR、包络峭度或单个事件峰不能直接命名太阳轮断齿、行星轮裂纹。
- #75 VMD AM-FM、MSB、CVS 与其他复合流程已提供独立研究入口，当前行星基础评估不消费其证据，也不使其参与生产融合；见 [复合契约](../composite/INDEX.md)。SC/SCoh 完整行星组合未因研究入口自动补齐。

## 输入、输出与单位

| 对象 | 稳定语义 |
|------|----------|
| 输入振动/采样率 | 一维有限样本；采样率 Hz，幅值保留输入单位 |
| 转速 | 对应明确参考轴的 Hz；不以齿数或固定 10 Hz 补缺 |
| 阶次谱 | 阶次相对声明参考轴，幅值遵循 [阶次契约](../order/INDEX.md) |
| TSA | 等角序列，采样率为点/转；保存同步轴、每转点数与完整转数 |
| 指标 | FM0/FM4/M6A/M8A、NA4/NB4、SER/CAR 无量纲，附可评估状态、原因和表示定义 |
| 基线/历史 | 带来源与表示键；方差为输入单位平方，不允许跨对象/工况比较 |

### 固定齿圈运动学

令太阳、齿圈、行星齿数为 Zs/Zr/Zp，行星数 Np；要求 `Zr=Zs+2Zp`，均布装配与相邻节圆无干涉。Willis 方程给出 `fc/fsun=Zs/(Zs+Zr)`；啮合频率 `fm=Zr*fc=Zs*(fsun-fc)`。绝对行星自转 `fp=fc-fm/Zp` 可带负号；相对行星架的自转幅值为 `fm/Zp`。

事件候选为太阳轮 `Np*(fsun-fc)`、行星轮一次/两次啮合 `fm/Zp` 与 `2*fm/Zp`、齿圈 `Np*fc`；`fc` 是传递路径调制候选。各频率除所声明参考轴频率得到阶次。这些是运动学候选，不保证壳体传感器必然可观测，也不直接证明故障类型。

WTgearbox 的 Zs=28、Zr=100、Zp=36、Np=4：太阳轴参考的 carrier 阶次 7/32、mesh 21.875、太阳事件 3.125、行星单次事件约 0.607639、齿圈事件 0.875；行星架参考则分别换算，不能混用。数据配置以 [数据集说明](../../datasets.md) 为准。

## 必要前提

- 缺参数与畸形配置区分。定轴必须有相应齿数；行星必须有完整几何、固定构件与参考轴，不把 `input/output` 简单伪装为完整行星模型。
- 所需啮合/边带在原物理 Nyquist 与角域 Nyquist 内。搜索窗不足、重叠或共享峰时保留不可评估，不重复计数。
- TSA 需要至少配置要求的完整转数。同步于所选轴的事件保留在 TSA；非同步 residual 会抑制这些事件，不能将两个表示互换解释。
- NA4/NB4 必须有可比健康方差历史；行星异常评估需匹配几何、速度、采样率、实际长度、单位、方法参数和 TSA 选项的基线。无历史不退化为当前方差归一化后冒称趋势。

## Pipeline 组合

### 定轴

```text
转速/阶次分析 + 齿数 → 阶次谱和可选精确 TSA
→ regular/residual/differential、边带与倒谱表示
→ 原始矩、SER/CAR、边带观测 → 独立工程阈值评估
```

本项目明确：`regular=纯啮合谐波+配置边带`，`residual=TSA-regular`，`differential=regular-纯啮合谐波`。`原始角域信号-平铺TSA` 另名 nonsynchronous，不是经典 residual。FM0 使用啮合谐波峰幅值，避免把窗主瓣多个 bin 相加。M6A/M8A/NA4/NB4 没有已验证故障阈值时只给原始值，warning/critical 保留未知。

`FixedAxisGearPipeline.analyze` 生成已有指标对象；evaluate 可直接重评，改变阈值不重算 FFT/TSA。业务 `fault_indicators` 是规范评估的兼容视图，不产生第二套指标。

### 行星

```text
完整运动学 + 明确恒速 → 最多 5 秒记录与等角表示
→ carrier 间隔 SER + narrowband/fullband/highpass 包络
→ 可选 sun/carrier TSA 与角域 nonsynchronous 包络
→ 方法专属事件峰/背景、矩、CAR 和历史指标
→ 匹配表示键的基线评估，或保留 unknown
```

SER 使用 carrier 间隔，搜索窗互不重叠，不能再被定轴 1 阶 SER 覆盖。TSA residual 已是角域数据，FFT 采用点/转而非原始 fs。窄带峰必须有可观测的邻域背景；全带 Hilbert 存在多分量交叉项。经典整数啮合梳 TSA 指标只在所选同步轴啮合阶次为整数且谐波覆盖充分时计算。

行星 FM4/M6A/M8A 当前明确指所选轴 TSA 的 `regular-minus-mesh` 差分信号中心归一化 4/6/8 阶矩；carrier 是默认 TSA 轴。它们是该处理链的数学描述，不能据名称声称已验证所有经典行星诊断定义，更不直接套用定轴阈值。当前依据为 Willis 手算、表示恒等式和合成向量；没有完成原始文献逐项外部复现或真实健康基线标定。

`PlanetaryGearPipeline` 分开 analyze/evaluate/run；evaluate 不重做表示，只检查已产生且被标定的指标。缺基线保留 `unconsumed_metrics`。有效基线也只给异常或“已校准指标未见异常”，不将异常命名为具体损伤类型。

## 错误与不可判定语义

- 非法几何、轴定义和阈值方向明确报错；缺配置、无有效转速、快速变速、短记录、零能量、超带宽或方法失败保留原因。
- 原始指标 `not_evaluable` 时值为 `None`，不能以 0 构造健康；可评估阴性和未知分开。
- 定轴 `evaluation.status=evaluated` 仅说明有有效指标；不等于全部指标或故障结论可信。领域状态与结论进一步拆分由 #84/#77 收敛。
- 行星无基线/基线不匹配时 `evaluation.status=not_evaluable`、`conclusion=unknown`。某个方法失败不抹掉其他合法原始结果。
- 没有进入评估器的研究输出不参与融合、健康评分或告警。

## 复杂度与内存

等角/谱分析约 O(N log N)，TSA 需角域与周期表示；各包络方法串行计算。行星窗口最多 5 秒，禁止为复合方法并发放大内存。生产两线程池和单批分析限制见 [运行时](../../backend/architecture.md)。

#126 将 TSA、Chirp-Z、CAR 倒谱与谱窗数值、高阶中心矩和边带峰计算下沉到 `lib/rotation/`、`lib/sequence/`。TSA 的 mesh/regular 共用一次单圈 DFT，长记录周期 Hann 幅值谱由 DFT 移频恒等式构造，不重复执行平铺长记录 FFT；mesh/regular/residual/differential 仍分别拥有独立输出，保持已有表示定义。原始值的可评估门控、可比历史检查和工程阈值留在 Python。Windows 数值及公开调用测量见[原生验收记录](../order/native_rotation_validation.md)，不声明 ARM 或生产资源已验证。

## 参考文献

- Randall (1982)，齿轮振动；McFadden (1986/1987)，解调与 TSA。
- Feng & Zuo (2012)，行星振动模型；Willis 运动学。
- [经典推导](../../算法原理.md)；[历史行星评估](../../行星齿轮箱诊断进展.md) 保留原日期与数据语境。

## 验证向量与验证状态

定轴已完成独立数学/业务审查；行星验证覆盖运动学、单位和不适用工况。文档轮次不重复算法测试，真实数据效果未据此宣称完成。

| 资产 | 覆盖 |
|------|------|
| `cloud/tests/diagnosis/algorithms/test_fixed_axis_gear.py` | 手算矩/啮合、TSA 恒等式、角域轴、边带/倒谱、缺历史、直接重评 |
| `cloud/tests/diagnosis/algorithms/test_fixed_axis_gear_api.py` | Engine/API、规范评估和兼容字段 |
| `cloud/tests/diagnosis/planetary/test_planetary_pipeline.py` | WT 参数手算、参考轴、SER 重叠、角域 residual、覆盖不足、缺基线和重评 |
| `cloud/tests/diagnosis/planetary/test_planetary_business.py`、`test_planetary_api.py` | Engine/ensemble/评分门控、当前通道完整几何、真实隔离 HTTP 四方法/gear_advanced 与旧标识拒绝 |
| `cloud/tests/diagnosis/regression/` | None 参数与工况边界 |
| `cloud/tests/diagnosis/real_data/` | 原始齿轮记录与真实效果评估，依赖有效参数与工况 |

历史端到端数据报告不能外推为当前 Pipeline 的效果。主仓 CW 有 36 个变速 `.npy`，其他数据可用性按实际目录或 `CNN_DATA_ROOT` 分别确认；不能一概写为全部缺失或全部已验证。
