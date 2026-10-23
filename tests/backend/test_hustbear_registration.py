"""HUSTbear 独立设备注册：真实 SQLite 提交、幂等与冲突回滚。"""
import importlib.util
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))
from app.database import Base
from app.models import Device

spec = importlib.util.spec_from_file_location("register_hustbear", ROOT / "scripts/register_hustbear_devices.py")
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_independent_devices_and_idempotence(self):
        self.db.add(Device(device_id="WTG-001", name="existing CW", bearing_params={"D": 39.04}))
        self.db.commit()
        self.assertEqual(len(registration.register_devices(self.db)), 5)
        self.assertEqual(registration.register_devices(self.db), [])
        self.assertEqual(self.db.query(Device).count(), 6)
        cw = self.db.query(Device).filter_by(device_id="WTG-001").one()
        self.assertEqual(cw.bearing_params, {"D": 39.04})
        for dev, label in registration.SPECS:
            device = self.db.query(Device).filter_by(device_id=dev).one()
            self.assertEqual(device.name, f"HUSTbear轴承-{label}")
            self.assertEqual(device.bearing_params, registration.PARAMS)
            self.assertEqual(device.channel_names, {"1": "X", "2": "Y", "3": "Z"})
            self.assertIsNone(device.gear_teeth)
            self.assertEqual(device.is_online, 0)

    def test_conflict_rolls_back_all_new_devices(self):
        self.db.add(Device(device_id="HUST-004", name="unrelated", bearing_params={"n": 1}))
        self.db.commit()
        with self.assertRaises(ValueError):
            registration.register_devices(self.db)
        self.assertEqual(self.db.query(Device).count(), 1)
        self.assertEqual(self.db.query(Device).one().name, "unrelated")


if __name__ == "__main__":
    unittest.main()
