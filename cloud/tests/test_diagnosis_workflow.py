"""统一业务闭环：实际HTTP、精确缓存、无算法重评、worker事务和未知告警。"""

import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import database, lifespan
from app.database import Base, get_db
from app.models import Device, SensorData, Diagnosis, Alarm
from app.api.data_view import router
from app.api.dashboard import router as dashboard_router
from app.api.monitor import router as monitor_router
from app.services import diagnosis_workflow as workflow
from app.services.alarms import generate_alarms
from app.services.diagnosis.domain import DiagnosisKey
from app.services.diagnosis_store import read_diagnosis, save_diagnosis, save_batch
from tests.diagnosis_fixtures import snapshot, batch_snapshot


class DiagnosisBusinessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        time = np.arange(2048) / 2048
        signal = (
            0.8 * np.sin(2 * np.pi * 16 * time)
            + np.sin(2 * np.pi * 288 * time)
            + 0.2 * np.sin(2 * np.pi * 272 * time)
        )
        with self.sessions() as db:
            db.add(
                Device(
                    device_id="BUSINESS",
                    name="测试设备",
                    channel_count=3,
                    sample_rate=2048,
                    is_online=1,
                    gear_teeth={"1": {"input": 18}},
                    bearing_params={},
                )
            )
            db.add_all(
                [
                    SensorData(
                        device_id="BUSINESS",
                        batch_index=1,
                        channel=channel,
                        data=(signal if channel == 1 else np.zeros(2048)).tolist(),
                        sample_rate=2048,
                        is_analyzed=0,
                    )
                    for channel in (1, 3)
                ]
            )
            db.commit()
        application = FastAPI()
        for route in (router, dashboard_router, monitor_router):
            application.include_router(route)

        def session():
            with self.sessions() as db:
                yield db

        application.dependency_overrides[get_db] = session
        self.client = TestClient(application)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_real_http_channel_diagnosis_is_canonical_and_does_not_overwrite_device(
        self,
    ):
        response = self.client.get(
            "/api/data/BUSINESS/1/1/analyze", params={"rot_freq_hz": 16}
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["data"]
        self.assertEqual(result["contract_version"], 1)
        self.assertEqual(result["evaluation_status"], "evaluated")
        self.assertNotIn("status", result)
        self.assertNotIn("fault_probabilities", result)
        with self.sessions() as db:
            self.assertEqual(db.query(Diagnosis).one().channel, 1)
            self.assertEqual(db.query(Device).one().diagnosis_conclusion, "unknown")
        cached = self.client.get("/api/data/BUSINESS/1/1/diagnosis").json()["data"]
        self.assertEqual(cached, result)
        self.assertEqual(
            self.client.get(
                "/api/data/BUSINESS/1/1/diagnosis?denoise_method=wavelet"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/data/BUSINESS/1/3/diagnosis").status_code, 404
        )
        with patch(
            "app.services.diagnosis.engine.DiagnosisEngine.analyze_research_ensemble",
            side_effect=AssertionError("重评不运行算法"),
        ):
            response = self.client.post("/api/data/BUSINESS/1/1/reevaluate")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["evaluations"], result["evaluations"])
        self.assertEqual(
            response.json()["data"]["health_score"], result["health_score"]
        )

    def test_real_http_batch_keeps_sparse_channel_identity_and_partial_coverage(self):
        with patch.object(workflow.manager, "broadcast", new=AsyncMock()):
            response = self.client.post("/api/data/BUSINESS/1/reanalyze")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["data"]
        self.assertEqual(set(result["channels"]), {"ch1", "ch3"})
        self.assertEqual(result["aggregation"]["channel_numbers"], [1, 3])
        self.assertEqual(result["coverage"], "partial")
        self.assertEqual(result["channels"]["ch3"]["diagnosis_conclusion"], "unknown")
        self.assertIsNone(result["channels"]["ch3"]["health_score"])
        with self.sessions() as db:
            self.assertEqual({row.channel for row in db.query(Diagnosis)}, {0, 1, 3})
            self.assertTrue(all(row.is_analyzed for row in db.query(SensorData)))
            self.assertEqual(
                db.query(Device).one().health_score, result["health_score"]
            )
        summary = self.client.get("/api/data/BUSINESS/batches").json()["data"][0]
        self.assertEqual(summary["coverage"], "partial")
        dashboard = self.client.get("/api/dashboard/").json()["data"]
        self.assertEqual(
            dashboard["diagnosis"]["BUSINESS"]["health_score"], result["health_score"]
        )
        monitor = self.client.get("/api/monitor/latest?device_id=BUSINESS").json()[
            "data"
        ]
        self.assertEqual(monitor[1]["channel"], 3)
        self.assertEqual(monitor[1]["diagnosis_conclusion"], "unknown")
        self.assertIsNone(monitor[1]["health_score"])

    def test_cache_append_exact_keys_and_legacy_snapshot_requires_reanalysis(self):
        with self.sessions() as db:
            save_diagnosis(
                db,
                DiagnosisKey("BUSINESS", 1, 1, "none"),
                snapshot(conclusion="warning"),
            )
            save_diagnosis(
                db, DiagnosisKey("BUSINESS", 1, 1, "none"), snapshot(conclusion="fault")
            )
            save_diagnosis(
                db,
                DiagnosisKey("BUSINESS", 1, 1, "wavelet"),
                snapshot(denoise="wavelet", conclusion="normal"),
            )
            db.add(
                Diagnosis(
                    device_id="BUSINESS",
                    batch_index=2,
                    channel=1,
                    denoise_method="none",
                    engine_result={"status": "normal", "health_score": 100},
                )
            )
            db.commit()
            self.assertEqual(
                read_diagnosis(db, DiagnosisKey("BUSINESS", 1, 1, "none"))[
                    "diagnosis_conclusion"
                ],
                "fault",
            )
            self.assertEqual(
                read_diagnosis(db, DiagnosisKey("BUSINESS", 1, 1, "wavelet"))[
                    "diagnosis_conclusion"
                ],
                "normal",
            )
            self.assertIsNone(
                read_diagnosis(db, DiagnosisKey("BUSINESS", 1, 0, "none"))
            )
            self.assertEqual(db.query(Diagnosis).count(), 4)
        legacy = self.client.get("/api/data/BUSINESS/2/1/diagnosis").json()["data"]
        self.assertEqual(legacy["diagnosis_conclusion"], "unknown")
        self.assertIsNone(legacy["health_score"])
        self.assertEqual(
            self.client.post("/api/data/BUSINESS/2/1/reevaluate").status_code, 409
        )

    def test_research_and_wrong_record_cannot_enter_production_cache(self):
        with self.sessions() as db:
            with self.assertRaises(ValueError):
                save_diagnosis(
                    db,
                    DiagnosisKey("BUSINESS", 1, 1, "none"),
                    {**snapshot(), "research_only": True},
                )
            with self.assertRaisesRegex(ValueError, "identity"):
                save_diagnosis(db, DiagnosisKey("BUSINESS", 2, 1, "none"), snapshot())
            self.assertEqual(db.query(Diagnosis).count(), 0)

    def test_rotation_update_accepts_object_and_only_touches_exact_summary(self):
        with self.sessions() as db:
            save_batch(db, "BUSINESS", 1, "none", batch_snapshot())
            db.commit()
            previous = db.query(Diagnosis).filter_by(channel=0).one()
            stamp = previous.analyzed_at
            score = previous.health_score
        response = self.client.put(
            "/api/data/BUSINESS/1/diagnosis", json={"rot_freq": 23.5}
        )
        self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            row = db.query(Diagnosis).filter_by(channel=0).one()
            self.assertEqual(row.rot_freq, 23.5)
            self.assertEqual(row.health_score, score)
            self.assertEqual(row.analyzed_at, stamp)
            self.assertTrue(
                all(
                    item.rot_freq is None
                    for item in db.query(Diagnosis).filter(Diagnosis.channel > 0)
                )
            )
        self.assertEqual(
            self.client.put(
                "/api/data/BUSINESS/2/diagnosis", json={"rot_freq": 23.5}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(
                "/api/data/BUSINESS/1/diagnosis", json={"rot_freq": 0}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.put("/api/data/BUSINESS/1/diagnosis", json=23.5).status_code,
            422,
        )

    def test_alarms_use_conclusion_once_and_unknown_has_no_health_alarm(self):
        with self.sessions() as db:
            payload = batch_snapshot()
            alarms = generate_alarms(db, "BUSINESS", payload, batch_index=1)
            self.assertEqual({alarm.channel for alarm in alarms}, {None, 1})
            self.assertTrue(all(alarm.level == "warning" for alarm in alarms))
            db.commit()
            self.assertEqual(
                generate_alarms(db, "BUSINESS", payload, batch_index=1), []
            )
            self.assertEqual(
                generate_alarms(db, "BUSINESS", snapshot(conclusion="unknown")), []
            )
            db.query(Device).one().is_online = 0
            db.flush()
            self.assertEqual(
                generate_alarms(db, "BUSINESS", snapshot(conclusion="fault")), []
            )

    def test_failed_transaction_rolls_back_cache_raw_markers_and_device(self):
        async def run():
            with self.sessions() as db:
                with (
                    patch.object(
                        workflow, "analyze_device", return_value=batch_snapshot()
                    ),
                    patch.object(
                        workflow,
                        "generate_alarms",
                        side_effect=RuntimeError("alarm write failed"),
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, "alarm write failed"):
                        await workflow.process_batch(
                            db,
                            db.query(Device).one(),
                            1,
                            semaphore=asyncio.Semaphore(1),
                        )

        asyncio.run(run())
        with self.sessions() as db:
            self.assertEqual(db.query(Diagnosis).count(), 0)
            self.assertEqual(db.query(Alarm).count(), 0)
            self.assertTrue(all(row.is_analyzed == 0 for row in db.query(SensorData)))
            self.assertIsNone(db.query(Device).one().health_score)

    def test_worker_uses_shared_transaction_and_strict_json_after_commit(self):
        payload = batch_snapshot()
        payload["channels"]["ch1"]["numeric"] = {
            "value": np.float32(np.nan),
            "flags": np.array([1, 2]),
        }
        events = []

        async def broadcast(message):
            json.dumps(message, allow_nan=False)
            with self.sessions() as db:
                self.assertEqual(db.query(Diagnosis).count(), 3)
            events.append(message)

        async def run():
            with (
                patch.object(lifespan, "SessionLocal", self.sessions),
                patch.object(workflow, "analyze_device", return_value=payload),
                patch.object(workflow.manager, "broadcast", side_effect=broadcast),
                patch.object(
                    lifespan.asyncio,
                    "sleep",
                    AsyncMock(side_effect=[None, asyncio.CancelledError]),
                ),
            ):
                await lifespan.analysis_worker()

        asyncio.run(run())
        with self.sessions() as db:
            channel = db.query(Diagnosis).filter_by(channel=1).one()
            self.assertEqual(
                channel.engine_result["numeric"], {"value": None, "flags": [1, 2]}
            )
            self.assertEqual(db.query(Alarm).count(), 2)
        self.assertEqual(events[0]["type"], "diagnosis_update")
        self.assertEqual(len(events), 3)

    def test_openapi_exposes_state_axes_and_nullable_score(self):
        schema = self.client.get("/openapi.json").json()
        snapshot_schema = schema["components"]["schemas"]["DiagnosisSnapshot"]
        self.assertIn("health_score", snapshot_schema["required"])
        self.assertNotIn("status", snapshot_schema["properties"])
        self.assertTrue(
            any(
                item.get("type") == "null"
                for item in snapshot_schema["properties"]["health_score"]["anyOf"]
            )
        )
        self.assertEqual(
            set(schema["components"]["schemas"]["EvaluationStatus"]["enum"]),
            {"evaluated", "not_evaluable", "indeterminate"},
        )

    def test_configured_weight_is_applied_once_without_changing_conclusion(self):
        from app.core.config import DIAGNOSIS_WEIGHTS
        from app.services.diagnosis.assessment import reassess_diagnosis

        with patch.dict(DIAGNOSIS_WEIGHTS, {"ser": 2.0}):
            payload = snapshot()
            self.assertEqual(payload["health_score"], 76.0)
            self.assertEqual(payload["diagnosis_conclusion"], "warning")
            self.assertEqual(reassess_diagnosis(payload).health_score, 76.0)


class MigrationTests(unittest.TestCase):
    def test_legacy_migration_is_unknown_null_and_idempotent(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE devices (id INTEGER PRIMARY KEY, device_id VARCHAR(50), health_score INTEGER, status VARCHAR(20))"
                    )
                )
                conn.execute(
                    text(
                        "CREATE TABLE diagnosis (id INTEGER PRIMARY KEY, device_id VARCHAR(50), batch_index INTEGER, analyzed_at DATETIME, health_score INTEGER, status VARCHAR(20))"
                    )
                )
                conn.execute(text("INSERT INTO devices VALUES (1,'OLD',100,'normal')"))
                conn.execute(
                    text("INSERT INTO diagnosis VALUES (1,'OLD',1,NULL,100,'normal')")
                )
            with patch.object(database, "engine", engine):
                database.init_db()
                database.init_db()
            with engine.connect() as conn:
                for table in ("devices", "diagnosis"):
                    row = conn.execute(
                        text(
                            f"SELECT evaluation_status, diagnosis_conclusion, health_score, coverage FROM {table}"
                        )
                    ).one()
                    self.assertEqual(
                        tuple(row), ("not_evaluable", "unknown", None, "none")
                    )
            self.assertIn(
                "status",
                {value["name"] for value in inspect(engine).get_columns("devices")},
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
