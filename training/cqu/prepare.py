"""生成可追溯的离线输入缓存；只在全部核验完成后写出成功摘要。"""

import argparse
import json
from pathlib import Path
import platform

import numpy as np
import scipy

from .catalog import (EXPERIMENTS, PACKAGE, REPO_ROOT, build_splits, load_catalog,
                      resolve_cqu_root, sha256_file, source_path, verify_sources)
from .preprocessing import PROTOCOL, preprocess_channel, read_record


def write_json(path: Path, value: object) -> None:
    """写严格UTF-8 JSON，不接受NaN；不得覆盖已有本轮产物。"""
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(output: Path, data_root: Path | None = None) -> dict:
    """核验70份源数据，保存文件划分、105个通道缓存及逐窗来源。"""
    output = Path(output).resolve()
    # 本项目要求现场数据产物留在忽略目录，避免写入源数据或提交权重。
    allowed = (REPO_ROOT / "tmp/cqu").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError("输出必须是本仓库tmp/cqu内新的任务子目录")
    cqu_root = resolve_cqu_root(data_root)
    catalog = load_catalog()
    records = catalog["records"]
    splits = build_splits(records)
    before = verify_sources(records, cqu_root)
    output.mkdir(parents=True, exist_ok=False)
    (output / "arrays").mkdir()
    write_json(output / "catalog.json", catalog)
    write_json(output / "splits.json", splits)
    write_json(output / "protocol.json", PROTOCOL)
    assets = []
    with (output / "windows.jsonl").open("x", encoding="utf-8", newline="\n") as index_file:
        for number, record in enumerate(records, start=1):
            raw = read_record(source_path(record, cqu_root), record)
            channels = sorted({e["channel"] for e in EXPERIMENTS.values()
                               if e["device"] == record["device"]})
            for channel in channels:
                signal = raw[:, channel - 1]
                windows, stats = preprocess_channel(signal)
                relative = f"arrays/{record['record_id']}_ch{channel}.npy"
                path = output / relative
                with path.open("xb") as stream:
                    np.save(stream, windows, allow_pickle=False)
                asset = {
                    "record_id": record["record_id"], "channel": channel,
                    "array_path": relative, "array_sha256": sha256_file(path),
                    "shape": list(windows.shape), "dtype": str(windows.dtype),
                    "raw_full_record_mean_mps2": float(signal.mean()),
                    "raw_full_record_std_mps2": float(signal.std()),
                    "raw_full_record_rms_mps2": float(np.sqrt(np.mean(signal ** 2))),
                }
                assets.append(asset)
                for stat in stats:
                    stat.update(record_id=record["record_id"], channel=channel,
                                raw_file=record["raw_file"], array_path=relative,
                                binary_label=record["binary_label"],
                                device=record["device"], role=record["role"])
                    index_file.write(json.dumps(stat, ensure_ascii=False, allow_nan=False) + "\n")
            print(f"[{number}/{len(records)}] {record['raw_file']}", flush=True)
    after = verify_sources(records, cqu_root)
    manifest = {
        "schema_version": 1, "complete": True,
        "protocol": PROTOCOL,
        "catalog_sha256": sha256_file(output / "catalog.json"),
        "splits_sha256": sha256_file(output / "splits.json"),
        "windows_index_sha256": sha256_file(output / "windows.jsonl"),
        "preparation_code_sha256": {
            name: sha256_file(PACKAGE / name)
            for name in ("catalog.py", "preprocessing.py", "prepare.py")
        },
        "environment": {"python": platform.python_version(),
                        "numpy": np.__version__, "scipy": scipy.__version__},
        "source_checks_before": before, "source_checks_after": after,
        "records": len(records), "primary_records": 42, "historical_records": 28,
        "record_channels": len(assets), "windows": sum(a["shape"][0] for a in assets),
        "assets": assets,
    }
    write_json(output / "prepared.json", manifest)
    return manifest


def iter_partition(prepared_dir: Path, experiment: str, fold: int, split: str):
    """按已冻结的文件分组读取单通道窗口，不跨设备/通道合并或丢弃尾批。"""
    prepared_dir = Path(prepared_dir)
    manifest = json.loads((prepared_dir / "prepared.json").read_text(encoding="utf-8"))
    if not manifest["complete"] or manifest["protocol"] != PROTOCOL:
        raise ValueError("缓存未完成或预处理协议不符")
    for name, key in (("catalog.json", "catalog_sha256"), ("splits.json", "splits_sha256")):
        if sha256_file(prepared_dir / name) != manifest[key]:
            raise ValueError(f"缓存来源或划分已变化：{name}")
    catalog = load_catalog(prepared_dir / "catalog.json")
    splits = json.loads((prepared_dir / "splits.json").read_text(encoding="utf-8"))
    from .catalog import validate_splits
    validate_splits(catalog["records"], splits)
    if fold not in (0, 1, 2) or split not in ("train", "validation", "test", "historical"):
        raise ValueError("未知折编号或集合")
    config = EXPERIMENTS[experiment]
    selected = {r["record_id"]: r for r in catalog["records"]
                if r["device"] == config["device"]
                and splits["folds"][fold]["assignments"][r["record_id"]] == split}
    for asset in manifest["assets"]:
        if asset["record_id"] not in selected or asset["channel"] != config["channel"]:
            continue
        path = prepared_dir / asset["array_path"]
        if sha256_file(path) != asset["array_sha256"]:
            raise ValueError("输入缓存已变化，不能继续使用")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if array.shape != (60, 1, 4096) or array.dtype != np.float32:
            raise ValueError("缓存张量形状或类型不符")
        record = selected[asset["record_id"]]
        for index in range(len(array)):
            yield {"x": array[index].copy(), "label": record["binary_label"],
                   "record_id": record["record_id"], "channel": config["channel"],
                   "window_index": index, "nominal_motor_rpm": record["nominal_motor_rpm"],
                   "sequence_group": record["sequence_group"]}


def main() -> None:
    """命令行入口不启动训练，也不安装依赖或访问网络。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, help="含CQU子目录的数据根目录；默认CNN_DATA_ROOT或data")
    parser.add_argument("--output", type=Path, required=True, help="tmp/cqu下尚不存在的新结果目录")
    args = parser.parse_args()
    result = prepare(args.output, args.data_root)
    print(json.dumps({k: result[k] for k in ("complete", "records", "record_channels", "windows")}))


if __name__ == "__main__":
    main()
