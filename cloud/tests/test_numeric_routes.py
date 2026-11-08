"""专用路由契约：五秒截断必须先于慢去噪，响应形状保持兼容。"""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.api.data_view import cepstrum, spectrum
from app.database import Base
from app.models import SensorData


class NumericRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_numeric_routes_truncate_before_denoising(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(SensorData(
                device_id="NUMERIC",
                batch_index=1,
                channel=1,
                data=np.sin(np.arange(600) / 10).tolist(),
                sample_rate=100,
            ))
            db.commit()
            cases = [
                (spectrum, spectrum.get_channel_fft, {"max_freq": 40}),
                (spectrum, spectrum.get_channel_stft, {
                    "max_freq": 40, "nperseg": 64, "noverlap": 32,
                }),
                (spectrum, spectrum.get_channel_stats, {"window_size": 64, "step": 32}),
                (cepstrum, cepstrum.get_channel_cepstrum, {"max_quefrency": 500}),
            ]
            for module, endpoint, kwargs in cases:
                with self.subTest(endpoint=endpoint.__name__):
                    observed_lengths = []

                    def check_length(signal, method):
                        observed_lengths.append(len(signal))
                        return signal

                    with patch.object(module, "denoise_signal", side_effect=check_length):
                        response = await endpoint(
                            "NUMERIC", 1, 1,
                            detrend=False, denoise="vmd", db=db, **kwargs,
                        )
                    self.assertEqual(observed_lengths, [500])
                    self.assertEqual(response["code"], 200)
        engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
