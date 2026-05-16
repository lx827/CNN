"""
数据集加载与分类
"""
from pathlib import Path
from typing import Dict, List, Tuple

from collections import defaultdict
from .config import HUSTBEAR_DIR, CW_DIR, WTGEARBOX_DIR
from .utils import load_npy

MAX_PER_CLASS = 5  # 每个类别最多取5个文件，控制运行时间

def _limit_files(files, max_per_class=MAX_PER_CLASS):
    class_files = defaultdict(list)
    for f, info in files:
        lbl = info.get("label", "unknown")
        class_files[lbl].append((f, info))
    result = []
    for lbl in sorted(class_files.keys()):
        result.extend(class_files[lbl][:max_per_class])
    return result


def classify_hustbear(filename: str) -> Dict:
    """HUSTbear文件分类"""
    parts = filename.replace(".npy", "").split("-")
    name_part = parts[0]
    channel = parts[1] if len(parts) > 1 else "X"
    # 支持格式: H_20Hz, 0.5X_B_20Hz, B_20Hz, 0.5X_O_20Hz 等
    # 提取故障类型字段（以下划线分隔）
    segments = name_part.split("_")
    # 找故障类型段: H/N/B/IR/OR/C/I
    fault_type = None
    for seg in segments:
        if seg in ("H", "N"):
            fault_type = "healthy"
        elif seg == "B":
            fault_type = "ball"
        elif seg == "IR":
            fault_type = "inner"
        elif seg in ("O", "OR"):
            fault_type = "outer"
        elif seg == "C":
            fault_type = "composite"
        elif seg == "I":
            fault_type = "inner"
    if fault_type == "healthy":
        return {"label": "healthy", "fault": None, "channel": channel}
    elif fault_type == "ball":
        return {"label": "ball", "fault": "ball", "channel": channel}
    elif fault_type == "inner":
        return {"label": "inner", "fault": "inner", "channel": channel}
    elif fault_type == "outer":
        return {"label": "outer", "fault": "outer", "channel": channel}
    elif fault_type == "composite":
        return {"label": "composite", "fault": "composite", "channel": channel}
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
    return _limit_files(files)


def get_cw_files() -> List[Tuple[Path, Dict]]:
    """获取CW数据集文件列表"""
    if not CW_DIR.exists():
        return []
    files = []
    for f in sorted(CW_DIR.glob("*.npy")):
        info = classify_cw(f.name)
        if info["label"] != "unknown":
            files.append((f, info))
    return _limit_files(files)


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
    return _limit_files(files)
