"""隔离 SQLite 上真实 HTTP 方法入口、按通道几何和无基线语义。"""

import sys
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.api.auth import optional_auth
from app.database import Base, get_db
from app.main import app
from app.models import Device, SensorData
from tests.diagnosis.planetary.test_planetary_business import FS, SIGNAL, GEOMETRY


class PlanetaryApiTests(unittest.TestCase):
    def test_method_metadata_response_geometry_and_removed_methods(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        with factory() as db:
            db.add(
                Device(
                    device_id="PLANETARY",
                    name="行星测试",
                    bearing_params={},
                    gear_teeth={"1": {"input": 18}, "2": GEOMETRY},
                )
            )
            db.add(
                SensorData(
                    device_id="PLANETARY",
                    batch_index=1,
                    channel=2,
                    sample_rate=FS,
                    data=SIGNAL.tolist(),
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
            metadata = client.get("/api/data/method-info").json()["data"]
            self.assertIn("planetary_tsa_residual", metadata)
            self.assertNotIn("planetary_vmd_demod", metadata)
            url = "/api/data/PLANETARY/1/2/method-analysis"
            for method, internal in (
                ("planetary_narrowband", "narrowband"),
                ("planetary_tsa_residual", "tsa_residual"),
                ("planetary_highpass", "highpass"),
                ("planetary_fullband", "fullband"),
            ):
                response = client.get(url, params={"method": method, "rot_freq_hz": 20})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()["data"]
                self.assertEqual(result["mechanical_model"]["sun_teeth"], 28)
                self.assertEqual(result["evaluation_status"], "not_evaluable")
                self.assertEqual(result["diagnosis_conclusion"], "unknown")
                self.assertEqual(list(result["planetary_methods"]), [internal])
            advanced = client.get(
                url, params={"method": "gear_advanced", "rot_freq_hz": 20}
            )
            self.assertEqual(advanced.status_code, 200, advanced.text)
            self.assertEqual(advanced.json()["data"]["method"], "planetary_gear")
            for old in (
                "planetary_vmd_demod",
                "planetary_sc_scoh",
                "planetary_msb",
                "planetary_tsa_envelope",
            ):
                self.assertEqual(
                    client.get(
                        url, params={"method": old, "rot_freq_hz": 20}
                    ).status_code,
                    400,
                )
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(optional_auth, None)
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
