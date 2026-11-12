# PyWavelets 内核归属

`vendor/pywt/` 是 PyWavelets 官方 v1.8.0（Git 标签源码）的独立 C 滤波器、卷积与离散变换实现，保留原始 MIT 许可证 `COPYING`。来源：<https://github.com/PyWavelets/pywt/tree/v1.8.0/pywt/_extensions/c>。

未编译 Python/Cython 包装或连续小波实现。CNN C++ 层复用一维 double 分解/合成入口，管理多层与包分解、裁剪、工作区及阈值收缩；运行时不需要 PyWavelets。官方内核同时包含未导出使用的 float、轴向和 SWT 例程，保留上游文件整体以便追踪来源。上游系数表属于必要算法源码，不是运行时生成清单。
