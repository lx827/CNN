"""定轴齿轮 DataView HTTP 响应契约测试，使用隔离内存 SQLite。"""
import os
import sys
import unittest

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.database import Base, get_db
from app.main import app
from app.api.auth import optional_auth
from app.models import Device, SensorData


class FixedAxisGearApiTest(unittest.TestCase):
    def test_gear_response_exposes_metric_status_not_fake_zero(self) -> None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        fs = 2048
        time = np.arange(fs * 3) / fs
        signal = (
            0.8 * np.sin(2 * np.pi * 16 * time)
            + np.sin(2 * np.pi * 288 * time)
            + 0.2 * np.sin(2 * np.pi * 272 * time)
            + 0.2 * np.sin(2 * np.pi * 304 * time)
        )
        db.add(Device(
            device_id="TEST-FIXED-GEAR", name="定轴齿轮测试设备", gear_teeth={"input": 18},
        ))
        db.add(SensorData(
            device_id="TEST-FIXED-GEAR", batch_index=1, channel=1,
            data=signal.tolist(), sample_rate=fs,
        ))
        db.commit()

        def override_get_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[optional_auth] = lambda: "test-user"
        try:
            client = TestClient(app)
            response = client.get(
                "/api/data/TEST-FIXED-GEAR/1/1/gear",
                params={"method": "advanced"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertIn("metrics", data)
            self.assertIn("evaluation", data)
            self.assertEqual(data["metrics"]["ser"]["status"], "evaluated", data["metrics"]["ser"])
            self.assertIsNone(data["na4"])
            self.assertEqual(data["metrics"]["na4"]["status"], "not_evaluable")
            self.assertIsNone(data["fault_indicators"]["na4"]["warning"])
            self.assertNotEqual(data["metrics"]["na4"]["status"], "healthy")
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(optional_auth, None)
            db.close()
            engine.dispose()
    def test_analyze_http_ensemble_skips_unavailable_values_and_zero_is_not_healthy(self) -> None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        fs = 2048
        time = np.arange(fs * 2) / fs
        signal = (
            0.8 * np.sin(2 * np.pi * 16 * time)
            + np.sin(2 * np.pi * 288 * time)
            + 0.2 * np.sin(2 * np.pi * 272 * time)
        )
        db.add(Device(
            device_id="TEST-FIXED-ENSEMBLE", name="定轴集成测试设备", gear_teeth={"input": 18},
        ))
        db.add(SensorData(
            device_id="TEST-FIXED-ENSEMBLE", batch_index=1, channel=1,
            data=signal.tolist(), sample_rate=fs,
        ))
        db.add(SensorData(
            device_id="TEST-FIXED-ENSEMBLE", batch_index=2, channel=1,
            data=np.zeros(fs).tolist(), sample_rate=fs,
        ))
        db.commit()

        def override_get_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[optional_auth] = lambda: "test-user"
        try:
            client = TestClient(app)
            response = client.get("/api/data/TEST-FIXED-ENSEMBLE/1/1/analyze")
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            best_gear = data["gear"]
            self.assertIsNone(best_gear["na4"])
            self.assertIsNone(best_gear["fault_indicators"]["na4"]["warning"])
            self.assertIn(data["diagnosis_conclusion"], {"normal", "warning", "fault"})

            zero_response = client.get("/api/data/TEST-FIXED-ENSEMBLE/2/1/analyze")
            self.assertEqual(zero_response.status_code, 200, zero_response.text)
            zero_data = zero_response.json()["data"]
            self.assertIsNone(zero_data["health_score"])
            self.assertEqual(zero_data["evaluation_status"], "indeterminate")
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(optional_auth, None)
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
