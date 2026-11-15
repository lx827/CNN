"""#75真实研究HTTP闭环：五组合、相位输入、只读生产库和事件循环。"""

import asyncio
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.api.data_view import research
from app.database import Base, get_db
from app.models import Device, SensorData, Diagnosis, Alarm
from app.services.diagnosis.adapters import unavailable_result


class CompositeResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.app = FastAPI()
        self.app.include_router(research.router)

        def database():
            with self.factory() as session:
                yield session

        self.app.dependency_overrides[get_db] = database
        fs = 2048
        time = np.arange(fs * 2) / fs
        fixed = (1 + 0.4 * np.cos(2 * np.pi * 8 * time)) * np.cos(
            2 * np.pi * 256 * time
        ) + 0.2 * np.cos(2 * np.pi * 32 * time)
        time = np.arange(fs * 4) / fs
        self.planet_hz = 2 * 54 / 17
        planet = 2 * np.pi * self.planet_hz * time
        planetary = np.cos(17 * planet) + 0.2 * np.cos(planet)
        self.alignment = {
            "carrier_phase_rad": (2 * np.pi * 2 * time).tolist(),
            "planet_phase_rad": planet.tolist(),
            "planet_azimuths_rad": [0, np.pi],
            "selected_planet": 0,
            "sensor_azimuth_rad": 0,
            "passage_half_width_rad": 1,
            "planet_relative_frequency_hz": self.planet_hz,
            "samples_per_planet_revolution": 512,
        }
        with self.factory() as session:
            session.add(
                Device(
                    device_id="COMPOSITE",
                    name="研究",
                    health_score=42,
                    evaluation_status="evaluated",
                    diagnosis_conclusion="warning",
                    coverage="complete",
                    gear_teeth={
                        "1": {"input": 32},
                        "2": {
                            "sun": 20,
                            "ring": 54,
                            "planet": 17,
                            "planet_count": 2,
                            "reference_axis": "carrier",
                            "fixed_member": "ring",
                        },
                    },
                )
            )
            for channel, signal in ((1, fixed), (2, planetary)):
                session.add(
                    SensorData(
                        device_id="COMPOSITE",
                        batch_index=1,
                        channel=channel,
                        sample_rate=fs,
                        data=signal.tolist(),
                    )
                )
            session.add(
                Diagnosis(
                    device_id="COMPOSITE",
                    batch_index=1,
                    channel=1,
                    denoise_method="none",
                    health_score=42,
                    evaluation_status="evaluated",
                    diagnosis_conclusion="warning",
                    coverage="complete",
                    full_analysis={"production_sentinel": True},
                )
            )
            session.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_five_combinations_are_viewable_and_never_mutate_production(self):
        cases = [
            (
                "composite_vmd_amfm",
                1,
                8,
                {"modes": 2, "vmd_iterations": 500, "vmd_tolerance": 1e-6},
                None,
            ),
            ("composite_msb", 1, 8, {"segment_length": 512}, None),
            (
                "composite_cvs_med_msb",
                2,
                2,
                {"segment_length": 512, "filter_length": 8, "med_iterations": 8},
                self.alignment,
            ),
            (
                "composite_vmd_ica",
                1,
                None,
                {"modes": 2, "vmd_iterations": 500, "vmd_tolerance": 1e-6},
                None,
            ),
            (
                "composite_mswpee",
                1,
                None,
                {"wavelet": "haar", "level": 1, "max_scale": 3},
                None,
            ),
        ]
        with (
            TestClient(self.app) as client,
            patch.object(
                research.DiagnosisEngine,
                "analyze_all_methods",
                side_effect=AssertionError("research entered production aggregation"),
            ),
        ):
            metadata = client.get("/api/data/method-info").json()["data"]
            for method, channel, speed, options, alignment in cases:
                with self.subTest(method=method):
                    self.assertTrue(metadata[method]["research_only"])
                    response = client.post(
                        f"/api/data/COMPOSITE/1/{channel}/composite-analysis",
                        json={
                            "method": method,
                            "rot_freq_hz": speed,
                            "options": options,
                            "alignment": alignment,
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()["data"]
                    self.assertIn(
                        payload["analysis"]["status"],
                        ("computed", "approximate"),
                        response.text[:1000],
                    )
                    self.assertEqual(payload["analysis_method"], method)
                    self.assertEqual(payload["evaluation_status"], "not_evaluable")
                    self.assertEqual(payload["diagnosis_conclusion"], "unknown")
                    self.assertIsNone(payload["health_score"])
                    self.assertNotIn("status", payload)
                    self.assertFalse(payload["production_eligible"])
                    self.assertFalse(payload["validation"]["independent_vote"])
                    self.assertNotIn("fault_probabilities", payload)
                    self.assertEqual(
                        payload["evidence_family"],
                        "shared_signal_decomposition_demodulation",
                    )
                    self.assertTrue(payload["analysis"]["stages"])
                    json.dumps(payload, allow_nan=False)
                    if method == "composite_vmd_amfm":
                        self.assertNotIn(
                            "modes", payload["analysis"]["data"]["decomposition"]
                        )
                        curve = payload["analysis"]["data"]["demodulation"][
                            "amplitude_spectrum"
                        ]
                        self.assertLessEqual(len(curve["points"]), 800)
                        self.assertEqual(curve["axis_unit"], "Hz")
        with self.factory() as session:
            self.assertEqual(session.query(Diagnosis).count(), 1)
            original = session.query(Diagnosis).one()
            self.assertEqual(original.full_analysis, {"production_sentinel": True})
            self.assertEqual(
                (
                    original.health_score,
                    original.evaluation_status,
                    original.diagnosis_conclusion,
                ),
                (42, "evaluated", "warning"),
            )
            device = session.query(Device).one()
            self.assertEqual(
                (
                    device.health_score,
                    device.evaluation_status,
                    device.diagnosis_conclusion,
                ),
                (42, "evaluated", "warning"),
            )
            self.assertEqual(session.query(Alarm).count(), 0)

    def test_domain_research_summary_uses_record_identity_and_bounded_worker_input(
        self,
    ):
        with self.factory() as session:
            record = session.query(SensorData).filter(SensorData.channel == 1).one()
            record.data = record.data * 4
            session.commit()
        calls = []
        request_thread = threading.get_ident()

        def unavailable(engine, signal, fs, *args):
            calls.append((engine.diagnosis_key, len(signal), threading.get_ident()))
            return unavailable_result(
                "missing_test_baseline",
                key=engine.diagnosis_key,
                object_id="gear",
                method="standard",
            )

        with (
            TestClient(self.app) as client,
            patch.object(research.DiagnosisEngine, "analyze_all_methods", unavailable),
            patch.object(
                research.DiagnosisEngine, "analyze_research_ensemble", unavailable
            ),
        ):
            for endpoint, params in (
                ("method-analysis", {"method": "all"}),
                ("research-analysis", {}),
            ):
                response = client.get(
                    f"/api/data/COMPOSITE/1/1/{endpoint}", params=params
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()["data"]
                self.assertEqual(
                    (
                        payload["evaluation_status"],
                        payload["diagnosis_conclusion"],
                        payload["health_score"],
                    ),
                    ("not_evaluable", "unknown", None),
                )
                self.assertNotIn("status", payload)
                self.assertEqual(
                    payload["evaluations"][0]["evidence"][0]["key"],
                    {
                        "device_id": "COMPOSITE",
                        "batch_index": 1,
                        "channel": 1,
                        "denoise_method": "none",
                    },
                )
        self.assertEqual(len(calls), 2)
        for key, length, thread in calls:
            self.assertEqual(key.record_id, "COMPOSITE:1:ch1")
            self.assertEqual(length, 2048 * 5)
            self.assertNotEqual(thread, request_thread)
        with self.factory() as session:
            self.assertEqual(
                session.query(Diagnosis).one().full_analysis,
                {"production_sentinel": True},
            )
            self.assertEqual(session.query(Alarm).count(), 0)

    def test_missing_phase_stage_failures_and_removed_methods_remain_explicit(self):
        with TestClient(self.app) as client:
            url = "/api/data/COMPOSITE/1/2/method-analysis"
            response = client.get(
                url, params={"method": "composite_cvs_med_msb", "rot_freq_hz": 2}
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()["data"]
            self.assertEqual(payload["analysis"]["status"], "indeterminate")
            self.assertIn("missing_spatial", payload["analysis"]["reason"])
            self.assertEqual(payload["analysis"]["data"]["cvs"]["sample_count"], 0)
            missing_speed = client.get(
                url, params={"method": "composite_vmd_amfm"}
            ).json()["data"]
            self.assertEqual(
                missing_speed["analysis"]["reason"], "constant_reference_speed_required"
            )
            for old in ("planetary_vmd_demod", "planetary_msb", "planetary_cvs_med"):
                self.assertEqual(
                    client.get(url, params={"method": old}).status_code, 400
                )
            bad_alignment = client.post(
                "/api/data/COMPOSITE/1/2/composite-analysis",
                json={
                    "method": "composite_cvs_med_msb",
                    "rot_freq_hz": 2,
                    "alignment": {"unexpected": []},
                },
            )
            self.assertEqual(bad_alignment.status_code, 400)
            too_large = client.post(
                "/api/data/COMPOSITE/1/1/composite-analysis",
                json={"method": "composite_vmd_ica", "options": {"modes": 99}},
            )
            self.assertEqual(too_large.status_code, 400)
            phase_failure = {**self.alignment, "passage_half_width_rad": 0.001}
            failed = client.post(
                "/api/data/COMPOSITE/1/2/composite-analysis",
                json={
                    "method": "composite_cvs_med_msb",
                    "rot_freq_hz": 2,
                    "alignment": phase_failure,
                },
            )
            self.assertEqual(failed.status_code, 200, failed.text)
            self.assertEqual(
                failed.json()["data"]["analysis"]["status"], "indeterminate"
            )

    def test_composite_work_yields_the_request_event_loop(self):
        async def run():
            release = threading.Event()
            original = research._run_composite_method

            def wait(*args, **kwargs):
                if not release.wait(1):
                    raise AssertionError("composite blocked event loop")
                return original(*args, **kwargs)

            async def heartbeat():
                await asyncio.sleep(0.01)
                release.set()

            with (
                self.factory() as session,
                patch.object(research, "_run_composite_method", side_effect=wait),
            ):
                result, _ = await asyncio.gather(
                    research.post_channel_composite_analysis(
                        "COMPOSITE",
                        1,
                        1,
                        research.CompositeResearchRequest(
                            method="composite_mswpee",
                            options={"wavelet": "haar", "level": 1, "max_scale": 2},
                        ),
                        session,
                    ),
                    heartbeat(),
                )
                self.assertEqual(result["code"], 200)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
