"""实时示波不落盘、原厂档位、显示开关和长记录流式传输。"""
import json
from pathlib import Path
import sys
import unittest
import threading
from unittest.mock import MagicMock, patch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'cloud'))
sys.path.insert(0, str(ROOT/'dc24'))
from app.api import acquisition_live as api
from app.services.acquisition_live import live
from dc24_live import Recording, EventBuffer, decode
from dc24_live import SessionRunner
from dc24_capture import command, samples


def frame(sequence=0, rows=254):
    values = (-8388608, 8388607, -1, 12345)
    group = b''.join(bytes([tag])+v.to_bytes(3, 'little', signed=True) for tag, v in enumerate(values))
    body = b'\x80'+sequence.to_bytes(2, 'little')+group*rows
    return b'\x7e'+len(body).to_bytes(2, 'big')+body+b'\xff'


class LiveTests(unittest.TestCase):
    def setUp(self):
        from test_dc24_acquisition import AcquisitionTests
        self.fixture = AcquisitionTests('test_validation_auth_and_claim')
        self.fixture.setUp()
        self.client = self.fixture.client
        self.client.app.include_router(api.router)
        self.user, self.edge = self.fixture.user, self.fixture.edge
        live.sessions.clear(); live.pickers.clear()
        self.client.post('/api/acquisition/agents/heartbeat', headers=self.edge,
            json={'agent_id': 'test', 'source': 'dc24_tcp', 'state': {'version': 3}}).raise_for_status()

    def tearDown(self):
        live.sessions.clear(); live.pickers.clear()
        self.fixture.tearDown()

    def session(self, rate=5000):
        r = self.client.post('/api/acquisition/sessions', headers=self.user, json={'agent_id': 'test', 'sample_rate': rate})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['data']['id']

    def test_native_rates_duration_and_source_guard(self):
        rates = self.client.get('/api/acquisition/capabilities', headers=self.user).json()['data']['sample_rates']
        self.assertEqual(rates, [50, 100, 200, 500, 1000, 2000, 4000, 5000, 10000, 20000, 50000, 100000])
        self.assertEqual(self.client.post('/api/acquisition/sessions', headers=self.user,
            json={'agent_id': 'test', 'sample_rate': 6000}).status_code, 422)
        sid = self.session(4000)
        record = self.client.post(f'/api/acquisition/sessions/{sid}/record', headers=self.user,
            json={'duration': 3600, 'save_directory': self.fixture.temp.name})
        self.assertEqual(record.status_code, 200)
        self.assertEqual(record.json()['data']['duration'], 3600)
        self.client.post('/api/acquisition/agents/heartbeat', headers=self.edge,
            json={'agent_id': 'replay', 'source': 'recording_replay', 'state': {}})
        self.assertEqual(self.client.post('/api/acquisition/sessions', headers=self.user,
            json={'agent_id': 'replay', 'sample_rate': 5000}).status_code, 409)

    def test_old_voltage_configuration_agent_cannot_start_live_session(self):
        self.client.post('/api/acquisition/agents/heartbeat', headers=self.edge,
            json={'agent_id': 'old', 'source': 'dc24_tcp', 'state': {'version': 2}})
        r = self.client.post('/api/acquisition/sessions', headers=self.user,
            json={'agent_id': 'old', 'sample_rate': 10000})
        self.assertEqual(r.status_code, 409)
        self.assertIn('旧输入配置', r.json()['detail'])

    def test_preview_realtime_has_no_saved_job_and_matches_counts(self):
        sid = self.session(5000)
        x = np.arange(1000, dtype=np.int32)
        values = np.column_stack((x, -x, 2*x, -2*x)).astype('<i4')
        r = self.client.post(f'/api/acquisition/sessions/{sid}/frames?agent_id=test&start=5000&sequence=8', headers=self.edge, content=values.tobytes())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/acquisition/jobs', headers=self.user).json()['data'], [])
        self.assertEqual(list(Path(self.fixture.temp.name).iterdir()), [])
        v = self.client.get(f'/api/acquisition/sessions/{sid}/view?fft=false&rms=false', headers=self.user).json()['data']
        self.assertEqual(v['channels'][2]['waveform'][10], [1.002, 20.0])
        self.assertNotIn('fft', v['channels'][0]); self.assertNotIn('rms', v['channels'][0])
        self.assertEqual(self.client.get(f'/api/acquisition/sessions/{sid}/view?envelope=true&band_low=1&band_high=2500', headers=self.user).status_code, 422)
        self.assertEqual(self.client.get(f'/api/acquisition/agents/test/control', headers=self.user).status_code, 403)

    def test_variable_frames_recording_starts_at_clicked_frame_and_streams(self):
        sid = self.session(20000)
        request = self.client.post(f'/api/acquisition/sessions/{sid}/record', headers=self.user,
            json={'duration': 0, 'save_directory': str(Path(self.fixture.temp.name)/'chosen')}).json()['data']
        r = Recording({'id': request['id'], 'duration': 0, 'save_directory': str(Path(self.fixture.temp.name)/'chosen')},
                      {'id': sid, 'sample_rate': 20000}, EventBuffer())
        original = frame(sequence=99, rows=508)
        seq, values = decode(original)
        # 独立标准库解码和实时NumPy解码必须相同，包括负满量程。
        self.assertTrue(np.array_equal(values, np.asarray(samples(original)[1])))
        r.append(original, seq, values); meta = r.close()
        self.assertEqual(meta['first_device_sequence'], 99)
        self.assertEqual(meta['samples_per_channel'], 508)
        self.assertEqual((r.path/'rx_stream.bin').read_bytes(), original)
        for name in api.STREAM_FILES:
            result = self.client.put(f"/api/acquisition/jobs/{request['id']}/stream-files/{name}?agent_id=test", headers=self.edge,
                                     content=(r.path/name).read_bytes())
            self.assertEqual(result.status_code, 200, result.text)
        result = self.client.post(f"/api/acquisition/jobs/{request['id']}/finish-stream?agent_id=test", headers=self.edge)
        self.assertEqual(result.json()['data']['status'], 'completed')
        self.assertEqual(self.client.get(f"/api/acquisition/jobs/{request['id']}/files/samples.csv", headers=self.user).content,
                         (r.path/'samples.csv').read_bytes())
        wave = self.client.get(f"/api/acquisition/jobs/{request['id']}/waveform?channel=0&seconds=.01", headers=self.user).json()['data']
        self.assertEqual(wave[0][1], -8388608)

    def test_gaps_are_not_joined_and_memory_window_is_bounded(self):
        sid = self.session(1000)
        s = live.get(sid)
        for i in range(40):
            live.push(s, np.full((500, 4), i, dtype=np.int32), i*500, i)
        start, data = live.window(s)
        self.assertEqual(len(data), 2000)
        self.assertEqual(start, 18000)
        live.push(s, np.ones((100, 4), dtype=np.int32), 25000, 45)
        self.assertEqual(len(live.window(s)[1]), 100)

    def test_stopped_is_published_only_after_saved_files_finish_upload(self):
        sid = self.session()
        agent = MagicMock()
        agent.agent_id = 'test'
        agent.get_control.return_value = {'session': {**live.snapshot(live.get(sid)), 'stop_requested': True}}
        runner = SessionRunner(agent, live.snapshot(live.get(sid)))
        runner.stop.set()
        pending, upload_started = threading.Event(), threading.Event()
        def slow_upload():
            upload_started.set(); pending.wait(3)
        upload = threading.Thread(target=slow_upload)
        upload.start(); upload_started.wait(1)
        runner.upload_threads = [upload]
        states = []
        original_update = runner.update
        def update(status):
            states.append(status); original_update(status)
        runner.update = update
        # 仅模拟未连接就停止的socket外壳；真实执行runner的最终清理与上传等待。
        with patch('dc24_live.socket.socket'):
            run = threading.Thread(target=runner.run); run.start()
            for _ in range(100):
                if 'stopping' in states:
                    break
                __import__('time').sleep(.01)
            self.assertIn('stopping', states)
            self.assertNotIn('stopped', states)
            pending.set(); run.join(5)
        self.assertFalse(run.is_alive())
        self.assertEqual(states[-1], 'stopped')


if __name__ == '__main__':
    unittest.main()
