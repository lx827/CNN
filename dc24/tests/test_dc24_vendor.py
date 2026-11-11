"""原厂 DLL 的回环集成回归，使用模拟采集器，不连接硬件。"""

import io
import os
from pathlib import Path
import socket
import sys
import threading
from time import monotonic
import unittest

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dc24"))
from dc24_capture import B5_PROFILES, CONFIG_B2, Frames, Link, command, samples
from dc24_vendor import VendorConnection


class VendorConnectionTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "原厂 DLL 需要 Windows")
    def test_dll_receives_frames_and_preserves_control_messages(self):
        vendor_root = os.environ.get(
            "DC24_VENDOR_ROOT",
            dotenv_values(ROOT / "dc24/.env").get("DC24_VENDOR_ROOT"),
        )
        if not vendor_root:
            self.skipTest("未配置本机原厂软件目录")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        expected = [
            (0xBA, b""),
            (0xB8, b""),
            (0xB2, CONFIG_B2),
            (0xB5, B5_PROFILES[10000]),
            (0xB7, b"\x00"),
            (0xB8, b""),
        ]
        identity = bytes.fromhex("7e0013ba5500000000000000000600002b1a0cffff5942")
        tagged = b"".join(
            bytes([ch]) + count.to_bytes(3, "little", signed=True)
            for ch, count in enumerate((-8388608, -1, 0, 8388607))
        )
        wire_frame = b"\x7e\x1f\xc3\x80\x00\x00" + tagged * 508 + b"\xff"
        observed, errors, received = [], [], []

        def simulate():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=5) as peer:
                    peer.settimeout(5)
                    peer.sendall(command(0xE0, b"\x09\x00Lan Login"))
                    parser = Frames()
                    while len(observed) < len(expected):
                        chunk = peer.recv(65536)
                        if not chunk:
                            raise ConnectionError("模拟采集器提前断开")
                        for frame in parser.feed(chunk):
                            observed.append(frame)
                            code = frame[3]
                            peer.sendall(
                                identity if code == 0xBA else command(code, b"\x00")
                            )
                            if code == 0xB7:
                                peer.sendall(wire_frame[:2])
                                peer.sendall(wire_frame[2:])
                    if parser.buffer:
                        raise ValueError("控制帧未完整接收")
                    # 由边端先释放连接，便于确认正常停止退出。
                    if peer.recv(1):
                        raise ValueError("设备停止后收到额外控制命令")
            except Exception as exc:
                errors.append(exc)

        connection = VendorConnection(vendor_root, "127.0.0.1", port, "127.0.0.1")
        worker = threading.Thread(target=simulate, daemon=True)
        try:
            deadline = monotonic() + 8
            while not connection.ready.wait(0.1):
                self.assertFalse(connection.disconnected.is_set(), "DLL 提前退出")
                self.assertLess(monotonic(), deadline, "DLL 未进入监听")
            worker.start()
            self.assertTrue(connection.wait_for_device(threading.Event(), 5))
            link = Link(connection, io.BytesIO(), io.StringIO())
            link.on_data = lambda frame: received.append(samples(frame))
            for code, payload in expected[:-1]:
                link.exchange(code, payload, status=code != 0xBA)
            deadline = monotonic() + 5
            while not received:
                self.assertLess(monotonic(), deadline, "没有收到回调采样帧")
                link.pump()
            link.exchange(*expected[-1])
        finally:
            connection.close()
            if worker.ident is not None:
                worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            observed, [command(code, payload) for code, payload in expected]
        )
        self.assertEqual(received, [(0, [(-8388608, -1, 0, 8388607)] * 508)])


if __name__ == "__main__":
    unittest.main()
