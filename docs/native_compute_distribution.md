# C ABI 与独立 CMake 分发

独立分发把现有 C++ 数学入口提供给 C 或未来的边端宿主。算法不依赖 Python；Python 扩展和 C ABI 共用同一批静态计算模块。架构决定见 [ADR 0009](adr/0009-c-abi-native-distribution.md)，算法、单位和可信状态仍以 [算法族契约](algorithms/INDEX.md) 为准，真实函数签名以 [C 头](../capi/include/cnn_compute.h) 和 `lib/` 各公开头为准。

## 构建与安装

独立 CMake 默认关闭 Python、开启共享库；scikit-build wheel 默认开启 Python、关闭共享库。可以分别用 `CNN_COMPUTE_BUILD_PYTHON` 和 `CNN_COMPUTE_BUILD_SHARED` 显式选择。独立构建需要 CMake 3.28+、Ninja 和 C/C++20 工具链，默认单线程构建。根目录已有的 uv 工作流见 [计算库说明](native_compute.md)。

Windows MSVC，在已有开发环境的 PowerShell 中执行：

```powershell
cmake -S . -B build/native-msvc -GNinja -DCMAKE_BUILD_TYPE=Release -DCNN_COMPUTE_BUILD_PYTHON=OFF -DCMAKE_INSTALL_PREFIX=C:/cnn-compute
cmake --build build/native-msvc --parallel 1
cmake --install build/native-msvc
cmake -S examples/native-consumer -B build/consume-msvc -GNinja -DCMAKE_C_COMPILER=cl -DCMAKE_CXX_COMPILER=cl -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/cnn-compute
cmake --build build/consume-msvc --parallel 1
$env:PATH='C:/cnn-compute/bin;'+$env:PATH
ctest --test-dir build/consume-msvc --output-on-failure
```

Windows 根工程默认选择 `cl`。外部工程需显式选择同一工具链，避免 CMake 自动找到 MinGW；MSVC 与 MinGW 的 C++ 二进制依赖不能混用。DLL 由库自身分配、释放结果，调用者不得使用自己的 CRT 释放结果存储。根构建和安装后的 CMake package 使用系统 PowerShell 探测真实 `/showIncludes` 前缀，不需要 Python 或英文 MSVC 资源；按控制台代码页或 ANSI 解码后以 UTF-8 交给 CMake。纯 C/C++ 直接编译时，源码和头使用 UTF-8，MSVC 添加 `/utf-8`。

Linux 原生构建：

```bash
cmake -S . -B build/native-linux -G Ninja -DCMAKE_BUILD_TYPE=Release -DCNN_COMPUTE_BUILD_PYTHON=OFF -DCMAKE_INSTALL_PREFIX="$PWD/build/install-linux"
cmake --build build/native-linux --parallel 1
cmake --install build/native-linux
cmake -S examples/native-consumer -B build/consume-linux -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$PWD/build/install-linux"
cmake --build build/consume-linux --parallel 1
ctest --test-dir build/consume-linux --output-on-failure
```

安装树包含 `include/cnn_compute.h`、`include/cnn_compute/` 的 C++ 头与 Eigen 公共依赖、`lib/cmake/CnnCompute/` package、各算法静态库及共享库。Windows 的 DLL 在 `bin/`，导入库在 `lib/`；Linux 为 `lib/libcnn_compute.so`。PyWavelets 的私有 C 静态依赖随 C++ target 导出，vendor 头和 pocketfft 实现头不成为公共依赖。Eigen 与第三方许可证随分发保留。

外部 CMake 使用 `find_package(CnnCompute 0.1.0 EXACT CONFIG REQUIRED)`；C 消费链接 `CNN::c`，C++ 按实际模块链接 `CNN::wavelet`、`CNN::numeric` 等。头文件和 CMake targets 可随前缀一起移动，消费者无需保留仓库或构建目录。也可以在源码工程中关闭 Python 后 `add_subdirectory`，链接同名 `CNN::` targets；源码路径与安装路径使用同一套模块入口。

## C 边界与所有权

```text
调用方连续输入 ──同步只读借用──> C 参数适配 ──> 既有 C++ 入口/执行接口
                                              └─> 拥有型结果
                                                   └─> cnn_result
                                                        └─> cnn_result_free
```

头与动态库按同一源码版本配套升级，不承诺长期二进制 ABI 兼容。所有入口同步执行，不创建线程；不同活跃调用的 Plan/Workspace 各自独占。C ABI 使用显式长度的数组、参数结构体、枚举和不透明 owner，不把 STL、Eigen、异常或宿主分配器带过边界。

结果是有限的具名数组、标量与文本字段；每个字段携带类型和行列数。数值数组行优先，`CNN_COMPLEX` 输出是连续的交错 `double(real,imag)`，可直接读取 double 或用 `cnn_field_complex` 按值读取；不能把其指针别名当作 `cnn_complex*`。复数输入结构体在边界转换一次。C++ 的独立数组通过移动交给 owner，复数结果使用标准保证的数组定向 double 访问，避免最终整数组打包复制。

`cnn_result_field`/`find` 返回的字段指针只借用到对应 owner 释放；输入可以在同步函数返回后释放，后续计算、计划释放都不覆盖已有输出。使用 `cnn_result_free` 释放库结果，允许传入空指针；不得释放或修改字段里的借用存储。函数出错返回空指针并写调用方提供的 `cnn_error`，错误消息在固定缓冲内截断。参数、求解或内存错误不越过 C 边界，正常的未收敛或不可判定通过族结果保留。

连续同规模 FFT 使用 `cnn_fft_plan` 保留实/复变换计划与必要输入适配容量；执行直接写本次独立输出，仍需最终输出和后端执行临时空间。连续 SOS 零相位过滤使用 `cnn_sos_plan` 保留系数与延拓工作区，工作区仅随输入规模增长扩容。其他 C 一次性入口准备独占工作区；需要直接控制更多工作区的 C++ 调用方使用各数学族的公开执行接口。

## 能力与真实状态

| 数学族 | C 边界表达 |
|---|---|
| Fourier、滤波、插值、三对角求解 | 完整/半谱、卷积、Butterworth SOS、SG、Hann、去趋势、显式插值方法 |
| 基础表示与统计 | spectrum/STFT/倒谱/Hilbert、总体/窗口/分段统计、抽点、自相关；不改变单位与轴顺序 |
| 包络、EMD 与 Hilbert/NHT | 包络极值不足保留状态；逐分量数组和真实筛分迭代；集成噪声由宿主提供，不内建 RNG 框架 |
| mask 与二层 EMD | 真实频率、分层深度与状态；迭代 mask 的收敛平均频率为 Hz、上限退出时为 cycles/sample，保持原算法语义 |
| 小波与 VMD | 系数 owner 可继续整体/分量/选择重构；VMD 保留输入/有效长度、原因、收敛和实际有效历史行 |
| MED/MCKD、ICA、LMS | 目标历史与实际迭代；ICA 数值秩、秩亏/奇异/迭代上限分别保留 |
| 诊断基础运算 | TEO、CPW、谱峭度、滤波器组峭度图、SC/SCOH、MSB；复杂结果保留复数值和有效网格 |
| 旋转与时序 | 相位、等角重采样、TSA、局部峰、测速原因、CVS 有效区间；Holt、Kalman、CUSUM 与窗口趋势统计 |

字段命名、数组形状和枚举含义以 C 头为准。统计值顺序、kurtogram 列顺序等布局在头中注明；C ABI 不把所有算法强行映射到统一成功标志。owner 对未知字段没有默认填补；调用者按本次同版本头解释结果。

## ARM64 交叉构建

Linux 主机安装目标 GNU 工具链后，使用 [aarch64 toolchain](../cmake/toolchains/linux-aarch64.cmake)：

```bash
cmake -S . -B build/native-aarch64 -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/linux-aarch64.cmake -DCMAKE_BUILD_TYPE=Release -DCNN_COMPUTE_BUILD_PYTHON=OFF -DCMAKE_INSTALL_PREFIX="$PWD/build/install-aarch64"
cmake --build build/native-aarch64 --parallel 1
cmake --install build/native-aarch64
```

toolchain 使用 `aarch64-linux-gnu-gcc/g++`，默认 baseline；目标 sysroot 与运行系统匹配时可通过标准 CMake 参数指定。切换系统、架构、编译器或 ISA 使用独立构建目录，不混用 Windows/x64/ARM64 产物。本次只提供 ARM64 配置和命令，未访问或验证树莓派、未部署服务；x64 构建结果不作为 ARM64 运行证据。

## 已执行验证

2026-11-13：Windows MSVC 19.50 x64 baseline 的无 Python DLL 构建、纯 C 消费、安装后独立 C/C++ 消费通过。C 消费检查 FFT/SOS 计划复用和 owner 生命周期、小波重构、包络极值不足、EMD 状态、VMD 有效窗口/历史、ICA 秩亏及错误转换；C++ 消费包含公共族头并实际链接小波私有静态依赖、基础表示与时序模块。MSVC 回归分别在 936/65001 控制台验证生成、编译和间接头变更触发重编。Linux x64 构建与安装消费结果在完成后记录于本节。

这些验证针对分发和边界；各数学族定向正确性与性能证据见其契约，不重复整套数学验收。没有服务器、ARM64 实机或 2C2G 资源结论。
