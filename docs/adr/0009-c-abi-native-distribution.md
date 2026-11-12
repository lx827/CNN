# ADR 0009：C ABI 与无 Python 的计算库分发

- 状态：已接受并实现
- 日期：2026-11-13

未来边端需要直接复用计算能力，不能以 Python 扩展的加载环境作为数学库前提。决定保留一套 C++ 数学实现：公开拥有型入口和内部执行接口共用计算核，Python 绑定与 C ABI 仅做输入布局、参数和结果所有权适配。

根 CMake 独立构建默认不查找 Python，默认生成 C ABI 动态库；Python wheel 默认只生成 Python 扩展。独立安装同时提供 C 头、动态库、公共 C++ 头与可传递依赖的 CMake targets。Eigen 是公共 C++ 头依赖，私有 vendor 的实现头不对消费者公开；静态链接所需的私有库随 targets 一起分发。

C ABI 使用显式数组/参数与有限的具名 owner，正常质量状态保留算法本义；异常不跨边界，输出由原库释放，重复执行不覆盖历史结果。FFT 与连续 SOS 过滤提供按真实资源生命周期组织的复用计划。C 头和动态库按同一版本升级，不建立长期 ABI 兼容层，不引入 Rust 实现或另一套公式。

这扩展了 [ADR 0007](0007-native-algorithm-module-interfaces.md) 当时的 C++ 源码集成边界，保留其历史语境。部署、业务策略、长期 ABI 承诺与 ARM64 实机验证均有独立责任边界。构建、所有权、调用示例和实际验证见 [独立分发说明](../native_compute_distribution.md)。
