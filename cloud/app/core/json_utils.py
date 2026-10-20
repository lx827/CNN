"""严格 JSON 转换，统一处理算法输出的 NumPy 类型和非有限数值。"""
import math

import numpy as np


def sanitize_for_json(obj):
    """递归转成 JSON 原生类型；NaN/Infinity 以 null 表示缺失结果。"""
    if isinstance(obj, np.ndarray):
        return sanitize_for_json(obj.tolist())
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, dict):
        return {key: sanitize_for_json(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(value) for value in obj]
    return obj
