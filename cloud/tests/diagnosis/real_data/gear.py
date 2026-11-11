"""齿轮箱原始小样本读取；保留原采样率、辅助电信号及不可判定信息。"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np

from .common import LoadedRecord


def _window(entry: dict, fs: float) -> tuple[int, int]:
    spec = entry.get("_window", {})
    start = float(spec.get("start_seconds", 0))
    duration = float(spec.get("duration_seconds", 5))
    if not math.isfinite(start) or start < 0:
        raise ValueError("window start_seconds must be finite and nonnegative")
    if not math.isfinite(duration) or not 0 < duration <= 5:
        raise ValueError("window duration_seconds must be in (0, 5]")
    return int(start * fs), max(1, int(duration * fs))


def _source(entry: dict, data_root: Path) -> Path:
    root = Path(data_root).resolve()
    relative = Path(entry["source_path"])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root):
        raise ValueError("source_path must stay within data_root")
    return path


def _hust(entry: dict, path: Path, fs: float) -> LoadedRecord:
    # 原文头部之后直接读取窗口，避免整记录加载。8块局部时间各自归零，
    # 块间连续性未获证实，任何窗口都不得跨块拼接。
    with path.open(encoding="utf-8-sig") as stream:
        header: dict[str, str] = {}
        for line in stream:
            if line.strip() == "Time (seconds) and Data Channels":
                break
            if "\t" in line:
                key, value = line.rstrip().split("\t", 1)
                header[key] = value
        else:
            raise ValueError("HUST data marker missing")
        full_count = int(header["Total Data Rows"])
        blocks = int(header["Number of Blocks"])
        if blocks < 1 or full_count <= 0 or full_count % blocks:
            raise ValueError("Invalid HUST block dimensions")
        block_size = full_count // blocks
        start, count = _window(entry, fs)
        if start >= full_count:
            raise ValueError("window starts beyond record")
        count = min(count, block_size - start % block_size, full_count - start)
        for _ in range(start):
            if not stream.readline():
                raise ValueError("HUST record truncated before window")
        values = np.loadtxt(stream, max_rows=count, ndmin=2)
    if values.shape != (count, 5) or not np.isfinite(values).all():
        raise ValueError("Expected finite HUST time/speed/X/Y/Z columns")
    # 时间文本仅保留8位小数，允许其量化误差，不把Frequency Limit当fs。
    if count > 1 and not np.allclose(np.diff(values[:, 0]), 1 / fs, rtol=0, atol=1.1e-8):
        raise ValueError("HUST time steps disagree with declared fs or cross a block")
    metadata = {k: v for k, v in entry.items() if k != "_window"}
    metadata.update(
        source_format="hust_tab_text", full_sample_count=full_count,
        source_shape=[full_count, 5], block_count=blocks,
        continuous_block_sample_count=block_size, block_continuity="unknown",
        loaded_block_index=start // block_size,
        loaded_start_seconds=start / fs, loaded_sample_count=count,
        time_column="block-local seconds; resets at each acquisition block",
        speed_column="uncalibrated electrical signal; never interpreted as Hz",
        sample_rate_evidence="source description 25600 Hz; local time increments agree",
        header=header,
    )
    return LoadedRecord(
        sample_id=entry["sample_id"], dataset_id=entry["dataset_id"], sample_rate_hz=fs,
        vibration={name: values[:, i].copy() for i, name in enumerate(("X", "Y", "Z"), 2)},
        auxiliary={"time": values[:, 0].copy(), "speed": values[:, 1].copy()},
        metadata=metadata,
    )


def _tag(stream: BinaryIO, endian: str, limit: int) -> tuple[int, int, int, int]:
    """返回type/size/payload_offset/next_offset；支持Level5短tag。"""
    raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError("Truncated MAT element tag")
    first_word = struct.unpack(endian + "I", raw[:4])[0]
    # miCOMPRESSED 不适用本 reader 的普通元素对齐检查；先明确拒绝，
    # 避免将合法压缩文件误报为截断并掩盖真正的不支持原因。
    if first_word == 15:
        raise ValueError("Only uncompressed miMATRIX elements are supported")
    if first_word > 0xFFFF:
        small_type, small_size = struct.unpack(endian + "HH", raw[:4])
        if small_size > 4:
            raise ValueError("Invalid small MAT element")
        result = small_type, small_size, stream.tell() - 4, stream.tell()
    else:
        kind, size = struct.unpack(endian + "II", raw)
        result = kind, size, stream.tell(), stream.tell() + ((size + 7) // 8) * 8
    if result[2] + result[1] > limit or result[3] > limit:
        raise ValueError("Truncated MAT element payload")
    return result


def _mat_layout(path: Path) -> tuple[str, dict]:
    # 仅接入已验证的未压缩Level5实double矩阵，拒绝隐式全量解压。
    # 格式依据：MathWorks MAT-File Format, Level 5 data elements。
    size = path.stat().st_size
    matrices = {}
    with path.open("rb") as stream:
        header = stream.read(128)
        if len(header) != 128 or not header.startswith(b"MATLAB 5.0 MAT-file"):
            raise ValueError("Only uncompressed MATLAB Level 5 files are supported")
        endian = {b"IM": "<", b"MI": ">"}.get(header[126:128])
        if endian is None:
            raise ValueError("Invalid MAT endian marker")
        while stream.tell() < size:
            kind, length, offset, end = _tag(stream, endian, size)
            if kind != 14:
                raise ValueError("Only uncompressed miMATRIX elements are supported")
            matrix_end = offset + length
            components = []
            stream.seek(offset)
            for _ in range(4):
                tag = _tag(stream, endian, matrix_end)
                components.append(tag)
                stream.seek(tag[3])
            flags, dims, name, real = components
            if flags[:2] != (6, 8) or dims[0] != 5 or dims[1] != 8 or name[0] != 1:
                raise ValueError("Unsupported MAT matrix layout")
            stream.seek(flags[2])
            class_flags = struct.unpack(endian + "II", stream.read(8))[0]
            if class_flags & 0xFF != 6 or class_flags & 0xA00:
                raise ValueError("Expected real, nonlogical double MAT matrix")
            stream.seek(dims[2])
            shape = struct.unpack(endian + "ii", stream.read(8))
            if min(shape) < 1 or real[0] != 9 or real[1] != math.prod(shape) * 8:
                raise ValueError("Invalid MAT double shape or payload size")
            stream.seek(name[2])
            variable = stream.read(name[1]).decode("ascii")
            if variable in matrices:
                raise ValueError("Duplicate MAT variable")
            matrices[variable] = {"shape": shape, "offset": real[2]}
            stream.seek(end)
    return endian, matrices


def _wt(entry: dict, path: Path, fs: float) -> LoadedRecord:
    endian, layout = _mat_layout(path)
    required = ("Data", "DataCount", "ChannelCount", "SampleRate", "Interval")
    if any(name not in layout for name in required):
        raise ValueError("WT metadata or Data variable missing")
    scalars = {}
    with path.open("rb") as stream:
        for name in required[1:]:
            if layout[name]["shape"] != (1, 1):
                raise ValueError(f"WT {name} must be scalar")
            stream.seek(layout[name]["offset"])
            scalars[name] = struct.unpack(endian + "d", stream.read(8))[0]
    shape = layout["Data"]["shape"]
    if shape[1] != 4 or scalars["DataCount"] != shape[0] or scalars["ChannelCount"] != 4:
        raise ValueError("WT Data shape disagrees with verified four-channel layout")
    if not math.isclose(scalars["SampleRate"], fs, rel_tol=1e-12) or not math.isclose(
        scalars["Interval"], 1 / fs, rel_tol=1e-12
    ):
        raise ValueError("WT SampleRate/Interval disagree with manifest fs_hz")
    start, count = _window(entry, fs)
    if start >= shape[0]:
        raise ValueError("window starts beyond record")
    count = min(count, shape[0] - start)
    mapped = np.memmap(path, mode="r", dtype=endian + "f8", offset=layout["Data"]["offset"], shape=shape, order="F")
    try:
        values = np.array(mapped[start:start + count, :], dtype=np.float64, copy=True)
    finally:
        # 输出不依赖映射，及时释放Windows文件句柄。
        mapped._mmap.close()
    if not np.isfinite(values).all():
        raise ValueError("WT window contains nonfinite samples")
    metadata = {k: v for k, v in entry.items() if k != "_window"}
    metadata.update(
        source_format="matlab_level5_uncompressed_double", source_shape=list(shape),
        full_sample_count=shape[0], loaded_start_seconds=start / fs,
        loaded_sample_count=count, mat_scalars=scalars,
        sample_rate_evidence="local MAT SampleRate and Interval agree with source 48000 Hz",
        encoder_column="uncalibrated electrical signal; pulses per revolution unknown",
        channel_4="unknown purpose and units; retained without interpretation",
    )
    return LoadedRecord(
        sample_id=entry["sample_id"], dataset_id=entry["dataset_id"], sample_rate_hz=fs,
        vibration={"X": values[:, 0].copy(), "Y": values[:, 1].copy()},
        auxiliary={"encoder": values[:, 2].copy(), "raw_channel_4": values[:, 3].copy()},
        metadata=metadata,
    )


def load_record(entry: dict, data_root: Path) -> LoadedRecord:
    """读取单条原记录的有限窗口，不重采样、不估转速。

    ``_window``可选start_seconds/duration_seconds，默认0/5，最长5秒；
    HUST额外截断到当前1.28秒块末端，避免假定块间连续。起点是按fs换算
    的记录行索引，不代表已证实的跨块物理时间。MAT只支持本地核实过的
    四列未压缩Level5实double格式，拒绝不受控解压或HDF5回退。
    """
    fs = float(entry["fs_hz"])
    if not math.isfinite(fs) or fs <= 0:
        raise ValueError("fs_hz must be finite and positive")
    path = _source(entry, data_root)
    dataset = entry["dataset_id"]
    if dataset == "hust_gearbox":
        return _hust(entry, path, fs)
    if dataset == "wt_planetary":
        return _wt(entry, path, fs)
    raise ValueError(f"Unsupported gear dataset: {dataset}")
