"""DC24 已验证帧格式与控制报文；不包含任务、保存或上传编排。"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from importlib.resources import files

import numpy as np

HOST = "192.168.2.100"
PEER = "192.168.2.101"
PORT = 6800
RATE = 10000
SAMPLES_PER_FRAME = 254
CONFIG_B2 = bytes.fromhex("00010001000100010301000000")
INPUT_CONFIGURATION = {
    "measurement": "IEPE",
    "coupling": "AC0.2Hz",
    "upper_frequency": "PASS",
    "profile_id": "iepe-ac02-pass-20261106",
}
# 原厂2026-11-06有效10kHz B5为基准，只替换已验证的采样率字段；未知字段原样保留。
B5_PROFILES = {
    int(rate): bytes.fromhex(payload)
    for rate, payload in json.loads(
        files(__package__).joinpath("dc24_profiles.json").read_text(encoding="utf-8")
    ).items()
}


def command(code: int, payload: bytes = b"") -> bytes:
    body = bytes([code]) + payload
    if len(body) > 65535:
        raise ValueError("Control frame is too long")
    return b"\x7e" + len(body).to_bytes(2, "big") + body + bytes([(~sum(body)) & 255])


class Frames:
    """TCP 流解析：处理半包、粘包；数据帧尾 FF 与控制帧校验分开验证。"""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self.buffer.extend(chunk)
        result = []
        while self.buffer:
            if self.buffer[0] == 0:  # 主机的单字节保活，不是 7E 帧。
                del self.buffer[0]
                continue
            if self.buffer[0] != 0x7E:
                raise ValueError(f"Unexpected stream prefix: {self.buffer[:16].hex()}")
            if len(self.buffer) < 4:
                break
            size = int.from_bytes(self.buffer[1:3], "big") + 4
            if size < 5:
                raise ValueError("Zero-length frame body")
            if len(self.buffer) < size:
                break
            frame = bytes(self.buffer[:size])
            del self.buffer[:size]
            if frame[3] == 0x80:
                if frame[-1] != 0xFF:
                    raise ValueError(
                        "Data frame does not have the observed FF terminator"
                    )
            elif sum(frame[3:]) & 255 != 255:
                raise ValueError(f"Invalid control checksum: {frame[:24].hex()}")
            result.append(frame)
        return result


def decode(frame: bytes) -> tuple[int, np.ndarray]:
    """将一个设备 80 帧解码为帧序号和四路小端 int32 原始计数。"""
    if frame[3] != 0x80 or len(frame) < 23 or (len(frame) - 7) % 16:
        raise ValueError("四通道数据帧尺寸无效")
    words = np.frombuffer(
        frame, dtype="<i4", offset=6, count=(len(frame) - 7) // 4
    ).reshape(-1, 4)
    if not np.all((words & 255) == np.arange(4)):
        raise ValueError("设备通道排列与四通道配置不符")
    return int.from_bytes(frame[4:6], "little"), (words >> 8).astype("<i4")


def samples(frame: bytes) -> tuple[int, list[tuple[int, int, int, int]]]:
    """标准库风格的兼容返回形式；实际协议解码统一由 decode 执行。"""
    sequence, values = decode(frame)
    return sequence, [tuple(row) for row in values.tolist()]


class Link:
    """在已连接的字节流上执行控制应答、心跳、原始日志与完整帧交付。"""

    def __init__(self, connection, raw, events):
        self.socket = connection
        self.socket.settimeout(0.1)
        self.raw = raw
        self.events = events
        self.frames = Frames()
        self.last_heartbeat = 0.0
        self.on_data = None
        self.rx_bytes = 0

    def event(self, **entry):
        self.events.write(
            json.dumps(
                {"host_time_utc": datetime.now(UTC).isoformat(), **entry},
                ensure_ascii=False,
            )
            + "\n"
        )
        self.events.flush()

    def send(self, code, payload=b""):
        frame = command(code, payload)
        self.socket.sendall(frame)
        self.event(direction="host_to_device", command=f"{code:02X}", hex=frame.hex())

    def pump(self):
        if time.monotonic() - self.last_heartbeat >= 1:
            self.socket.sendall(b"\x00")
            self.last_heartbeat = time.monotonic()
            self.event(direction="host_to_device", heartbeat="00")
        try:
            chunk = self.socket.recv(65536)
        except TimeoutError:
            return []
        if not chunk:
            raise ConnectionError("Device closed its TCP connection")
        self.raw.write(chunk)
        self.rx_bytes += len(chunk)
        frames = self.frames.feed(chunk)
        for frame in frames:
            if frame[3] == 0x80:
                if self.on_data:
                    self.on_data(frame)
            else:
                self.event(
                    direction="device_to_host",
                    command=f"{frame[3]:02X}",
                    hex=frame.hex(),
                )
        return frames

    def exchange(self, code, payload=b"", timeout=5, status=True):
        self.send(code, payload)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.pump():
                if frame[3] == code:
                    if status and frame[4:-1] != b"\x00":
                        raise RuntimeError(
                            f"Unexpected {code:02X} response: {frame.hex()}"
                        )
                    return frame
        raise TimeoutError(f"No response to command {code:02X}")
