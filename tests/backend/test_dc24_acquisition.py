"""DC24 任务、完整文件传输、可选分析与边界；仅使用隔离SQLite和临时目录。"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"cloud"))
from app.api import acquisition as api
from app.api.auth import optional_auth
from app.database import Base, get_db
from app.models import Alarm, Diagnosis


def auth_override(request: Request):
    if request.headers.get("X-Edge-Key") == "test-edge":
        return "edge"
    if request.headers.get("Authorization") == "Bearer test-user":
        return "test-user"
    raise HTTPException(401, "测试认证失败")


def archive(samples=2032, rate=2000, cancelled=False, extra=None):
    t = np.arange(samples)/rate
    carrier = np.rint(1000*(1+.5*np.sin(2*np.pi*30*t))*np.sin(2*np.pi*400*t))
    values = np.column_stack([carrier*(j+1) for j in range(4)])
    text = io.StringIO()
    text.write("sample_index,time_s,ch0_counts,ch1_counts,ch2_counts,ch3_counts\n")
    np.savetxt(text, np.column_stack((np.arange(samples), t, values)), delimiter=",", fmt=["%d", "%.7f", "%d", "%d", "%d", "%d"])
    meta = {"sample_rate_hz": rate, "samples_per_channel": samples,
            "recorded_sample_duration_s": samples/rate, "complete": not cancelled,
            "cancelled": cancelled, "value_unit": "signed_24_bit_ADC_counts",
            "sequence_gaps": [], "unparsed_tail_bytes": 0}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("samples.csv", text.getvalue())
        z.writestr("metadata.json", json.dumps(meta))
        if extra:
            z.writestr(extra, "unwanted")
    return output.getvalue(), values, text.getvalue()


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT/"tmp/dc24_acquisition"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.old_storage = os.environ.get("ACQUISITION_DATA_DIR")
        os.environ["ACQUISITION_DATA_DIR"] = self.temp.name
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        app = FastAPI()
        app.include_router(api.router)

        def database():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[optional_auth] = auth_override
        self.client = TestClient(app)
        self.user = {"Authorization": "Bearer test-user"}
        self.edge = {"X-Edge-Key": "test-edge"}
        self.client.post("/api/acquisition/agents/heartbeat", headers=self.edge,
                         json={"agent_id": "test", "source": "recording_replay", "state": {"sample_rate": 2000}}).raise_for_status()

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        if self.old_storage is None:
            os.environ.pop("ACQUISITION_DATA_DIR", None)
        else:
            os.environ["ACQUISITION_DATA_DIR"] = self.old_storage
        self.temp.cleanup()

    def create(self, **kwargs):
        body = {"agent_id": "test", "sample_rate": 2000, "duration": 1,
                "analysis": {"fft": False, "rms": False, "envelope": False}}
        body.update(kwargs)
        return self.client.post("/api/acquisition/jobs", headers=self.user, json=body)

    def upload(self, job, blob):
        return self.client.post(f"/api/acquisition/jobs/{job}/upload?agent_id=test", headers=self.edge, content=blob)

    def test_validation_auth_and_claim(self):
        self.assertEqual(self.client.get("/api/acquisition/agents").status_code, 401)
        self.assertEqual(self.create(sample_rate=6000).status_code, 422)
        self.assertEqual(self.create(duration=61).status_code, 422)
        self.assertEqual(self.create(analysis={"envelope": True, "band_low": 200, "band_high": 1000}).status_code, 422)
        job = self.create().json()["data"]["id"]
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(self.client.get("/api/acquisition/agents/test/next", headers=self.user).status_code, 403)
        self.assertEqual(self.client.get("/api/acquisition/agents/test/next", headers=self.edge).json()["data"]["id"], job)
        self.assertIsNone(self.client.get("/api/acquisition/agents/test/next", headers=self.edge).json()["data"])
        self.assertEqual(self.client.post(f"/api/acquisition/jobs/{job}/progress?agent_id=other", headers=self.edge, json={"stage": "capturing"}).status_code, 403)

    def test_full_transfer_no_optional_analysis_and_no_diagnosis(self):
        job = self.create().json()["data"]["id"]
        blob, values, csv_text = archive()
        response = self.upload(job, blob)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "completed")
        self.assertTrue(np.array_equal(api.load_values(job), values))
        output = self.client.get(f"/api/acquisition/jobs/{job}/files/samples.csv", headers=self.user)
        self.assertEqual(output.text, csv_text)
        analysis = self.client.get(f"/api/acquisition/jobs/{job}/analysis", headers=self.user).json()["data"]
        self.assertNotIn("fft", analysis["channels"][0])
        self.assertNotIn("rms", analysis["channels"][0])
        self.assertNotIn("envelope", analysis["channels"][0])
        self.assertEqual(self.client.get(f"/api/acquisition/jobs/{job}/waveform?channel=3&start=0&seconds=.1", headers=self.user).json()["data"][3][1], values[3, 3])
        self.assertEqual(self.client.get(f"/api/acquisition/jobs/{job}/waveform?start=9", headers=self.user).status_code, 422)
        self.assertEqual(self.upload(job, blob).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(Alarm).count(), 0)
            self.assertEqual(db.query(Diagnosis).count(), 0)

    def test_selected_fft_rms_and_envelope_band(self):
        job = self.create(analysis={"fft": True, "rms": True, "envelope": True, "band_low": 300, "band_high": 500}).json()["data"]["id"]
        blob, values, _ = archive()
        self.assertEqual(self.upload(job, blob).status_code, 200)
        a = self.client.get(f"/api/acquisition/jobs/{job}/analysis", headers=self.user).json()["data"]
        for j, c in enumerate(a["channels"]):
            self.assertAlmostEqual(c["rms"], np.std(values[:, j]), places=6)
            peak = max(c["fft"], key=lambda item: item[1])[0]
            self.assertLess(abs(peak-400), 2)
            peak = max(c["envelope"], key=lambda item: item[1])[0]
            self.assertLess(abs(peak-30), 2)
        self.assertEqual(self.client.get(f"/api/acquisition/jobs/{job}/files/analysis_arrays.npz", headers=self.user).status_code, 200)

    def test_cancel_preserves_partial_data(self):
        job = self.create().json()["data"]["id"]
        self.client.get("/api/acquisition/agents/test/next", headers=self.edge)
        self.client.post(f"/api/acquisition/jobs/{job}/cancel", headers=self.user)
        stop = self.client.post(f"/api/acquisition/jobs/{job}/progress?agent_id=test", headers=self.edge, json={"stage": "capturing", "samples_per_channel": 254})
        self.assertTrue(stop.json()["data"]["cancel_requested"])
        response = self.upload(job, archive(254, cancelled=True)[0])
        self.assertEqual(response.json()["data"]["status"], "cancelled")
        self.assertEqual(self.client.get(f"/api/acquisition/jobs/{job}/files/samples.csv", headers=self.user).status_code, 200)

    def test_bad_archives_and_rate_rejected(self):
        job = self.create().json()["data"]["id"]
        self.assertEqual(self.upload(job, archive(extra="../outside.txt")[0]).status_code, 422)
        job = self.create().json()["data"]["id"]
        self.assertEqual(self.upload(job, archive(rate=5000)[0]).status_code, 422)


if __name__ == "__main__":
    unittest.main()
