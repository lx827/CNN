"""以本机TCP仿真设备验证拆包、配置、停止及异常；不连接现场硬件。"""
import csv
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"edge"))
import dc24_capture as driver


def data_frame(sequence):
    word = b"".join(bytes([tag])+value.to_bytes(3, "little", signed=True)
                    for tag, value in enumerate((-8388608, 8388607, -1, 12345)))
    body = b"\x80"+sequence.to_bytes(2, "little")+word*254
    return b"\x7e"+len(body).to_bytes(2, "big")+body+b"\xff"


class DriverTests(unittest.TestCase):
    def run_device(self, rate=5000, cancel=False, gap=False):
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            port = reserve.getsockname()[1]
        stop, done = threading.Event(), threading.Event()
        commands, failures = [], []

        def device():
            try:
                with socket.socket() as s:
                    for _ in range(100):
                        try:
                            s.connect(("127.0.0.1", port))
                            break
                        except ConnectionRefusedError:
                            time.sleep(.01)
                    s.settimeout(.03)
                    parser, active, seq = driver.Frames(), False, 0
                    while not done.is_set():
                        try:
                            chunk = s.recv(65536)
                            if not chunk:
                                break
                            for frame in parser.feed(chunk):
                                code = frame[3]
                                commands.append((code, frame[4:-1]))
                                ack = driver.command(code, b"\x00")
                                # 有意拆开控制应答，验证TCP半包。
                                s.sendall(ack[:2]); s.sendall(ack[2:])
                                if code == 0xB7:
                                    active = True
                                if code == 0xB8:
                                    active = False
                        except socket.timeout:
                            pass
                        if active:
                            frame = data_frame(seq)
                            s.sendall(frame[:97]); s.sendall(frame[97:])
                            seq += 2 if gap else 1
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                failures.append(exc)

        root = ROOT/"tmp/dc24_acquisition"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp, patch.object(driver, "PORT", port):
            thread = threading.Thread(target=device, daemon=True)
            thread.start()
            try:
                def progress(state):
                    if cancel and state["samples_per_channel"] >= 254:
                        stop.set()
                output = Path(tmp)/"record"
                if gap:
                    with self.assertRaisesRegex(ValueError, "Nonconsecutive"):
                        driver.record(output, 1, host="127.0.0.1", peer="127.0.0.1", sample_rate=rate)
                    meta = json.loads((output/"metadata.json").read_text(encoding="utf-8"))
                    self.assertFalse(meta["complete"])
                    self.assertEqual(meta["sequence_gaps"], [[0, 2]])
                else:
                    meta = driver.record(output, 1 if cancel else .05, host="127.0.0.1", peer="127.0.0.1",
                                         sample_rate=rate, on_progress=progress, should_stop=stop.is_set)
                    self.assertEqual(meta["cancelled"], cancel)
                    self.assertEqual(meta["complete"], not cancel)
                    with (output/"samples.csv").open() as f:
                        rows = list(csv.DictReader(f))
                    self.assertGreaterEqual(len(rows), 254)
                    self.assertEqual([int(rows[0][f"ch{i}_counts"]) for i in range(4)],
                                     [-8388608, 8388607, -1, 12345])
                    self.assertEqual(len(rows), meta["samples_per_channel"])
                self.assertIn((0xB5, driver.B5_PROFILES[rate]), commands)
                # 固定为用户2026-11-06确认有效的原厂IEPE/AC0.2Hz/PASS报文，
                # 不能用“等于实现自身常量”掩盖再次发送旧电压配置。
                self.assertIn((0xB2, bytes.fromhex('00010001000100010301000000')), commands)
                if rate == 10000:
                    self.assertIn((0xB5, bytes.fromhex('00001c00102700000f000000')), commands)
                self.assertGreaterEqual(sum(c == 0xB8 for c, _ in commands), 2 if not gap else 1)
            finally:
                done.set()
                thread.join(2)
            self.assertFalse(failures, failures)

    def test_both_profiles_and_signed_counts(self):
        for rate in (2000, 5000):
            with self.subTest(rate=rate):
                self.run_device(rate)

    def test_confirmed_iepe_pass_configuration_on_wire(self):
        self.run_device(10000)

    def test_stop_saves_partial_data(self):
        self.run_device(cancel=True)

    def test_sequence_gap_fails_loud(self):
        self.run_device(gap=True)

    def test_waiting_device_can_stop(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp/dc24_acquisition") as tmp, patch.object(driver, "PORT", 0):
            meta = driver.record(Path(tmp)/"cancelled", 1, host="127.0.0.1", should_stop=lambda: True)
            self.assertTrue(meta["cancelled"])
            self.assertFalse(meta["complete"])
            self.assertEqual(meta["samples_per_channel"], 0)


if __name__ == "__main__":
    unittest.main()
