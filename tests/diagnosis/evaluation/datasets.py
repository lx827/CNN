"""
数据集加载与分类
"""
from pathlib import Path
from typing import Dict, List, Tuple

from .config import HUSTBEAR_DIR, CW_DIR, WTGEARBOX_DIR
from .utils import load_npy


def classify_hustbear(filename: str) -> Dict:
    """HUSTbear文件分类"""
    parts = filename.replace(".npy", "").split("-")
    name_part = parts[0]
    channel = parts[1] if len(parts) > 1 else "X"
    # 支持格式: H_20Hz, 0.5X_B_20Hz, B_20Hz 等
    if name_part.startswith("H_") or "_N_" in name_part:
        return {"label": "healthy", "fault": None, "channel": channel}
    elif "_B_" in name_part or name_part.startswith("B_"):
        return {"label": "ball", "fault": "ball", "channel": channel}
    elif "_IR_" in name_part or name_part.startswith("IR_"):
        return {"label": "inner", "fault": "inner", "channel": channel}
    elif "_OR_" in name_part or name_part.startswith("OR_"):
        return {"label": "outer", "fault": "outer", "channel": channel}
    elif "_C_" in name_part or name_part.startswith("C_"):
        return {"label": "composite", "fault": "composite", "channel": channel}
    elif "_I_" in name_part or name_part.startswith("I_"):
        return {"label": "inner", "fault": "inner", "channel": channel}
    return {"label": "unknown", "fault": None, "channel": channel}


def classify_cw(filename: str) -> Dict:
    """CW文件分类"""
    name = filename.replace(".npy", "")
    parts = name.split("-")
    health_state = parts[0]
    if health_state == "H":
        return {"label": "healthy", "fault": None, "speed_mode": parts[1], "seq": parts[2]}
    elif health_state == "I":
        return {"label": "inner", "fault": "inner", "speed_mode": parts[1], "seq": parts[2]}
    elif health_state == "O":
        return {"label": "outer", "fault": "outer", "speed_mode": parts[1], "seq": parts[2]}
    return {"label": "unknown", "fault": None}


def classify_wtgearbox(filename: str) -> Dict:
    """WTgearbox文件分类"""
    name = filename.replace(".npy", "")
    parts = name.split("-")
    main_part = parts[0]
    channel_part = parts[1] if len(parts) > 1 else "c1"
    fault_parts = main_part.split("_")
    category = fault_parts[0]
    mapping = {"He": "healthy", "Br": "break", "Mi": "missing", "Rc": "crack", "We": "wear"}
    return {"label": mapping.get(category, "unknown"), "fault": mapping.get(category), "channel": channel_part}


def get_hustbear_files() -> List[Tuple[Path, Dict]]:
    """获取HUSTbear数据集文件列表（仅X通道）"""
    if not HUSTBEAR_DIR.exists():
        return []
    files = []
    for f in sorted(HUSTBEAR_DIR.glob("*.npy")):
        if not f.name.endswith("-X.npy"):
            continue
        info = classify_hustbear(f.name)
        if info["label"] != "unknown":
            files.append((f, info))
    return files


def get_cw_files() -> List[Tuple[Path, Dict]]:
    """获取CW数据集文件列表"""
    if not CW_DIR.exists():
        return []
    files = []
    for f in sorted(CW_DIR.glob("*.npy")):
        info = classify_cw(f.name)
        if info["label"] != "unknown":
            files.append((f, info))
    return files


def get_wtgearbox_files() -> List[Tuple[Path, Dict]]:
    """获取WTgearbox数据集文件列表（仅c1通道）"""
    if not WTGEARBOX_DIR.exists():
        return []
    files = []
    for f in sorted(WTGEARBOX_DIR.glob("*.npy")):
        if not f.name.endswith("-c1.npy"):
            continue
        info = classify_wtgearbox(f.name)
        if info["label"] != "unknown":
            files.append((f, info))
    return files
