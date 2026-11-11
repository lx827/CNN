"""真实HTTP、后台worker和去噪失败语义的最终业务闭环。"""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.models import Device, SensorData, Diagnosis, Alarm
from app.api.data_view import router
from app import lifespan as worker
from app.services import analyzer, diagnosis_workflow as workflow
from app.services.diagnosis import DiagnosisEngine
from app.services.diagnosis.signal_utils import DenoisingError, denoise_signal, prepare_signal
from app.algorithms.decomposition.wavelet import denoise_wavelet


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


class PreprocessingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.engine = database()
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add(Device(device_id="DENOISE", channel_count=1, sample_rate=1024, is_online=1))
            db.add(SensorData(device_id="DENOISE", batch_index=1, channel=1,
                              data=np.zeros(1024).tolist(), sample_rate=1024))
            db.commit()
        application = FastAPI()
        application.include_router(router)

        def session():
            with self.sessions() as db:
                yield db

        application.dependency_overrides[get_db] = session
        self.application = application
        self.client = TestClient(application)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_failed_emd_is_422_across_real_read_and_diagnosis_routes(self):
        cases = [
            ("", {}), ("/export", {}), ("/fft", {}), ("/stft", {}),
            ("/stats", {}), ("/cepstrum", {}), ("/order", {"rot_freq": 20}),
        ]
        for suffix, parameters in cases:
            with self.subTest(route=suffix):
                    response = self.client.get("/api/data/DENOISE/1/1" + suffix,
                                               params={"denoise": "emd", **parameters})
                    self.assertEqual(response.status_code, 422, response.text)
                    detail = response.json()["detail"]
                    self.assertEqual(detail["status"], "not_evaluable")
                    self.assertEqual(detail["method"], "emd")
                    self.assertTrue(detail["reason"])
        with self.sessions() as db:
            self.assertEqual(db.query(Diagnosis).count(), 0)

    def test_unknown_denoising_method_is_never_silently_none(self):
        for suffix in ("/fft", "/envelope", "/gear", "/analyze", "/method-analysis", "/research-analysis"):
            with self.subTest(route=suffix):
                response = self.client.get("/api/data/DENOISE/1/1" + suffix,
                    params={"denoise": "typo", "profile": "runtime"})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"]["method"], "typo")

    def test_none_and_new_wavelet_import_keep_working(self):
        for method in ("none", "wavelet"):
            with self.subTest(method=method):
                response = self.client.get("/api/data/DENOISE/1/1/fft", params={"denoise": method})
                self.assertEqual(response.status_code, 200, response.text)
        signal = np.random.default_rng(4).normal(size=1024)
        actual = DiagnosisEngine(denoise_method="wavelet").preprocess(signal)
        np.testing.assert_allclose(actual, denoise_wavelet(prepare_signal(signal, detrend=True)))

    def test_computation_exception_does_not_return_input_or_fallback(self):
        signal = np.random.default_rng(4).normal(size=1024)
        with patch("app.services.diagnosis.vmd_denoise.vmd_denoise", side_effect=RuntimeError("numerical failure")):
            with self.assertRaisesRegex(DenoisingError, "numerical failure"):
                denoise_signal(signal, "vmd")
        result = analyzer.analyze_device({"ch1": signal.tolist()}, 1024, denoise_method="typo")
        self.assertEqual(result["evaluation_status"], "indeterminate")
        self.assertEqual(result["diagnosis_conclusion"], "unknown")
        self.assertIsNone(result["health_score"])

    def test_openapi_declares_both_denoising_and_request_validation_422(self):
        schema = self.application.openapi()
        responses = schema["paths"]["/api/data/{device_id}/{batch_index}/{channel}/fft"]["get"]["responses"]
        declared = responses["422"]["content"]["application/json"]["schema"]["$ref"]
        self.assertTrue(declared.endswith("/DataViewUnprocessableResponse"))
        detail = schema["components"]["schemas"]["DataViewUnprocessableResponse"]["properties"]["detail"]
        self.assertTrue(any(variant.get("$ref", "").endswith("/DenoisingFailureDetail")
                            for variant in detail["anyOf"]))
        self.assertTrue(any(variant.get("type") == "array" for variant in detail["anyOf"]))
        response = self.client.get("/api/data/DENOISE/1/1/stft", params={"nperseg": 1})
        self.assertEqual(response.status_code, 422)
        self.assertIsInstance(response.json()["detail"], list)


class PreprocessingWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_failed_denoising_persists_unknown_and_broadcasts_without_health_alarm(self):
        engine = database()
        sessions = sessionmaker(bind=engine, autoflush=False)
        with sessions() as db:
            db.add(Device(device_id="FAILED-DENOISE", channel_count=1, sample_rate=1024, is_online=1))
            db.add(SensorData(device_id="FAILED-DENOISE", batch_index=1, channel=1,
                              data=np.zeros(1024).tolist(), sample_rate=1024, is_analyzed=0))
            db.commit()
        messages = []

        async def broadcast(message):
            json.dumps(message, allow_nan=False)
            messages.append(message)

        try:
            with patch.object(worker, "SessionLocal", sessions), \
                 patch.object(workflow, "analyze_device", side_effect=lambda channels, rate, device, rot, denoise, batch: analyzer.analyze_device(channels, rate, device, rot, "emd", batch)), \
                 patch.object(workflow.manager, "broadcast", side_effect=broadcast), \
                 patch.object(worker.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError])):
                await worker.analysis_worker()
            with sessions() as db:
                batch = db.query(Diagnosis).filter_by(channel=0).one()
                channel = db.query(Diagnosis).filter_by(channel=1).one()
                for result in (batch, channel, db.query(Device).one()):
                    self.assertIsNone(result.health_score)
                    self.assertEqual(result.evaluation_status, "indeterminate")
                    self.assertEqual(result.diagnosis_conclusion, "unknown")
                self.assertTrue(channel.engine_result["reason"])
                self.assertEqual(channel.engine_result["evaluations"][0]["evidence"][0]["key"]["denoise_method"], "emd")
                self.assertEqual(db.query(SensorData).one().is_analyzed, 1)
                self.assertEqual(db.query(Alarm).count(), 0)
            self.assertEqual(len(messages), 1)
            self.assertIsNone(messages[0]["data"]["health_score"])
            self.assertEqual(messages[0]["data"]["evaluation_status"], "indeterminate")
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
