"""传输层抽象：串口（桌面/Linux）与 TCP（串口服务器）。

上位机只依赖 read/write，不关心底层。
"""

from __future__ import annotations

import time
from typing import Protocol


class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> None: ...
    def read(self, n: int, timeout: float) -> bytes: ...
    @property
    def is_open(self) -> bool: ...


class SerialTransport:
    """基于 pyserial 的串口传输。"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.2) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self) -> None:
        import serial  # 延迟导入，便于无串口环境下跑模拟器

        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        self._ser.reset_input_buffer()

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise RuntimeError("serial port not open")
        self._ser.write(data)
        self._ser.flush()

    def read(self, n: int, timeout: float) -> bytes:
        if self._ser is None:
            raise RuntimeError("serial port not open")
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while len(buf) < n and time.monotonic() < deadline:
            chunk = self._ser.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
        return bytes(buf)

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open


class TcpTransport:
    """串口服务器 / WiFi 转串口（CS350 本身无网口，需外接）。"""

    def __init__(self, host: str, port: int = 4001, timeout: float = 0.2) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None

    def open(self) -> None:
        import socket

        s = socket.create_connection((self.host, self.port), timeout=max(self.timeout, 2.0))
        s.settimeout(self.timeout)
        self._sock = s

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def write(self, data: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("socket not open")
        self._sock.sendall(data)

    def read(self, n: int, timeout: float) -> bytes:
        if self._sock is None:
            raise RuntimeError("socket not open")
        self._sock.settimeout(timeout)
        try:
            return self._sock.recv(n)
        except (TimeoutError, OSError):
            return b""

    @property
    def is_open(self) -> bool:
        return self._sock is not None


class LoopbackTransport:
    """本地回环：把写进去的帧直接当作应答,供离线自测。"""

    def __init__(self, responder=None) -> None:
        self._open = False
        self.written: list[bytes] = []
        self._pending = bytearray()
        self._responder = responder

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> None:
        self.written.append(data)
        if self._responder is not None:
            reply = self._responder(data)
            if reply:
                self._pending.extend(reply)

    def read(self, n: int, timeout: float) -> bytes:
        take = bytes(self._pending[:n])
        del self._pending[: len(take)]
        return take

    @property
    def is_open(self) -> bool:
        return self._open