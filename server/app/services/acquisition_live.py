"""示波的有界内存窗口；不把示波样本写到文件或业务数据库。"""

from collections import deque
import copy
from datetime import datetime, timezone
import threading
import time
import uuid
import numpy as np


class LiveStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}
        self.pickers = {}

    def create(self, agent_id, rate):
        with self.lock:
            for s in self.sessions.values():
                if s["agent_id"] == agent_id and s["status"] not in (
                    "stopped",
                    "failed",
                ):
                    raise ValueError("该边端已有示波会话，请先停止")
            # 仅保留最近会话，避免长时间使用时积累已停止的示波缓存。
            ended = [
                k
                for k, v in self.sessions.items()
                if v["status"] in ("stopped", "failed")
            ]
            for k in ended[:-10]:
                del self.sessions[k]
            s = dict(
                id=uuid.uuid4().hex,
                agent_id=agent_id,
                sample_rate=rate,
                status="waiting_device",
                stop_requested=False,
                recording=None,
                samples_received=0,
                revision=0,
                frame_sequence=None,
                error=None,
                received_at=None,
                last_upload=0,
                chunks=deque(),
                rms_history=deque(maxlen=240),
            )
            self.sessions[s["id"]] = s
            return s

    def get(self, session_id):
        with self.lock:
            if session_id not in self.sessions:
                raise KeyError("示波会话不存在，后端可能已重启")
            return self.sessions[session_id]

    def snapshot(self, s):
        with self.lock:
            return copy.deepcopy(
                {
                    k: v
                    for k, v in s.items()
                    if k not in ("chunks", "rms_history", "last_upload")
                }
            )

    def current(self, agent_id):
        with self.lock:
            return next(
                (
                    s
                    for s in reversed(list(self.sessions.values()))
                    if s["agent_id"] == agent_id
                    and s["status"] not in ("stopped", "failed")
                ),
                None,
            )

    def push(self, s, values, start, sequence):
        with self.lock:
            if start < s["samples_received"]:
                return
            s["chunks"].append((start, values.copy()))
            s["samples_received"] = start + len(values)
            s["frame_sequence"] = sequence
            cutoff = s["samples_received"] - s["sample_rate"] * 2
            while s["chunks"] and s["chunks"][0][0] + len(s["chunks"][0][1]) <= cutoff:
                s["chunks"].popleft()
            s["received_at"] = datetime.now(timezone.utc).isoformat()
            s["last_upload"] = time.monotonic()
            s["revision"] += 1
            centered = values.astype(float) - values.mean(axis=0)
            s["rms_history"].append(
                [
                    s["samples_received"] / s["sample_rate"],
                    *np.sqrt(np.mean(centered**2, axis=0)).tolist(),
                ]
            )

    def window(self, s):
        with self.lock:
            if not s["chunks"]:
                return 0, np.empty((0, 4), dtype=np.int32)
            # 网络中断产生的缺口不能拼接成连续波形，只取最近的连续片段。
            contiguous = []
            end = s["samples_received"]
            for start, data in reversed(s["chunks"]):
                if start + len(data) != end:
                    break
                contiguous.append(data)
                end = start
            a = np.concatenate(list(reversed(contiguous)))
            a = a[-s["sample_rate"] * 2 :]
            return s["samples_received"] - len(a), a


live = LiveStore()
