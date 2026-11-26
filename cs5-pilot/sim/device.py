"""CS350 设备模拟器：按逆向出的帧格式应答，用于无硬件自测。

用法：
    dev = SimDevice()
    tp = LoopbackTransport(dev.handle)
    sess = CS350Session(tp)
"""

from __future__ import annotations

import math
import struct

from cs5 import frame


class SimDevice:
    """一个最小的 CS350 行为模型。"""

    def __init__(self, *, ocp: float = -0.139, serial: str = "CS3501501006",
                 noise: float = 0.0005, slowness: float = 1.0) -> None:
        self.ocp = ocp
        self.serial = serial
        self.noise = noise
        self.slowness = slowness

        self.io_bytes: bytes | None = None
        self.da_volt: float | None = None
        self.acquiring = False
        self.point_index = 0
        self.pending: list[bytes] = []
        self.received: list[bytes] = []

    # ---------- 对外入口 ----------

    def handle(self, data: bytes) -> bytes:
        """收到一帧或多帧，返回应答字节。"""
        self.received.append(data)
        out = bytearray()
        for chunk in self._split(data):
            out.extend(self._handle_one(chunk))
        if self.acquiring:
            out.extend(self._sample())
        return bytes(out)

    # ---------- 内部 ----------

    @staticmethod
    def _split(data: bytes) -> list[bytes]:
        """按 16 字节切帧；不足则原样返回。"""
        if len(data) <= frame.FRAME_LEN:
            return [data]
        return [data[i : i + frame.FRAME_LEN] for i in range(0, len(data), frame.FRAME_LEN)]

    def _handle_one(self, f: bytes) -> bytes:
        if len(f) < 2 or f[0] != frame.HEAD:
            return b""
        cmd = f[1]
        if cmd in (0xD0, 0xD1, 0x8B, 0xCF):
            return f  # echo
        if cmd == 0x88:
            return f
        if cmd == 0x81:
            if len(f) > 2 and f[2] == 0x00:
                return self.serial.encode("ascii")
            return f
        if cmd == 0x53:
            return self._ocp_reply()
        if cmd == 0x85:
            self.io_bytes = bytes(f[2:5])
            return f
        if cmd == 0x72:
            dac = (f[3] << 8) | f[4]
            self.da_volt = dac / 65535.0 * 20.0 - 10.0
            return f
        if cmd == 0x74:
            self.acquiring = True
            self.point_index = 0
            return f
        if cmd == 0x80:
            sub = f[2]
            if sub == 0x51:
                self.acquiring = True
            elif sub in (0x52, 0x53):
                self.acquiring = False
            return f
        return f

    def _ocp_reply(self) -> bytes:
        raw = int((self.ocp + 10.0) / 20.0 * 16777215.0)
        raw = max(0, min((1 << 24) - 1, raw))
        buf = bytearray(frame.FRAME_LEN)
        buf[0] = 0xAA
        buf[1] = 0x53
        buf[2] = (raw >> 16) & 0xFF
        buf[3] = (raw >> 8) & 0xFF
        buf[4] = raw & 0xFF
        buf[15] = frame.checksum(buf)
        return bytes(buf)

    def _sample(self) -> bytes:
        """产出一帧 10 字节数据。"""
        t = self.point_index
        self.point_index += 1
        # 恒电流极化：电流恒定，电位按 IR + 缓慢漂移演化
        i = 2.0e-4
        e = self.da_volt if self.da_volt is not None else self.ocp
        e += self.noise * math.sin(t * 0.7) + 1e-5 * t
        return (
            bytes((frame.DATA_FRAME_HEAD,))
            + struct.pack("<f", e)
            + struct.pack("<f", i)
            + bytes((t & 0xFF,))
        )