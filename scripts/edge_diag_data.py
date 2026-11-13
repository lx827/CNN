"""边端诊断 POC 基准数据生成。

产出 <data_root>/edge_diag/ 下:
- synth_L{n}_fs10000.f64        确定性合成信号,float64 小端裸二进制,n=5000/50000/128000
- hustbear_L128000_fs25600.f64  HUSTbear X 通道真实切段 128000 点
- manifest.json                 文件、采样率、点数、来源与生成时间

数据根:--data-root > CNN_DATA_ROOT > 本 checkout 的 data/;独立 worktree
按 docs/datasets.md 约定经 CNN_DATA_ROOT 共享主仓数据目录。

用法:仓库根 `uv run python scripts/edge_diag_data.py`(仅依赖 numpy)。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------- 合成信号参数 ----------
FS_SYNTH = 10_000.0
SEED = 42
LENGTHS = (5_000, 50_000, 128_000)
F0 = 25.0  # 基频,Hz
HARMONIC_ORDERS = (1, 2, 3, 4)  # 基频及 2/3/4 次谐波
NOISE_POWER_RATIO = 0.1  # 噪声方差 = 谐波总功率 / 10
# 轴承冲击串(确定性,重复率与 25 Hz 不成整数比)
IMPACT_RATE_HZ = 107.3
IMPACT_RESONANCE_HZ = 1_500.0
IMPACT_TAU_S = 0.004  # 冲击指数衰减时间常数
IMPACT_AMPLITUDE = 0.15

# ---------- HUSTbear 真实切段参数 ----------
# 格式与采样率见 docs/datasets.md:文本头 + TSV,time/Speed/X/Y/Z 五列,25600 Hz
HUST_SOURCE = Path("raw_sources/HUSTbear/representative_excel/raw data/H_20Hz.xls")
HUST_FS = 25_600.0
HUST_COLUMN_INDEX = 2  # X 振动通道
HUST_OFFSET = 0
HUST_LENGTH = 128_000
HUST_FILE = "hustbear_L128000_fs25600.f64"


def synth_signal(n: int, impacts: bool) -> np.ndarray:
    """一段合成信号:谐波 + 高斯噪声 + 可选轴承冲击串。

    每个文件独立以 SEED 播种,内容只由 (n, impacts) 决定,同参数重跑逐位一致。
    """
    rng = np.random.default_rng(SEED)
    t = np.arange(n) / FS_SYNTH
    amplitudes = np.array([1.0 / k for k in HARMONIC_ORDERS])  # 幅值随谐波次序递减
    phases = rng.uniform(0.0, 2.0 * np.pi, len(HARMONIC_ORDERS))
    signal = np.zeros(n)
    for amplitude, order, phase in zip(amplitudes, HARMONIC_ORDERS, phases):
        signal += amplitude * np.sin(2.0 * np.pi * order * F0 * t + phase)
    harmonic_power = float(np.sum(amplitudes**2)) / 2.0
    signal += rng.normal(0.0, np.sqrt(harmonic_power * NOISE_POWER_RATIO), n)
    if impacts:
        signal += impact_train(n)
    return signal


def impact_train(n: int) -> np.ndarray:
    """确定性轴承冲击串:周期单位脉冲经指数衰减共振核展开,无随机量。"""
    kernel_len = int(np.ceil(6.0 * IMPACT_TAU_S * FS_SYNTH))  # 6 倍时间常数后衰减殆尽
    idx = np.arange(kernel_len)
    kernel = (
        IMPACT_AMPLITUDE
        * np.exp(-idx / (IMPACT_TAU_S * FS_SYNTH))
        * np.sin(2.0 * np.pi * IMPACT_RESONANCE_HZ * idx / FS_SYNTH)
    )
    train = np.zeros(n)
    positions = np.arange(0.0, n, FS_SYNTH / IMPACT_RATE_HZ).astype(np.int64)
    train[positions] = 1.0
    return np.convolve(train, kernel)[:n]


def hustbear_segment(path: Path) -> np.ndarray:
    """跳过文本头到 Data 标记行,读 X 通道整列,取固定偏移的切段。"""
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip() == "Data":
                break
        column = np.loadtxt(handle, delimiter="\t", usecols=(HUST_COLUMN_INDEX,), dtype=np.float64)
    return column[HUST_OFFSET : HUST_OFFSET + HUST_LENGTH]


def resolve_data_root(value: str | None) -> Path:
    """显式参数 > CNN_DATA_ROOT > 本 checkout 的 data/。"""
    selected = value if value is not None else os.environ.get("CNN_DATA_ROOT")
    if selected:
        return Path(selected).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data"


def write_f64(path: Path, values: np.ndarray) -> int:
    """float64 小端裸二进制落盘,返回字节数。"""
    values.astype("<f8", copy=False).tofile(path)
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description="生成边端诊断 POC 基准数据")
    parser.add_argument("--data-root", help="数据根(默认 CNN_DATA_ROOT 或仓库根 data/)")
    parser.add_argument("--no-impacts", action="store_true", help="合成信号不含轴承冲击串")
    args = parser.parse_args()

    data_root = resolve_data_root(args.data_root)
    out_dir = data_root / "edge_diag"
    out_dir.mkdir(parents=True, exist_ok=True)
    impacts = not args.no_impacts

    synth_files = []
    for n in LENGTHS:
        name = f"synth_L{n}_fs10000.f64"
        size = write_f64(out_dir / name, synth_signal(n, impacts))
        synth_files.append({"file": name, "fs_hz": FS_SYNTH, "n": n, "dtype": "<f8", "bytes": size})
        print(f"{name}: {n} 点, {size} 字节")

    hust_path = data_root / HUST_SOURCE
    size = write_f64(out_dir / HUST_FILE, hustbear_segment(hust_path))
    print(f"{HUST_FILE}: {HUST_LENGTH} 点, {size} 字节 (源 {hust_path} 偏移 {HUST_OFFSET})")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "synthetic": {
            "seed": SEED,
            "fs_hz": FS_SYNTH,
            "f0_hz": F0,
            "harmonic_orders": list(HARMONIC_ORDERS),
            "harmonic_amplitudes": [1.0 / k for k in HARMONIC_ORDERS],
            "noise_power_ratio": NOISE_POWER_RATIO,
            "bearing_impacts": None
            if not impacts
            else {
                "rate_hz": IMPACT_RATE_HZ,
                "resonance_hz": IMPACT_RESONANCE_HZ,
                "decay_tau_s": IMPACT_TAU_S,
                "amplitude": IMPACT_AMPLITUDE,
            },
            "files": synth_files,
        },
        "hustbear": {
            "source_path": HUST_SOURCE.as_posix(),
            "dataset_id": "hust_bearing",
            "channel": "X",
            "fs_hz": HUST_FS,
            "offset_points": HUST_OFFSET,
            "n": HUST_LENGTH,
            "dtype": "<f8",
            "bytes": size,
            "file": HUST_FILE,
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
