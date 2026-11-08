# 算法模块契约索引

本目录是公开算法族稳定语义的唯一权威入口。函数签名、参数类型和默认值以源码 docstring 为准；HTTP 字段以 [API 文档](../api/backend_api.md) 为准。

## 当前契约

| 算法族 | 权威入口 | 当前范围 | 验证入口 |
|------|----------|----------|----------|
| 轴承包络与故障证据 | [bearing/INDEX.md](bearing/INDEX.md) | #68 标准包络 Pipeline；现有高级轴承方法的统一边界 | [测试指南](../tests/INDEX.md) |
| 转速、相位与阶次 | [order/INDEX.md](order/INDEX.md) | #69 标量/局部/连续转速、等角采样、三种 Pipeline | [测试指南](../tests/INDEX.md) |
| 齿轮与行星箱 | [gear/INDEX.md](gear/INDEX.md) | 当前服务层 TSA、指标、边带和行星解调；#71 独立算法库切片待定稿 | [测试指南](../tests/INDEX.md) |
| 小波与模态分解 | [decomposition/INDEX.md](decomposition/INDEX.md) | 当前降噪与敏感分量组合；#74 独立算法库切片待定稿 | [测试指南](../tests/INDEX.md) |
| 基础数值表示 | [numeric/INDEX.md](numeric/INDEX.md) | #76 / PR #81 FFT/STFT/倒谱、统计、通用包络和显示抽点 | [测试指南](../tests/INDEX.md) |

## 理论与系统组合

- [经典算法原理](../算法原理.md)：公式推导、物理意义和参考文献，不承担函数签名同步。
- [诊断算法体系全景](../诊断算法体系全景.md)：业务诊断的组合与评分背景；算法族的单位和不可判定语义以本目录为准。
- [小波与模态分解理论](wavelet_and_modality_decomposition.md)：保留的理论资料，不是独立分解库的实现状态声明。
- [数据集说明](../datasets.md)：验证数据、采样率和机械参数。

## 新增或修改算法文档

1. 先选择上表中的算法族；新机械对象或新方法族才建立新入口，避免按 `.py` 文件建文档。
2. 按 [模块模板](TEMPLATE.md) 写全稳定契约。没有实测证据时明确写“未验证”，不把理论适用性写成已验证效果。
3. 签名变化只改源码 docstring；数学目的、单位、前提、Pipeline、不可判定语义或验证状态变化才改模块文档。
4. 未合并切片使用“待定稿”状态，不提前修改当前 API 契约。
5. 运行 `bash docs/internal/check_markdown_links.sh` 检查相对链接和必需结构。
