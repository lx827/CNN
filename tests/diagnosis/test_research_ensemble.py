"""
Research ensemble diagnosis regression tests.

Run from repo root:
    cloud/venv/Scripts/python.exe tests/diagnosis/test_research_ensemble.py
"""
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLOUD = os.path.join(ROOT, "cloud")
if CLOUD not in sys.path:
    sys.path.insert(0, CLOUD)

from app.services.diagnosis.ensemble import run_research_ensemble


FS = 8192
DATA_DIR = r"E:\A-codehub\CNN\HUSTbear\down8192"


def _impact_train(duration=4.0, rot_freq=30.0, fault_freq=138.0, noise=0.08):
    rng = np.random.default_rng(123)
    t = np.arange(int(FS * duration)) / FS
    sig = 0.25 * np.sin(2 * np.pi * rot_freq * t)
    sig += 0.08 * np.sin(2 * np.pi * 2 * rot_freq * t)
    for ti in np.arange(0.05, duration, 1.0 / fault_freq):
        idx = int(ti * FS)
        end = min(len(sig), idx + int(0.04 * FS))
        k = np.arange(end - idx) / FS
        sig[idx:end] += 2.5 * np.exp(-160 * k) * np.sin(2 * np.pi * 2200 * k)
    sig += noise * rng.standard_normal(len(sig))
    return sig


def _healthy_signal(duration=4.0, rot_freq=30.0, noise=0.08):
    rng = np.random.default_rng(456)
    t = np.arange(int(FS * duration)) / FS
    sig = 0.28 * np.sin(2 * np.pi * rot_freq * t)
    sig += 0.10 * np.sin(2 * np.pi * 2 * rot_freq * t)
    sig += 0.05 * np.sin(2 * np.pi * 3 * rot_freq * t)
    sig += noise * rng.standard_normal(len(sig))
    return sig


def test_research_ensemble_separates_synthetic_fault():
    healthy = run_research_ensemble(_healthy_signal(), FS, profile="runtime")
    fault = run_research_ensemble(_impact_train(), FS, profile="runtime")

    print("healthy", healthy["status"], healthy["fault_likelihood"], healthy["health_score"])
    print("fault", fault["status"], fault["fault_likelihood"], fault["health_score"])

    assert healthy["status"] == "normal"
    assert healthy["fault_likelihood"] < 0.45
    assert fault["status"] in {"warning", "fault"}
    assert fault["fault_likelihood"] > healthy["fault_likelihood"] + 0.25
    assert fault["health_score"] < healthy["health_score"]


def test_hustbear_optional_detection_smoke():
    healthy_path = os.path.join(DATA_DIR, "H_25hz-X.npy")
    fault_path = os.path.join(DATA_DIR, "I_25hz-X.npy")
    if not os.path.exists(healthy_path) or not os.path.exists(fault_path):
        print("HUSTbear files not found, skipped")
        return

    healthy = np.load(healthy_path)[: FS * 4]
    fault = np.load(fault_path)[: FS * 4]
    healthy_result = run_research_ensemble(healthy, FS, profile="runtime")
    fault_result = run_research_ensemble(fault, FS, profile="runtime")

    print("HUST healthy", healthy_result["status"], healthy_result["fault_likelihood"])
    print("HUST fault", fault_result["status"], fault_result["fault_likelihood"])

    assert fault_result["fault_likelihood"] >= healthy_result["fault_likelihood"]
    assert fault_result["status"] in {"warning", "fault"}


if __name__ == "__main__":
    test_research_ensemble_separates_synthetic_fault()
    test_hustbear_optional_detection_smoke()
    print("research ensemble tests passed")
