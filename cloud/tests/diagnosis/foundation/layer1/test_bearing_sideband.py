"""边带原始观测与评估的独立数学测试。"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from app.algorithms.bearing.analysis import (
    SidebandObservation,
    SidebandTarget,
    compute_sideband_metrics,
)
from app.algorithms.bearing.evaluation import evaluate_sideband_evidence
from tests.diagnosis.foundation.layer1.synthetic_signals import NumpyEncoder

OUTPUT_DIR = Path(__file__).parent / "output"


def observations(snr):
    return tuple(
        SidebandObservation(
            order=order,
            side=side,
            theory_frequency_hz=90.0 + sign * order * 25.0,
            snr=snr,
        )
        for order in range(1, 4)
        for side, sign in (("upper", 1), ("lower", -1))
    )


def as_targets(items):
    return tuple(
        SidebandTarget(item.order, item.side, item.theory_frequency_hz)
        for item in items
    )


def test_sideband_density_synthetic():
    """六个可观测强边带全部显著，分母为 6。"""
    evidence = compute_sideband_metrics(
        observations(15.0), as_targets(observations(15.0))
    )
    result = evaluate_sideband_evidence(evidence)
    passed = (
        result["sideband_significant_count"] == 6 and result["sideband_density"] == 1.0
    )
    return [{"test": "six_observable_sidebands", "passed": passed, **result}]


def test_sideband_density_clean():
    """六个可观测弱边带均不显著，不使用固定搜索数作分母。"""
    evidence = compute_sideband_metrics(
        observations(1.0), as_targets(observations(1.0))
    )
    result = evaluate_sideband_evidence(evidence)
    passed = (
        result["sideband_significant_count"] == 0 and result["sideband_density"] == 0.0
    )
    return [{"test": "six_weak_sidebands", "passed": passed, **result}]


def main():
    all_results = {
        "synthetic_with_mod": test_sideband_density_synthetic(),
        "synthetic_clean": test_sideband_density_clean(),
    }
    items = [item for group in all_results.values() for item in group]
    passed = sum(item["passed"] for item in items)
    all_results["summary"] = {
        "total": len(items),
        "passed": passed,
        "failed": len(items) - passed,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "bearing_sideband.json"
    out.write_text(
        json.dumps(all_results, indent=2, cls=NumpyEncoder, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"边带测试: {passed}/{len(items)} 通过，结果: {out}")
    assert passed == len(items)


if __name__ == "__main__":
    main()
