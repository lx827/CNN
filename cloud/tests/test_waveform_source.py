"""统一波形读取接口：数据库数组与 DC24 原始文件共用同一接缝。"""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models import Device, SensorData
from app.services.waveform import load_waveform


class WaveformSourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_database_arrays_keep_values_and_records(self):
        values = [0.0, 1.25, -2.5, 4.0]
        self.db.add(Device(device_id="DB", sample_rate=25600, is_online=1))
        record = SensorData(
            device_id="DB",
            batch_index=7,
            channel=3,
            data=values.copy(),
            sample_rate=8192,
        )
        self.db.add(record)
        self.db.commit()

        waveform = load_waveform(self.db, "DB", 7)

        self.assertEqual(waveform.sample_rate, 8192)
        self.assertEqual(waveform.records, [record])
        self.assertEqual(set(waveform.signals), {"ch3"})
        self.assertEqual(waveform.signals["ch3"].dtype, np.float64)
        np.testing.assert_array_equal(waveform.signals["ch3"], values)
        self.assertEqual(record.data, values)

    def test_dc24_file_reads_sample_window_and_real_channels(self):
        counts = np.array(
            [
                [0, 10, 20, 30],
                [1, 11, 21, 31],
                [2, 12, 22, 32],
                [3, 13, 23, 33],
                [4, 14, 24, 34],
                [5, 15, 25, 35],
            ],
            dtype="<i4",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counts.i32"
            counts.tofile(path)
            source = {
                "kind": "dc24_counts",
                "job_id": "acquisition-job",
                "path": str(path),
                "start_sample": 1,
                "end_sample": 5,
            }
            self.db.add_all(
                [
                    SensorData(
                        device_id="LOCAL",
                        batch_index=101,
                        channel=channel,
                        data=source,
                        sample_rate=1000,
                    )
                    for channel in (2, 4)
                ]
            )
            self.db.commit()

            waveform = load_waveform(self.db, "LOCAL", 101)

        self.assertEqual(waveform.sample_rate, 1000)
        self.assertEqual(set(waveform.signals), {"ch2", "ch4"})
        for signal in waveform.signals.values():
            self.assertEqual(signal.dtype, np.float64)
            self.assertEqual(signal.ndim, 1)
        np.testing.assert_array_equal(waveform.signals["ch2"], [11, 12, 13, 14])
        np.testing.assert_array_equal(waveform.signals["ch4"], [31, 32, 33, 34])

    def test_dataview_stats_http_uses_unified_file_source(self):
        counts = np.arange(128 * 4, dtype="<i4").reshape(128, 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counts.i32"
            counts.tofile(path)
            self.db.add(Device(device_id="LOCAL", sample_rate=1000, is_online=1))
            self.db.add(
                SensorData(
                    device_id="LOCAL",
                    batch_index=101,
                    channel=2,
                    data={
                        "kind": "dc24_counts",
                        "job_id": "acquisition-job",
                        "path": str(path),
                        "start_sample": 0,
                        "end_sample": 128,
                    },
                    sample_rate=1000,
                )
            )
            self.db.commit()
            application = FastAPI()
            from app.api.data_view import router

            application.include_router(router)
            application.dependency_overrides[get_db] = lambda: self.db
            with (
                patch(
                    "app.services.waveform.load_waveform", wraps=load_waveform
                ) as load,
                TestClient(application) as client,
            ):
                response = client.get(
                    "/api/data/LOCAL/101/2/stats",
                    params={"window_size": 64, "step": 64},
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["sample_rate"], 1000)
        self.assertEqual(load.call_count, 1)

    def test_monitor_http_uses_unified_file_source(self):
        counts = np.arange(128 * 4, dtype="<i4").reshape(128, 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counts.i32"
            counts.tofile(path)
            self.db.add(Device(device_id="LOCAL", sample_rate=1000, is_online=1))
            self.db.add(
                SensorData(
                    device_id="LOCAL",
                    batch_index=101,
                    channel=2,
                    data={
                        "kind": "dc24_counts",
                        "job_id": "acquisition-job",
                        "path": str(path),
                        "start_sample": 0,
                        "end_sample": 128,
                    },
                    sample_rate=1000,
                    is_special=1,
                )
            )
            self.db.commit()
            application = FastAPI()
            from app.api.monitor import router

            application.include_router(router)
            application.dependency_overrides[get_db] = lambda: self.db
            with TestClient(application) as client:
                latest = client.get("/api/monitor/latest?device_id=LOCAL")
                history = client.get(
                    "/api/monitor/history?device_id=LOCAL&channel=2&batches=1"
                )

        self.assertEqual(latest.status_code, 200, latest.text)
        item = latest.json()["data"][0]
        self.assertEqual(item["channel"], 2)
        self.assertEqual(item["data"], counts[:, 1].tolist())
        self.assertTrue(item["fft_freq"])
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(
            history.json()["data"]["items"][0]["data"], counts[:, 1].tolist()
        )

    def test_reanalyze_http_uses_unified_file_source_and_marks_records(self):
        from app.services import diagnosis_workflow as workflow

        counts = np.arange(128 * 4, dtype="<i4").reshape(128, 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counts.i32"
            counts.tofile(path)
            self.db.add(Device(device_id="LOCAL", sample_rate=1000, is_online=1))
            record = SensorData(
                device_id="LOCAL",
                batch_index=101,
                channel=2,
                data={
                    "kind": "dc24_counts",
                    "job_id": "acquisition-job",
                    "path": str(path),
                    "start_sample": 0,
                    "end_sample": 128,
                },
                sample_rate=1000,
                is_analyzed=0,
            )
            self.db.add(record)
            self.db.commit()
            application = FastAPI()
            from app.api.data_view import router

            application.include_router(router)
            application.dependency_overrides[get_db] = lambda: self.db
            observed = {}

            def analyze(signals, sample_rate, *args):
                observed["signals"] = signals
                observed["sample_rate"] = sample_rate
                from tests.diagnosis_fixtures import batch_snapshot

                return batch_snapshot("LOCAL", 101)

            with (
                patch(
                    "app.services.waveform.load_waveform", wraps=load_waveform
                ) as load,
                patch.object(workflow, "analyze_device", side_effect=analyze),
                patch.object(workflow, "save_batch"),
                patch.object(workflow, "generate_alarms", return_value=[]),
                patch.object(workflow.manager, "broadcast", new=AsyncMock()),
                TestClient(application) as client,
            ):
                response = client.post("/api/data/LOCAL/101/reanalyze")

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(observed["sample_rate"], 1000)
            self.assertEqual(set(observed["signals"]), {"ch2"})
            np.testing.assert_array_equal(
                observed["signals"]["ch2"], counts[:, 1].astype(np.float64)
            )
            self.assertEqual(record.is_analyzed, 1)
            self.assertEqual(load.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
