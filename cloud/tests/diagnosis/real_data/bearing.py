"""轴承原始记录读取边界；保留原采样率、原测速波形及采集身份。"""

from itertools import islice
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .common import LoadedRecord

_SAMPLE_RATES = {"ottawa_bearing": 200_000.0, "hust_bearing": 25_600.0}


def _source_path(entry: dict, data_root: Path) -> Path:
    """清单只接受数据根内的相对路径，避免工作区/来源盘混读。"""
    relative = Path(entry["source_path"])
    if relative.is_absolute() or relative.drive:
        raise ValueError("source_path must be relative to data_root")
    root = data_root.resolve()
    source = (root / relative).resolve()
    if not source.is_relative_to(root):
        raise ValueError("source_path escapes data_root")
    return source


def _vector(value: np.ndarray, name: str) -> np.ndarray:
    values = np.asarray(value)
    if values.ndim not in (1, 2) or (values.ndim == 2 and 1 not in values.shape):
        raise ValueError(f"{name} must be a vector, got {values.shape}")
    if not np.issubdtype(values.dtype, np.number) or np.iscomplexobj(values):
        raise ValueError(f"{name} must contain real numeric samples")
    values = values.reshape(-1)
    if not values.size or not np.isfinite(values).all():
        raise ValueError(f"{name} must contain nonempty finite samples")
    return values


def _read_hust(
    source: Path, fs: float, window: tuple[int, int] | None
) -> tuple[dict, dict, dict]:
    """原xls实际为文本头+TSV；Speed不是经过标定的Hz。"""
    header = []
    with source.open("r", encoding="utf-8-sig") as handle:
        for _ in range(1000):
            line = handle.readline()
            if not line:
                raise ValueError("HUSTbear file is missing the Data marker")
            if line.strip() == "Data":
                break
            header.append(line.rstrip("\r\n"))
        else:
            raise ValueError("HUSTbear header exceeds 1000 lines")
        declared_rows = next(
            (
                int(line.split("\t")[1])
                for line in header
                if line.startswith("Total Data Rows\t")
            ),
            None,
        )
        if declared_rows is None or declared_rows <= 0:
            raise ValueError("HUSTbear is missing a valid Total Data Rows")
        if window is None:
            values = np.loadtxt(handle, delimiter="\t", dtype=np.float64, ndmin=2)
        else:
            start, size = window
            if start + size > declared_rows:
                raise ValueError("Requested window exceeds original record")
            values = np.loadtxt(
                islice(handle, start, start + size),
                delimiter="\t",
                dtype=np.float64,
                ndmin=2,
            )
    legend = next(
        (line.split("\t")[1:] for line in header if line.startswith("Legend\t")), None
    )
    if legend != ["Speed", "X", "Y", "Z"]:
        raise ValueError(f"Unsupported HUSTbear channel legend: {legend}")
    if values.shape[1] != 5 or not len(values):
        raise ValueError(
            f"HUSTbear expects time/Speed/X/Y/Z columns, got {values.shape}"
        )
    channels = {
        name: _vector(values[:, index], name)
        for index, name in enumerate(["time", *legend])
    }
    if len(values) != (declared_rows if window is None else window[1]):
        raise ValueError("HUSTbear Total Data Rows does not match parsed rows")
    # 原时间列保留到微秒，不能用逐点差分的舍入噪声推翻原说明采样率。
    expected_time = channels["time"][0] + np.arange(len(values)) / fs
    if np.any(np.diff(channels["time"]) <= 0) or not np.allclose(
        channels["time"], expected_time, rtol=0, atol=1e-6
    ):
        raise ValueError("HUSTbear time column disagrees with the original sample rate")
    return (
        {name: channels[name] for name in ("X", "Y", "Z")},
        {name: channels[name] for name in ("time", "Speed")},
        {
            "raw_header": header,
            "declared_rows": declared_rows,
            "original_columns": ["time", *legend],
        },
    )


def load_record(entry: dict, data_root: Path) -> LoadedRecord:
    """读取单次采集，不降采样、不归一化、不生成转速真值。

    entry来自schema_version=1清单，包含sample_id/dataset_id/source_path/fs_hz。
    entry可带_window={start_seconds,duration_seconds}显式选择原采样网格窗口；
    默认读取完整记录，窗口不改变fs。data_root为原始数据统一根目录。辅助通道保留原名与数值；其电压/脉冲
    未标定，不能当作Hz传入诊断。所有振动轴仍属于同一sample_id/group_id。
    """
    dataset = entry["dataset_id"]
    if dataset not in _SAMPLE_RATES:
        raise ValueError(f"Unsupported bearing dataset_id: {dataset}")
    fs = float(entry["fs_hz"])
    if fs != _SAMPLE_RATES[dataset]:
        raise ValueError(
            f"{dataset} original sample rate must be {_SAMPLE_RATES[dataset]} Hz"
        )
    source = _source_path(entry, Path(data_root))
    window = None
    if "_window" in entry:
        start = float(entry["_window"].get("start_seconds", 0))
        duration = float(entry["_window"]["duration_seconds"])
        if (
            not np.isfinite(start)
            or not np.isfinite(duration)
            or start < 0
            or duration <= 0
        ):
            raise ValueError(
                "Requested window must have finite nonnegative start and positive duration"
            )
        window = round(start * fs), round(duration * fs)
        if window[1] < 1:
            raise ValueError("Requested window is shorter than one original sample")
    details = {}
    if dataset == "ottawa_bearing":
        raw = loadmat(source, variable_names=["Channel_1", "Channel_2"])
        missing = {"Channel_1", "Channel_2"} - raw.keys()
        if missing:
            raise ValueError(
                f"Ottawa MAT is missing original channels: {sorted(missing)}"
            )
        vibration = {"Channel_1": _vector(raw["Channel_1"], "Channel_1")}
        auxiliary = {"Channel_2": _vector(raw["Channel_2"], "Channel_2")}
        if len(vibration["Channel_1"]) != len(auxiliary["Channel_2"]):
            raise ValueError("Original channels have unequal lengths")
        full_count = len(vibration["Channel_1"])
        if window is not None:
            start, size = window
            if start + size > full_count:
                raise ValueError("Requested window exceeds original record")
            # copy使短窗口不继续持有整个MAT通道内存。
            vibration = {
                name: values[start : start + size].copy()
                for name, values in vibration.items()
            }
            auxiliary = {
                name: values[start : start + size].copy()
                for name, values in auxiliary.items()
            }
        details["original_columns"] = ["Channel_1", "Channel_2"]
    else:
        vibration, auxiliary, details = _read_hust(source, fs, window)
        full_count = details["declared_rows"]
    lengths = {len(values) for values in [*vibration.values(), *auxiliary.values()]}
    if len(lengths) != 1:
        raise ValueError("Original channels have unequal lengths")
    count = lengths.pop()
    if "expected_samples" in entry and full_count != int(entry["expected_samples"]):
        raise ValueError(
            f"Expected {entry['expected_samples']} samples, found {full_count}"
        )
    duration = count / fs
    if "expected_duration_seconds" in entry and not np.isclose(
        full_count / fs, float(entry["expected_duration_seconds"]), rtol=0, atol=1 / fs
    ):
        raise ValueError("Original duration does not match the manifest")
    metadata = dict(entry.get("metadata", {}))
    metadata.update(
        {
            key: entry[key]
            for key in (
                "source_path",
                "original_source_path",
                "sha256",
                "acquisition_id",
                "group_id",
                "label",
                "original_label",
                "fault_types",
                "severity",
                "channel_roles",
            )
            if key in entry
        }
    )
    metadata.update(details)
    metadata.update(
        {
            "n_samples": count,
            "duration_seconds": duration,
            "full_sample_count": full_count,
            "loaded_start_seconds": 0.0 if window is None else window[0] / fs,
            "auxiliary_is_calibrated_speed_hz": False,
            "resampled": False,
        }
    )
    return LoadedRecord(
        sample_id=entry["sample_id"],
        dataset_id=dataset,
        sample_rate_hz=fs,
        vibration=vibration,
        auxiliary=auxiliary,
        metadata=metadata,
    )
