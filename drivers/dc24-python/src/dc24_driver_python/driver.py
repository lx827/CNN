"""直接监听 DC24 设备 TCP 连接，不加载厂商软件或 DLL。"""

import socket
import time

from dc24_driver import Dc24Driver, LinkState


class PythonTcpDriver(Dc24Driver):
    transport = "python_tcp"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.server = None

    def connect(self, should_stop, wait=45):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        deadline = time.monotonic() + wait
        print(
            f"Listening on {self.host}:{self.port}; waiting for {self.peer} ...",
            flush=True,
        )
        while not should_stop() and time.monotonic() < deadline:
            self.server.settimeout(min(0.5, max(0.1, deadline - time.monotonic())))
            try:
                candidate, address = self.server.accept()
            except TimeoutError:
                continue
            if address[0] == self.peer:
                self.connection = candidate
                self.device_source_port = address[1]
                self.state = LinkState.CONNECTED
                print(f"Connected: {self.peer}:{address[1]}", flush=True)
                return True
            candidate.close()
        if not should_stop():
            raise TimeoutError("Device did not connect")
        return False

    def close(self):
        super().close()
        if self.server is not None:
            self.server.close()
            self.server = None
