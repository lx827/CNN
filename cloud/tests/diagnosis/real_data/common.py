"""真实原始记录的公共身份、路径与 manifest 契约。"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class LoadedRecord:
    """一次原始采集中的已加载窗口；多通道和切窗不增加独立采集数。

    vibration 为一维振动窗口，auxiliary 保留 time/encoder/speed 等原角色。
    sample_rate_hz 只表示采样率，未经标定的辅助列不能用作转频。
    metadata 保存来源、全记录规模、实际窗口和未解决的物理前提。
    """

    sample_id: str
    dataset_id: str
    sample_rate_hz: float
    vibration: dict[str, np.ndarray]
    auxiliary: dict[str, np.ndarray]
    metadata: dict


DATASETS = frozenset({"ottawa_bearing", "hust_bearing", "hust_gearbox", "wt_planetary"})


def resolve_data_root(value: str | Path | None = None) -> Path:
    """优先显式参数，其次 CNN_DATA_ROOT，最后为当前 checkout 的 data。"""
    selected = value if value is not None else os.environ.get("CNN_DATA_ROOT")
    return (
        Path(selected).expanduser().resolve()
        if selected
        else Path(__file__).resolve().parents[4] / "data"
    )


def resolve_source_path(data_root: Path, source_path: str) -> Path:
    """manifest 仅允许 DATA_ROOT 内的相对源路径。"""
    relative = Path(source_path)
    if relative.is_absolute() or relative.drive:
        raise ValueError("source_path must be relative to data_root")
    root = Path(data_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("source_path escapes data_root")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def load_manifest(path: Path) -> list[dict]:
    """读取严格 schema_version=1 清单；空清单、重复身份或缺字段均报错。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported manifest schema: {path}")
    samples = payload.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"manifest contains no samples: {path}")
    identities = set()
    for entry in samples:
        if not isinstance(entry, dict):  # JSON 内容错误按统一清单校验异常报告。
            raise ValueError("manifest sample must be an object")  # noqa: TRY004
        for field in ("sample_id", "dataset_id", "source_path", "label", "group_id"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"manifest sample requires nonempty {field}")
        if entry["dataset_id"] not in DATASETS:
            raise ValueError(f"unsupported dataset_id: {entry['dataset_id']}")
        if entry["sample_id"] in identities:
            raise ValueError(f"duplicate sample_id: {entry['sample_id']}")
        identities.add(entry["sample_id"])
        fs = entry.get("fs_hz")
        if (
            isinstance(fs, bool)
            or not isinstance(fs, (int, float))
            or not math.isfinite(fs)
            or fs <= 0
        ):
            raise ValueError("manifest fs_hz must be finite and positive")
        if not isinstance(entry.get("fault_types"), list) or not all(
            isinstance(x, str) for x in entry["fault_types"]
        ):
            raise ValueError("manifest fault_types must be a list of strings")
    return samples


def json_value(value):
    """严格 JSON：非有限数显式 null，不把大信号数组写入报告。"""
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value
