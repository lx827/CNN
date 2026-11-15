"""dc24_edge_core 的进程内 ctypes 绑定；不包含采集、保存或上传编排。"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import threading

MSG_SAMPLES = 1
MSG_EVENT = 2
MSG_STATE = 3
ERR_BUFFER_BYTES = 512


class _Message(ctypes.Structure):
    _fields_ = [
        ("tag", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("start_sample", ctypes.c_uint64),
        ("len", ctypes.c_size_t),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
    ]


class EdgeCore:
    def __init__(self, library_path=None):
        selected = library_path or os.environ.get("DC24_EDGE_LIB")
        if selected is None:
            name = "dc24_edge_core.dll" if os.name == "nt" else "libdc24_edge_core.so"
            selected = Path(__file__).with_name(name)
        self.path = Path(selected)
        if not self.path.is_file():
            raise RuntimeError(f"找不到 dc24_edge_core 原生库: {self.path}")
        self._lib = ctypes.CDLL(str(self.path))
        self._lock = threading.Lock()
        self._handle = None
        self._bind()

    def _bind(self):
        lib = self._lib
        lib.dc24_edge_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_open.restype = ctypes.c_void_p
        lib.dc24_edge_start.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_start.restype = ctypes.c_int32
        lib.dc24_edge_poll.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Message), ctypes.c_int32]
        lib.dc24_edge_poll.restype = ctypes.c_int32
        byte_pointer = ctypes.POINTER(ctypes.c_uint8)
        lib.dc24_edge_sample_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(byte_pointer), ctypes.POINTER(ctypes.c_size_t)]
        lib.dc24_edge_sample_frame.restype = ctypes.c_int32
        lib.dc24_edge_stop.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_stop.restype = ctypes.c_int32
        lib.dc24_edge_close.argtypes = [ctypes.c_void_p]
        lib.dc24_edge_close.restype = None

    @staticmethod
    def _error(buffer):
        return buffer.value.decode("utf-8", "replace")

    def _handle_or_raise(self):
        if self._handle is None:
            raise RuntimeError("dc24_edge_core 句柄未打开")
        return self._handle

    def open(self, config_text):
        error = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            handle = self._lib.dc24_edge_open(config_text.encode("utf-8"), error, len(error))
            if not handle:
                raise RuntimeError(f"dc24_edge_open 失败: {self._error(error)}")
            self._handle = handle

    def start(self, sample_rate):
        error = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            code = self._lib.dc24_edge_start(self._handle_or_raise(), sample_rate, error, len(error))
            if code:
                raise RuntimeError(f"dc24_edge_start 失败: {self._error(error)}")

    def poll(self, timeout_ms=0):
        message = _Message()
        with self._lock:
            code = self._lib.dc24_edge_poll(self._handle_or_raise(), ctypes.byref(message), timeout_ms)
            if code == 0:
                return None
            if code != 1:
                raise RuntimeError(f"dc24_edge_poll 返回 {code}")
            data = ctypes.string_at(message.data, message.len) if message.len else b""
            frame = None
            if message.tag == MSG_SAMPLES:
                pointer = ctypes.POINTER(ctypes.c_uint8)()
                length = ctypes.c_size_t()
                code = self._lib.dc24_edge_sample_frame(
                    self._handle_or_raise(), ctypes.byref(pointer), ctypes.byref(length)
                )
                if code != 1:
                    raise RuntimeError(f"dc24_edge_sample_frame 返回 {code}")
                frame = ctypes.string_at(pointer, length.value)
            return message.tag, message.sequence, message.start_sample, data, frame

    def stop(self):
        error = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            code = self._lib.dc24_edge_stop(self._handle_or_raise(), error, len(error))
            if code:
                raise RuntimeError(f"dc24_edge_stop 失败: {self._error(error)}")

    def close(self):
        with self._lock:
            handle, self._handle = self._handle, None
            if handle is not None:
                self._lib.dc24_edge_close(handle)
