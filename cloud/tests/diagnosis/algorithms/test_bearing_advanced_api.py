"""隔离 SQLite 上的真实研究/包络 HTTP 参数、方法名称与专属评估契约。"""

import os
import sys
import unittest

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.api.auth import optional_auth
from app.database import Base, get_db
from app.main import app
from app.models import Device, SensorData


class AdvancedBearingApiTests(unittest.TestCase):
    def test_http_method_parameters_and_dedicated_response(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        t = np.arange(4096) / 2048
        signal = (1 + 0.8 * np.cos(2 * np.pi * 90 * t)) * np.sin(2 * np.pi * 700 * t)
        with factory() as db:
            db.add(
                Device(
                    device_id="ADVANCED",
                    name="高级轴承测试",
                    bearing_params={"n": 9, "d": 7.94, "D": 38.52},
                )
            )
            db.add(
                SensorData(
                    device_id="ADVANCED",
                    batch_index=1,
                    channel=1,
                    data=signal.tolist(),
                    sample_rate=2048,
                )
            )
            db.commit()

        def override_db():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[optional_auth] = lambda: "test-user"
        try:
            client = TestClient(app)
            url = "/api/data/ADVANCED/1/1/method-analysis"
            params = {"rot_freq_hz": 25}
            missing = client.get(url, params={**params, "method": "cpw"})
            self.assertEqual(missing.status_code, 200, missing.text)
            self.assertEqual(
                missing.json()["data"]["evaluation"]["evaluation_status"],
                "indeterminate",
            )
            mckd = client.get(
                url, params={**params, "method": "mckd", "target_fault": "BPFI"}
            )
            self.assertEqual(mckd.status_code, 200, mckd.text)
            data = mckd.json()["data"]
            self.assertEqual(data["method"], "mckd")
            self.assertEqual(data["target_fault"], "BPFI")
            self.assertEqual(
                data["period_samples"], round(2048 / data["target_frequency_hz"])
            )
            sc = client.get(url, params={**params, "method": "sc_scoh"})
            self.assertEqual(sc.status_code, 200, sc.text)
            data = sc.json()["data"]
            self.assertEqual(data["evaluation_kind"], "sc_scoh")
            self.assertNotIn("sc_scoh_indicators", data)
            self.assertIsNone(data["spectrum"])
            self.assertIn("cyclic_spectrum", data)
            self.assertNotIn("snr", data["evaluation"]["indicators"]["BPFI"])
            invalid = client.get(
                url, params={"method": "mckd", "target_fault": "UNKNOWN"}
            )
            self.assertEqual(invalid.status_code, 422, invalid.text)
            old = client.get(
                "/api/data/ADVANCED/1/1/envelope", params={"method": "kurtogram"}
            )
            self.assertEqual(old.status_code, 400, old.text)
            metadata = client.get("/api/data/method-info").json()["data"]
            self.assertIn("filter_bank_sk", metadata)
            self.assertNotIn("kurtogram", metadata)
            ensemble = client.get(
                "/api/data/ADVANCED/1/1/research-analysis",
                params=[
                    ("profile", "runtime"),
                    ("rot_freq_hz", 25),
                    ("comb_frequencies_hz", 25),
                    ("comb_frequencies_hz", 50),
                    ("comb_is_stable", "true"),
                ],
            )
            self.assertEqual(ensemble.status_code, 200, ensemble.text)
            cpw = ensemble.json()["data"]["bearing_results"]["none:cpw"]
            self.assertEqual(cpw["comb_frequencies_hz"], [25.0, 50.0])
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(optional_auth, None)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
