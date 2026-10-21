"""
数据集路径统一入口

所有数据集统一放在仓库根目录的 data/ 下，使用仓库相对路径：
换机器、换盘符、克隆到其他目录都无需修改代码。

数据集也可以放在仓库外，通过环境变量覆盖：
    CNN_DATA_ROOT     数据集根目录（默认 <仓库根>/data）
    HUSTBEAR_DIR      HUSTbear 数据目录
    CW_DIR            CW 数据目录
    WTGEARBOX_DIR     WTgearbox 数据目录
    HUSTGEARBOX_DIR   HUSTgearbox 数据目录
    CQU_DIR           CQU 现场 CSV 目录
"""
import os
from pathlib import Path

# tests/diagnosis/data_paths.py -> 仓库根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 数据集根目录，可用 CNN_DATA_ROOT 指向仓库外的数据目录
DATA_ROOT = Path(os.environ.get("CNN_DATA_ROOT", PROJECT_ROOT / "data"))


def _dataset_dir(env_name: str, *parts: str) -> Path:
    """优先读取环境变量，否则拼到 DATA_ROOT 下"""
    override = os.environ.get(env_name)
    return Path(override) if override else DATA_ROOT.joinpath(*parts)


HUSTBEAR_DIR = _dataset_dir("HUSTBEAR_DIR", "HUSTbear", "down8192")
CW_DIR = _dataset_dir("CW_DIR", "CW", "down8192_CW")
WTGEARBOX_DIR = _dataset_dir("WTGEARBOX_DIR", "WTgearbox", "down8192")
HUSTGEARBOX_DIR = _dataset_dir("HUSTGEARBOX_DIR", "HUSTgearbox", "down8192")
CQU_DIR = _dataset_dir("CQU_DIR", "CQU")
