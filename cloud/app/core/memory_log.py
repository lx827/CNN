"""
内存日志环形缓冲区

解决 Windows 开发环境没有 journalctl、以及生产环境无需 systemd 也能查看日志的问题。
通过自定义 logging.Handler，将应用运行中的关键日志保留在内存中，
前端 /api/logs/ 接口可直接读取。
"""
import logging
import sys
from collections import deque
from datetime import datetime


class RingBufferHandler(logging.Handler):
    """
    内存环形日志缓冲区
    默认保留最近 2000 条日志，超出后自动丢弃最旧的。
    """

    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.capacity = capacity
        self._buffer = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._buffer.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self, lines: int = 200) -> str:
        """获取最近 N 条日志，以换行符拼接"""
        if not self._buffer:
            return ""
        recent = list(self._buffer)[-lines:]
        return "\n".join(recent)

    def clear(self):
        """清空缓冲区"""
        self._buffer.clear()


# 全局单例：应用启动时由 main.py 注册到 root logger
_ring_handler: RingBufferHandler = None


def setup_memory_logging(capacity: int = 2000, level: int = logging.INFO):
    """
    初始化内存日志捕获。
    将 RingBufferHandler 挂载到 root logger，同时重定向 stdout 的 print 输出。
    """
    global _ring_handler

    if _ring_handler is not None:
        return

    _ring_handler = RingBufferHandler(capacity=capacity)
    _ring_handler.setLevel(level)

    # 获取 root logger 并添加 handler
    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加
    if _ring_handler not in root.handlers:
        root.handlers.append(_ring_handler)

    # 如果已有 StreamHandler，保持它继续向控制台输出
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RingBufferHandler) for h in root.handlers)
    if not has_stream:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(_ring_handler.formatter)
        root.handlers.append(console)


def get_memory_logs(lines: int = 200) -> str:
    """获取内存中最近 N 条日志"""
    if _ring_handler is None:
        return ""
    return _ring_handler.get_logs(lines)


def get_ring_handler() -> RingBufferHandler:
    """返回全局 handler 实例（供测试或外部扩展使用）"""
    return _ring_handler
