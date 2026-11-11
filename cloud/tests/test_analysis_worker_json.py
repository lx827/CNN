"""用实际worker验证规范诊断、NumPy原始读数和追加缓存一起提交。"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Device, Diagnosis, SensorData
from app import lifespan as worker
from app.services import diagnosis_workflow as workflow
from app.services.diagnosis.domain import DiagnosisKey
from app.services.diagnosis_store import read_diagnosis, save_diagnosis
from tests.diagnosis_fixtures import snapshot, batch_snapshot


class AnalysisWorkerJsonTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_appends_channel_history_and_sanitizes_json(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, autoflush=False)
        with sessions() as db:
            db.add(Device(device_id="JSON-TEST", channel_count=3, is_online=1))
            db.add(
                SensorData(
                    device_id="JSON-TEST",
                    batch_index=1,
                    channel=1,
                    data=[1.0, -1.0],
                    sample_rate=8192,
                    is_analyzed=0,
                )
            )
            save_diagnosis(
                db,
                DiagnosisKey("JSON-TEST", 1, 1, "none"),
                snapshot("JSON-TEST", conclusion="normal"),
            )
            db.commit()
        result = batch_snapshot("JSON-TEST")
        result["channels"]["ch1"]["raw"] = {
            "significant": np.bool_(True),
            "missing": np.float64(np.nan),
            "energy": np.array([1.0, np.inf]),
        }
        messages = []

        async def broadcast(message):
            json.dumps(message, allow_nan=False)
            messages.append(message)

        try:
            with (
                patch.object(worker, "SessionLocal", sessions),
                patch.object(workflow, "analyze_device", return_value=result),
                patch.object(workflow.manager, "broadcast", side_effect=broadcast),
                patch.object(
                    worker.asyncio,
                    "sleep",
                    AsyncMock(side_effect=[None, asyncio.CancelledError]),
                ),
            ):
                await worker.analysis_worker()
            with sessions() as db:
                self.assertEqual(db.query(Diagnosis).count(), 4)
                saved = read_diagnosis(db, DiagnosisKey("JSON-TEST", 1, 1, "none"))
                self.assertEqual(
                    saved["raw"],
                    {"significant": True, "missing": None, "energy": [1.0, None]},
                )
                self.assertEqual(saved["diagnosis_conclusion"], "warning")
                self.assertEqual(db.query(SensorData).one().is_analyzed, 1)
                self.assertEqual(
                    db.query(Device).one().health_score, result["health_score"]
                )
            self.assertEqual(messages[0]["type"], "diagnosis_update")
            self.assertIsInstance(
                result["channels"]["ch1"]["raw"]["significant"], np.bool_
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
