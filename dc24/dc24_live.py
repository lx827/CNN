"""真正的连续示波：预览只驻留内存，开始保存后从下一完整帧记录。"""

from collections import deque
from contextlib import closing, contextmanager
import csv
import io
import json
from pathlib import Path
import socket
import threading
import time
import numpy as np
from dc24_capture import (
    HOST,
    PEER,
    PORT,
    B5_PROFILES,
    CONFIG_B2,
    INPUT_CONFIGURATION,
    Link,
)
from dc24_vendor import VendorConnection


def decode(frame):
    if frame[3] != 0x80 or len(frame) < 23 or (len(frame) - 7) % 16:
        raise ValueError("四通道数据帧尺寸无效")
    words = np.frombuffer(
        frame, dtype="<i4", offset=6, count=(len(frame) - 7) // 4
    ).reshape(-1, 4)
    if not np.all((words & 255) == np.arange(4)):
        raise ValueError("设备通道排列与四通道配置不符")
    return int.from_bytes(frame[4:6], "little"), (words >> 8).astype("<i4")


class EventBuffer:
    def __init__(self):
        self.lines = deque(maxlen=100)

    def write(self, value):
        self.lines.append(value)
        return len(value)

    def flush(self):
        pass


class Discard:
    def write(self, value):
        return len(value)


class Recording:
    def __init__(self, command, session, events):
        root = Path(command["save_directory"]).expanduser()
        if not root.is_absolute():
            raise ValueError("保存目录必须是现场电脑上的绝对路径")
        self.path = root.resolve() / command["id"]
        self.path.mkdir(parents=True, exist_ok=False)
        self.job_id, self.duration, self.rate = (
            command["id"],
            command["duration"],
            session["sample_rate"],
        )
        self.count, self.frames, self.first_sequence, self.last_sequence = (
            0,
            0,
            None,
            None,
        )
        self.csv_file = (self.path / "samples.csv").open(
            "x", encoding="utf-8", newline=""
        )
        self.writer = csv.writer(self.csv_file)
        self.writer.writerow(
            [
                "sample_index",
                "time_s",
                "ch0_counts",
                "ch1_counts",
                "ch2_counts",
                "ch3_counts",
            ]
        )
        self.raw = (self.path / "rx_stream.bin").open("xb")
        self.binary = (self.path / "counts.i32").open("xb")
        (self.path / "commands.jsonl").write_text(
            "".join(events.lines), encoding="utf-8"
        )
        self.meta = dict(
            source="dc24_tcp",
            session_id=session["id"],
            device_ip=PEER,
            host_ip=HOST,
            host_tcp_port=PORT,
            sample_rate_hz=self.rate,
            requested_duration_s=self.duration,
            value_unit="signed_24_bit_ADC_counts",
            physical_scaling="未确认传感器标定；保留原始计数",
            channel_tags=[0, 1, 2, 3],
            b5_payload_hex=B5_PROFILES[self.rate].hex(),
            sequence_gaps=[],
            b2_payload_hex=CONFIG_B2.hex(),
            input_configuration=dict(INPUT_CONFIGURATION),
            raw_content="所保存样本对应的完整设备协议帧；示波开始前样本未保存",
            saved_directory=str(self.path),
            complete=False,
        )

    def append(self, frame, sequence, values):
        if self.first_sequence is None:
            self.first_sequence = sequence
        self.last_sequence = sequence
        self.raw.write(frame)
        self.binary.write(values.tobytes())
        start = self.count
        self.writer.writerows(
            [start + i, f"{(start + i) / self.rate:.9f}", *row]
            for i, row in enumerate(values.tolist())
        )
        self.count += len(values)
        self.frames += 1

    def close(self, error=None):
        self.csv_file.close()
        self.raw.close()
        self.binary.close()
        self.meta.update(
            samples_per_channel=self.count,
            data_frames=self.frames,
            recorded_sample_duration_s=self.count / self.rate,
            first_device_sequence=self.first_sequence,
            last_device_sequence=self.last_sequence,
            complete=not error,
            error=error,
            unparsed_tail_bytes=0,
            end_reason="error" if error else "operator_or_requested_duration",
        )
        (self.path / "metadata.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.meta


class SessionRunner:
    def __init__(self, agent, session, vendor_root=None):
        self.agent, self.session = agent, session
        self.vendor_root = vendor_root
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.control = session
        self.chunks = deque()
        self.count = self.sent = 0
        self.sequence = None
        self.previous_sequence = None
        self.recording = None
        self.seen_records = set()
        self.upload_threads = []
        self.events = EventBuffer()
        self.status, self.error, self.record_state = "waiting_device", None, None

    def update(self, status):
        with self.lock:
            self.status = status
        self.agent.progress(
            {
                "stage": status,
                "hardware_connected": status == "streaming",
                "session_id": self.session["id"],
            }
        )

    def upload(self, recording, meta):
        state = dict(
            id=recording.job_id,
            status="uploading",
            samples_per_channel=recording.count,
            saved_directory=str(recording.path),
        )
        with self.lock:
            self.record_state = state
        try:
            self.agent.call(
                "POST",
                f"/jobs/{recording.job_id}/progress",
                params={"agent_id": self.agent.agent_id},
                json={"stage": "uploading", "samples_per_channel": recording.count},
            )
            for name in (
                "samples.csv",
                "metadata.json",
                "rx_stream.bin",
                "commands.jsonl",
                "counts.i32",
            ):
                for attempt in range(3):
                    try:
                        with (recording.path / name).open("rb") as f:
                            self.agent.call(
                                "PUT",
                                f"/jobs/{recording.job_id}/stream-files/{name}",
                                params={"agent_id": self.agent.agent_id},
                                data=f,
                                timeout=(5, 180),
                            )
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(1)
            result = self.agent.call(
                "POST",
                f"/jobs/{recording.job_id}/finish-stream",
                params={"agent_id": self.agent.agent_id},
                timeout=(5, 180),
            )
            state["status"] = result["status"]
        except Exception as exc:
            state["status"], state["error"] = "failed", str(exc)[:300]
            try:
                self.agent.call(
                    "POST",
                    f"/jobs/{recording.job_id}/progress",
                    params={"agent_id": self.agent.agent_id},
                    json={
                        "stage": "failed",
                        "samples_per_channel": recording.count,
                        "message": "上传失败，本地文件保留：" + str(recording.path),
                    },
                )
            except Exception:
                pass
        with self.lock:
            self.record_state = state

    def end_record(self, error=None):
        r = self.recording
        if not r:
            return
        self.recording = None
        meta = r.close(error)
        t = threading.Thread(target=self.upload, args=(r, meta), daemon=True)
        self.upload_threads.append(t)
        t.start()

    def consume(self, frame):
        sequence, values = decode(frame)
        if (
            self.previous_sequence is not None
            and (sequence - self.previous_sequence) & 65535 != 1
        ):
            raise ValueError(f"设备数据帧不连续：{self.previous_sequence} → {sequence}")
        self.previous_sequence = sequence
        with self.lock:
            self.sequence = sequence
            self.chunks.append((self.count, values))
            self.count += len(values)
            cutoff = self.count - self.session["sample_rate"] * 2
            while self.chunks and self.chunks[0][0] + len(self.chunks[0][1]) <= cutoff:
                self.chunks.popleft()
            command = self.control.get("recording")
            if (
                command
                and command["id"] not in self.seen_records
                and not command.get("stop_requested")
            ):
                self.seen_records.add(command["id"])
                try:
                    self.recording = Recording(command, self.session, self.events)
                    self.recording.meta["session_sample_start"] = self.count - len(
                        values
                    )
                    self.recording.meta["transport"] = (
                        "jmserver" if self.vendor_root else "python_tcp"
                    )
                except Exception as exc:
                    self.record_state = dict(
                        id=command["id"], status="failed", error=str(exc)
                    )
                    self.agent.call(
                        "POST",
                        f"/jobs/{command['id']}/progress",
                        params={"agent_id": self.agent.agent_id},
                        json={"stage": "failed", "message": str(exc)[:500]},
                    )
            if self.recording:
                if command and command.get("stop_requested"):
                    self.end_record()
                else:
                    self.recording.append(frame, sequence, values)
                    self.record_state = dict(
                        id=self.recording.job_id,
                        status="capturing",
                        samples_per_channel=self.recording.count,
                        saved_directory=str(self.recording.path),
                    )
                    if (
                        self.recording.duration
                        and self.recording.count
                        >= self.recording.duration * self.recording.rate
                    ):
                        self.end_record()

    def monitor(self):
        last_heartbeat = 0
        while not self.finished.is_set():
            try:
                if time.monotonic() - last_heartbeat >= 1:
                    self.agent.heartbeat()
                    last_heartbeat = time.monotonic()
                control = self.agent.get_control()["session"]
                if not control or control["id"] != self.session["id"]:
                    self.stop.set()
                else:
                    with self.lock:
                        self.control = control
                    if control["stop_requested"]:
                        self.stop.set()
                with self.lock:
                    state = dict(
                        status=self.status,
                        error=self.error,
                        recording=self.record_state,
                    )
                    chunks = [
                        (start, values)
                        for start, values in self.chunks
                        if start + len(values) > self.sent
                    ]
                    sequence = self.sequence
                self.agent.call(
                    "POST",
                    f"/sessions/{self.session['id']}/state",
                    params={"agent_id": self.agent.agent_id},
                    json=state,
                )
                if chunks:
                    start = chunks[0][0]
                    data = np.concatenate([v for _, v in chunks])
                    # 裁去重叠部分，不重复绘制；断网超出窗口时明确保留绝对样本索引缺口。
                    if start < self.sent:
                        data, start = data[self.sent - start :], self.sent
                    self.agent.call(
                        "POST",
                        f"/sessions/{self.session['id']}/frames",
                        params={
                            "agent_id": self.agent.agent_id,
                            "start": start,
                            "sequence": sequence,
                        },
                        data=data.astype("<i4").tobytes(),
                    )
                    self.sent = start + len(data)
            except Exception:
                pass  # 网络暂时断开不影响正在进行的本地完整保存。
            self.finished.wait(0.25)

    @contextmanager
    def _connection(self):
        if self.vendor_root:
            with closing(
                VendorConnection(self.vendor_root, HOST, PORT, PEER)
            ) as connection:
                yield connection if connection.wait_for_device(self.stop, 45) else None
            return
        with socket.socket() as server:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            server.bind((HOST, PORT))
            server.listen(1)
            server.settimeout(0.25)
            deadline = time.monotonic() + 45
            while not self.stop.is_set() and time.monotonic() < deadline:
                try:
                    candidate, address = server.accept()
                except socket.timeout:
                    continue
                with candidate:
                    if address[0] == PEER:
                        yield candidate
                        return
            if not self.stop.is_set():
                raise TimeoutError(
                    "45秒内未收到采集器连接，请检查网线、IP和原厂软件是否脱机"
                )
            yield None

    def run(self):
        monitor = threading.Thread(target=self.monitor, daemon=True)
        monitor.start()
        try:
            self.update("waiting_device")
            with self._connection() as connection:
                if connection is None:
                    return
                started = False
                link = Link(connection, Discard(), self.events)
                try:
                    self.update("configuring")
                    link.exchange(0xBA, status=False)
                    link.exchange(0xB8)
                    link.exchange(0xB2, CONFIG_B2)
                    link.exchange(0xB5, B5_PROFILES[self.session["sample_rate"]])
                    if self.stop.is_set():
                        return
                    link.on_data = self.consume
                    started = True
                    link.exchange(0xB7, b"\x00")
                    self.update("streaming")
                    while not self.stop.is_set():
                        if any(frame[3] == 0xB8 for frame in link.pump()):
                            raise RuntimeError("设备在示波期间应答了未请求的停止命令")
                        with self.lock:
                            if self.recording and self.control.get("recording", {}).get(
                                "stop_requested"
                            ):
                                self.end_record()
                    with self.lock:
                        self.end_record()
                    link.exchange(0xB8)
                    started = False
                finally:
                    if started:
                        try:
                            link.send(0xB8)
                        except OSError:
                            pass
        except BaseException as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (
                10013,
                10048,
            ):
                self.error = "电脑TCP 6800被占用，请先让原厂软件脱机"
            with self.lock:
                self.end_record(self.error)
        finally:
            self.update("stopping")
            # 停止期间继续报告上传状态；副本完成后才发布终态，避免启动器过早结束边端。
            for t in self.upload_threads:
                t.join()
            self.update("failed" if self.error else "stopped")
            self.finished.set()
            monitor.join(timeout=12)
            try:
                self.agent.call(
                    "POST",
                    f"/sessions/{self.session['id']}/state",
                    params={"agent_id": self.agent.agent_id},
                    json=dict(
                        status=self.status,
                        error=self.error,
                        recording=self.record_state,
                    ),
                )
            except Exception:
                pass
            self.agent.progress(
                {"stage": "idle", "hardware_connected": False, "session_id": None}
            )
