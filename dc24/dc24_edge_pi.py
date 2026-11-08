"""树莓派边端驱动：Rust 网络核心(cdylib) + 云端会话编排 + 五件套落盘 + 上传。

部署形态（edge/README.md 的"核心动态库"路线）：设备链路全部由 dc24_edge_core
承担（常驻监听、每秒 00 心跳、BA/B8/B2/B5/B7 时序、80 帧解码、序号校验），
本文件只做宿主侧工作——加载库、轮询消息、按云端会话编排、落盘、上传。

行为基线对照 edge/src/runtime.rs：
- 实时窗口约最近 2 秒，按绝对样本索引显式保留缺口，不重发已确认区间；
- 保存任务五件套（samples.csv / counts.i32 / rx_stream.bin / commands.jsonl /
  metadata.json），格式与 dc24_capture.py / dc24_live.py 既有链路一致；
- 失败补传用本地清单（storage/.uploads/*.json）持久化，幂等可重试；
- 控制/心跳短超时与文件上传长超时分离（两个独立 HTTP 会话）；
- 边端重启后拒绝复用旧会话的样本索引（防索引从零重用）。

v1 范围：只做云端下发会话（config.json 的 mode=cloud），本地定时/持续模式不做。
配置与 Rust 核心共用同一份 config.json（schema 见 edge/src/config.rs，
deny_unknown_fields，不得添加私有键）；密钥只从 api_key_env 指定的环境变量读取。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import requests

from dc24_ffi import EdgeCore, MSG_EVENT, MSG_SAMPLES, MSG_STATE

# 五件套文件名与上传顺序（与云端 STREAM_FILES、runtime.rs FILES 一致）。
RECORD_FILES = ("samples.csv", "metadata.json", "rx_stream.bin", "commands.jsonl", "counts.i32")
TERMINAL_STATES = ("stopped", "failed")
AGENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
# 核心链路状态 → 云端会话状态（云端只接受 acquisition_live.state 的六个取值）。
STATE_TO_STATUS = {
    "connected": "configuring",
    "streaming": "streaming",
    "stopping": "stopping",
    "stopped": "stopped",
    "failed": "failed",
}


def valid_id(value) -> bool:
    """云端会话/任务 ID：32 位小写十六进制（与 config.rs valid_id 一致）。"""
    return isinstance(value, str) and len(value) == 32 and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def atomic_json(path: Path, payload) -> None:
    """临时文件 + 原子替换写 JSON（镜像 recording.rs atomic_json）。"""
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


# ===================================================================== 云端客户端
class CloudError(RuntimeError):
    """云端拒绝请求（HTTP 错误或业务 code != 200）。"""


class CloudClient:
    """现有 /api/acquisition 接口客户端；控制与上传分离为两个会话、两套超时。"""

    def __init__(self, cloud_url: str, agent_id: str, key: str, http_timeout=4.0, upload_timeout=180.0):
        if not key or "\r" in key or "\n" in key:
            raise ValueError("密钥为空或含换行符")
        self.base = cloud_url.rstrip("/") + "/api/acquisition"
        self.agent_id = agent_id
        # 超时分离（重要教训）：控制/心跳短超时，文件上传长超时。
        self.http_timeout = float(http_timeout)
        self.upload_timeout = float(upload_timeout)
        self.control_http = requests.Session()
        self.upload_http = requests.Session()
        for http in (self.control_http, self.upload_http):
            http.headers.update({"X-Edge-Key": key})

    def _call(self, method, path, *, params=None, json_body=None, data=None, upload=False, headers=None):
        http = self.upload_http if upload else self.control_http
        timeout = self.upload_timeout if upload else self.http_timeout
        response = http.request(method, self.base + path, params=params, json=json_body,
                                data=data, timeout=timeout, headers=headers)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 200:
            raise CloudError(f"云端业务响应失败: {body}")
        return body.get("data")

    def heartbeat(self, state: dict):
        return self._call("POST", "/agents/heartbeat",
                          json_body={"agent_id": self.agent_id, "source": "dc24_tcp", "state": state})

    def control(self):
        return self._call("GET", f"/agents/{self.agent_id}/control")

    def state(self, session_id: str, body: dict):
        return self._call("POST", f"/sessions/{session_id}/state",
                          params={"agent_id": self.agent_id}, json_body=body)

    def frames(self, session_id: str, start: int, sequence: int, data: bytes):
        return self._call("POST", f"/sessions/{session_id}/frames",
                          params={"agent_id": self.agent_id, "start": int(start), "sequence": int(sequence)},
                          data=data, headers={"Content-Type": "application/octet-stream"})

    def get_job(self, job_id: str):
        return self._call("GET", f"/jobs/{job_id}")

    def progress(self, job_id: str, stage: str, samples_per_channel: int = 0, message: str = ""):
        return self._call("POST", f"/jobs/{job_id}/progress", params={"agent_id": self.agent_id},
                          json_body={"stage": stage, "samples_per_channel": int(samples_per_channel),
                                     "message": message[:500]})

    def put_stream_file(self, job_id: str, name: str, path: Path):
        with open(path, "rb") as stream:
            return self._call("PUT", f"/jobs/{job_id}/stream-files/{name}",
                              params={"agent_id": self.agent_id}, data=stream, upload=True)

    def finish_stream(self, job_id: str):
        return self._call("POST", f"/jobs/{job_id}/finish-stream",
                          params={"agent_id": self.agent_id}, json_body={}, upload=True)

    def directory_result(self, picker_id: str, error: str):
        return self._call("POST", f"/agents/{self.agent_id}/directory-result",
                          json_body={"id": picker_id, "error": error})


# ===================================================================== 心跳与实时窗口
def heartbeat_state(info: dict, *, stage: str, hardware_connected: bool, save_directory: str,
                    session_id, error) -> dict:
    """组装心跳 state 字段：元数据全部取自 dc24_edge_info_json()，不硬编码。

    字段集合对齐 runtime.rs heartbeat()（stage/hardware_connected/sample_rates/
    channel_count/save_directory/version/input_configuration/transport/
    implementation/session_id/error）；云端只强校验 version >= 3。
    """
    return {"stage": stage, "hardware_connected": bool(hardware_connected),
            "sample_rates": info["sample_rates"], "channel_count": info["channel_count"],
            "save_directory": save_directory, "version": info["version"],
            "input_configuration": info["input_configuration"], "transport": info["transport"],
            "implementation": info["implementation"], "session_id": session_id, "error": error}


class Window:
    """最近约 2 秒的有界实时窗口（语义对照 runtime.rs Window）。

    块携带会话内绝对样本索引；被窗口裁剪或断网超出窗口后，after() 返回的
    start 相对已确认位置显式跳变——缺口保留在绝对索引里，绝不拼接成连续波形。
    """

    def __init__(self):
        self.chunks: deque[tuple[int, bytes]] = deque()
        self.end = 0  # 窗口末尾的绝对样本索引（不含）

    def push(self, start: int, data: bytes, rate: int) -> None:
        self.chunks.append((start, data))
        self.end = start + len(data) // 16
        cutoff = self.end - int(rate) * 2
        while self.chunks:
            head_start, head = self.chunks[0]
            if head_start + len(head) // 16 > cutoff:
                break
            self.chunks.popleft()

    def after(self, sent: int) -> tuple[int, bytes] | None:
        """返回 (起始绝对索引, 未确认字节)；无新数据返回 None。

        跳过与已确认区间 [0, sent) 重叠的前缀，不重发已确认样本。
        """
        if not self.chunks:
            return None
        first = max(self.chunks[0][0], sent)
        payload = bytearray()
        for start, data in self.chunks:
            rows = len(data) // 16
            skip = min(max(sent - start, 0), rows) * 16
            payload += data[skip:]
        if not payload:
            return None
        return first, bytes(payload)


# ===================================================================== 落盘
def rebuild_frame(sequence: int, data: bytes) -> bytes:
    """把核心解码后的样本块逐字节还原为设备 80 帧。

    核心解码为可逆变换：原始 4 字节项 word=(24位计数<<8)|通道标记，解码值
    word>>8；标记被协议校验为等于通道位置（protocol.rs samples），因此
    (解码值<<8)|通道位置 可无损还原原始字节。rx_stream.bin 由此重建，
    与设备实际发送的帧逐字节一致。
    """
    values = np.frombuffer(data, dtype="<i4").reshape(-1, 4)
    packed = ((values << np.int32(8)) | np.arange(4, dtype="<i4")).tobytes()
    body_length = 3 + len(data)  # 命令字(1) + 帧序号(2) + 采样负载
    return (b"\x7e" + body_length.to_bytes(2, "big") + b"\x80"
            + int(sequence).to_bytes(2, "little") + packed + b"\xff")


def check_free_space(path: Path, reserve: int, extra: int) -> None:
    """磁盘剩余空间保护（镜像 recording.rs free_space）：不足即报错停写。"""
    if shutil.disk_usage(path).free < reserve + extra:
        raise OSError("磁盘剩余空间不足；停止保存，保留已有文件")


def manifest_path(storage: Path, job: str) -> Path:
    return Path(storage) / ".uploads" / f"{job}.json"


class Recorder:
    """一个云端保存任务的五件套落盘（格式与 dc24_live.Recording / recording.rs 一致）。"""

    def __init__(self, *, command: dict, session_id: str, rate: int, info: dict, events,
                 sample_start: int, storage_root: Path, agent_id: str,
                 host_ip: str, device_ip: str, port: int, min_free: int = 0):
        job = command.get("id")
        if not valid_id(job):
            raise ValueError("云端保存任务 ID 无效")
        duration = command.get("duration")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            raise ValueError("保存时长必须为非负整数")
        root = Path(str(command.get("save_directory", ""))).expanduser()
        if not root.is_absolute():
            raise ValueError("保存目录必须是树莓派上的绝对路径")
        if manifest_path(storage_root, job).exists():
            raise ValueError("任务已在本地执行；拒绝覆盖")
        root.mkdir(parents=True, exist_ok=True)
        if min_free:
            check_free_space(root, min_free, 1024 * 1024)
        self.path = root / job
        self.path.mkdir(exist_ok=False)  # 永不覆盖已有采集结果
        self.job_id, self.duration, self.rate = job, duration, int(rate)
        self.count = 0
        self.frames = 0
        self.first_sequence = None
        self.last_sequence = None
        self.min_free = int(min_free)
        self.storage_root = Path(storage_root)
        b5 = info["b5_payload_hex_by_rate"].get(str(rate))
        if b5 is None:
            raise ValueError(f"核心不支持采样率档位 {rate}")
        self.csv_file = open(self.path / "samples.csv", "x", encoding="utf-8", newline="")
        self.writer = csv.writer(self.csv_file)
        self.writer.writerow(["sample_index", "time_s", "ch0_counts", "ch1_counts", "ch2_counts", "ch3_counts"])
        self.raw = open(self.path / "rx_stream.bin", "xb")
        self.binary = open(self.path / "counts.i32", "xb")
        self.log = open(self.path / "commands.jsonl", "x", encoding="utf-8")
        for line in events:  # 开始保存前已缓冲的事件（环形，容量 100）
            self.log.write(line)
        self.log.flush()
        self.meta = {
            "source": "dc24_tcp", "session_id": session_id, "device_ip": device_ip,
            "host_ip": host_ip, "host_tcp_port": int(port),
            "sample_rate_hz": self.rate, "requested_duration_s": duration,
            "value_unit": "signed_24_bit_ADC_counts",
            "physical_scaling": "NOT VERIFIED; no voltage/acceleration conversion applied",
            "channel_tags": [0, 1, 2, 3], "b5_payload_hex": b5,
            "b2_payload_hex": info["b2_payload_hex"], "input_configuration": info["input_configuration"],
            "session_sample_start": int(sample_start), "saved_directory": str(self.path),
            "complete": False, "transport": info["transport"],
            "time_axis": "relative sample index / sample_rate_hz; not device UTC time",
            "sequence_gaps": [], "implementation": info["implementation"],
        }
        atomic_json(self.path / "metadata.json", self.meta)  # 先落一份 complete=False
        self.manifest = {"job": job, "session": session_id, "agent": agent_id,
                         "path": str(self.path), "status": "recording", "samples": 0}
        atomic_json(manifest_path(storage_root, job), self.manifest)

    def _record_meta(self, key, value) -> None:
        self.meta[key] = value

    def append(self, sequence: int, data: bytes) -> None:
        """追加一个样本块（对应一个设备 80 帧）。"""
        rows = len(data) // 16
        frame = rebuild_frame(sequence, data)
        if self.min_free:  # 写前预留空间，绝不自动删旧数据（镜像 recording.rs）
            check_free_space(self.path, self.min_free, rows * 192 + len(frame))
        self.raw.write(frame)
        self.binary.write(data)
        values = np.frombuffer(data, dtype="<i4").reshape(-1, 4).tolist()
        start = self.count
        self.writer.writerows([start + i, f"{(start + i) / self.rate:.9f}", *row]
                              for i, row in enumerate(values))
        if self.first_sequence is None:
            self.first_sequence = sequence
        self.last_sequence = sequence
        self.count += rows
        self.frames += 1

    def append_event(self, line: str) -> None:
        self.log.write(line)

    def due(self) -> bool:
        return self.duration > 0 and self.count >= self.duration * self.rate

    def close(self, error: str | None) -> dict:
        """关闭文件、写终版 metadata 与上传清单；返回 metadata。"""
        self.log.flush()
        self.csv_file.close()
        self.raw.close()
        self.binary.close()
        self.log.close()
        self._record_meta("samples_per_channel", self.count)
        self._record_meta("data_frames", self.frames)
        self._record_meta("recorded_sample_duration_s", self.count / self.rate)
        self._record_meta("first_device_sequence", self.first_sequence)
        self._record_meta("last_device_sequence", self.last_sequence)
        self._record_meta("complete", error is None and self.count > 0)
        self._record_meta("error", error)
        self._record_meta("end_reason", "error" if error else "operator_or_requested_duration")
        self._record_meta("unparsed_tail_bytes", 0)
        atomic_json(self.path / "metadata.json", self.meta)
        self.manifest["samples"] = self.count
        # 无样本的记录不冒充完整数据：标 interrupted，由补传循环向云端报失败。
        self.manifest["status"] = "pending" if self.count > 0 else "interrupted"
        atomic_json(manifest_path(self.storage_root, self.job_id), self.manifest)
        return self.meta


# ===================================================================== 上传清单
def load_manifests(storage: Path) -> list[tuple[Path, dict]]:
    """读取 .uploads 下全部清单（按文件名排序，保证重试顺序稳定）。"""
    root = Path(storage) / ".uploads"
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.glob("*.json")):
        try:
            result.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            print(f"补传清单不可读，跳过 [{path.name}]: {exc}", flush=True)
    return result


def prepare_manifests(storage: Path) -> None:
    """崩溃恢复：上次进程中断的记录标 interrupted，不冒充完整数据。"""
    for path, manifest in load_manifests(storage):
        if manifest.get("status") == "recording":
            manifest["status"] = "interrupted"
            atomic_json(path, manifest)
            print(f"上次进程中断，保留未完成记录，不冒充完整数据: {manifest.get('job')}", flush=True)


def step_manifest(config, cloud: CloudClient, manifest: dict, path: Path) -> None:
    """推进单个清单的状态机：recording→interrupted→interrupted_reported；
    pending→(远端已完成则直接 uploaded，否则 progress+五文件+finish-stream)→uploaded。
    每步持久化，失败抛出由调用方保留原件重试——整个流程幂等。
    """
    status = manifest.get("status")
    if status == "recording":  # 正常运行期不应出现；防御性处理
        manifest["status"] = "interrupted"
        atomic_json(path, manifest)
        status = "interrupted"
    if manifest.get("agent") != config.agent_id or not valid_id(manifest.get("job")):
        if status != "mismatched":
            manifest["status"] = "mismatched"  # 不属于当前边端：终态标记，避免每轮重扫报错
            atomic_json(path, manifest)
            print(f"补传记录不属于当前边端，跳过: {manifest.get('job')}", flush=True)
        return
    job = manifest["job"]
    if status == "interrupted":
        cloud.progress(job, stage="failed",
                       message="边端进程中断；现场文件保留，未冒充完整记录上传")
        manifest["status"] = "interrupted_reported"
        atomic_json(path, manifest)
        return
    if status != "pending":
        return
    # finish-stream 的成功响应可能丢失：先查任务，避免重传时卡在终态。
    remote = cloud.get_job(job)
    if (remote or {}).get("status") in ("completed", "failed") and isinstance((remote or {}).get("metadata"), dict):
        manifest["status"] = "uploaded"
        atomic_json(path, manifest)
        print(f"云端已有该任务结果，跳过重传: {job}", flush=True)
        return
    cloud.progress(job, stage="uploading", samples_per_channel=manifest.get("samples", 0))
    directory = Path(manifest["path"])
    for name in RECORD_FILES:
        cloud.put_stream_file(job, name, directory / name)
    cloud.finish_stream(job)
    manifest["status"] = "uploaded"
    atomic_json(path, manifest)
    print(f"文件上传确认完成: {job}", flush=True)


def uploader_loop(config, cloud: CloudClient, quit_event: threading.Event) -> None:
    """后台补传循环：每 2 秒扫描清单，失败保留原件下一轮重试。"""
    while not quit_event.is_set():
        for path, manifest in load_manifests(config.storage):
            if quit_event.is_set():
                break
            try:
                step_manifest(config, cloud, manifest, path)
            except Exception as exc:  # 网络/云端暂不可达：原件保留，稍后重试
                print(f"文件上传待重试，原件保留 [{manifest.get('job')}]: {exc}", flush=True)
        quit_event.wait(2)


def wait_uploaded(config, job: str, timeout: float) -> str | None:
    """等待某任务的清单到达终态（uploaded/interrupted_reported/mismatched）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for _, manifest in load_manifests(config.storage):
            if manifest.get("job") == job:
                if manifest.get("status") in ("uploaded", "interrupted_reported", "mismatched"):
                    return manifest["status"]
        time.sleep(0.2)
    return None


# ===================================================================== 会话
def session_is_stale(session: dict) -> bool:
    """边端重启后旧会话样本索引不能从零重用（对照 runtime.rs session 的守卫）。"""
    return (session.get("samples_received") or 0) > 0 or \
        session.get("status") in ("streaming", "configuring", "stopping")


class SessionRunner:
    """一次云端下发会话：核心消息消费 + 云端监控上报 + 保存任务编排。"""

    def __init__(self, config, cloud: CloudClient, core: EdgeCore, info: dict, session: dict):
        self.config, self.cloud, self.core, self.info = config, cloud, core, info
        self.session_id = session["id"]
        self.rate = int(session["sample_rate"])
        self.lock = threading.RLock()
        self.status = "waiting_device"
        self.error: str | None = None
        self.record_state: dict | None = None
        self.window = Window()
        self.sequence = 0
        self.count = 0  # 会话内累计样本数（绝对索引）
        self.control = session
        self.recorder: Recorder | None = None
        self.last_record = None
        self.events: deque[str] = deque(maxlen=100)      # 事件环形缓冲（镜像 device.rs 容量 100）
        self.seen_lines: dict[str, None] = {}            # 事件行去重（时间戳保证同一事件同文本）
        self.seen_pickers: set[str] = set()
        self.stop_request = threading.Event()  # 云端要求停止 / 本地致命错误
        self.terminal = threading.Event()      # 核心已交付 stopped/failed 终态
        self.terminate = threading.Event()     # 消费者可以退出（队列排空后）
        self.done = threading.Event()          # 会话结束，监控线程退出
        self.upload_jobs: list[str] = []

    # ---------------------------------------------------------------- 状态视图
    def snapshot(self) -> dict:
        with self.lock:
            return {"status": self.status, "error": self.error,
                    "recording": dict(self.record_state) if self.record_state else None}

    def beat_state(self) -> dict:
        with self.lock:
            status, error = self.status, self.error
        return heartbeat_state(self.info, stage=status,
                               hardware_connected=status in ("configuring", "streaming"),
                               save_directory=str(self.config.storage),
                               session_id=self.session_id, error=error)

    # ---------------------------------------------------------------- 消费者线程
    def _consume(self) -> None:
        while True:
            message = self.core.poll(200)
            if message is not None:
                try:
                    self._dispatch(*message)
                except Exception as exc:  # 落盘/编排失败按会话失败处理，保留数据
                    with self.lock:
                        self.error = f"消费消息失败: {type(exc).__name__}: {exc}"
                    self.stop_request.set()
            if self.terminate.is_set() and message is None:
                return  # 已请求终止且队列排空

    def _dispatch(self, tag: int, sequence: int, start: int, data: bytes) -> None:
        if tag == MSG_STATE:
            self._on_state(json.loads(data.decode("utf-8")))
        elif tag == MSG_EVENT:
            self._on_event(data.decode("utf-8"))
        elif tag == MSG_SAMPLES:
            self._on_samples(sequence, start, data)
        else:
            raise ValueError(f"意外消息标签 {tag}")

    def _on_state(self, value: dict) -> None:
        status = STATE_TO_STATUS.get(value.get("state"))
        if status is None:
            return
        with self.lock:
            self.status = status
            if status == "failed":
                self.error = str(value.get("detail") or "设备链路失败")
        if status in TERMINAL_STATES:
            self.terminal.set()

    def _on_event(self, line: str) -> None:
        # 事件环形缓冲被裁剪时核心会全量重发；整行含时间戳，按行去重即可。
        if line in self.seen_lines:
            return
        self.seen_lines[line] = None
        if len(self.seen_lines) > 10000:  # 超长会话兜底：丢弃最早的去重键（重复风险可忽略）
            self.seen_lines.pop(next(iter(self.seen_lines)))
        self.events.append(line)
        if self.recorder is not None:
            self.recorder.append_event(line)

    def _on_samples(self, sequence: int, start: int, data: bytes) -> None:
        if not data or len(data) % 16:
            raise ValueError(f"样本块长度无效: {len(data)}")
        with self.lock:
            self.window.push(start, data, self.rate)
            self.sequence = sequence
            self.count = start + len(data) // 16
            command = (self.control or {}).get("recording") or None
        self._control_record(command)
        recorder = self.recorder
        if recorder is not None:
            recorder.append(sequence, data)
            with self.lock:
                self.record_state = {"id": recorder.job_id, "status": "capturing",
                                     "samples_per_channel": recorder.count,
                                     "saved_directory": str(recorder.path), "error": None}
            if recorder.due():  # 按实际点数满足请求时长，整帧收尾
                self.close_record()

    def _control_record(self, command: dict | None) -> None:
        if command and command.get("stop_requested"):
            self.close_record()
            return
        record_id = command.get("id") if command else None
        if not record_id or self.last_record == record_id:
            return
        if self.recorder is not None:
            raise RuntimeError("云端在当前保存未结束时下发另一任务")
        recorder = Recorder(command=command, session_id=self.session_id, rate=self.rate,
                            info=self.info, events=self.events, sample_start=self.count,
                            storage_root=self.config.storage, agent_id=self.config.agent_id,
                            host_ip=self.config.listen_ip, device_ip=self.config.device_ip,
                            port=self.config.port, min_free=self.config.min_free_bytes)
        self.last_record = record_id
        self.recorder = recorder
        with self.lock:
            self.record_state = {"id": record_id, "status": "capturing",
                                 "samples_per_channel": 0, "saved_directory": str(recorder.path),
                                 "error": None}

    def close_record(self, error: str | None = None) -> None:
        recorder = self.recorder
        if recorder is None:
            return
        self.recorder = None
        with self.lock:
            self.record_state = {"id": recorder.job_id,
                                 "status": "uploading" if recorder.count else "failed",
                                 "samples_per_channel": recorder.count,
                                 "saved_directory": str(recorder.path), "error": None}
        recorder.close(error)
        self.upload_jobs.append(recorder.job_id)

    # ---------------------------------------------------------------- 监控线程
    def _answer_picker(self, picker: dict | None) -> None:
        """无界面边端：目录选择请求一律回错误，引导页面直接填绝对路径。"""
        if not picker or picker.get("status") != "pending":
            return
        picker_id = picker.get("id")
        if not valid_id(picker_id) or picker_id in self.seen_pickers:
            return
        self.seen_pickers.add(picker_id)
        try:
            self.cloud.directory_result(picker_id, error="无界面边端，请在页面直接填写树莓派绝对保存路径")
        except Exception as exc:
            print(f"目录选择应答失败: {exc}", flush=True)

    def _monitor(self) -> None:
        sent = 0
        last_beat = 0.0
        while not self.done.is_set():
            # 控制与上传都在消息消费线程之外；HTTP 超时不阻塞采集和心跳。
            try:
                if time.monotonic() - last_beat >= 1:
                    self.cloud.heartbeat(self.beat_state())
                    last_beat = time.monotonic()
            except Exception as exc:
                print(f"云端心跳失败: {exc}", flush=True)
            try:
                control = self.cloud.control() or {}
                session = control.get("session")
                if not session or session.get("id") != self.session_id or session.get("stop_requested"):
                    self.stop_request.set()
                else:
                    with self.lock:
                        self.control = session
                    self._answer_picker(control.get("picker"))
            except Exception as exc:
                print(f"云端控制暂不可达；继续本地采集，等待恢复: {exc}", flush=True)
            try:
                self.cloud.state(self.session_id, self.snapshot())
            except Exception as exc:
                print(f"状态上报失败: {exc}", flush=True)
            with self.lock:
                batch = self.window.after(sent)
                sequence = self.sequence
            if batch:
                start, payload = batch
                try:
                    self.cloud.frames(self.session_id, start, sequence, payload)
                    sent = start + len(payload) // 16
                except Exception as exc:
                    print("实时上传失败；窗口有界，完整保存文件仍保留: "
                          f"{exc}", flush=True)
            self.done.wait(0.25)

    # ---------------------------------------------------------------- 主流程
    def _reject_stale_or_invalid(self, session: dict) -> str | None:
        if session_is_stale(session):
            return "边端进程已重启，旧会话样本索引不能从零重用；请在云端新建会话"
        if not valid_id(self.session_id):
            return "会话 ID 无效"
        if self.rate not in self.info["sample_rates"]:
            return f"不是已验证的原厂采样率档位: {self.rate}"
        return None

    def _report_orphan_failure(self, error: str | None) -> None:
        """会话失败且保存任务从未建立清单时，向该任务报失败（对照 runtime.rs）。"""
        if not error:
            return
        with self.lock:
            command = (self.control or {}).get("recording") or {}
        job = command.get("id")
        if valid_id(job) and not manifest_path(self.config.storage, job).exists():
            try:
                self.cloud.progress(job, stage="failed", message=error[:500])
            except Exception as exc:
                print(f"任务失败状态未上报 [{job}]: {exc}", flush=True)

    def run(self, quit_event: threading.Event | None = None) -> str | None:
        """执行会话，返回错误文本（None=正常结束）。

        健康会话持续到云端请求停止（示波可长达数分钟，不设人为期限）；
        设备等待与数据超时由核心线程强制并以 failed 终态交付。
        """
        problem = self._reject_stale_or_invalid(self.control)
        if problem:
            try:
                self.cloud.state(self.session_id, {"status": "failed", "error": problem})
            except Exception as exc:
                print(f"会话拒绝原因未上报: {exc}", flush=True)
            self._report_orphan_failure(problem)
            print(f"会话被拒绝: {problem}", flush=True)
            return problem
        consumer = threading.Thread(target=self._consume, name="dc24-consumer", daemon=True)
        monitor = threading.Thread(target=self._monitor, name="dc24-monitor", daemon=True)
        error: str | None = None
        try:
            self.core.start(self.rate)
            consumer.start()
            monitor.start()
            # 等待云端停止请求 / 核心终态 / 进程退出请求；无期限（核心自身强制超时）。
            while not self.stop_request.is_set() and not self.terminal.is_set() \
                    and not (quit_event and quit_event.is_set()):
                time.sleep(0.05)
            if quit_event and quit_event.is_set() and not self.stop_request.is_set():
                print("进程退出请求中断会话", flush=True)
            # 停止硬件：内部完成 B8 与应答，最长约 5~7 秒；随后队列消息仍可继续 poll。
            self.core.stop()
            self.terminate.set()
            if consumer.is_alive():
                consumer.join(timeout=15)
                if consumer.is_alive():
                    print("消费者线程未在期限内退出", flush=True)
            self.done.set()
            if monitor.is_alive():
                monitor.join(timeout=15)
                if monitor.is_alive():
                    print("监控线程未在期限内退出", flush=True)
            with self.lock:
                error = self.error
            self.close_record(error)  # 若保存仍未结束，此时收尾
            self._report_orphan_failure(error)
            with self.lock:
                self.status = "failed" if error else (self.status if self.status in TERMINAL_STATES else "stopped")
                self.error = error
        finally:
            self.terminate.set()
            self.done.set()
            for worker in (consumer, monitor):
                if worker.is_alive():
                    worker.join(timeout=15)
        try:
            self.cloud.state(self.session_id, self.snapshot())
        except Exception as exc:
            print(f"会话终态未上报: {exc}", flush=True)
        # 等待本会话的保存任务完成上传（有界；超时交给后台补传循环）。
        for job in list(self.upload_jobs):
            state = wait_uploaded(self.config, job, timeout=self.config.upload_timeout_seconds)
            if state is None:
                print(f"文件上传仍在进行，交给后台补传: {job}", flush=True)
        return error


# ===================================================================== 配置与入口
class PiConfig:
    """与 Rust 核心共用同一份 config.json（schema 见 edge/src/config.rs）。

    本类只做 Python 侧需要的字段抽取与轻校验；完整校验（含
    deny_unknown_fields、地址族、URL 形态）由核心 dc24_edge_open 执行——
    因此把原始文本原样传给核心，绝不改写。
    """

    def __init__(self, data: dict, text: str, path: Path):
        self.data, self.text, self.path = data, text, path
        self.cloud_url = str(data.get("cloud_url", ""))
        if not self.cloud_url.startswith(("http://", "https://")):
            raise ValueError("cloud_url 必须是 HTTP(S) 服务根地址")
        self.agent_id = str(data.get("agent_id", ""))
        if not AGENT_ID_PATTERN.fullmatch(self.agent_id):
            raise ValueError("agent_id 无效（1~64 个字母、数字、点、横杠、下划线）")
        self.api_key_env = str(data.get("api_key_env", ""))
        if not self.api_key_env:
            raise ValueError("api_key_env 不能为空")
        self.storage = Path(str(data.get("storage", "")))
        if not self.storage.is_absolute():
            raise ValueError("storage 不是绝对路径")
        mode = data.get("mode", "cloud")
        if mode != "cloud":
            raise ValueError("v1 只支持云端下发会话（mode=cloud）；本地定时/持续模式未实现")
        self.min_free_bytes = int(data.get("min_free_bytes", 256 * 1024 * 1024))
        self.listen_ip = str(data.get("listen_ip", ""))
        self.device_ip = str(data.get("device_ip", ""))
        self.port = int(data.get("port", 0))
        self.http_timeout_seconds = float(data.get("http_timeout_seconds", 4))
        self.upload_timeout_seconds = float(data.get("upload_timeout_seconds", 180))
        self.device_wait_seconds = float(data.get("device_wait_seconds", 45))
        self.data_timeout_seconds = float(data.get("data_timeout_seconds", 10))
        if min(self.http_timeout_seconds, self.upload_timeout_seconds,
               self.device_wait_seconds, self.data_timeout_seconds) <= 0:
            raise ValueError("超时必须大于零")

    @classmethod
    def load(cls, path: Path) -> "PiConfig":
        path = Path(path)
        return cls(json.loads(path.read_text(encoding="utf-8")),
                   path.read_text(encoding="utf-8"), path)


def run(config_path, library_path=None, once=False, quit_event: threading.Event | None = None) -> None:
    """驱动主循环：心跳 → 控制轮询 → 会话执行；once=True 完成一个会话后返回。"""
    config = PiConfig.load(Path(config_path))
    key = os.environ.get(config.api_key_env, "")
    if not key:
        raise SystemExit(f"没有设置密钥环境变量 {config.api_key_env}")
    config.storage.mkdir(parents=True, exist_ok=True)
    (config.storage / ".uploads").mkdir(parents=True, exist_ok=True)
    cloud = CloudClient(config.cloud_url, config.agent_id, key,
                        config.http_timeout_seconds, config.upload_timeout_seconds)
    core = EdgeCore(library_path)
    try:
        core.open(config.text)  # 绑定常驻监听（进程内一次）
        info = core.info()
        prepare_manifests(config.storage)
        quit_event = quit_event or threading.Event()
        uploader = threading.Thread(target=uploader_loop, args=(config, cloud, quit_event),
                                    name="dc24-uploader", daemon=True)
        uploader.start()
        print(f"边端已启动: agent={config.agent_id} core={info['implementation']} "
              f"监听 {core.path.name}", flush=True)
        while not quit_event.is_set():
            try:
                cloud.heartbeat(heartbeat_state(
                    info, stage="idle", hardware_connected=False,
                    save_directory=str(config.storage), session_id=None, error=None))
                control = cloud.control() or {}
                session = control.get("session")
                if session:
                    error = SessionRunner(config, cloud, core, info, session).run(quit_event)
                    if error:
                        print(f"边端任务失败，保留数据并等待重试: {error}", flush=True)
                    if once:
                        break
                    continue
            except Exception as exc:
                print(f"边端任务失败，保留数据并等待重试: {exc}", flush=True)
            quit_event.wait(1)
        quit_event.set()
        uploader.join(timeout=15)
    finally:
        core.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config.json"),
                        help="与 Rust 核心共用的边端 config.json（schema 见 edge/config.example.json）")
    parser.add_argument("--library", type=Path, default=None,
                        help="dc24_edge_core 动态库路径；默认搜索 edge/target/{release,debug} 或 DC24_EDGE_LIB")
    parser.add_argument("--once", action="store_true", help="完成一个云端会话后退出")
    args = parser.parse_args()
    run(args.config, args.library, args.once)


if __name__ == "__main__":
    main()
