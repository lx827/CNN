# `json_utils.py` — 算法结果 JSON 转换

对应源码：`cloud/app/core/json_utils.py`。

## `sanitize_for_json(obj)`

递归返回 JSON 原生对象：NumPy 整数、浮点、布尔转换为对应 Python 类型，数组转换为列表，元组转换为列表，字典保留键并递归转换值。Python/NumPy 的 NaN、正负 Infinity 转成 `None`，序列化时为 `null`，表示该数值结果缺失。

转换不改变输入对象。不为缺失值补零，也不根据缺失值生成健康状态。

`app.api.data_view._sanitize_for_json` 保留兼容重导出；后台任务直接依赖本模块，不再从路由包导入基础转换函数。调用方需自行保证字典键为 JSON 支持的类型。
