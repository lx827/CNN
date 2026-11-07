"""DC24 的 Windows 厂商连接，向现有协议处理提供完整设备帧。"""
import base64
import hashlib
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time


JM_SERVER_SHA256 = '15295ee583e94c3e9583c71e0de5cc433436ab027c7edd0d57506a43993251df'


class VendorConnection:
    """通过子进程调用已验证的 x86 DLL，复用 Link 的套接字读写约定。"""

    def __init__(self, root, host, port, peer):
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError('DC24_VENDOR_ROOT 必须是原厂软件安装目录的绝对路径')
        dll = root/'dll/JMServer.dll'
        if not dll.is_file() or hashlib.sha256(dll.read_bytes()).hexdigest() != JM_SERVER_SHA256:
            raise ValueError('DC24_VENDOR_ROOT 未找到已验证版本的 dll/JMServer.dll')
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'SysWOW64/WindowsPowerShell/v1.0/powershell.exe'
        if not powershell.is_file():
            raise RuntimeError('原厂 DC24 DLL 需要 Windows 32 位 PowerShell')
        self.frames = queue.Queue(maxsize=128)
        self.ready = threading.Event()
        self.connected = threading.Event()
        self.disconnected = threading.Event()
        self.error = None
        self.timeout = .1
        self.process = subprocess.Popen([
            str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(Path(__file__).with_name('dc24_vendor_bridge.ps1')), '-VendorRoot', str(root),
            '-HostIp', host, '-Port', str(port), '-PeerIp', peer,
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding='ascii', errors='replace',
            bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                kind, _, payload = line.rstrip().partition(' ')
                if kind == 'FRAME' and not self.error:
                    try:
                        self.frames.put_nowait(base64.b64decode(payload, validate=True))
                    except queue.Full:
                        self.error = '原厂 DLL 接收队列已满，采样可能不连续'
                elif kind == 'READY':
                    self.ready.set()
                elif kind == 'CONNECTED':
                    self.connected.set()
                elif kind == 'ERROR':
                    self.error = payload
                elif kind == 'DISCONNECTED':
                    self.disconnected.set()
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self.disconnected.set()

    def wait_for_device(self, stop, seconds):
        deadline = time.monotonic() + seconds
        while not stop.is_set():
            if self.error or self.disconnected.is_set():
                raise ConnectionError(self.error or '原厂 DLL 进程提前退出，请检查边端日志和 TCP 6800')
            if self.connected.wait(.1) and self.ready.is_set():
                return not stop.is_set()
            if time.monotonic() >= deadline:
                raise TimeoutError('45秒内未收到采集器连接，请检查网线、IP和原厂软件是否退出')
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, max_length):
        if self.error:
            raise ConnectionError(self.error)
        try:
            frame = self.frames.get(timeout=self.timeout)
        except queue.Empty:
            if self.disconnected.is_set():
                return b''
            raise socket.timeout() from None
        if len(frame) > max_length:
            raise ValueError('原厂 DLL 返回超长设备帧')
        return frame

    def sendall(self, data):
        if self.disconnected.is_set():
            raise ConnectionError('原厂 DLL 的设备连接已关闭')
        self.process.stdin.write('TX ' + base64.b64encode(data).decode('ascii') + '\n')
        self.process.stdin.flush()

    def close(self):
        try:
            try:
                self.process.stdin.write('QUIT\n')
                self.process.stdin.flush()
            except BrokenPipeError:
                pass
            finally:
                self.process.stdin.close()
            if self.process.wait(timeout=8):
                raise RuntimeError(self.error or '原厂 DLL 进程异常退出，请检查边端日志')
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise RuntimeError('原厂 DLL 进程停止超时') from None
        finally:
            self.reader.join(2)
            self.process.stdout.close()
