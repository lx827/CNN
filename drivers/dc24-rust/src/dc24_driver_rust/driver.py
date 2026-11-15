"""将 dc24_edge_core 消息流适配为公共 Dc24Driver，不实现宿主业务逻辑。"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np

from dc24_driver import B5_PROFILES, Dc24Driver, LinkState, SampleBlock

from ._core import MSG_EVENT, MSG_SAMPLES, MSG_STATE, EdgeCore


class RustDriver(Dc24Driver):
    transport = "rust_tcp"

    def __init__(self, *args, library_path=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.library_path = library_path
        self._core = None
        self._should_stop = lambda: False
        self._on_samples = None
        self._raw = None
        self._events = None

    def connect(self, should_stop, wait=45):
        if should_stop():
            return False
        self._should_stop = should_stop
        config = {
            "cloud_url": os.environ.get("CLOUD_BASE_URL", "http://127.0.0.1:8000"),
            "listen_ip": self.host,
            "device_ip": self.peer,
            "port": self.port,
            "storage": str(Path.cwd().resolve()),
            "device_wait_seconds": math.ceil(wait),
        }
        self._core = EdgeCore(self.library_path)
        self._core.open(json.dumps(config))
        return True

    def start(self, sample_rate, on_samples, raw, events):
        if sample_rate not in B5_PROFILES:
            raise ValueError("Sampling rate must be a supported native profile")
        self.state = LinkState.CONFIGURING
        self._on_samples, self._raw, self._events = on_samples, raw, events
        self._core.start(sample_rate)
        self.started = True
        while self.started and self.state != LinkState.STREAMING:
            if self._should_stop():
                self.stop()
                return
            message = self._core.poll(100)
            if message is not None:
                self._dispatch(message)

    def _dispatch(self, message):
        tag, sequence, _start, data, frame = message
        if tag == MSG_STATE:
            value = json.loads(data.decode("utf-8"))
            states = {
                "connected": LinkState.CONNECTED,
                "streaming": LinkState.STREAMING,
                "stopping": LinkState.STOPPING,
                "stopped": LinkState.STOPPED,
            }
            state = value["state"]
            if state == "failed":
                self.started = False
                raise RuntimeError(value["detail"])
            self.state = states[state]
            if state == "stopped":
                self.started = False
            return
        if tag == MSG_EVENT:
            line = data.decode("utf-8")
            event = json.loads(line)
            if event.get("command") == "BA" and event.get("direction") == "device_to_host":
                self.identity_frame = bytes.fromhex(event["hex"])
            self._events.write(line)
            self._events.flush()
            return
        if tag == MSG_SAMPLES:
            values = np.frombuffer(data, dtype="<i4").reshape(-1, 4)
            self._raw.write(frame)
            self._on_samples(SampleBlock(sequence=sequence, frame=frame, values=values))
            return
        raise RuntimeError(f"未知 dc24_edge_core 消息标签: {tag}")

    def poll(self):
        while (message := self._core.poll(0)) is not None:
            self._dispatch(message)

    def stop(self):
        if not self.started:
            return
        self.state = LinkState.STOPPING
        self._core.stop()
        while self.started:
            message = self._core.poll(100)
            if message is not None:
                self._dispatch(message)

    def close(self):
        if self._core is not None:
            if self.started:
                try:
                    self.stop()
                except Exception as exc:
                    self.emergency_stop_error = str(exc)
            self._core.close()
            self._core = None
        self.started = False
        self.state = LinkState.STOPPED

    @property
    def received_tcp_bytes(self):
        return 0

    @property
    def unparsed_tail_bytes(self):
        return 0
