"""采集宿主使用的窄驱动接口及两种传输共用的控制时序。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import IO

import numpy as np

from .protocol import B5_PROFILES, CONFIG_B2, HOST, PEER, PORT, Link, decode


class LinkState(str, Enum):
    WAITING_DEVICE = "waiting_device"
    CONNECTED = "connected"
    CONFIGURING = "configuring"
    STREAMING = "streaming"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SampleBlock:
    """一个完整设备帧：原始报文、16 位帧序号和四路 int32 样本。"""

    sequence: int
    frame: bytes
    values: np.ndarray


class Dc24Driver(ABC):
    """DC24 可选驱动接口。

    connect 等待匹配设备；start 完成 BA/B8/B2/B5/B7 时序并注册样本回调；
    poll 驱动一次非阻塞接收；stop 以 B8 正常收尾；close 释放设备与监听资源。
    事件以 JSON 行写入 events，原始接收字节写入 raw，文件所有权仍属宿主。
    """

    transport: str

    def __init__(self, host=HOST, peer=PEER, port=PORT):
        self.host, self.peer, self.port = host, peer, port
        self.state = LinkState.WAITING_DEVICE
        self.connection = None
        self.link = None
        self.started = False
        self.identity_frame = None
        self.device_source_port = None
        self.emergency_stop_error = None

    @abstractmethod
    def connect(self, should_stop: Callable[[], bool], wait=45) -> bool:
        """等待目标设备；已连接返回 True，等待期间收到停止返回 False。"""

    def start(
        self,
        sample_rate: int,
        on_samples: Callable[[SampleBlock], None],
        raw: IO[bytes],
        events: IO[str],
    ) -> None:
        if sample_rate not in B5_PROFILES:
            raise ValueError("Sampling rate must be a supported native profile")
        self.state = LinkState.CONFIGURING
        self.link = Link(self.connection, raw, events)
        self.identity_frame = self.link.exchange(0xBA, status=False)
        self.link.exchange(0xB8)
        self.link.exchange(0xB2, CONFIG_B2)
        self.link.exchange(0xB5, B5_PROFILES[sample_rate])

        def consume(frame):
            sequence, values = decode(frame)
            on_samples(SampleBlock(sequence=sequence, frame=frame, values=values))

        self.link.on_data = consume
        self.started = True  # 启动应答超时也必须由 close 尝试停止。
        self.link.exchange(0xB7, b"\x00")
        self.state = LinkState.STREAMING

    def poll(self) -> None:
        for frame in self.link.pump():
            if self.started and frame[3] == 0xB8:
                raise RuntimeError("设备在示波期间应答了未请求的停止命令")

    def stop(self) -> None:
        if not self.started:
            return
        self.state = LinkState.STOPPING
        self.link.exchange(0xB8)
        self.started = False
        self.state = LinkState.STOPPED

    def close(self) -> None:
        if self.started and self.link is not None:
            try:
                self.link.on_data = None
                self.link.exchange(0xB8)
            except (OSError, TimeoutError) as exc:
                self.emergency_stop_error = str(exc)
            self.started = False
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        self.state = LinkState.STOPPED

    @property
    def received_tcp_bytes(self):
        return self.link.rx_bytes if self.link is not None else 0

    @property
    def unparsed_tail_bytes(self):
        return len(self.link.frames.buffer) if self.link is not None else 0
