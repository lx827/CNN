"""采集宿主的窄驱动接口，以及 Python/DLL 共用的帧协议生命周期。"""

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
    """宿主所需的最小驱动能力，不要求实现方使用 TCP 帧协议对象。"""

    transport: str

    def __init__(self, host=HOST, peer=PEER, port=PORT):
        self.host, self.peer, self.port = host, peer, port
        self.state = LinkState.WAITING_DEVICE
        self.started = False
        self.identity_frame = None

    @abstractmethod
    def connect(self, should_stop: Callable[[], bool], wait=45) -> bool:
        """等待目标设备；已连接返回 True，等待期间收到停止返回 False。"""

    @abstractmethod
    def start(
        self,
        sample_rate: int,
        on_samples: Callable[[SampleBlock], None],
        raw: IO[bytes],
        events: IO[str],
    ) -> None:
        """启动采样并注册完整样本块、原始字节与事件输出。"""

    @abstractmethod
    def poll(self) -> None:
        """驱动一次接收与消息分发。"""

    @abstractmethod
    def stop(self) -> None:
        """正常停止采样。"""

    @abstractmethod
    def close(self) -> None:
        """释放设备与监听资源；停止或释放错误必须向宿主传播。"""


class FrameProtocolDriver(Dc24Driver):
    """Python TCP 与原厂 DLL 共用的 BA/B8/B2/B5/B7 帧协议实现。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = None
        self.link = None
        self.device_source_port = None

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
        self.started = True
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
        try:
            if self.started and self.link is not None:
                self.link.on_data = None
                self.link.exchange(0xB8)
        finally:
            self.started = False
            try:
                if self.connection is not None:
                    self.connection.close()
            finally:
                self.connection = None
                self.state = LinkState.STOPPED

    @property
    def received_tcp_bytes(self):
        return self.link.rx_bytes if self.link is not None else 0

    @property
    def unparsed_tail_bytes(self):
        return len(self.link.frames.buffer) if self.link is not None else 0
