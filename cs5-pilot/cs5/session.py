"""CS350 设备会话：连接、读取、恒电流极化执行。

移植自 CS Studio 5 的通讯层行为。设备是轮询式（不主动推送），
上位机下发 AA 53/AA 74 等命令后读回数据帧。
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from . import frame, protocol
from .datalog import CorFile, CorPoint
from .galstatic import GalStaticParams

POLL_INTERVAL = 0.05
READ_BACKLOG = 512


@dataclass
class DataPoint:
    """一帧测量数据。"""

    e: float
    i: float
    seq: int
    t: float = 0.0


def parse_data_frame(buf: bytes) -> DataPoint | None:
    """解析 10 字节数据帧：60 | E(f32 LE) | I(f32 LE) | seq"""
    if len(buf) < frame.DATA_FRAME_LEN or buf[0] != frame.DATA_FRAME_HEAD:
        return None
    e = struct.unpack("<f", buf[1:5])[0]
    i = struct.unpack("<f", buf[5:9])[0]
    return DataPoint(e=e, i=i, seq=buf[9])


def parse_ocp_reply(buf: bytes) -> float | None:
    """解析 AA 53 应答里的电位（24 位编码，符号约定待真机确认）。"""
    if len(buf) < 6 or buf[0] != 0xAA or buf[1] != 0x53:
        return None
    raw = (buf[2] << 16) | (buf[3] << 8) | buf[4]
    return raw / 16777215.0 * 20.0 - 10.0


class CS350Session:
    """一个设备会话。transport 需实现 open/close/write/read。"""

    def __init__(self, transport, *, echo_retries: int = 3) -> None:
        self.tp = transport
        self.echo_retries = echo_retries
        self.serial = ""
        self.boot_version = ""
        self.soft_version = ""
        self.ocp = 0.0
        self.connected = False
        self._rx = bytearray()

    # ---------- 基础收发 ----------

    def _send(self, data: bytes) -> None:
        self.tp.write(data)

    def _drain(self, timeout: float = 0.15) -> bytes:
        """读空接收缓冲，返回本次读到的全部字节。"""
        got = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.tp.read(READ_BACKLOG, max(0.0, deadline - time.monotonic()))
            if not chunk:
                break
            got.extend(chunk)
        self._rx.extend(got)
        return bytes(got)

    def _send_expect(self, data: bytes, timeout: float = 0.3) -> bytes:
        """发一帧并收集应答；设备不回也不算失败（很多命令无应答）。"""
        self._send(data)
        return self._drain(timeout)

    def _extract_data_frames(self) -> list[DataPoint]:
        """从接收缓冲里切出所有 10 字节数据帧。"""
        pts: list[DataPoint] = []
        while True:
            idx = self._rx.find(bytes((frame.DATA_FRAME_HEAD,)))
            if idx < 0:
                self._rx.clear()
                break
            if len(self._rx) - idx < frame.DATA_FRAME_LEN:
                del self._rx[:idx]
                break
            chunk = bytes(self._rx[idx : idx + frame.DATA_FRAME_LEN])
            del self._rx[: idx + frame.DATA_FRAME_LEN]
            p = parse_data_frame(chunk)
            if p is not None:
                pts.append(p)
        return pts

    # ---------- 连接 ----------

    def connect(self) -> bool:
        if not self.tp.is_open:
            self.tp.open()
        for f in protocol.connect_sequence():
            self._send_expect(f, 0.1)
        for _ in range(3):
            self._send(protocol.SERIAL_FRAME)
            reply = self._drain(0.2)
            sn = _ascii_sn(reply)
            if sn:
                self.serial = sn
                break
        self.connected = True
        return True

    def heartbeat(self) -> None:
        """设备空闲时的心跳，CS Studio 每秒发一次。"""
        self._send(protocol.HEARTBEAT_CF)

    def read_ocp(self) -> float:
        """读开路电位，同时更新 self.ocp。"""
        reply = self._send_expect(protocol.READ_OCP_FRAME, 0.3)
        v = parse_ocp_reply(reply)
        if v is not None:
            self.ocp = v
        return self.ocp

    # ---------- 恒电流极化 ----------

    def begin_acquisition(self) -> None:
        self._send_expect(protocol.ACQ_BEGIN, 0.2)

    def run_galstatic(
        self,
        params: GalStaticParams,
        *,
        on_point: Callable[[DataPoint], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        stop_early_after: float | None = None,
    ) -> CorFile:
        """执行一次恒电流极化并返回结果。"""
        if not self.connected:
            self.connect()
        self.read_ocp()

        started = datetime.now()
        t0 = time.monotonic()
        total = params.test_time_s
        if stop_early_after is not None:
            total = min(total, stop_early_after)

        # 下发方法参数：IO 配置 + 单点 DA
        for f in params.method_frames():
            self._send_expect(f, 0.2)

        self.begin_acquisition()

        cor = CorFile(
            method="ID_GalStatic",
            serial=self.serial,
            soft_version=self.soft_version or CorFile().soft_version,
            boot_version=self.boot_version,
            summary=params.summary(),
            ocp=self.ocp,
            started=started,
        )

        next_poll = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                if now - t0 >= total:
                    break
                if should_stop is not None and should_stop():
                    break

                if now >= next_poll:
                    self._send(protocol.READ_OCP_FRAME)
                    next_poll = now + 1.0 / params.sample_frq

                self._drain(1.0 / params.sample_frq)
                for p in self._extract_data_frames():
                    p.t = time.monotonic() - t0
                    cor.points.append(CorPoint(e=p.e, i=p.i, t=p.t))
                    if on_point is not None:
                        on_point(p)
        finally:
            self.stop()
            cor.finished = datetime.now()
        return cor

    def stop(self) -> None:
        for f in protocol.stop_sequence():
            self._send_expect(f, 0.1)

    def close(self) -> None:
        try:
            if self.connected:
                self.stop()
        finally:
            self.tp.close()
            self.connected = False


def _ascii_sn(reply: bytes) -> str:
    text = bytes(b for b in reply if 32 <= b < 127).decode("ascii", "ignore")
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) >= 6 else ""