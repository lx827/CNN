"""使用隔离 SQLite 验证页面读路径、SQL 开销和研究诊断缓存。"""
import json
import os
from pathlib import Path
import sys
import time
import unittest
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Device, SensorData, Diagnosis
from app.api.monitor import get_latest_monitor, get_monitor_history
from app.api.dashboard import get_dashboard
from app.api.data_view.core import get_all_device_data, get_device_batches
from app.api.data_view.research import _save_research_diagnosis
from app.api.data_view import _sanitize_for_json
from unittest.mock import patch
from app import database
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


class ReadPathTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.statements = []
        event.listen(self.engine, "before_cursor_execute", self._capture)
        self.db.add(Device(device_id="TEST", channel_count=1, is_online=1))
        self.db.commit()
        self.statements.clear()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _capture(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.statements.append(statement)

    def add_batches(self, count=16):
        for batch in range(1, count + 1):
            self.db.add(SensorData(device_id="TEST", batch_index=batch,
                                   channel=1, data=[0., 1., -1.] * 100, sample_rate=8192))
        self.db.commit()
        self.statements.clear()

    def test_history_has_constant_query_count_and_keeps_order(self):
        self.add_batches()
        result = get_monitor_history("TEST", 1, 16, True, self.db)
        self.assertEqual([x["batch_index"] for x in result["data"]["items"]], list(range(16, 0, -1)))
        print(f"history SELECT count: {len(self.statements)}")
        self.assertLessEqual(len(self.statements), 2)

    def test_latest_avoids_loading_full_diagnosis_and_duplicate_waveform(self):
        self.add_batches(1)
        self.db.add(Diagnosis(device_id="TEST", batch_index=1, channel=0, rot_freq=20,
                              full_analysis={"large": [1.] * 10000}))
        self.db.commit()
        self.statements.clear()
        result = get_latest_monitor("TEST", False, 3, self.db)
        self.assertEqual(result["sensor_params"]["rot_freq"], 20)
        self.assertEqual(result["data"][0]["batch_index"], 1)
        self.assertEqual(len(result["data"][0]["fft_freq"]), len(result["data"][0]["fft_amp"]))
        self.assertFalse(any("diagnosis.full_analysis" in sql for sql in self.statements))
        self.assertLessEqual(len(self.statements), 4)

    def test_batch_summaries_use_latest_timestamp_not_insert_order(self):
        self.add_batches(1)
        now = datetime(2026, 10, 21)
        self.db.add_all([
            Diagnosis(device_id="TEST", batch_index=1, health_score=40, status="critical", analyzed_at=now),
            Diagnosis(device_id="TEST", batch_index=1, health_score=90, status="normal", analyzed_at=now - timedelta(days=1)),
        ])
        self.db.commit()
        all_batches = get_all_device_data(self.db)["data"][0]["batches"]
        one_device = get_device_batches("TEST", True, self.db)["data"]
        self.assertEqual(one_device[0]["health_score"], all_batches[0]["health_score"])
        self.assertEqual(one_device[0]["health_score"], 40)

    def test_batch_lists_do_not_materialize_analysis_payloads(self):
        self.add_batches(1)
        self.db.add_all([Diagnosis(device_id="TEST", batch_index=1, health_score=80,
                                   full_analysis={"large": [1.] * 10000}) for _ in range(30)])
        self.db.commit()
        self.statements.clear()
        start = time.perf_counter()
        get_all_device_data(self.db)
        get_device_batches("TEST", True, self.db)
        print(f"batch summaries elapsed: {1000 * (time.perf_counter() - start):.1f} ms")
        self.assertFalse(any("diagnosis.full_analysis" in sql or "diagnosis.order_analysis" in sql
                             for sql in self.statements))

    def test_dashboard_query_count_does_not_grow_with_devices(self):
        self.db.add_all([Device(device_id=f"OTHER-{i}", is_online=1) for i in range(10)])
        self.db.commit()
        self.statements.clear()
        result = get_dashboard(self.db)
        self.assertEqual(len(result["data"]["devices"]), 11)
        print(f"dashboard SELECT count: {len(self.statements)}")
        self.assertLessEqual(len(self.statements), 3)

    def test_research_cache_persists_insert_and_update(self):
        _save_research_diagnosis(self.db, "TEST", 1, 1, "wavelet", {"health_score": 80, "status": "warning"})
        diag = self.db.query(Diagnosis).one_or_none()
        self.assertIsNotNone(diag, "研究诊断应实际写入缓存，不能吞掉异常后假装保存成功")
        _save_research_diagnosis(self.db, "TEST", 1, 1, "wavelet", {"health_score": 60, "status": "warning"})
        self.db.expire_all()
        self.assertEqual(self.db.query(Diagnosis).one().full_analysis["health_score"], 60)

    def test_numpy_and_nonfinite_values_are_valid_strict_json(self):
        value = {"array": np.array([1., np.nan, np.inf]), "nested": (np.float32(-np.inf), np.int64(2))}
        safe = _sanitize_for_json(value)
        json.dumps(safe, allow_nan=False)
        self.assertEqual(safe, {"array": [1., None, None], "nested": [None, 2]})

    def test_existing_database_gets_indexes_idempotently(self):
        for index in Diagnosis.__table__.indexes:
            if index.name.startswith("ix_diagnosis_"):
                index.drop(self.engine)
        with patch.object(database, "engine", self.engine):
            database.init_db()
            database.init_db()
        names = {index["name"] for index in inspect(self.engine).get_indexes("diagnosis")}
        self.assertTrue({"ix_diagnosis_device_time", "ix_diagnosis_batch_time", "ix_diagnosis_cache"} <= names)

    def test_registered_http_endpoints_with_isolated_database(self):
        # 测试真实应用路由与 JSON 编码，不启动默认设备/后台任务、不读写本地生产库。
        from app.main import app
        from app.api.auth import optional_auth
        isolated = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(isolated)
        with Session(isolated) as db:
            db.add(Device(device_id="HTTP-TEST", channel_count=1, is_online=1))
            db.add(SensorData(device_id="HTTP-TEST", batch_index=1, channel=1,
                              data=[0., 1., -1.] * 100, sample_rate=8192))
            db.commit()

        def get_test_db():
            with Session(isolated) as db:
                yield db

        previous = app.dependency_overrides.copy()
        app.dependency_overrides[database.get_db] = get_test_db
        app.dependency_overrides[optional_auth] = lambda: "test-user"
        try:
            client = TestClient(app)
            for path in ["/api/dashboard/", "/api/data/devices", "/api/data/HTTP-TEST/batches",
                         "/api/monitor/latest?device_id=HTTP-TEST",
                         "/api/monitor/history?device_id=HTTP-TEST"]:
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertEqual(response.json()["code"], 200, path)
            client.close()
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
            isolated.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
