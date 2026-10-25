"""固定现场记录身份，先按完整文件分组，禁止通过切窗或通道改变分组。"""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


PACKAGE = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE.parents[1]
PRIMARY = "primary_candidate"
HISTORICAL = "historical_batch_check_only"
RPM_LEVELS = (200, 600, 1000)
EXPERIMENTS = {
    "device1_ch2": {"device": 1, "channel": 2, "purpose": "main"},
    "device1_ch1": {"device": 1, "channel": 1, "purpose": "comparison"},
    "device2_ch3": {"device": 2, "channel": 3, "purpose": "main"},
}


def sha256_file(path: Path) -> str:
    """分块校验源文件，避免一次性读取整批数据。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_catalog(path: Path = PACKAGE / "catalog.json") -> dict:
    """读取已冻结的70份元数据；新增或变化记录必须先重新核实来源。"""
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if catalog["schema_version"] != 1:
        raise ValueError("不支持的清单版本")
    records = catalog["records"]
    if len(records) != 70:
        raise ValueError("本轮固定范围应为70份")
    for field in ("record_id", "raw_file", "numeric_sha256_prior_qc"):
        if len({r[field] for r in records}) != len(records):
            raise ValueError(f"记录身份或四通道数值重复：{field}")
    for record in records:
        relative = PurePosixPath(record["raw_file"])
        if relative.is_absolute() or len(relative.parts) != 1 or "\\" in str(relative):
            raise ValueError("源文件必须是CQU目录内的单个文件名")
        if relative.suffix.lower() != ".csv":
            raise ValueError("本轮只支持已确认的CSV")
        if record["source_sha256"] != record["record_id"]:
            raise ValueError("文件身份必须等于原始字节哈希")
        expected_label = "normal" if record["binary_label"] == 0 else {
            1: "imbalance", 2: "outer_race"
        }.get(record["device"])
        if record["binary_label"] not in (0, 1) or record["label"] != expected_label:
            raise ValueError("现场标签与设备不符")
        if record["sample_rate_hz"] != 10000 or record["unit"] != "m/s²":
            raise ValueError("不允许静默变更采样率或单位")
        if record["role"] not in (PRIMARY, HISTORICAL):
            raise ValueError("未知的数据用途")
        if record["role"] == HISTORICAL and record["binary_label"] != 1:
            raise ValueError("本轮历史范围只包含故障记录")
    for device in (1, 2):
        subset = [r for r in records if r["device"] == device]
        if Counter(r["role"] for r in subset) != {PRIMARY: 21, HISTORICAL: 14}:
            raise ValueError("每台设备应为21份主要记录和14份历史记录")
        strata = Counter((r["nominal_motor_rpm"], r["binary_label"])
                         for r in subset if r["role"] == PRIMARY)
        expected = {(rpm, label): 3 + label for rpm in RPM_LEVELS for label in (0, 1)}
        if strata != expected:
            raise ValueError("主要记录应在每档转速包含正常3份、故障4份")
    return catalog


def resolve_cqu_root(data_root: Path | None = None) -> Path:
    """参数和CNN_DATA_ROOT均指向含CQU子目录的数据根目录。"""
    root = data_root if data_root is not None else os.environ.get("CNN_DATA_ROOT")
    return (Path(root) if root is not None else REPO_ROOT / "data").resolve() / "CQU"


def source_path(record: dict, cqu_root: Path) -> Path:
    """限制为指定CQU目录内的普通源文件，不跟随文件级符号链接。"""
    path = cqu_root / record["raw_file"]
    if path.is_symlink() or not path.is_file() or path.resolve().parent != cqu_root.resolve():
        raise ValueError(f"源路径不存在或越界：{record['raw_file']}")
    return path


def verify_sources(records: list[dict], cqu_root: Path) -> dict:
    """核对全部CSV的范围与原始字节；不接受静默新增、缺失或修改。"""
    expected = {r["raw_file"] for r in records}
    actual = {p.relative_to(cqu_root).as_posix() for p in cqu_root.rglob("*")
              if p.is_file() and p.suffix.lower() == ".csv"}
    if actual != expected:
        raise ValueError(f"CSV范围变化：缺失={sorted(expected - actual)}；新增={sorted(actual - expected)}")
    for record in records:
        if sha256_file(source_path(record, cqu_root)) != record["source_sha256"]:
            raise ValueError(f"原始文件已变化：{record['raw_file']}")
    return {"files": len(records), "all_source_hashes_match": True}


def build_splits(records: list[dict]) -> dict:
    """三折外层轮换；每折每设备训练8、验证6、外层留出7份。"""
    folds = []
    for fold in range(3):
        assignment = {r["record_id"]: "historical" for r in records
                      if r["role"] == HISTORICAL}
        for device in (1, 2):
            for rpm_index, rpm in enumerate(RPM_LEVELS):
                for label in (0, 1):
                    group = sorted((r for r in records if r["device"] == device
                                    and r["role"] == PRIMARY
                                    and r["nominal_motor_rpm"] == rpm
                                    and r["binary_label"] == label),
                                   key=lambda r: (r["capture_start_csv"], r["raw_file"]))
                    # 三份正常逐折各留一份；四份故障按2/1/1分配，双份档位轮换。
                    remaining = []
                    for index, record in enumerate(group):
                        outer_fold = index % 3 if label == 0 else (index + rpm_index) % 3
                        if outer_fold == fold:
                            assignment[record["record_id"]] = "test"
                        else:
                            remaining.append(record)
                    # 只在本折训练侧选验证记录；规则由顺序确定，不读取信号或成绩。
                    validation = remaining[fold % len(remaining)]["record_id"]
                    for record in remaining:
                        assignment[record["record_id"]] = (
                            "validation" if record["record_id"] == validation else "train")
        folds.append({"fold": fold, "assignments": assignment})
    result = {
        "schema_version": 1,
        "protocol": "chronological_stratified_three_fold_v1",
        "evaluation_scope": "development_only_not_independent_installation_or_blind_test",
        "group_unit": "entire_csv_all_channels_all_windows_all_augmentations",
        "experiments": EXPERIMENTS,
        "folds": folds,
    }
    validate_splits(records, result)
    return result


def validate_splits(records: list[dict], splits: dict) -> None:
    """检查覆盖、比例、类别和转速；历史文件不能进入训练或选权重。"""
    if [f["fold"] for f in splits["folds"]] != [0, 1, 2]:
        raise ValueError("必须有三个不重复的折编号")
    for item in splits["folds"]:
        assignment = item["assignments"]
        if set(assignment) != {r["record_id"] for r in records}:
            raise ValueError("划分未完整覆盖文件")
        for record in records:
            allowed = ("train", "validation", "test") if record["role"] == PRIMARY else ("historical",)
            if assignment[record["record_id"]] not in allowed:
                raise ValueError("历史与主要用途混用")
        for device in (1, 2):
            subset = [r for r in records if r["device"] == device]
            counts = Counter(assignment[r["record_id"]] for r in subset)
            if counts != {"train": 8, "validation": 6, "test": 7, "historical": 14}:
                raise ValueError("每折记录比例不符")
            for split in ("train", "validation", "test"):
                cells = {(r["nominal_motor_rpm"], r["binary_label"]) for r in subset
                         if assignment[r["record_id"]] == split}
                if cells != {(rpm, label) for rpm in RPM_LEVELS for label in (0, 1)}:
                    raise ValueError("某个集合未覆盖全部转速与类别")
    for record in records:
        if record["role"] == PRIMARY:
            if sum(f["assignments"][record["record_id"]] == "test" for f in splits["folds"]) != 1:
                raise ValueError("主要文件必须且仅能在一个外层折留出")
