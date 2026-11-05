"""DC24 独立采集验证脚本：仅标准库，不加载厂商软件或 DLL。

只实现本机实测的配置：2000/5000 Hz、四个信号通道、示波模式。
保存原始 TCP 字节、原始有符号 24 位 ADC 计数和命令记录，不冒充物理单位。
协议依据及未确认字段见 ../docs/DC24_PROTOCOL.md。运行前让原厂软件脱机以释放 TCP 6800。
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import socket
import struct
import time

HOST = "192.168.2.100"
PEER = "192.168.2.101"
PORT = 6800
RATE = 5000
SAMPLES_PER_FRAME = 254
CONFIG_B2 = bytes.fromhex("00000000000000000001000000")
CONFIG_B5 = bytes.fromhex("0000fe00d00700000f000000")
# 完整保留两组原厂实测配置。5000 Hz 时第二个字段也变化，不能只替换采样率。
B5_PROFILES = {
    2000: CONFIG_B5,
    5000: bytes.fromhex("0000f500881300000f000000"),
}


class CaptureCancelled(Exception):
    """等待设备阶段收到停止请求，未启动ADC。"""


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
                    raise ValueError("Data frame does not have the observed FF terminator")
            elif sum(frame[3:]) & 255 != 255:
                raise ValueError(f"Invalid control checksum: {frame[:24].hex()}")
            result.append(frame)
        return result


def samples(frame: bytes):
    """返回 (帧序号, 四通道原始计数组)；拒绝未验证的帧尺寸和通道排列。"""
    if frame[3] != 0x80 or len(frame) != 4071:
        raise ValueError("Only the verified 4071-byte 4-channel data profile is supported")
    sequence = int.from_bytes(frame[4:6], "little")
    data = frame[6:-1]
    rows = []
    for offset in range(0, len(data), 16):
        group = data[offset:offset+16]
        if group[::4] != b"\x00\x01\x02\x03":
            raise ValueError(f"Unverified channel order: {group[::4].hex()}")
        rows.append(tuple(int.from_bytes(group[j+1:j+4], "little", signed=True)
                          for j in range(0, 16, 4)))
    return sequence, rows


class Link:
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
        self.events.write(json.dumps({"host_time_utc": datetime.now(timezone.utc).isoformat(),
                                      **entry}, ensure_ascii=False) + "\n")
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
        except socket.timeout:
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
                self.event(direction="device_to_host", command=f"{frame[3]:02X}", hex=frame.hex())
        return frames

    def exchange(self, code, payload=b"", timeout=5, status=True):
        self.send(code, payload)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.pump():
                if frame[3] == code:
                    if status and frame[4:-1] != b"\x00":
                        raise RuntimeError(f"Unexpected {code:02X} response: {frame.hex()}")
                    return frame
        raise TimeoutError(f"No response to command {code:02X}")


def record(output: Path, seconds: float, host=HOST, peer=PEER, wait=45, sample_rate=RATE,
           on_progress=None, should_stop=None):
    if sample_rate not in B5_PROFILES:
        raise ValueError("Only captured 2000/5000 Hz profiles are supported")
    target_samples = math.ceil(seconds * sample_rate)
    output.mkdir(parents=True, exist_ok=False)  # 永不覆盖已有采集结果。
    metadata = {
        "profile": f"DC24_observed_{sample_rate}Hz_four_channels",
        "host_ip": host, "device_ip": peer, "host_tcp_port": PORT,
        "sample_rate_hz": sample_rate, "sample_rate_source": "verified captured native B5 profile",
        "b5_payload_hex": B5_PROFILES[sample_rate].hex(),
        "channel_tags": [0, 1, 2, 3], "value_unit": "signed_24_bit_ADC_counts",
        "physical_scaling": "NOT VERIFIED; no voltage/acceleration conversion applied",
        "time_axis": f"relative sample index / {sample_rate}; not a device UTC timestamp",
        "duration_policy": "at least requested samples; stop on whole frames",
        "target_samples_per_channel": target_samples,
        "requested_duration_s": seconds, "data_frames": 0, "samples_per_channel": 0,
        "sequence_gaps": [], "complete": False,
    }
    connection = None
    link = None
    started = False
    previous_sequence = None
    current_index = 0
    first_frame_time = None
    last_frame_time = None
    stopping = should_stop or (lambda: False)

    def notify(stage):
        if on_progress:
            on_progress({"stage": stage, "samples_per_channel": current_index,
                         "target_samples_per_channel": target_samples,
                         "hardware_connected": stage in ("configuring", "capturing")})
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            server.bind((host, PORT))
            server.listen(1)
            notify("waiting_device")
            deadline = time.monotonic() + wait
            print(f"Listening on {host}:{PORT}; waiting for {peer} ...", flush=True)
            while time.monotonic() < deadline:
                if stopping():
                    raise CaptureCancelled()
                server.settimeout(min(.5, max(.1, deadline-time.monotonic())))
                try:
                    candidate, address = server.accept()
                except socket.timeout:
                    continue
                if address[0] == peer:
                    connection = candidate
                    metadata["device_source_port"] = address[1]
                    break
                candidate.close()
            if connection is None:
                raise TimeoutError("Device did not connect")
            print(f"Connected: {peer}:{metadata['device_source_port']}", flush=True)
            notify("configuring")
            with connection, (output/"rx_stream.bin").open("xb") as raw, \
                    (output/"commands.jsonl").open("x", encoding="utf-8") as events, \
                    (output/"samples.csv").open("x", encoding="utf-8", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["sample_index", "time_s", "ch0_counts", "ch1_counts", "ch2_counts", "ch3_counts"])
                link = Link(connection, raw, events)

                def consume(frame):
                    nonlocal previous_sequence, current_index, first_frame_time, last_frame_time
                    sequence, rows = samples(frame)
                    now = time.monotonic()
                    if first_frame_time is None:
                        first_frame_time = now
                    last_frame_time = now
                    if previous_sequence is None:
                        if sequence != 0:
                            raise ValueError(f"First data sequence is {sequence}, not 0")
                    elif (sequence-previous_sequence) & 0xFFFF != 1:
                        metadata["sequence_gaps"].append([previous_sequence, sequence])
                        raise ValueError(f"Nonconsecutive frame sequence: {previous_sequence} -> {sequence}")
                    for row in rows:
                        writer.writerow([current_index, f"{current_index/sample_rate:.7f}", *row])
                        current_index += 1
                    previous_sequence = sequence
                    metadata["data_frames"] += 1
                    metadata["samples_per_channel"] += len(rows)
                    notify("capturing")

                try:
                    identity = link.exchange(0xBA, status=False)
                    metadata["identity_frame_hex"] = identity.hex()
                    link.exchange(0xB8)
                    link.exchange(0xB2, CONFIG_B2)
                    link.exchange(0xB5, B5_PROFILES[sample_rate])
                    link.on_data = consume
                    started = True  # 即使启动应答超时，finally 也必须发送停止。
                    link.exchange(0xB7, b"\x00")
                    # 主机计时会包含设备启动等待；以实际样本数保证记录时长。
                    until = time.monotonic() + seconds + max(10, seconds * 0.25)
                    next_progress = sample_rate * 10
                    while current_index < target_samples and not stopping():
                        link.pump()
                        if current_index >= next_progress:
                            print(f"Samples/channel: {current_index}/{target_samples}", flush=True)
                            next_progress += sample_rate * 10
                        if time.monotonic() > until:
                            raise TimeoutError(f"Only {current_index}/{target_samples} samples received")
                    link.exchange(0xB8)
                    started = False
                    metadata["cancelled"] = bool(stopping())
                    if link.frames.buffer:
                        raise RuntimeError("Incomplete frame remains after the stop acknowledgement")
                    if metadata["data_frames"] == 0 and not metadata["cancelled"]:
                        raise RuntimeError("Start/stop acknowledged but no sample frames received")
                    metadata["complete"] = not metadata["cancelled"]
                finally:
                    if started:
                        try:
                            link.send(0xB8)
                        except OSError as exc:
                            metadata["emergency_stop_error"] = str(exc)
                    metadata["received_tcp_bytes"] = link.rx_bytes
                    metadata["unparsed_tail_bytes"] = len(link.frames.buffer)
    except CaptureCancelled:
        metadata["cancelled"] = True
    except BaseException as exc:
        metadata["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if connection:
            connection.close()
        metadata["recorded_sample_duration_s"] = metadata["samples_per_channel"] / sample_rate
        if first_frame_time is not None and last_frame_time > first_frame_time:
            span = last_frame_time-first_frame_time
            metadata["data_frame_arrival_span_s"] = span
            metadata["arrival_rate_estimate_hz"] = (metadata["data_frames"]-1)*SAMPLES_PER_FRAME/span
        (output/"metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False), flush=True)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5, help="最少样本时长，默认 5 秒；按完整帧收尾")
    parser.add_argument("--rate", type=int, choices=sorted(B5_PROFILES), default=RATE,
                        help="采用原厂抓包验证的采样率，默认 5000 Hz")
    parser.add_argument("--output", type=Path, required=True, help="新目录，不覆盖旧结果")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("--seconds 必须为大于 0 的有限数")
    record(args.output, args.seconds, sample_rate=args.rate)
