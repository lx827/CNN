"""DC24 任务、完整文件传输、可选分析与边界；仅使用隔离SQLite和临时目录。"""

import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import AsyncMock, patch

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from app.api import acquisition as api
from app.api.auth import optional_auth
from app.database import Base, get_db
from app.models import AcquisitionJob, Alarm, Device, Diagnosis, SensorData
from app.services.waveform import load_waveform


def auth_override(request: Request):
    if request.headers.get("X-Edge-Key") == "test-edge":
        return "edge"
    if request.headers.get("Authorization") == "Bearer test-user":
        return "test-user"
    raise HTTPException(401, "测试认证失败")


def archive(samples=2032, rate=2000, cancelled=False, extra=None):
    t = np.arange(samples) / rate
    carrier = np.rint(
        1000 * (1 + 0.5 * np.sin(2 * np.pi * 30 * t)) * np.sin(2 * np.pi * 400 * t)
    )
    values = np.column_stack([carrier * (j + 1) for j in range(4)])
    text = io.StringIO()
    text.write("sample_index,time_s,ch0_counts,ch1_counts,ch2_counts,ch3_counts\n")
    np.savetxt(
        text,
        np.column_stack((np.arange(samples), t, values)),
        delimiter=",",
        fmt=["%d", "%.7f", "%d", "%d", "%d", "%d"],
    )
    meta = {
        "sample_rate_hz": rate,
        "samples_per_channel": samples,
        "recorded_sample_duration_s": samples / rate,
        "complete": not cancelled,
        "cancelled": cancelled,
        "value_unit": "signed_24_bit_ADC_counts",
        "sequence_gaps": [],
        "unparsed_tail_bytes": 0,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("samples.csv", text.getvalue())
        z.writestr("metadata.json", json.dumps(meta))
        if extra:
            z.writestr(extra, "unwanted")
    return output.getvalue(), values, text.getvalue()


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "tmp/dc24_acquisition"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.old_storage = os.environ.get("ACQUISITION_DATA_DIR")
        os.environ["ACQUISITION_DATA_DIR"] = self.temp.name
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
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
        self.client.post(
            "/api/acquisition/agents/heartbeat",
            headers=self.edge,
            json={
                "agent_id": "test",
                "source": "recording_replay",
                "state": {"sample_rate": 2000},
            },
        ).raise_for_status()

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        if self.old_storage is None:
            os.environ.pop("ACQUISITION_DATA_DIR", None)
        else:
            os.environ["ACQUISITION_DATA_DIR"] = self.old_storage
        self.temp.cleanup()

    def create(self, **kwargs):
        body = {
            "agent_id": "test",
            "sample_rate": 2000,
            "duration": 1,
            "analysis": {"fft": False, "rms": False, "envelope": False},
        }
        body.update(kwargs)
        return self.client.post("/api/acquisition/jobs", headers=self.user, json=body)

    def upload(self, job, blob):
        return self.client.post(
            f"/api/acquisition/jobs/{job}/upload?agent_id=test",
            headers=self.edge,
            content=blob,
        )

    def test_validation_auth_and_claim(self):
        self.assertEqual(self.client.get("/api/acquisition/agents").status_code, 401)
        self.assertEqual(self.create(sample_rate=6000).status_code, 422)
        self.assertEqual(self.create(duration=0).status_code, 422)
        self.assertEqual(self.create(enabled_channels=[]).status_code, 422)
        self.assertEqual(self.create(enabled_channels=[1, 5]).status_code, 422)
        self.assertEqual(
            self.create(
                analysis={"envelope": True, "band_low": 200, "band_high": 1000}
            ).status_code,
            422,
        )
        job = self.create().json()["data"]["id"]
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(
            self.client.get(
                "/api/acquisition/agents/test/next", headers=self.user
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/acquisition/agents/test/next", headers=self.edge
            ).json()["data"]["id"],
            job,
        )
        self.assertIsNone(
            self.client.get(
                "/api/acquisition/agents/test/next", headers=self.edge
            ).json()["data"]
        )
        self.assertEqual(
            self.client.post(
                f"/api/acquisition/jobs/{job}/progress?agent_id=other",
                headers=self.edge,
                json={"stage": "capturing"},
            ).status_code,
            403,
        )

    def test_full_transfer_registers_one_pending_diagnosis_window(self):
        job = self.create().json()["data"]["id"]
        blob, values, csv_text = archive()
        response = self.upload(job, blob)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "completed")
        with self.sessions() as db:
            self.assertTrue(np.array_equal(api.load_values(db.get(AcquisitionJob, job)), values))
        output = self.client.get(
            f"/api/acquisition/jobs/{job}/files/samples.csv", headers=self.user
        )
        self.assertEqual(output.text, csv_text)
        analysis = self.client.get(
            f"/api/acquisition/jobs/{job}/analysis", headers=self.user
        ).json()["data"]
        self.assertNotIn("fft", analysis["channels"][0])
        self.assertNotIn("rms", analysis["channels"][0])
        self.assertNotIn("envelope", analysis["channels"][0])
        self.assertEqual(
            self.client.get(
                f"/api/acquisition/jobs/{job}/waveform?channel=3&start=0&seconds=.1",
                headers=self.user,
            ).json()["data"][3][1],
            values[3, 3],
        )
        self.assertEqual(
            self.client.get(
                f"/api/acquisition/jobs/{job}/waveform?start=9", headers=self.user
            ).status_code,
            422,
        )
        self.assertEqual(self.upload(job, blob).status_code, 200)
        with self.sessions() as db:
            records = db.query(SensorData).order_by(SensorData.channel).all()
            self.assertEqual([record.channel for record in records], [1, 2, 3, 4])
            self.assertEqual({record.batch_index for record in records}, {101})
            self.assertTrue(all(record.is_special == 1 for record in records))
            self.assertTrue(all(record.is_analyzed == 0 for record in records))
            self.assertEqual(db.query(Device).one().device_id, "test")
            self.assertEqual(db.query(Alarm).count(), 0)
            self.assertEqual(db.query(Diagnosis).count(), 0)

    def test_registered_batch_runs_worker_and_existing_result_pages(self):
        from app import lifespan as worker
        from app.services import diagnosis_workflow as workflow
        from tests.diagnosis_fixtures import batch_snapshot

        job = self.create().json()["data"]["id"]
        blob, values, _ = archive()
        self.assertEqual(self.upload(job, blob).status_code, 200)
        result = batch_snapshot("test", 101)
        with (
            patch.object(worker, "SessionLocal", self.sessions),
            patch.object(workflow, "analyze_device", return_value=result) as analyze,
            patch.object(workflow.manager, "broadcast", new=AsyncMock()),
            patch.object(
                worker.asyncio,
                "sleep",
                AsyncMock(side_effect=[None, asyncio.CancelledError]),
            ),
        ):
            asyncio.run(worker.analysis_worker())

        signals = analyze.call_args.args[0]
        self.assertEqual(set(signals), {"ch1", "ch2", "ch3", "ch4"})
        for channel, signal in signals.items():
            np.testing.assert_array_equal(signal, values[:, int(channel[2:]) - 1])
            self.assertEqual(signal.dtype, np.float64)
        with self.sessions() as db:
            self.assertTrue(
                all(record.is_analyzed == 1 for record in db.query(SensorData))
            )
            self.assertGreater(db.query(Alarm).count(), 0)
            self.assertGreater(db.query(Diagnosis).count(), 0)

        from app.api.data_view import router as data_router

        self.client.app.include_router(data_router)
        batches = self.client.get("/api/data/devices", headers=self.user)
        self.assertEqual(batches.status_code, 200, batches.text)
        device = next(row for row in batches.json()["data"] if row["device_id"] == "test")
        self.assertEqual(device["batches"][0]["batch_index"], 101)
        self.assertEqual(device["batches"][0]["analyzed_at"] is not None, True)
        diagnosis = self.client.get(
            "/api/data/test/101/1/diagnosis", headers=self.user
        )
        self.assertEqual(diagnosis.status_code, 200, diagnosis.text)
        self.assertEqual(diagnosis.json()["data"]["diagnosis_conclusion"], "warning")

    def test_next_job_reuses_the_same_agent_device(self):
        first = self.create().json()["data"]["id"]
        self.assertEqual(self.upload(first, archive()[0]).status_code, 200)
        second = self.create().json()["data"]["id"]
        response = self.upload(second, archive()[0])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["metadata"]["diagnosis_device_id"], "test")
        self.assertEqual(response.json()["data"]["metadata"]["diagnosis_batches"], [102])
        with self.sessions() as db:
            self.assertEqual(db.query(Device).count(), 1)
            self.assertEqual(db.query(SensorData).count(), 8)

    def test_upload_registers_multiple_windows_tail_and_selected_channels_once(self):
        self.client.post(
            "/api/acquisition/agents/heartbeat",
            headers=self.edge,
            json={
                "agent_id": "test",
                "source": "recording_replay",
                "state": {"sample_rate": 50},
            },
        ).raise_for_status()
        job = self.create(
            sample_rate=50, duration=6, enabled_channels=[4, 2]
        ).json()["data"]["id"]
        blob, values, _ = archive(samples=300, rate=50)
        response = self.upload(job, blob)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["enabled_channels"], [2, 4])
        self.assertEqual(response.json()["data"]["metadata"]["diagnosis_batches"], [101, 102])
        # 完成通知网络重试不得再次登记批次。
        self.assertEqual(self.upload(job, blob).status_code, 200)

        with self.sessions() as db:
            records = (
                db.query(SensorData)
                .order_by(SensorData.batch_index, SensorData.channel)
                .all()
            )
            self.assertEqual(len(records), 4)
            self.assertEqual(
                [(r.batch_index, r.channel) for r in records],
                [(101, 2), (101, 4), (102, 2), (102, 4)],
            )
            self.assertEqual(
                [(r.data["start_sample"], r.data["end_sample"]) for r in records],
                [(0, 250), (0, 250), (250, 300), (250, 300)],
            )
            self.assertTrue(all(r.data["kind"] == "dc24_counts" for r in records))
            self.assertTrue(all(r.data["job_id"] == job for r in records))
            first = load_waveform(db, "test", 101)
            last = load_waveform(db, "test", 102)
        np.testing.assert_array_equal(first.signals["ch2"], values[:250, 1])
        np.testing.assert_array_equal(first.signals["ch4"], values[:250, 3])
        np.testing.assert_array_equal(last.signals["ch2"], values[250:, 1])
        np.testing.assert_array_equal(last.signals["ch4"], values[250:, 3])

    def test_local_single_upload_uses_originals_without_backend_copy(self):
        self.client.post(
            "/api/acquisition/agents/heartbeat",
            headers=self.edge,
            json={"agent_id": "test", "source": "dc24_tcp", "state": {}},
        ).raise_for_status()
        job = self.create().json()["data"]["id"]
        blob, values, csv_text = archive()
        with zipfile.ZipFile(io.BytesIO(blob)) as zipped:
            metadata = zipped.read("metadata.json")
        original = Path(self.temp.name) / "field-original"
        original.mkdir()
        (original / "samples.csv").write_text(csv_text, encoding="utf-8")
        (original / "metadata.json").write_bytes(metadata)
        (original / "rx_stream.bin").write_bytes(b"original-frames")
        (original / "commands.jsonl").write_text("{}\n", encoding="utf-8")

        with patch.object(api.config, "IS_LOCAL_DEPLOYMENT", True):
            response = self.client.post(
                f"/api/acquisition/jobs/{job}/upload",
                params={"agent_id": "test", "local_directory": str(original)},
                headers=self.edge,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "completed")
        self.assertEqual(
            response.json()["data"]["metadata"]["local_directory"], str(original)
        )
        self.assertTrue((original / "counts.i32").is_file())
        self.assertTrue((original / "analysis.json").is_file())
        self.assertFalse(api.directory(job).exists())
        with self.sessions() as db:
            orm_job = db.get(AcquisitionJob, job)
            np.testing.assert_array_equal(api.load_values(orm_job), values)
            records = db.query(SensorData).all()
            self.assertEqual(len(records), 4)
            self.assertEqual(
                {record.data["path"] for record in records},
                {str((original / "counts.i32").resolve())},
            )
        analysis = self.client.get(
            f"/api/acquisition/jobs/{job}/analysis", headers=self.user
        )
        self.assertEqual(analysis.status_code, 200, analysis.text)

    def test_selected_fft_rms_and_envelope_band(self):
        job = self.create(
            analysis={
                "fft": True,
                "rms": True,
                "envelope": True,
                "band_low": 300,
                "band_high": 500,
            }
        ).json()["data"]["id"]
        blob, values, _ = archive()
        self.assertEqual(self.upload(job, blob).status_code, 200)
        a = self.client.get(
            f"/api/acquisition/jobs/{job}/analysis", headers=self.user
        ).json()["data"]
        for j, c in enumerate(a["channels"]):
            self.assertAlmostEqual(c["rms"], np.std(values[:, j]), places=6)
            peak = max(c["fft"], key=lambda item: item[1])[0]
            self.assertLess(abs(peak - 400), 2)
            peak = max(c["envelope"], key=lambda item: item[1])[0]
            self.assertLess(abs(peak - 30), 2)
        self.assertEqual(
            self.client.get(
                f"/api/acquisition/jobs/{job}/files/analysis_arrays.npz",
                headers=self.user,
            ).status_code,
            200,
        )

    def test_cancel_preserves_partial_data(self):
        job = self.create().json()["data"]["id"]
        self.client.get("/api/acquisition/agents/test/next", headers=self.edge)
        self.client.post(f"/api/acquisition/jobs/{job}/cancel", headers=self.user)
        stop = self.client.post(
            f"/api/acquisition/jobs/{job}/progress?agent_id=test",
            headers=self.edge,
            json={"stage": "capturing", "samples_per_channel": 254},
        )
        self.assertTrue(stop.json()["data"]["cancel_requested"])
        response = self.upload(job, archive(254, cancelled=True)[0])
        self.assertEqual(response.json()["data"]["status"], "cancelled")
        self.assertEqual(
            self.client.get(
                f"/api/acquisition/jobs/{job}/files/samples.csv", headers=self.user
            ).status_code,
            200,
        )

    def test_bad_archives_and_rate_rejected(self):
        job = self.create().json()["data"]["id"]
        self.assertEqual(
            self.upload(job, archive(extra="../outside.txt")[0]).status_code, 422
        )
        job = self.create().json()["data"]["id"]
        self.assertEqual(self.upload(job, archive(rate=5000)[0]).status_code, 422)


if __name__ == "__main__":
    unittest.main()
