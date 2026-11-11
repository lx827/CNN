"""Engine 与 DataView /order 的结构化转速/相位接入测试。"""
import asyncio
import os
import sys

import numpy as np
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from app.api.data_view.order import get_channel_order
from app.database import Base
from app.models import Diagnosis, Device, SensorData
from app.services.diagnosis import DiagnosisEngine, GearMethod
from app.services.diagnosis.ensemble import run_research_ensemble
from tests.diagnosis.algorithms.test_order_pipeline import _triangle_revolutions


def _constant_signal(fs=8192, duration=4.0):
    time_s = np.arange(int(fs * duration) + 1) / fs
    return 0.75 * np.sin(2 * np.pi * 3 * 20 * time_s)


def _fast_signal(fs=8192, duration=6.0):
    time_s = np.arange(int(fs * duration)) / fs
    revolutions = _triangle_revolutions(time_s)
    return (
        np.sin(2 * np.pi * revolutions)
        + 0.5 * np.sin(2 * np.pi * 3.5 * revolutions)
        + 0.6 * np.sin(2 * np.pi * 18 * revolutions)
        + 0.3 * np.sin(2 * np.pi * 17 * revolutions)
        + 0.2 * np.sin(2 * np.pi * 19 * revolutions)
    )


def test_engine_indeterminate_and_fast_downstream_boundaries():
    bearing_params = {"n": 9, "d": 7.94, "D": 39.04}
    engine = DiagnosisEngine(bearing_params=bearing_params, gear_teeth={"input": 18})
    rot_freq, _, _, method, _ = engine._estimate_rot_freq(np.ones(100), 8192)
    assert rot_freq is None and method == "indeterminate"

    signal = _fast_signal()
    order_analysis = engine._analyze_order(signal, 8192)
    assert order_analysis.tracking_method == "varying_speed"
    scalar_summary, _ = engine._order_speed_summary(order_analysis)
    for call in (
        lambda: engine.analyze_bearing(signal, 8192),
        # 模拟 ensemble 先取中位 rf 的旧旁路；cached_order 必须拥有最终前提决定权。
        lambda: engine.analyze_bearing(
            signal, 8192, rot_freq=scalar_summary,
            preprocess=False, _cached_order=order_analysis,
        ),
    ):
        result = call()
        assert result["evaluation_status"] == "indeterminate"
        assert result["diagnosis_conclusion"] == "unknown"
        assert "快速变速" in result["reason"]

    # 定轴新契约：SER 可以消费连续相位补偿谱，但 TSA/CAR 不得使用轨迹中位数。
    gear_engine = DiagnosisEngine(gear_method=GearMethod.ADVANCED, gear_teeth={"input": 18})
    gear_order = gear_engine._analyze_order(signal, 8192)
    assert gear_order.tracking_method == "varying_speed"
    gear = gear_engine.analyze_gear(signal, 8192, _cached_order=gear_order)
    assert gear["tracking_method"] == "varying_speed"
    assert gear["metrics"]["ser"]["status"] == "evaluated"
    assert gear["mesh_amp"] > 0.3
    # 17/18/19 阶峰只能在补偿后的角域谱中同时保持窄带幅值。
    assert gear["sidebands"][0]["amp_low"] > 0.15
    assert gear["sidebands"][0]["amp_high"] > 0.10
    assert gear["tsa_status"] == "not_evaluable"
    assert gear["metrics"]["fm4"]["reason"] == "tsa_requires_accurate_constant_speed_with_continuous_phase"
    assert gear["metrics"]["car"]["reason"] == "car_requires_accurate_constant_speed"


def test_ensemble_fast_speed_never_becomes_bearing_constant_input():
    result = run_research_ensemble(
        _fast_signal(), 8192,
        bearing_params={"n": 9, "d": 7.94, "D": 39.04},
        gear_teeth={"input": 18}, profile="runtime", max_seconds=6.0,
    )
    assert result["bearing_results"]
    for method_result in result["bearing_results"].values():
        assert "快速变速" in method_result.get("reason", "")
        assert method_result["diagnosis_conclusion"] == "unknown"
        assert method_result["evaluation_status"] == "indeterminate"
    assert result["bearing"]["diagnosis_conclusion"] == "unknown"


def test_order_api_constant_axis_amplitude_and_persistence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Device(device_id="ORDER", channel_count=1))
        db.add(SensorData(
            device_id="ORDER", batch_index=1, channel=1,
            data=_constant_signal().tolist(), sample_rate=8192,
        ))
        db.add(Diagnosis(
            device_id="ORDER", batch_index=1, channel=0, denoise_method="none",
            health_score=77, evaluation_status="evaluated", diagnosis_conclusion="warning", coverage="complete", rot_freq=10.0,
            order_analysis={"keep": "batch"},
        ))
        db.add(Diagnosis(
            device_id="ORDER", batch_index=1, channel=1, denoise_method="wavelet",
            health_score=42, evaluation_status="evaluated", diagnosis_conclusion="fault", coverage="complete", rot_freq=33.0,
            order_analysis={"keep": "channel"},
        ))
        db.commit()
        response = asyncio.run(get_channel_order(
            "ORDER", 1, 1, freq_min=10, freq_max=100,
            samples_per_rev=256, max_order=10, rot_freq=20,
            detrend=False, denoise="none", db=db,
        ))
        data = response["data"]
        orders = np.asarray(data["orders"])
        spectrum = np.asarray(data["spectrum"])
        assert data["tracking_method"] == "single_frame"
        assert np.isclose(orders[1] - orders[0], 1 / 80)
        index = int(np.argmin(np.abs(orders - 3)))
        assert np.isclose(orders[index], 3.0)
        # 期望值来自 A=0.75；容差覆盖插值和六位小数量化，而非旧输出 golden。
        assert np.isclose(spectrum[index], 0.75, atol=2e-4), spectrum[index]
        diagnosis = db.query(Diagnosis).filter(Diagnosis.channel == 0).one()
        assert diagnosis.rot_freq == 20.0
        assert diagnosis.order_analysis == {"keep": "batch", "rot_freq_hz": 20.0, "rot_rpm": 1200.0}
        assert diagnosis.health_score == 77 and diagnosis.diagnosis_conclusion == "warning"
        channel_cache = db.query(Diagnosis).filter(Diagnosis.channel == 1).one()
        assert channel_cache.rot_freq == 33.0
        assert channel_cache.order_analysis == {"keep": "channel"}
        assert channel_cache.health_score == 42 and channel_cache.diagnosis_conclusion == "fault"
        assert db.query(Diagnosis).count() == 2
    engine.dispose()


def test_order_api_fast_success_and_noise_indeterminate():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Device(device_id="ORDER", channel_count=1))
        db.add(SensorData(
            device_id="ORDER", batch_index=1, channel=1,
            data=_fast_signal().tolist(), sample_rate=8192,
        ))
        db.add(SensorData(
            device_id="ORDER", batch_index=2, channel=1,
            data=np.zeros(8192).tolist(), sample_rate=8192,
        ))
        db.commit()
        response = asyncio.run(get_channel_order(
            "ORDER", 1, 1, freq_min=8, freq_max=42,
            samples_per_rev=256, max_order=10, rot_freq=None,
            detrend=False, denoise="none", db=db,
        ))
        data = response["data"]
        assert data["tracking_method"] == "varying_speed"
        orders = np.asarray(data["orders"])
        spectrum = np.asarray(data["spectrum"])
        for expected_order, minimum in ((1.0, 0.7), (3.5, 0.25)):
            index = int(np.argmin(np.abs(orders - expected_order)))
            assert abs(orders[index] - expected_order) < 0.03
            assert spectrum[index] > minimum
        # 没有既有批次诊断时只返回阶次结果，不伪造 health=100/status=normal。
        assert db.query(Diagnosis).filter(Diagnosis.batch_index == 1).one_or_none() is None
        try:
            asyncio.run(get_channel_order(
                "ORDER", 2, 1, freq_min=10, freq_max=100,
                samples_per_rev=128, max_order=10, rot_freq=None,
                detrend=False, denoise="none", db=db,
            ))
            raise AssertionError("无转速证据不应返回正常阶次谱")
        except HTTPException as exc:
            assert exc.status_code == 400
        assert db.query(Diagnosis).filter(Diagnosis.batch_index == 2).one_or_none() is None
    engine.dispose()


def run_all_tests():
    tests = [
        test_engine_indeterminate_and_fast_downstream_boundaries,
        test_ensemble_fast_speed_never_becomes_bearing_constant_input,
        test_order_api_constant_axis_amplitude_and_persistence,
        test_order_api_fast_success_and_noise_indeterminate,
    ]
    for test in tests:
        test()
        print(f"  [PASS] {test.__name__}")
    print(f"order integration: {len(tests)} tests passed")


if __name__ == "__main__":
    run_all_tests()
