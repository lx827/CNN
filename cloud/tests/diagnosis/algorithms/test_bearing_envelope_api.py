"""标准包络 HTTP 接口的新响应契约测试，使用隔离内存 SQLite。"""
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


class BearingEnvelopeApiTest(unittest.TestCase):
    def test_envelope_response_uses_structured_spectrum(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        fs = 8192
        time = np.arange(fs) / fs
        signal = (1.0 + 0.5 * np.cos(2 * np.pi * 90 * time)) * np.sin(2 * np.pi * 2000 * time)
        db.add(Device(
            device_id="TEST-ENVELOPE",
            name="包络测试设备",
            bearing_params={"n": 9, "d": 7.94, "D": 38.52, "alpha": 0},
        ))
        db.add(SensorData(
            device_id="TEST-ENVELOPE",
            batch_index=1,
            channel=1,
            data=signal.tolist(),
            sample_rate=fs,
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
                "/api/data/TEST-ENVELOPE/1/1/envelope",
                params={"method": "envelope", "max_freq": 300},
            )
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()["data"]
            self.assertIn("spectrum", data)
            self.assertIn("band", data)
            self.assertIn("evaluation", data)
            self.assertLessEqual(max(data["spectrum"]["frequency_hz"]), 300.0)
            self.assertEqual(data["spectrum"]["scaling"], "single_sided_amplitude")
            self.assertNotIn("envelope_freq", data)
            self.assertNotIn("envelope_amp", data)
            self.assertNotIn("fault_indicators", data)
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(optional_auth, None)
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
