"""dc24_edge_pi 驱动回归：纯逻辑单测 + 回环集成（假设备 + 假云端 + 真实 FFI 核心）。

纯逻辑部分不需要动态库；集成部分定位 edge/target 下的 dc24_edge_core（找不到且
有 cargo 时先构建），用 Python socket 模拟 DC24（拨入→应答 BA/B8/B2/B5/B7→发
80 帧→应答停止，帧格式照 edge/tests/ffi.rs 的 data_frame），用 http.server 模拟
云端，跑通一整会话并以外显观测断言五件套与上传内容。
"""

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dc24"))

import numpy as np  # noqa: E402

import dc24_ffi  # noqa: E402
from dc24_capture import Frames, command, samples  # noqa: E402  既有实机验证过的协议解析
from dc24_ffi import Dc24Msg, EdgeCore  # noqa: E402
import dc24_edge_pi as pi  # noqa: E402

SID = "1" * 32
JOB = "2" * 32
ROW_VALUES = (-8388608, 8388607, -1, 12345)
IDENTITY = bytes.fromhex("7e0013ba5500000000000000000600002b1a0cffff5942")


def data_frame(sequence: int, rows: int = 254) -> bytes:
    """与 edge/tests/ffi.rs data_frame 同构的 80 采样帧。"""
    body = bytearray(b"\x80")
    body += sequence.to_bytes(2, "little")
    for _ in range(rows):
        for tag, value in enumerate(ROW_VALUES):
            body += (((value << 8) | tag) & 0xFFFFFFFF).to_bytes(4, "little")
    return b"\x7e" + len(body).to_bytes(2, "big") + bytes(body) + b"\xff"


# ===================================================================== 纯逻辑单测
class MessageLayoutTests(unittest.TestCase):
    def test_dc24_msg_mirrors_repr_c_layout(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("仅验证 64 位平台布局")
        offsets = {name: getattr(Dc24Msg, name).offset for name, _ in Dc24Msg._fields_}
        self.assertEqual(
            offsets, {"tag": 0, "sequence": 2, "start_sample": 8, "len": 16, "data": 24}
        )
        self.assertEqual(ctypes.sizeof(Dc24Msg), 32)


class WindowTests(unittest.TestCase):
    def test_after_returns_only_unsent_and_skips_confirmed_prefix(self):
        window = pi.Window()
        first, second = bytes(16 * 10), bytes(16 * 10)
        window.push(0, first, 10000)
        window.push(10, second, 10000)
        self.assertEqual(window.after(0), (0, first + second))
        self.assertEqual(window.after(10), (10, second))
        self.assertEqual(window.after(5), (5, first[80:] + second))
        self.assertIsNone(window.after(20))

    def test_window_stays_bounded_and_preserves_absolute_gap(self):
        window = pi.Window()
        for index in range(10):
            window.push(index * 100, bytes(16 * 100), 100)  # 速率100，2秒窗口=200样本
        self.assertEqual(window.end, 1000)
        start, payload = window.after(0)
        self.assertEqual(start, 800)  # 缺口显式保留在绝对索引，而非拼接补齐
        self.assertEqual(len(payload), 200 * 16)
        self.assertEqual(start + len(payload) // 16, window.end)
        self.assertIsNone(window.after(window.end))


class HeartbeatTests(unittest.TestCase):
    INFO = {
        "version": 3,
        "sample_rates": [50, 100, 1000],
        "channel_count": 4,
        "input_configuration": {"measurement": "IEPE"},
        "transport": "rust_tcp",
        "implementation": "dc24-edge-rust-ffi-0.1.0",
    }

    def test_state_fields_come_from_info_not_hardcoded(self):
        state = pi.heartbeat_state(
            self.INFO,
            stage="streaming",
            hardware_connected=True,
            save_directory="/var/lib/dc24-edge",
            session_id=SID,
            error=None,
        )
        self.assertEqual(state["version"], 3)
        self.assertEqual(state["sample_rates"], [50, 100, 1000])
        self.assertEqual(state["input_configuration"], {"measurement": "IEPE"})
        self.assertEqual(state["transport"], "rust_tcp")
        self.assertEqual(state["implementation"], "dc24-edge-rust-ffi-0.1.0")
        self.assertEqual(state["stage"], "streaming")
        self.assertTrue(state["hardware_connected"])
        info = dict(self.INFO, version=7, transport="other")
        changed = pi.heartbeat_state(
            info,
            stage="idle",
            hardware_connected=False,
            save_directory="/tmp",
            session_id=None,
            error="x",
        )
        self.assertEqual(changed["version"], 7)  # 元数据跟随核心上报，不在驱动里写死
        self.assertEqual(changed["transport"], "other")

    def test_state_key_set_matches_runtime_baseline(self):
        state = pi.heartbeat_state(
            self.INFO,
            stage="idle",
            hardware_connected=False,
            save_directory="/tmp",
            session_id=None,
            error=None,
        )
        self.assertEqual(
            set(state),
            {
                "stage",
                "hardware_connected",
                "sample_rates",
                "channel_count",
                "save_directory",
                "version",
                "input_configuration",
                "transport",
                "implementation",
                "session_id",
                "error",
            },
        )


class StaleSessionTests(unittest.TestCase):
    def test_restart_guard_detection(self):
        self.assertFalse(
            pi.session_is_stale({"samples_received": 0, "status": "waiting_device"})
        )
        self.assertTrue(
            pi.session_is_stale({"samples_received": 5, "status": "waiting_device"})
        )
        for status in ("streaming", "configuring", "stopping"):
            self.assertTrue(
                pi.session_is_stale({"samples_received": 0, "status": status})
            )


class RebuildFrameTests(unittest.TestCase):
    def test_rebuild_is_exact_inverse_of_protocol_decode(self):
        rng = np.random.default_rng(20261108)
        values = rng.integers(-8388608, 8388608, size=(254, 4)).astype("<i4")
        data = values.tobytes()
        frame = pi.rebuild_frame(7, data)
        sequence, rows = samples(frame)  # 既有实机验证过的解析器做仲裁
        self.assertEqual(sequence, 7)
        self.assertEqual(
            [tuple(row) for row in rows], [tuple(row) for row in values.tolist()]
        )
        self.assertEqual(frame[0], 0x7E)
        self.assertEqual(frame[-1], 0xFF)
        self.assertEqual(int.from_bytes(frame[1:3], "big"), 3 + len(data))
        self.assertEqual(len(frame), 7 + len(data))

    def test_rebuild_matches_protocol_frame_construction(self):
        values = (-8388608, 8388607, -1, 12345)
        data = b"".join(
            v.to_bytes(4, "little", signed=True) for v in values
        )  # 核心解码后的值
        packed = b"".join(
            ((v << 8) | ch).to_bytes(4, "little", signed=True)
            for ch, v in enumerate(values)
        )  # 设备线上原始 4 字节项
        manual = b"\x7e\x00\x13\x80\x00\x00" + packed + b"\xff"
        self.assertEqual(pi.rebuild_frame(0, data), manual)


class StubCloud:
    """清单状态机测试用的云端替身：记录调用，可注入失败与远端任务状态。"""

    def __init__(self, fail_uploads=0, remote_job=None):
        self.calls = []
        self.files = {}
        self.fail_uploads = fail_uploads
        self.remote_job = remote_job
        self.finished = []

    def get_job(self, job):
        self.calls.append(("get_job", job))
        return self.remote_job

    def progress(self, job, stage, samples_per_channel=0, message=""):
        self.calls.append(("progress", job, stage, message))

    def put_stream_file(self, job, name, path):
        if self.fail_uploads > 0:
            self.fail_uploads -= 1
            raise pi.CloudError("模拟 503")
        self.files[name] = path.read_bytes()
        self.calls.append(("put", job, name))

    def finish_stream(self, job):
        self.calls.append(("finish", job))
        self.finished.append(job)


class Cfg:
    def __init__(self, storage, agent_id="pi-test"):
        self.storage = Path(storage)
        self.agent_id = agent_id


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.storage = Path(tempfile.mkdtemp(prefix="dc24-pi-manifest-"))
        self.cfg = Cfg(self.storage)

    def tearDown(self):
        shutil.rmtree(self.storage, ignore_errors=True)

    def make_recording(self, job=JOB, agent="pi-test", status="pending", samples=10):
        root = self.storage / job
        root.mkdir(parents=True)
        for name in pi.RECORD_FILES:
            (root / name).write_bytes(b"x")
        path = pi.manifest_path(self.storage, job)
        path.parent.mkdir(parents=True, exist_ok=True)
        pi.atomic_json(
            path,
            {
                "job": job,
                "session": SID,
                "agent": agent,
                "path": str(root),
                "status": status,
                "samples": samples,
            },
        )
        return path

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_pending_uploads_five_files_then_finish(self):
        path = self.make_recording()
        cloud = StubCloud()
        manifest = self.read(path)
        pi.step_manifest(self.cfg, cloud, manifest, path)
        self.assertEqual(manifest["status"], "uploaded")
        self.assertEqual(self.read(path)["status"], "uploaded")  # 每步持久化
        self.assertEqual(cloud.finished, [JOB])
        self.assertEqual(
            [call[2] for call in cloud.calls if call[0] == "put"], list(pi.RECORD_FILES)
        )
        self.assertTrue(
            any(
                call[0] == "progress" and call[2] == "uploading" for call in cloud.calls
            )
        )

    def test_failed_upload_keeps_pending_and_retry_is_idempotent(self):
        path = self.make_recording()
        cloud = StubCloud(fail_uploads=1)
        manifest = self.read(path)
        with self.assertRaises(pi.CloudError):
            pi.step_manifest(self.cfg, cloud, manifest, path)
        self.assertEqual(self.read(path)["status"], "pending")  # 失败不清单，原件保留
        cloud.remote_job = {"status": "completed", "metadata": {"complete": True}}
        pi.step_manifest(self.cfg, cloud, manifest, path)
        self.assertEqual(manifest["status"], "uploaded")
        self.assertEqual(cloud.files, {})  # 远端已完成：不重传文件
        self.assertEqual(len([c for c in cloud.calls if c[0] == "get_job"]), 2)

    def test_interrupted_recording_reports_failure_without_upload(self):
        path = self.make_recording(status="recording")
        pi.prepare_manifests(self.storage)
        self.assertEqual(self.read(path)["status"], "interrupted")
        cloud = StubCloud()
        manifest = self.read(path)
        pi.step_manifest(self.cfg, cloud, manifest, path)
        self.assertEqual(manifest["status"], "interrupted_reported")
        failed = [c for c in cloud.calls if c[0] == "progress" and c[2] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("中断", failed[0][3])
        self.assertEqual(cloud.files, {})  # 未冒充完整记录上传

    def test_foreign_agent_manifest_is_skipped(self):
        path = self.make_recording(agent="someone-else")
        cloud = StubCloud()
        manifest = self.read(path)
        pi.step_manifest(self.cfg, cloud, manifest, path)
        self.assertEqual(manifest["status"], "mismatched")
        self.assertEqual(cloud.calls, [])


# ===================================================================== 回环集成
def build_or_locate_library():
    explicit = os.environ.get("DC24_EDGE_LIB")
    candidates = [Path(explicit)] if explicit else []
    candidates += dc24_ffi.default_search_paths()
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    edge = ROOT / "edge"
    if not (edge / "Cargo.toml").is_file():
        return None
    try:
        subprocess.run(
            ["cargo", "build"], cwd=edge, capture_output=True, timeout=570, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for candidate in dc24_ffi.default_search_paths():
        if candidate.is_file():
            return candidate
    return None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FakeCloud:
    """假云端：复刻 acquisition.py/acquisition_live.py 的关键校验与状态流转。"""

    def __init__(self, save_root: Path, agent="pi-test", key="pi-test-key"):
        self.agent, self.key, self.save_root = agent, key, save_root
        self.lock = threading.Lock()
        self.heartbeats = []
        self.states = []
        self.progress_calls = []
        self.frames_posts = []
        self.files = {}
        self.put_attempts = []
        self.finish_calls = []
        self.directory_results = []
        self.reject_left = 1  # 第一个未存过的文件 PUT 一律 503，验证驱动重试
        self.finished = False
        self.job_status = {}
        self.session = {
            "id": SID,
            "agent_id": agent,
            "sample_rate": 1000,
            "status": "waiting_device",
            "stop_requested": False,
            "recording": None,
            "samples_received": 0,
        }
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 30

            def log_message(self, *args):
                pass

            def _send(self, status, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def _route(self, method):
                parsed = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                if self.headers.get("X-Edge-Key") != outer.key:
                    self._send(403, {"detail": "边端密钥不符"})
                    return
                body = self._body()
                path = parsed.path
                if method == "POST" and path == "/api/acquisition/agents/heartbeat":
                    payload = json.loads(body)
                    with outer.lock:
                        outer.heartbeats.append(payload)
                    self._send(200, {"code": 200})
                elif (
                    method == "POST"
                    and path
                    == f"/api/acquisition/agents/{outer.agent}/directory-result"
                ):
                    with outer.lock:
                        outer.directory_results.append(json.loads(body))
                    self._send(200, {"code": 200})
                elif (
                    method == "GET"
                    and path == f"/api/acquisition/agents/{outer.agent}/control"
                ):
                    with outer.lock:
                        gone = outer.finished or outer.session["status"] in (
                            "stopped",
                            "failed",
                        )
                        data = {
                            "session": None
                            if gone
                            else json.loads(json.dumps(outer.session)),
                            "picker": None,
                        }
                    self._send(200, {"code": 200, "data": data})
                elif (
                    method == "POST"
                    and path == f"/api/acquisition/sessions/{SID}/state"
                ):
                    payload = json.loads(body)
                    with outer.lock:
                        outer.states.append(payload)
                        session = outer.session
                        if payload.get("status") in (
                            "waiting_device",
                            "configuring",
                            "streaming",
                            "stopping",
                            "stopped",
                            "failed",
                        ):
                            session["status"] = payload["status"]
                        session["error"] = payload.get("error")
                        if (
                            session.get("recording")
                            and payload.get("recording")
                            and payload["recording"].get("id")
                            == session["recording"]["id"]
                        ):
                            session["recording"].update(payload["recording"])
                    self._send(200, {"code": 200})
                elif (
                    method == "POST"
                    and path == f"/api/acquisition/sessions/{SID}/frames"
                ):
                    if not body or len(body) % 16:
                        self._send(422, {"detail": "四通道原始计数格式无效"})
                        return
                    with outer.lock:
                        post = {
                            "start": int(query["start"]),
                            "sequence": int(query["sequence"]),
                            "n": len(body) // 16,
                            "head": body[:16].hex(),
                        }
                        outer.frames_posts.append(post)
                        session = outer.session
                        end = post["start"] + post["n"]
                        session["samples_received"] = max(
                            session["samples_received"], end
                        )
                        if session["recording"] is None and end > 0:
                            session["recording"] = {
                                "id": JOB,
                                "duration": 1,
                                "save_directory": str(outer.save_root),
                                "stop_requested": False,
                                "status": "waiting_device",
                                "samples_per_channel": 0,
                            }
                            outer.job_status[JOB] = "waiting_device"
                    self._send(200, {"code": 200})
                elif method == "GET" and path == f"/api/acquisition/jobs/{JOB}":
                    with outer.lock:
                        status = (
                            "completed"
                            if outer.finished
                            else outer.job_status.get(JOB, "waiting_device")
                        )
                        metadata = None
                        if outer.finished and "metadata.json" in outer.files:
                            metadata = json.loads(outer.files["metadata.json"])
                    self._send(
                        200,
                        {"code": 200, "data": {"status": status, "metadata": metadata}},
                    )
                elif (
                    method == "POST" and path == f"/api/acquisition/jobs/{JOB}/progress"
                ):
                    payload = json.loads(body)
                    with outer.lock:
                        outer.progress_calls.append(
                            (
                                JOB,
                                payload["stage"],
                                payload.get("samples_per_channel", 0),
                                payload.get("message", ""),
                            )
                        )
                        if JOB not in outer.job_status or outer.job_status[JOB] not in (
                            "completed",
                            "failed",
                        ):
                            outer.job_status[JOB] = payload["stage"]
                    self._send(200, {"code": 200, "data": {"cancel_requested": False}})
                elif (
                    method == "PUT"
                    and f"/api/acquisition/jobs/{JOB}/stream-files/" in path
                ):
                    name = path.rsplit("/", 1)[-1]
                    if name not in pi.RECORD_FILES:
                        self._send(409, {"detail": "文件名无效"})
                        return
                    with outer.lock:
                        outer.put_attempts.append(name)
                        if outer.reject_left > 0 and name not in outer.files:
                            outer.reject_left -= 1
                            rejected = True
                        else:
                            outer.files[name] = body
                            rejected = False
                    if rejected:
                        self._send(503, {"detail": "模拟上传失败"})
                    else:
                        self._send(200, {"code": 200})
                elif (
                    method == "POST"
                    and path == f"/api/acquisition/jobs/{JOB}/finish-stream"
                ):
                    with outer.lock:
                        missing = [
                            name for name in pi.RECORD_FILES if name not in outer.files
                        ]
                        if missing:
                            self._send(422, {"detail": f"缺少文件 {missing}"})
                            return
                        meta = json.loads(outer.files["metadata.json"])
                        count = meta.get("samples_per_channel", 0)
                        if (
                            meta.get("source") != "dc24_tcp"
                            or meta.get("sample_rate_hz") != 1000
                            or meta.get("value_unit") != "signed_24_bit_ADC_counts"
                            or count <= 0
                            or len(outer.files["counts.i32"]) != count * 16
                        ):
                            self._send(
                                422, {"detail": "实际数据、单位或采样率与任务不一致"}
                            )
                            return
                        outer.finished = True
                        outer.job_status[JOB] = (
                            "completed" if meta.get("complete") else "failed"
                        )
                        outer.session["stop_requested"] = True
                        outer.finish_calls.append(JOB)
                        data = {"status": outer.job_status[JOB]}
                    self._send(200, {"code": 200, "data": data})
                else:
                    self._send(404, {"detail": "未知端点"})

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

            def do_PUT(self):
                self._route("PUT")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def run_fake_device(port, errors, frame_delay=0.02):
    """模拟 DC24：拨入 → 应答控制命令 → B7 后持续发 80 帧直到 B8（照 ffi.rs spawn_device）。"""
    sock = None
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("无法连入核心监听")
                time.sleep(0.02)
        sock.settimeout(0.01)
        parser = Frames()
        sampling = False
        sequence = 0
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                chunk = None
            if chunk == b"":
                break
            if chunk:
                for frame in parser.feed(chunk):
                    code = frame[3]
                    if code == 0xB7:
                        sampling = True
                    elif code == 0xB8:
                        sampling = False
                    sock.sendall(IDENTITY if code == 0xBA else command(code, b"\x00"))
            if sampling:
                data = data_frame(sequence)
                sequence = (sequence + 1) & 0xFFFF
                half = len(data) // 2  # 分片发送，覆盖 TCP 重组路径
                sock.sendall(data[:half])
                sock.sendall(data[half:])
                time.sleep(frame_delay)
    except Exception as exc:  # 记录后由测试断言
        errors.append(exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class LibraryTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library = build_or_locate_library()
        if library is None:
            raise unittest.SkipTest(
                "找不到也无法构建 dc24_edge_core（需要 Rust 工具链，"
                "或设置 DC24_EDGE_LIB 指向已构建库）"
            )
        cls.library = library


class FfiBindingTests(LibraryTestCase):
    def test_info_json_reports_core_metadata(self):
        core = EdgeCore(self.library)
        try:
            info = core.info()
            self.assertEqual(info["version"], 3)
            self.assertEqual(info["channel_count"], 4)
            self.assertEqual(len(info["sample_rates"]), 12)
            self.assertEqual(
                info["b5_payload_hex_by_rate"]["10000"], "00001c00102700000f000000"
            )  # 第11节现行 IEPE 模板
            self.assertEqual(info["b2_payload_hex"], "00010001000100010301000000")
        finally:
            core.close()

    # 注意：不测错误文本路径——edge/src/ffi.rs write_err 存在越界 bug
    # （消息短于缓冲时 bytes[end] 越界 panic，宿主进程直接 abort），已在交付报告中
    # 登记；修复合入前，任何触发错误写入的 FFI 调用都会杀死宿主进程，无法断言。


class PiDriverEndToEndTests(LibraryTestCase):
    def test_full_session_records_five_files_and_uploads_with_retry(self):
        storage = Path(tempfile.mkdtemp(prefix="dc24-pi-storage-"))
        save_root = Path(tempfile.mkdtemp(prefix="dc24-pi-saves-"))
        cloud = FakeCloud(save_root)
        device_port = free_port()
        config_path = storage / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "cloud_url": cloud.url(),
                    "agent_id": "pi-test",
                    "api_key_env": "DC24_PI_TEST_KEY",
                    "listen_ip": "127.0.0.1",
                    "device_ip": "127.0.0.1",
                    "port": device_port,
                    "storage": storage.as_posix(),
                    "mode": "cloud",
                    "sample_rate": None,
                    "duration_seconds": None,
                    "interval_seconds": None,
                    "min_free_bytes": 0,
                    "http_timeout_seconds": 4,
                    "upload_timeout_seconds": 30,
                    "device_wait_seconds": 5,
                    "data_timeout_seconds": 3,
                }
            ),
            encoding="utf-8",
        )
        previous = os.environ.get("DC24_PI_TEST_KEY")
        os.environ["DC24_PI_TEST_KEY"] = "pi-test-key"
        device_errors, driver_errors = [], []
        quit = threading.Event()
        device = threading.Thread(
            target=run_fake_device, args=(device_port, device_errors), daemon=True
        )
        info = EdgeCore(self.library).info()

        def drive():
            try:
                pi.run(config_path, self.library, once=True, quit_event=quit)
            except BaseException as exc:  # 记录后由断言给出
                driver_errors.append(exc)

        driver = threading.Thread(target=drive, daemon=True)
        try:
            device.start()
            driver.start()
            deadline = time.monotonic() + 90
            while driver.is_alive() and time.monotonic() < deadline:
                time.sleep(0.1)
            driver.join(timeout=30)
            device.join(timeout=10)
            self.assertEqual(driver_errors, [], f"驱动异常退出: {driver_errors}")
            self.assertFalse(device.is_alive())
            self.assertEqual(device_errors, [])

            with cloud.lock:
                self.assertTrue(cloud.finished, f"会话未完成: states={cloud.states}")
                self.assertEqual(cloud.session["status"], "stopped")
                frames_posts = list(cloud.frames_posts)
                heartbeats = list(cloud.heartbeats)
                states = list(cloud.states)
                remote_files = dict(cloud.files)
                put_attempts = list(cloud.put_attempts)
                progress_calls = list(cloud.progress_calls)
            manifest = json.loads(
                (storage / ".uploads" / f"{JOB}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "uploaded")

            # ---- 本地五件套
            local = save_root / JOB
            meta = json.loads((local / "metadata.json").read_text(encoding="utf-8"))
            count = meta["samples_per_channel"]
            self.assertGreaterEqual(count, 1000)  # duration=1s@1000Hz，按实际点数
            self.assertEqual(count % 254, 0)  # 整帧收尾
            self.assertTrue(meta["complete"])
            self.assertIsNone(meta["error"])
            self.assertEqual(meta["source"], "dc24_tcp")
            self.assertEqual(meta["sample_rate_hz"], 1000)
            self.assertEqual(meta["value_unit"], "signed_24_bit_ADC_counts")
            self.assertEqual(meta["b2_payload_hex"], info["b2_payload_hex"])
            self.assertEqual(
                meta["b5_payload_hex"], info["b5_payload_hex_by_rate"]["1000"]
            )
            self.assertEqual(meta["input_configuration"], info["input_configuration"])
            self.assertEqual((local / "counts.i32").stat().st_size, count * 16)
            self.assertEqual(
                (local / "rx_stream.bin").stat().st_size, count // 254 * (7 + 254 * 16)
            )
            # 云端收到的五个文件与本地逐字节一致
            for name in pi.RECORD_FILES:
                self.assertEqual(remote_files[name], (local / name).read_bytes(), name)

            # ---- samples.csv：行数、表头、首尾行
            lines = (local / "samples.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), count + 1)
            self.assertEqual(
                lines[0],
                "sample_index,time_s,ch0_counts,ch1_counts,ch2_counts,ch3_counts",
            )
            self.assertEqual(lines[1], "0,0.000000000,-8388608,8388607,-1,12345")
            tail = lines[-1].split(",")
            self.assertEqual(int(tail[0]), count - 1)
            self.assertEqual(tail[2:], ["-8388608", "8388607", "-1", "12345"])
            self.assertAlmostEqual(float(tail[1]), (count - 1) / 1000, places=9)

            # ---- rx_stream.bin：用既有解析器重组，样本数与序号完全对齐
            parser = Frames()
            frames = parser.feed((local / "rx_stream.bin").read_bytes())
            self.assertEqual(len(parser.buffer), 0)  # 不留半帧
            self.assertEqual(len(frames), count // 254)
            decoded = [samples(frame) for frame in frames]
            sequences = [sequence for sequence, _ in decoded]
            # 保存从云端下发任务后的下一完整帧开始，帧号从中间起但必须连续
            self.assertEqual(
                sequences, list(range(sequences[0], sequences[0] + len(sequences)))
            )
            self.assertTrue(all(rows == [ROW_VALUES] * 254 for _, rows in decoded))
            self.assertEqual(meta["first_device_sequence"], sequences[0])
            self.assertEqual(meta["last_device_sequence"], sequences[-1])

            # ---- commands.jsonl：合法 JSON 行，含现行 B2/B5 下发与设备应答
            events = [
                json.loads(line)
                for line in (local / "commands.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertTrue(events)
            sent = {
                e["command"]: e["hex"]
                for e in events
                if e["direction"] == "host_to_device"
            }
            self.assertIn("B2", sent)
            self.assertIn(info["b2_payload_hex"], sent["B2"])
            self.assertIn("B5", sent)
            self.assertIn(info["b5_payload_hex_by_rate"]["1000"], sent["B5"])
            self.assertTrue(
                any(
                    e["direction"] == "device_to_host" and e["command"] == "B8"
                    for e in events
                )
            )

            # ---- 实时窗口上传：绝对索引、不重发已确认区间
            self.assertTrue(frames_posts)
            expected_head = b"".join(
                v.to_bytes(4, "little", signed=True) for v in ROW_VALUES
            ).hex()
            previous_end = 0
            for post in frames_posts:
                self.assertGreater(post["n"], 0)
                self.assertGreaterEqual(post["start"], previous_end)  # 只进不退：不重发
                self.assertEqual(post["head"], expected_head)
                previous_end = post["start"] + post["n"]
            self.assertGreaterEqual(
                frames_posts[0]["start"], 0
            )  # 首包可能已因窗口裁剪起于非0（缺口显式保留）
            self.assertEqual(cloud.session["samples_received"], previous_end)

            # ---- 心跳字段以核心元数据为准
            self.assertTrue(heartbeats)
            for beat in heartbeats:
                self.assertEqual(beat["agent_id"], "pi-test")
                self.assertEqual(beat["source"], "dc24_tcp")
                self.assertEqual(beat["state"]["version"], 3)
                self.assertEqual(beat["state"]["sample_rates"], info["sample_rates"])
                self.assertEqual(beat["state"]["channel_count"], 4)
                self.assertEqual(beat["state"]["transport"], "rust_tcp")
            # ---- 状态上报覆盖完整生命周期；上传有一次 503 重试
            reported = [state.get("status") for state in states]
            self.assertIn("streaming", reported)
            self.assertEqual(reported[-1], "stopped")
            self.assertIn("uploading", [stage for _, stage, _, _ in progress_calls])
            self.assertEqual(
                len(put_attempts), len(pi.RECORD_FILES) + 1
            )  # 首个 PUT 被拒后重试
        finally:
            quit.set()  # 无论断言结果如何，让驱动主循环与设备线程收尾
            cloud.close()
            shutil.rmtree(storage, ignore_errors=True)
            shutil.rmtree(save_root, ignore_errors=True)
            if previous is None:
                os.environ.pop("DC24_PI_TEST_KEY", None)
            else:
                os.environ["DC24_PI_TEST_KEY"] = previous


if __name__ == "__main__":
    unittest.main()
