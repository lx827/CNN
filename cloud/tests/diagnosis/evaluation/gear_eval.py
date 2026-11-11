"""WTgearbox 真实数据证据采集；无健康基线时不伪造分类准确率。"""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.services.diagnosis import DiagnosisEngine, GearMethod
from .config import SAMPLE_RATE
from .datasets import get_wtgearbox_files


WT_GEOMETRY = {
    "sun": 28,
    "ring": 100,
    "planet": 36,
    "planet_count": 4,
    "reference_axis": "sun",
    "fixed_member": "ring",
}


def evaluate_gear_methods():
    files = get_wtgearbox_files()
    if not files:
        print("[SKIP] WTgearbox 数据不可用；未验证真实效果")
        return []
    engine = DiagnosisEngine(gear_teeth=WT_GEOMETRY, gear_method=GearMethod.ADVANCED)
    results = []
    for filepath, info in files:
        # WT 文件名转速明确定义为太阳轴 Hz；非法命名不能填入默认转速。
        speed = float(filepath.stem.split("-c")[0].rsplit("_", 1)[1])
        result = engine.analyze_gear(np.load(filepath), SAMPLE_RATE, rot_freq=speed)
        results.append(
            {
                "file": filepath.name,
                "fault_label": info.get("fault_label", "unknown"),
                "analysis_status": result["analysis_status"],
                "evaluation_status": result["evaluation_status"],
                "diagnosis_conclusion": result["diagnosis_conclusion"],
                "mechanical_model": result["mechanical_model"],
                "metrics": result["metrics"],
                "sideband_analysis": result["sideband_analysis"],
                "planetary_methods": result["planetary_methods"],
            }
        )
    print(f"已采集 {len(results)} 条行星证据；未提供可比健康基线，不报告分类效果。")
    return results
