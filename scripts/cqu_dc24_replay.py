"""将 CQU 四通道 TIM 原始计数作为独立 DC24 TCP 设备循环回放。"""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import time

import numpy as np

from dc24_driver import (
    B5_PROFILES,
    HOST,
    PEER,
    PORT,
    RATE,
    SAMPLES_PER_FRAME,
    Frames,
    command,
)

DEFAULT_DIRECTORY = Path(r"D:\大创\CQU数据\正常-200-1")
FRAME_SECONDS = SAMPLES_PER_FRAME / RATE


def load_packed(directory: Path) -> np.ndarray:
    """按通道交织四路 packed word；保留通道标签和 signed24 原始位型。"""
    return np.stack(
        [
            np.fromfile(
                directory / f"{directory.name}#6-{channel + 1}.tim", dtype="<u4"
            )
            for channel in range(4)
        ],
        axis=1,
    )


def run_session(connection: socket.socket, packed: np.ndarray) -> None:
    """完成一次控制会话；B8 应答后返回外层等待下一次连接。"""
    parser = Frames()
    streaming = False
    sequence = 0
    offset = 0
    next_send = 0.0
    while True:
        timeout = 0.1
        if streaming:
            timeout = max(0.001, min(0.005, next_send - time.monotonic()))
        connection.settimeout(timeout)
        try:
            chunk = connection.recv(65536)
        except TimeoutError:
            chunk = None
        if chunk is not None:
            if not chunk:
                raise ConnectionError("采集主机已断开")
            for frame in parser.feed(chunk):
                code = frame[3]
                if code not in (0xBA, 0xB8, 0xB2, 0xB5, 0xB7):
                    raise ValueError(f"采集主机发来未知命令: {code:02X}")
                if code == 0xB5 and frame[4:-1] != B5_PROFILES[RATE]:
                    raise ValueError("采集主机请求的采样率不是源数据的 10000 Hz")
                connection.sendall(command(code, b"\x00"))
                if code == 0xB8 and streaming:
                    return
                if code == 0xB7:
                    streaming = True
                    sequence = 0
                    offset = 0
                    next_send = time.monotonic()
        now = time.monotonic()
        if not streaming or now < next_send:
            continue

        end = offset + SAMPLES_PER_FRAME
        if end <= len(packed):
            rows = packed[offset:end]
        else:
            rows = np.concatenate((packed[offset:], packed[: end % len(packed)]))
        body = (
            b"\x80"
            + sequence.to_bytes(2, "little")
            + rows.astype("<u4", copy=False).tobytes()
        )
        frame = b"\x7e" + len(body).to_bytes(2, "big") + body + b"\xff"
        connection.sendall(frame)
        sequence = (sequence + 1) & 0xFFFF
        offset = end % len(packed)
        next_send += FRAME_SECONDS
        if next_send <= now:
            # 发送受阻后按当前时间重新定拍，不用紧凑循环补发积压帧。
            next_send = now + FRAME_SECONDS


def run(directory: Path, host: str, peer: str, port: int) -> None:
    packed = load_packed(directory)
    print(f"已载入 {directory}：{len(packed)} 点/通道，{RATE} Hz", flush=True)
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
                connection.bind((peer, 0))
                connection.connect((host, port))
                print(
                    f"已连接 {host}:{port}，本机 {connection.getsockname()[0]}:{connection.getsockname()[1]}",
                    flush=True,
                )
                run_session(connection, packed)
                print("收到 B8，本次会话结束；等待下一次连接", flush=True)
        except OSError as exc:
            print(f"连接结束：{exc}；1 秒后重连", flush=True)
            time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?", type=Path, default=DEFAULT_DIRECTORY, help="CQU 采集目录"
    )
    parser.add_argument("--host", default=HOST, help="PythonTcpDriver 监听地址")
    parser.add_argument("--peer", default=PEER, help="替身绑定的本机源地址")
    parser.add_argument("--port", type=int, default=PORT, help="PythonTcpDriver 监听端口")
    args = parser.parse_args()
    try:
        run(args.directory, args.host, args.peer, args.port)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
