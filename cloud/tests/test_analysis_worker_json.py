"""用实际后台 worker 和隔离 SQLite 验证 NumPy 诊断结果入库及推送。"""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Device, Diagnosis, SensorData
from app import lifespan as worker


class AnalysisWorkerJsonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as db:
            db.add(Device(device_id="JSON-TEST", channel_count=1, is_online=1))
            db.add(SensorData(device_id="JSON-TEST", batch_index=1, channel=1,
                              data=[0., 1., -1.], sample_rate=8192, is_analyzed=0))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    async def run_worker_once(self):
        channel = {
            "bearing": {"significant": np.bool_(True), "missing": np.float64(np.nan)},
            "health_score": np.int64(72), "status": "warning",
            "rot_freq_hz": np.float32(20),
            "energy": np.array([1., np.inf]),
        }
        result = {
            "health_score": np.int64(72), "status": "warning",
            "fault_probabilities": {"bearing": 0.75},
            "imf_energy": {"energy": [1., None]},
            "order_analysis": {"engine_result": channel, "channels": {"ch1": channel}},
            "rot_freq": np.float32(20),
        }
        messages = []

        async def capture_message(message):
            # 与真实 WebSocket 一样严格编码，避免只验证数据库而漏掉推送。
            json.dumps(message, allow_nan=False)
            messages.append(message)

        with (
            patch.object(worker, "SessionLocal", self.sessions),
            patch.object(worker, "analyze_device", return_value=result),
            patch.object(worker, "compute_channel_features", return_value={}),
            patch.object(worker, "generate_alarms") as alarms,
            patch.object(worker.manager, "broadcast", side_effect=capture_message),
            patch.object(worker.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError])),
        ):
            await worker.analysis_worker()

        with self.sessions() as db:
            batch = db.query(Diagnosis).filter_by(channel=0).one_or_none()
            self.assertIsNotNone(batch, "批次诊断必须实际提交，不能吞掉序列化异常")
            self.assertIs(batch.order_analysis["engine_result"]["bearing"]["significant"], True)
            self.assertIsNone(batch.order_analysis["engine_result"]["bearing"]["missing"])
            self.assertEqual(batch.imf_energy, {"energy": [1., None]})
            self.assertEqual(batch.fault_probabilities, {"bearing": 0.75})
            saved_channel = db.query(Diagnosis).filter_by(channel=1).one()
            self.assertIs(saved_channel.full_analysis["bearing"]["significant"], True)
            self.assertIsNone(saved_channel.full_analysis["bearing"]["missing"])
            self.assertEqual(saved_channel.health_score, 72)
            self.assertEqual(saved_channel.full_analysis["energy"], [1., None])
            self.assertEqual(db.query(SensorData).one().is_analyzed, 1)
            self.assertEqual(db.query(Device).one().health_score, 72)
        alarms.assert_called_once()
        self.assertIs(alarms.call_args.kwargs["order_analysis"]["engine_result"]["bearing"]["significant"], True)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "diagnosis_update")
        self.assertIsInstance(result["order_analysis"]["engine_result"]["bearing"]["significant"], np.bool_)

    async def test_numpy_result_commits_batch_and_new_channel(self):
        await self.run_worker_once()

    async def test_numpy_result_updates_existing_channel(self):
        with self.sessions() as db:
            db.add(Diagnosis(device_id="JSON-TEST", batch_index=1, channel=1,
                             health_score=99, full_analysis={"previous": True}))
            db.commit()
        await self.run_worker_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
