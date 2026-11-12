# ADR 0008：以本地 emd.sift 为参考的独立原生算法族

- 状态：基础与集成候选已实现；mask 系列按依赖分支继续验证
- 日期：2026-11-12
- 关联：[基础 EMD](https://github.com/lx827/CNN/issues/116)、[集成算法](https://github.com/lx827/CNN/issues/117)、[Mask 算法](https://github.com/lx827/CNN/issues/118)

用户指定的参考是本地 distribution `emd==0.8.1` 的 `emd.sift`，并非名称相近的 `emd-signal/PyEMD`。记录包名、版本与实际源码路径；可选 `emd-reference` 组用于同依赖数值对照，不进入计算包运行依赖。来源与原始许可证随包保留，不建立参考源码 hash 校验或参考清单 JSON。

基础 EMD、EEMD、complete ensemble 与 mask 按算法分别实现和验收，对外模块统一叫 `emd`，`sift` 是算法函数。以 [ADR 0007](0007-native-algorithm-module-interfaces.md) 的公开/内部执行分工组合独立包络、插值、求解及变换能力，core 仅保留公共结构和非算法基础设施。结果列拥有存储，工作区可复用；Python 的二维兼容输出显式承担一次列布局复制，详细结果可以直接消费零复制交接的列。

本地参考的极值、延拓、停止接受点、集成选择和局部均值公式与原仓库算法不同，因此增加独立候选入口，不静默替换现有生产算法或旧原生筛分候选。完整算法循环在 C++，随机集成的纯 C++ 入口显式借用噪声；Python 用局部 legacy RandomState 保持参考随机序列并避免污染全局状态。

参考成功域按比较前固定的误差预算对照。参考的未定义变量、索引边界、未使用参数等缺陷单列限制，不复制成 C++ 越界，也不以修复后的结果冒充逐行为一致。具体验证、内存交接和限制见 [原生 EMD 契约](../algorithms/decomposition/native_emd.md)。本次独立候选不构成生产采用、目标 ECS 资源验收或未经测试架构的支持声明。
