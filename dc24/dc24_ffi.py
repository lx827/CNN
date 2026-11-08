"""dc24_edge_core 动态库的 ctypes 绑定（契约见 edge/FFI.md，真相源 edge/src/ffi.rs）。

只做库加载与消息搬运：契约要求同一句柄的所有调用串行化，因此全部 FFI 调用
持同一把锁；poll 返回的 data 是借用指针（有效期到下一次 poll/start/close），
必须在锁内立即拷贝为 bytes。本文件仅依赖标准库，导入时不加载动态库。
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import threading

# 消息标签，与 ffi.rs 的 MSG_* 常量一致。
MSG_SAMPLES = 1  # 样本块：data 为 16 字节/采样时刻的四路小端 int32
MSG_EVENT = 2    # 事件：UTF-8 JSON 行，以 \n 结尾
MSG_STATE = 3    # 链路状态：UTF-8 JSON {"state":…,"detail":…}

ERR_BUFFER_BYTES = 512


class Dc24Msg(ctypes.Structure):
    """ffi.rs 中 #[repr(C)] Message 的逐字段镜像（自然对齐，宿主须逐字段镜像）。

    64 位平台布局：tag@0, sequence@2, start_sample@8, len@16, data@24，总 32 字节。
    """

    _fields_ = [
        ("tag", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("start_sample", ctypes.c_uint64),
        ("len", ctypes.c_size_t),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
    ]


def library_filename() -> str:
    """按平台给出 cdylib 文件名（Windows: dll，其余: .so）。"""
    return "dc24_edge_core.dll" if os.name == "nt" else "libdc24_edge_core.so"


def default_search_paths() -> list[Path]:
    """默认搜索顺序：edge/target/release 优先（部署产物），其次 debug（开发构建）。"""
    root = Path(__file__).resolve().parents[1]
    name = library_filename()
    return [root / "edge" / "target" / profile / name for profile in ("release", "debug")]


def locate_library(explicit: str | os.PathLike | None = None) -> Path | None:
    """定位动态库：显式路径 > 环境变量 DC24_EDGE_LIB > edge/target 默认搜索。"""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    from_env = os.environ.get("DC24_EDGE_LIB")
    if from_env:
        candidates.append(Path(from_env))
    candidates.extend(default_search_paths())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class EdgeCoreError(RuntimeError):
    """FFI 调用失败（错误文本来自核心写入的 err 缓冲）。"""


def _err_text(buffer: ctypes.Array) -> str:
    """读取 err 缓冲中的 UTF-8 错误文本（核心保证 NUL 结尾、按字符边界截断）。"""
    return buffer.value.decode("utf-8", "replace")


class EdgeCore:
    """dc24_edge_core 句柄的线程安全封装。

    用法：
        core = EdgeCore()                # 或 EdgeCore(lib_path)
        core.open(config_text)           # 解析配置并绑定常驻监听
        core.start(10000)
        message = core.poll(250)         # None=超时；否则 (tag, sequence, start, bytes)
        core.stop(); core.close()
    也支持 with 语句（退出时 close）。
    """

    def __init__(self, library_path: str | os.PathLike | None = None):
        resolved = locate_library(library_path)
        if resolved is None:
            raise EdgeCoreError(
                f"找不到 {library_filename()}；请在 edge/ 目录 cargo build，"
                "或用参数/环境变量 DC24_EDGE_LIB 指定路径"
            )
        self.path = resolved
        self._lib = ctypes.CDLL(str(resolved))
        self._lock = threading.Lock()
        self._handle: int | None = None
        self._bind()

    # ------------------------------------------------------------------ 绑定
    def _bind(self) -> None:
        lib, msg = self._lib, ctypes.POINTER(Dc24Msg)
        lib.dc24_edge_open.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_open.restype = ctypes.c_void_p
        lib.dc24_edge_start.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_start.restype = ctypes.c_int32
        lib.dc24_edge_poll.argtypes = [ctypes.c_void_p, msg, ctypes.c_int32]
        lib.dc24_edge_poll.restype = ctypes.c_int32
        lib.dc24_edge_stop.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.dc24_edge_stop.restype = ctypes.c_int32
        lib.dc24_edge_running.argtypes = [ctypes.c_void_p]
        lib.dc24_edge_running.restype = ctypes.c_int32
        lib.dc24_edge_info_json.argtypes = []
        lib.dc24_edge_info_json.restype = ctypes.c_char_p  # 指向静态内存，借用期=进程生命周期
        lib.dc24_edge_close.argtypes = [ctypes.c_void_p]
        lib.dc24_edge_close.restype = None

    def _require_handle(self) -> int:
        if self._handle is None:
            raise EdgeCoreError("句柄未打开（先调用 open）")
        return self._handle

    # ------------------------------------------------------------------ API
    def open(self, config_text: str) -> None:
        """解析 config.json 全文并绑定常驻监听；失败抛 EdgeCoreError。"""
        err = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            handle = self._lib.dc24_edge_open(config_text.encode("utf-8"), err, len(err))
            if not handle:
                raise EdgeCoreError(f"dc24_edge_open 失败: {_err_text(err)}")
            self._handle = handle

    def start(self, sample_rate: int) -> None:
        """启动一次采集会话（内部线程执行设备时序，立即返回）。"""
        err = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            code = self._lib.dc24_edge_start(self._require_handle(), int(sample_rate), err, len(err))
            if code != 0:
                raise EdgeCoreError(f"dc24_edge_start 失败: {_err_text(err)}")

    def poll(self, timeout_ms: int = 200) -> tuple[int, int, int, bytes] | None:
        """拉取一条消息；返回 (tag, sequence, start_sample, data拷贝) 或 None（超时）。

        data 借用指针仅保证到下一次 poll/start/close，故在锁内立即拷贝。
        """
        message = Dc24Msg()
        with self._lock:
            code = self._lib.dc24_edge_poll(self._require_handle(), ctypes.byref(message), int(timeout_ms))
            if code == 0:
                return None
            if code != 1:
                raise EdgeCoreError(f"dc24_edge_poll 返回 {code}")
            data = ctypes.string_at(message.data, message.len) if message.len else b""
            return message.tag, message.sequence, message.start_sample, data

    def stop(self) -> None:
        """请求停止并等待会话线程收尾（内部完成 B8 与应答，最长约 5~7 秒）。"""
        err = ctypes.create_string_buffer(ERR_BUFFER_BYTES)
        with self._lock:
            code = self._lib.dc24_edge_stop(self._require_handle(), err, len(err))
            if code != 0:
                raise EdgeCoreError(f"dc24_edge_stop 失败: {_err_text(err)}")

    def running(self) -> bool:
        """会话线程是否存活。"""
        with self._lock:
            return self._lib.dc24_edge_running(self._require_handle()) == 1

    def info(self) -> dict:
        """进程级静态元数据（版本/档位/输入配置/B2、B5 负载模板等）。"""
        text = self._lib.dc24_edge_info_json()
        if not text:
            raise EdgeCoreError("dc24_edge_info_json 返回空")
        return json.loads(text.decode("utf-8"))

    def close(self) -> None:
        """停止会话并释放句柄；之后不得再使用本对象。"""
        with self._lock:
            handle, self._handle = self._handle, None
            if handle is not None:
                self._lib.dc24_edge_close(handle)

    def __enter__(self) -> "EdgeCore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
