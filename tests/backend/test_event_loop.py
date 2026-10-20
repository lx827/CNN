"""验证实际计算端点在慢速去噪期间仍允许其他协程响应。"""
import asyncio
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud"))
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import SensorData
from app.api.data_view import spectrum, cepstrum, order


class EventLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_denoising_does_not_block_other_requests(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(SensorData(device_id="TEST", batch_index=1, channel=1,
                              data=np.sin(np.arange(1024)).tolist(), sample_rate=1024))
            db.commit()
            for module, endpoint, kwargs in [
                (spectrum, spectrum.get_channel_stft, dict(max_freq=500, nperseg=128, noverlap=64)),
                (cepstrum, cepstrum.get_channel_cepstrum, dict(max_quefrency=500)),
                (order, order.get_channel_order, dict(freq_min=10, freq_max=100, samples_per_rev=64, max_order=20, rot_freq=20)),
            ]:
                with self.subTest(endpoint=endpoint.__name__):
                    release = threading.Event()
                    ticker_ran = False
                    ticker_observed = []

                    def slow_denoise(signal, method):
                        # 后台线程释放时限保护：旧实现会阻塞到超时，修复后协程立即放行。
                        release.wait(timeout=0.25)
                        ticker_observed.append(ticker_ran)
                        return signal

                    async def ticker():
                        nonlocal ticker_ran
                        ticker_ran = True
                        release.set()

                    with patch.object(module, "denoise_signal", slow_denoise):
                        request = asyncio.create_task(endpoint("TEST", 1, 1, detrend=False, denoise="vmd", db=db, **kwargs))
                        tick = asyncio.create_task(ticker())
                        result, _ = await asyncio.gather(request, tick)
                    self.assertEqual(result["code"], 200)
                    self.assertEqual(ticker_observed, [True], "去噪直接阻塞事件循环，其他请求无法被调度")
        engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
