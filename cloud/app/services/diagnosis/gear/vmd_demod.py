"""定轴VMD AM/FM研究响应边界，数学统一在composite Pipeline。"""
from app.algorithms.mechanics import FixedAxisGearGeometry
from app.algorithms.order import ScalarSpeed
from ..composite import analyze_composite_research, composite_to_dict


def vmd_fixed_axis_demod_analysis(signal, fs, rot_freq, gear_teeth, max_K=5, alpha=2000):
    geometry = FixedAxisGearGeometry(gear_teeth.get("input"), gear_teeth.get("output"))
    diagnosis = analyze_composite_research(
        "vmd_amfm", signal, fs, geometry=geometry, speed=ScalarSpeed(rot_freq, "caller_supplied"),
        options={"modes": max_K, "alpha": alpha},
    )
    return composite_to_dict(diagnosis)
