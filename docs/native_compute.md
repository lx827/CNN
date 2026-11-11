# 诊断计算库构建与安装

根目录的 `cnn-compute` 分发包使用 CMake、scikit-build-core、pybind11 与 Eigen。当前提供构建信息和 PCHIP/cubic、SD/Rilling 四种组合的单 IMF 原生筛分候选，EMD/EEMD/CEEMDAN 外层保持 Python；生产分解默认仍为 Python。技术路线见 [ADR 0006](adr/0006-native-diagnosis-compute-package.md)。

## 一次同步

Windows x64 安装 Visual Studio C++ 工具链后，在 Git Bash 执行：

```bash
vsdev uv sync
uv run --no-sync python -c "from cnn_compute import build_info; print(build_info())"
```

本机直接调用 `bash` 会进入 WSL；使用确认过路径的 Git Bash，例如 PowerShell 中运行 `& 'D:/Git/bin/bash.exe' -lc 'vsdev uv sync'`。MSVC 编译、链接始终经 `vsdev`；后续无源码变化的 Python 调用不需要重新进入编译环境。

Ubuntu x64 需要可用的 C++20 工具链，执行：

```bash
uv sync --frozen
uv run --no-sync python -c "from cnn_compute import build_info; print(build_info())"
```

Python 由 uv 托管，构建后端、pybind11、CMake 与 Ninja 的版本在根构建配置固定。Eigen 源码从官方版本归档下载并校验 SHA256，经 `Eigen3::Eigen` target 传播；纯 C++ 核心和 Python 绑定分别构建。Ninja 编译并行度为 1，依赖源码、生成头文件与构建产物保留在忽略的构建目录。

## 依赖与分发边界

根项目运行依赖仅包含计算库所需的 NumPy。cloud、dc24、dev 是日常默认依赖组；benchmark 通过 `uv sync --group benchmark` 显式安装。只需库运行环境时使用 `uv sync --no-default-groups`。

cloud 与现场采集源码不因打包迁移：后端继续以 cloud 为工作目录启动，采集继续按原脚本入口运行。各目录的 uv 命令向上发现同一个根项目和 `.venv`。应用依赖使用 `uv add --group cloud` 等命令添加；计算库本身的运行依赖才使用无分组的 `uv add`。

wheel 仅包含 `cnn_compute`、其原生扩展及库的分发元数据；应用、测试、数据、Eigen 头文件与构建目录不进入 wheel。NumPy/SciPy 等第三方 Python 依赖可使用官方 wheel；自有计算包从项目源码构建。运行依赖由根锁文件锁定，构建后端版本以根构建配置为准，C++ 依赖版本与哈希由 CMake 声明。

## 原生筛分候选

候选通过 `NativeEMDImplementation` 显式传入现有 EMD/EEMD/CEEMDAN 公开分解入口；该 adapter 复用 Python 外层，仅将一次完整 IMF 筛分交给原生核。默认及可选的插值/停止组合均走同一筛分循环，NumPy 噪声生成、种子顺序及 Torres 2011 集成公式保持原样。包级通用筛分入口及已有 PCHIP/SD 兼容入口的签名和所有权见源码 docstring；合规 float64 连续输入只读借用，非连续视图最多显式连续化一次，输出由 capsule 持有独立缓冲区。计算期间释放 GIL，不新增线程池。

极值差分掩码、抛物线精化、PCHIP 斜率与系数、分段多项式求值、信号更新及平方和使用 Eigen 数组表达式，索引压缩、镜像排序与区间查找保留专用流程。工作区按记录和节点数线性增长，输入只在单次筛分开始时复制为工作数组，不在每轮重复制输入或重做边界校验；数值产生非有限包络时明确抛错。

PCHIP 适配保留 SciPy 的端点规则、非等距节点、小节点退化、外推与常数项到三次项的累加次序；使用 MSVC `/fp:strict` 或 GCC/Clang `-ffp-contract=off` 抑制乘加收缩，实际规则也写入构建信息。此约定保留 SIMD，避免极平残差因改写求值次序而改变后续极值拓扑；跨后端仍按冻结误差预算验收，不承诺跨平台逐位相同。

候选筛选曾比较 Boost.Math 1.89 的 PCHIP：端点需覆写、原始求值不支持外推、内点加权调和均值的舍入次序也不同。受控对照显示，普通 Horner 以及该斜率次序的末位差异可放大到固定双频反例的后续模态；分别恢复 SciPy 求值及斜率次序后恢复预算内对照。需要覆写全部相关行为时，该库没有实际复用价值，因此最终以 Eigen 为计算基座，PCHIP 仅保留必要的语义适配。[SciPy BSD 归属](../native/LICENSE.scipy) 随源码与 wheel 许可证目录分发，没有额外链接无用依赖。

cubic 使用 not-a-knot 一阶导数三对角系统；两个节点为线性，三个节点使用固定 3×3 抛物线系统，其余节点使用带相邻部分主元的单右端项消元。两种插值共用 SciPy 兼容的分段系数与向量化求值，并允许首尾多项式外推。Rilling 的包络对称比使用 Eigen 数组计算；零幅值/零均值比值为 0，零幅值但非零均值为无穷，阈值与超标比例保留当前比较规则。

初始 cubic 候选使用 Eigen 自然排序稀疏 LU。它通过局部、合成及多数固定向量检查，但 HUSTbear 的 cubic/Rilling CEEMDAN 在第 4 模态出现 10 个点超过已冻结预算，迭代数相同。仅将大节点系统改为 Reference-LAPACK 3.12.1 DGTSV 的单右端项消元次序后，同一反馈四个模态差异归零；预算、右端项、插值与 Rilling 不变。该窄适配避免稀疏 LU 的倒数乘法及分离三角解所引入的不同舍入次序，并非要求全部浮点运算逐位相同。

带状适配持有下对角、主对角、上对角和右端项共 `4N-2` 个 double，下对角缓冲区复用为换行后产生的第二上对角，不进行通用稀疏填充或构造 N×N 稠密矩阵；相关节点和系数数组同样线性增长。递推求解保持标量依赖链，数组构造和多项式求值继续使用 Eigen SIMD。CMake 将适配源码链接进既有计算核心，没有新增 Fortran/BLAS 运行时；[LAPACK 归属](../native/LICENSE.lapack) 随源码和 wheel 分发。

## 指令集与缓存

默认目标为 baseline，在 x64 上使用 Eigen 的 SSE2 内核。需要 AVX2 的主机可显式选择固定目标；该产物要求运行 CPU 支持 AVX2/FMA：

```bash
CNN_COMPUTE_ARCH=avx2 vsdev uv sync  # Windows Git Bash
CNN_COMPUTE_ARCH=avx2 uv sync       # Linux
```

固定目标只允许 baseline 或 avx2。这里不将 native 字符串映射成未经探测的 AVX2，也不构建运行时多 ISA 派发。后端报告编译器、目标、编译选项、Eigen 版本和实际启用的 SIMD；具体数值函数的向量化仍需优化报告与基准验证。

uv 缓存键覆盖根配置、CMake 文件、原生源码、Python 源文件及影响目标/编译器的环境变量，不包含导入产生的 Python 字节码。切换 `CNN_COMPUTE_ARCH`、编译选项，以及修改源码/头文件后会重新构建；未变化时复用兼容产物。构建目录按 Python wheel tag 和 Ninja 隔离，Windows 和 Linux 不共用二进制。

更换编译器或工具链版本时，CMake 已缓存的编译器不会仅靠修改环境变量替换。使用新的忽略构建目录并强制重装计算包，例如 `uv sync --reinstall-package cnn-compute --config-setting build-dir=build/new-toolchain`；Windows 仍经 `vsdev`。新目录名应标识实际工具链，确认 `build_info()` 后再采用产物。

## 验证

```bash
uv run --no-sync python tests/test_compute_package.py -v
```

验证安装后的真实构建信息和独立库依赖边界。发布前另检查清洁环境同步、源码及头文件变更重建、构建目标切换、wheel 内容、后端导入及采集启动检查。WSL 的 Ubuntu 结果仅证明 Linux 构建链可用，不等同于目标 ECS 的 2C2G 整机资源验收；后者由性能与资源工单独立执行。
