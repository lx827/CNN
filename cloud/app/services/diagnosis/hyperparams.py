"""
诊断超参数加载器 — 三级回退 + 按设备缓存

加载优先级：
  1. 设备级覆盖 (Device.diagnosis_config JSON)
  2. 数据集默认 (dataset_profiles.json)
  3. 代码全局默认 (thresholds.py)

用法：
  from app.services.diagnosis.hyperparams import HyperParams

  hp = HyperParams.for_device(device_config)  # 从设备配置加载
  kurt_th = hp.get("diagnosis.bearing.kurtosis_threshold", 5.0)
  crest_th = hp.get("diagnosis.bearing.crest_evidence_threshold", 10.0)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 数据集默认配置 JSON 路径
_PROFILES_PATH = Path(__file__).resolve().parent.parent.parent / "core" / "dataset_profiles.json"

# 模块级缓存：避免每次调用都读 JSON
_cached_profiles: Optional[Dict] = None


def _load_profiles() -> Dict:
    """加载 dataset_profiles.json（带缓存）"""
    global _cached_profiles
    if _cached_profiles is not None:
        return _cached_profiles
    try:
        with open(_PROFILES_PATH, "r", encoding="utf-8") as f:
            _cached_profiles = json.load(f)
        logger.info("Loaded dataset profiles from %s", _PROFILES_PATH)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load dataset profiles: %s, using empty defaults", e)
        _cached_profiles = {}
    return _cached_profiles


def _nested_get(data: Dict, path: str, default: Any = None) -> Any:
    """按点分隔路径从嵌套字典取值，如 'diagnosis.bearing.kurtosis_threshold'"""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def _nested_merge(base: Dict, override: Dict) -> Dict:
    """深度合并两个字典，override 覆盖 base"""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _nested_merge(result[key], val)
        else:
            result[key] = val
    return result


class HyperParams:
    """设备级诊断超参数容器

    三级回退链：device_override → dataset_profile → thresholds_default
    """

    def __init__(
        self,
        device_override: Optional[Dict] = None,
        dataset: str = "default",
    ):
        profiles = _load_profiles()
        self._dataset = dataset
        self._dataset_profile = profiles.get(dataset, profiles.get("default", {}))
        self._device_override = device_override or {}

        # 合并：设备 > 数据集 > 全局 default
        self._merged = _nested_merge(self._dataset_profile, self._device_override)

    @classmethod
    def for_device(cls, device_config: Optional[Dict] = None, dataset: str = "default") -> "HyperParams":
        """从设备配置创建 HyperParams

        device_config: 可以是 Device.diagnosis_config (JSON) 或整个 device dict
        """
        override = {}
        prof = "default"
        if device_config:
            # 尝试提取 diagnosis_config 子字段
            diag_cfg = device_config.get("diagnosis_config")
            if isinstance(diag_cfg, str):
                try:
                    diag_cfg = json.loads(diag_cfg)
                except (json.JSONDecodeError, TypeError):
                    diag_cfg = None
            if isinstance(diag_cfg, dict):
                override = diag_cfg
            elif isinstance(device_config, dict):
                # 如果没有嵌套字段，把整个 device_config 当 override
                # 但排除非超参字段
                override = {k: v for k, v in device_config.items()
                           if k not in ("id", "name", "device_id", "created_at", "updated_at")}
            
            # 数据集类型
            prof = device_config.get("dataset", dataset) or dataset

        return cls(device_override=override, dataset=prof)

    @property
    def dataset(self) -> str:
        return self._dataset

    def get(self, path: str, default: Any = None) -> Any:
        """按路径获取超参数值

        示例：
          hp.get("diagnosis.bearing.kurtosis_threshold", 5.0)
          hp.get("diagnosis.ensemble.ds_dominant_prob", 0.4)
        """
        # 先从合并值取
        val = _nested_get(self._merged, path)
        if val is not None:
            return val
        # 回退到 default profile
        profiles = _load_profiles()
        def_profile = profiles.get("default", {})
        val = _nested_get(def_profile, path)
        if val is not None:
            return val
        return default

    def get_float(self, path: str, default: float = 0.0) -> float:
        try:
            return float(self.get(path, default))
        except (TypeError, ValueError):
            return default

    def get_int(self, path: str, default: int = 0) -> int:
        try:
            return int(self.get(path, default))
        except (TypeError, ValueError):
            return default

    def get_list(self, path: str, default=None) -> list:
        val = self.get(path, default)
        if isinstance(val, list):
            return val
        return default if default is not None else []

    def to_dict(self) -> Dict:
        """导出合并后的完整配置（用于调试）"""
        return dict(self._merged)

    def __repr__(self) -> str:
        return f"HyperParams(dataset={self._dataset}, keys={len(self._merged)})"


# ─── 全局便捷函数 ───

def get_hp(device_config: Optional[Dict] = None, dataset: str = "default") -> HyperParams:
    """快捷获取设备超参数（带缓存提示）"""
    return HyperParams.for_device(device_config, dataset)


def reload_profiles() -> None:
    """强制重新加载 dataset_profiles.json（调试用）"""
    global _cached_profiles
    _cached_profiles = None
    _load_profiles()
