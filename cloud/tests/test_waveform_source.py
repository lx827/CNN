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

from sqlalchemy import create_engine, text
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
        self.assertEqual(waveform.diagnosis_sample_rate, 8192)
        self.assertIsNone(record.diagnosis_sample_rate_override)
        self.assertEqual(waveform.records, [record])
        self.assertEqual(set(waveform.signals), {"ch3"})
        self.assertEqual(waveform.signals["ch3"].dtype, np.float64)
        np.testing.assert_array_equal(waveform.signals["ch3"], values)
        self.assertEqual(record.data, values)

    def test_missing_sample_rate_is_an_error_without_device_or_global_fallback(self):
        self.db.add(Device(device_id="LEGACY", sample_rate=2048, is_online=1))
        self.db.add(
            SensorData(
                device_id="LEGACY",
                batch_index=1,
                channel=1,
                data=[0.0, 1.0],
                sample_rate=None,
            )
        )
        self.db.commit()
        self.db.execute(text("UPDATE sensor_data SET sample_rate=NULL"))
        self.db.commit()
        self.db.expire_all()

        with self.assertRaisesRegex(ValueError, "batch_sample_rate_missing"):
            load_waveform(self.db, "LEGACY", 1)

    def test_migrated_override_separates_display_and_diagnosis_rates(self):
        self.db.add(
            SensorData(
                device_id="LEGACY",
                batch_index=2,
                channel=1,
                data=[0.0, 1.0],
                sample_rate=25600,
                diagnosis_sample_rate_override=48000,
            )
        )
        self.db.commit()
        waveform = load_waveform(self.db, "LEGACY", 2)
        self.assertEqual(waveform.sample_rate, 25600)
        self.assertEqual(waveform.diagnosis_sample_rate, 48000)

    def test_zero_override_keeps_legacy_display_but_fails_diagnosis_read(self):
        self.db.add(
            SensorData(
                device_id="LEGACY",
                batch_index=3,
                channel=1,
                data=[0.0, 1.0],
                sample_rate=25600,
                diagnosis_sample_rate_override=0,
            )
        )
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "batch_sample_rate_missing"):
            load_waveform(self.db, "LEGACY", 3)

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
                    diagnosis_sample_rate_override=48000,
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
                diagnosis_sample_rate_override=48000,
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
            self.assertEqual(observed["sample_rate"], 48000)
            self.assertEqual(set(observed["signals"]), {"ch2"})
            np.testing.assert_array_equal(
                observed["signals"]["ch2"], counts[:, 1].astype(np.float64)
            )
            self.assertEqual(record.is_analyzed, 1)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(self.db.query(SensorData).count(), 1)

    def test_reanalyze_file_selection_creates_new_special_batches(self):
        from app.services import diagnosis_workflow as workflow
        from tests.diagnosis_fixtures import batch_snapshot

        counts = np.arange(8 * 4, dtype="<i4").reshape(8, 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counts.i32"
            counts.tofile(path)
            original_bytes = path.read_bytes()
            source = {
                "kind": "dc24_counts",
                "job_id": "acquisition-job",
                "path": str(path),
                "start_sample": 0,
                "end_sample": 8,
            }
            self.db.add(Device(device_id="LOCAL", sample_rate=1000, is_online=1))
            self.db.add(
                SensorData(
                    device_id="LOCAL",
                    batch_index=101,
                    channel=2,
                    data=source,
                    sample_rate=1000,
                    is_special=1,
                )
            )
            self.db.commit()
            application = FastAPI()
            from app.api.data_view import router

            application.include_router(router)
            application.dependency_overrides[get_db] = lambda: self.db
            observed = []

            def analyze(signals, sample_rate, device, rot_freq, denoise, batch_index):
                observed.append((signals, sample_rate, batch_index))
                return batch_snapshot("LOCAL", batch_index)

            with (
                patch.object(workflow, "analyze_device", side_effect=analyze),
                patch.object(workflow, "save_batch"),
                patch.object(workflow, "generate_alarms", return_value=[]),
                patch.object(workflow.manager, "broadcast", new=AsyncMock()),
                TestClient(application) as client,
            ):
                by_samples = client.post(
                    "/api/data/LOCAL/101/reanalyze",
                    json={
                        "start_sample": 2,
                        "end_sample": 6,
                        "channels": [4, 1],
                    },
                )
                by_time = client.post(
                    "/api/data/LOCAL/101/reanalyze",
                    json={"start_time": 0.001, "end_time": 0.004, "channels": [4]},
                )
                batches = client.get("/api/data/devices")

            self.assertEqual(by_samples.status_code, 200, by_samples.text)
            self.assertEqual(by_samples.json()["data"]["batch_index"], 102)
            self.assertEqual(by_time.status_code, 200, by_time.text)
            self.assertEqual(by_time.json()["data"]["batch_index"], 103)
            self.assertEqual(observed[0][2], 102)
            self.assertEqual(set(observed[0][0]), {"ch1", "ch4"})
            np.testing.assert_array_equal(observed[0][0]["ch1"], counts[2:6, 0])
            np.testing.assert_array_equal(observed[0][0]["ch4"], counts[2:6, 3])
            self.assertEqual(observed[1][2], 103)
            np.testing.assert_array_equal(observed[1][0]["ch4"], counts[1:4, 3])
            records = (
                self.db.query(SensorData)
                .order_by(SensorData.batch_index, SensorData.channel)
                .all()
            )
            self.assertEqual(
                [(row.batch_index, row.channel) for row in records],
                [(101, 2), (102, 1), (102, 4), (103, 4)],
            )
            self.assertTrue(all(row.is_special for row in records))
            self.assertEqual(records[1].data["start_sample"], 2)
            self.assertEqual(records[1].data["end_sample"], 6)
            self.assertEqual(records[-1].data["start_sample"], 1)
            self.assertEqual(records[-1].data["end_sample"], 4)
            self.assertEqual(path.read_bytes(), original_bytes)
            listed = batches.json()["data"][0]["batches"]
            selected = next(row for row in listed if row["batch_index"] == 102)
            self.assertEqual(selected["channels"], [1, 4])
            self.assertEqual(selected["source_kind"], "dc24_counts")

    def test_non_file_batch_rejects_reanalysis_selection(self):
        from app.services import diagnosis_workflow as workflow
        from tests.diagnosis_fixtures import batch_snapshot

        self.db.add(Device(device_id="DB", sample_rate=1000, is_online=1))
        self.db.add(
            SensorData(
                device_id="DB",
                batch_index=1,
                channel=1,
                data=[0.0] * 64,
                sample_rate=1000,
            )
        )
        self.db.commit()
        application = FastAPI()
        from app.api.data_view import router

        application.include_router(router)
        application.dependency_overrides[get_db] = lambda: self.db
        with (
            patch.object(workflow, "analyze_device", return_value=batch_snapshot("DB", 1)),
            patch.object(workflow.manager, "broadcast", new=AsyncMock()),
            TestClient(application) as client,
        ):
            response = client.post(
                "/api/data/DB/1/reanalyze", json={"channels": [1]}
            )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.query(SensorData).count(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
