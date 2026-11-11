"""专用路由契约：五秒截断必须先于慢去噪，响应形状保持兼容。"""

import asyncio
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.data_view import cepstrum, order, spectrum
from app.database import Base, get_db
from app.models import SensorData
from app.algorithms.order import ConstantSpeedOrderPipeline, ScalarSpeed


class NumericRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_automatic_uses_raw_window_while_denoising_yields(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        release = threading.Event()
        values = np.sin(2 * np.pi * 2 * np.arange(600) / 100)
        with Session(engine) as db:
            db.add(
                SensorData(
                    device_id="ORDER_WINDOW",
                    batch_index=1,
                    channel=1,
                    data=values.tolist(),
                    sample_rate=100,
                )
            )
            db.commit()
            observed = {}

            def slow_denoise(signal, method):
                observed["denoise_input"] = signal.copy()
                if not release.wait(1):
                    raise AssertionError("去噪阻塞了事件循环")
                return signal * 0.25

            def capture_order(signal, sample_rate, raw_signal):
                observed["analysis_input"] = signal.copy()
                observed["speed_input"] = raw_signal.copy()
                return ConstantSpeedOrderPipeline().run(
                    signal, sample_rate, ScalarSpeed(2, "test")
                )

            async def heartbeat():
                await asyncio.sleep(0.01)
                release.set()

            with (
                patch.object(order, "denoise_signal", side_effect=slow_denoise),
                patch.object(
                    order.AutomaticOrderPipeline, "run", side_effect=capture_order
                ),
            ):
                response, _ = await asyncio.gather(
                    order.get_channel_order(
                        "ORDER_WINDOW",
                        1,
                        1,
                        freq_min=1,
                        freq_max=20,
                        samples_per_rev=128,
                        max_order=10,
                        rot_freq=None,
                        detrend=True,
                        denoise="vmd",
                        db=db,
                    ),
                    heartbeat(),
                )
            expected = order.prepare_signal(values[:500], detrend=True)
            np.testing.assert_array_equal(observed["speed_input"], expected)
            np.testing.assert_array_equal(observed["denoise_input"], expected)
            np.testing.assert_array_equal(observed["analysis_input"], expected * 0.25)
            self.assertEqual(response["code"], 200)
        engine.dispose()

    async def test_all_numeric_routes_truncate_before_denoising(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(
                SensorData(
                    device_id="NUMERIC",
                    batch_index=1,
                    channel=1,
                    data=np.sin(np.arange(600) / 10).tolist(),
                    sample_rate=100,
                )
            )
            db.commit()
            cases = [
                (spectrum, spectrum.get_channel_fft, {"max_freq": 40}),
                (
                    spectrum,
                    spectrum.get_channel_stft,
                    {
                        "max_freq": 40,
                        "nperseg": 64,
                        "noverlap": 32,
                    },
                ),
                (spectrum, spectrum.get_channel_stats, {"window_size": 64, "step": 32}),
                (cepstrum, cepstrum.get_channel_cepstrum, {"max_quefrency": 500}),
                (
                    order,
                    order.get_channel_order,
                    {
                        "freq_min": 1,
                        "freq_max": 20,
                        "samples_per_rev": 128,
                        "max_order": 10,
                        "rot_freq": 2,
                    },
                ),
            ]
            for module, endpoint, kwargs in cases:
                with self.subTest(endpoint=endpoint.__name__):
                    observed_lengths = []

                    def check_length(signal, method):
                        observed_lengths.append(len(signal))
                        return signal

                    with (
                        patch.object(
                            module, "denoise_signal", side_effect=check_length
                        ),
                        patch.object(
                            module, "prepare_signal", wraps=module.prepare_signal
                        ) as prepare,
                    ):
                        response = await endpoint(
                            "NUMERIC",
                            1,
                            1,
                            detrend=False,
                            denoise="vmd",
                            db=db,
                            **kwargs,
                        )
                    self.assertEqual(observed_lengths, [500])
                    self.assertEqual(len(prepare.call_args.args[0]), 500)
                    self.assertEqual(response["code"], 200)
        engine.dispose()


class NumericHTTPTests(unittest.TestCase):
    def test_order_http_response_is_json_serializable_and_window_limited(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        application = FastAPI()
        application.include_router(order.router)
        observed_lengths = []
        with Session(engine) as db:
            db.add(
                SensorData(
                    device_id="HTTP_ORDER",
                    batch_index=1,
                    channel=1,
                    data=np.sin(2 * np.pi * 2 * np.arange(600) / 100).tolist(),
                    sample_rate=100,
                )
            )
            db.commit()
            application.dependency_overrides[get_db] = lambda: db

            def denoise(signal, method):
                observed_lengths.append(len(signal))
                return signal

            with (
                patch.object(order, "denoise_signal", side_effect=denoise),
                TestClient(application) as client,
            ):
                response = client.get(
                    "/api/data/HTTP_ORDER/1/1/order",
                    params={
                        "rot_freq": 2,
                        "max_order": 10,
                        "samples_per_rev": 128,
                        "denoise": "vmd",
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()["data"]
            self.assertEqual(observed_lengths, [500])
            self.assertEqual(payload["sample_rate"], 100)
            self.assertEqual(len(payload["orders"]), len(payload["spectrum"]))
        engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
