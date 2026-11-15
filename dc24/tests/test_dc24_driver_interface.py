"""公共驱动接口与现有单次采集宿主的契约回归，不连接硬件。"""

import csv
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dc24"))

from dc24_agent import Agent, FILES
from dc24_capture import record
from dc24_driver import Dc24Driver, FrameProtocolDriver, LinkState, SampleBlock
from dc24_live import SessionRunner


def data_frame(sequence=0, rows=254):
    values = (-8388608, 8388607, -1, 12345)
    group = b"".join(
        bytes([tag]) + value.to_bytes(3, "little", signed=True)
        for tag, value in enumerate(values)
    )
    body = b"\x80" + sequence.to_bytes(2, "little") + group * rows
    return b"\x7e" + len(body).to_bytes(2, "big") + body + b"\xff"


class ScriptedDriver:
    transport = "contract_fake"

    def __init__(self):
        self.state = LinkState.WAITING_DEVICE
        self.identity_frame = None
        self.device_source_port = None
        self.on_samples = None
        self.sent = False
        self.after_poll = None

    def connect(self, should_stop, wait=45):
        self.state = LinkState.CONNECTED
        return True

    def start(self, sample_rate, on_samples, raw, events):
        self.on_samples = on_samples
        self.raw = raw
        self.state = LinkState.STREAMING

    def poll(self):
        if self.sent:
            return
        self.sent = True
        frame = data_frame()
        self.raw.write(frame)
        values = np.array([[-8388608, 8388607, -1, 12345]] * 254, dtype="<i4")
        self.on_samples(SampleBlock(sequence=0, frame=frame, values=values))
        if self.after_poll:
            self.after_poll()

    def stop(self):
        self.state = LinkState.STOPPED

    def close(self):
        pass


class DriverInterfaceTests(unittest.TestCase):
    def test_public_interface_does_not_impose_frame_protocol_storage_or_statistics(self):
        class MinimalDriver(Dc24Driver):
            transport = "minimal"

            def connect(self, should_stop, wait=45):
                return True

            def start(self, sample_rate, on_samples, raw, events):
                pass

            def poll(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

        driver = MinimalDriver()
        self.assertNotIsInstance(driver, FrameProtocolDriver)
        for name in ("connection", "link", "received_tcp_bytes", "unparsed_tail_bytes"):
            self.assertFalse(hasattr(driver, name), name)

    def test_record_consumes_public_sample_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "record"
            metadata = record(
                output,
                0.01,
                sample_rate=20000,
                driver=ScriptedDriver(),
            )
            self.assertEqual(metadata["samples_per_channel"], 254)
            self.assertEqual(metadata["transport"], "contract_fake")
            self.assertNotIn("received_tcp_bytes", metadata)
            self.assertNotIn("unparsed_tail_bytes", metadata)
            self.assertTrue(metadata["complete"])
            self.assertEqual((output / "rx_stream.bin").read_bytes(), data_frame())
            with (output / "samples.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 254)
            self.assertEqual(
                [int(rows[0][f"ch{channel}_counts"]) for channel in range(4)],
                [-8388608, 8388607, -1, 12345],
            )
            self.assertEqual(
                json.loads((output / "metadata.json").read_text(encoding="utf-8")),
                metadata,
            )

    def test_local_single_job_registers_original_directory_without_zip_upload(self):
        def save_original(output, *args, **kwargs):
            output.mkdir(parents=True)
            for name in FILES:
                (output / name).write_text("original", encoding="utf-8")
            return {
                "samples_per_channel": 1,
                "sample_rate_hz": 2000,
                "cancelled": False,
                "complete": True,
            }

        with tempfile.TemporaryDirectory() as directory:
            agent = Agent.__new__(Agent)
            agent.agent_id = "local-agent"
            agent.output = Path(directory)
            agent.replay_dir = None
            agent.source = "dc24_tcp"
            agent.local_originals = True
            agent.vendor_root = None
            agent.state = {"stage": "idle"}
            agent.lock = threading.Lock()
            agent.call = Mock(return_value={"status": "completed"})
            agent.heartbeat = Mock()
            agent.report = Mock(return_value={"cancel_requested": False})
            job = {
                "id": "local-job",
                "source": "dc24_tcp",
                "sample_rate": 2000,
                "duration": 1,
            }
            with (
                patch("dc24_agent.record", side_effect=save_original),
                patch("dc24_agent.create_driver"),
                patch("dc24_agent.zipfile.ZipFile") as zip_file,
            ):
                agent.execute(job)
            zip_file.assert_not_called()
            upload = next(
                call
                for call in agent.call.call_args_list
                if call.args[:2] == ("POST", "/jobs/local-job/upload")
            )
            self.assertEqual(
                upload.kwargs["params"]["local_directory"],
                str(Path(directory) / "local-job"),
            )
            self.assertNotIn("data", upload.kwargs)

    def test_live_session_uses_same_driver_interface_and_existing_recording(self):
        class Agent:
            agent_id = "contract-agent"

            def __init__(self, session, local_originals=False):
                self.session = session
                self.local_originals = local_originals
                self.calls = []
                self.requests = []

            def progress(self, state):
                pass

            def heartbeat(self):
                pass

            def get_control(self):
                return {"session": self.session}

            def call(self, method, path, **kwargs):
                self.calls.append((method, path))
                self.requests.append((method, path, kwargs))
                return {"status": "completed"}

        for local_originals in (False, True):
            with (
                self.subTest(local_originals=local_originals),
                tempfile.TemporaryDirectory() as directory,
            ):
                command = {
                    "id": "job",
                    "duration": 0,
                    "save_directory": directory,
                    "stop_requested": False,
                }
                session = {
                    "id": "session",
                    "sample_rate": 20000,
                    "recording": command,
                    "stop_requested": False,
                }
                agent = Agent(session, local_originals=local_originals)
                driver = ScriptedDriver()
                runner = SessionRunner(agent, session, driver=driver)
                driver.after_poll = runner.stop.set
                runner.run()
                output = Path(directory) / "job"
                metadata = json.loads(
                    (output / "metadata.json").read_text(encoding="utf-8")
                )
                self.assertEqual(metadata["samples_per_channel"], 254)
                self.assertEqual(metadata["transport"], "contract_fake")
                self.assertTrue(metadata["complete"])
                self.assertEqual((output / "counts.i32").stat().st_size, 254 * 16)
                finish = next(
                    request
                    for request in agent.requests
                    if request[:2] == ("POST", "/jobs/job/finish-stream")
                )
                uploads = [call for call in agent.calls if call[0] == "PUT"]
                if local_originals:
                    self.assertEqual(uploads, [])
                    self.assertEqual(
                        finish[2]["json"], {"local_directory": str(output)}
                    )
                else:
                    self.assertEqual(len(uploads), 5)
                    self.assertNotIn("json", finish[2])
                self.assertEqual(driver.state, LinkState.STOPPED)


if __name__ == "__main__":
    unittest.main()
