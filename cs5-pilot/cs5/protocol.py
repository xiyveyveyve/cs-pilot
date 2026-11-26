"""CS Studio 5 的固定命令帧与连接/启停流程。"""

from __future__ import annotations

from . import frame

# 实测自 CommandPackage 静态字段
BOOT_FRAME = bytes.fromhex("AAD000000000000000000000000000" "7A")
VERSION_FRAME = bytes.fromhex("AA8800000000000000000000000000" "32")
SERIAL_FRAME = bytes.fromhex("AA8100000000000000000000000000" "2B")
READ_OCP_FRAME = bytes.fromhex("AA5301000000000000000000000000" "FE")
START_FRAME = bytes.fromhex("AA8051000000000000000000000000" "7B")
PAUSE_FRAME = bytes.fromhex("AA8052000000000000000000000000" "7C")
STOP_FRAME = bytes.fromhex("AA8053000000000000000000000000" "7D")
REVERSE_FRAME = bytes.fromhex("AA6FFF000000000000000000000000" "18")

# 握手序列
HANDSHAKE_D0 = frame.build(0xD0)
HANDSHAKE_D1 = frame.build(0xD1)
HANDSHAKE_8B = frame.build(0x8B)
HEARTBEAT_CF = frame.build(0xCF)

# 数据采集起始（AA 74，后跟方法编号）
ACQ_BEGIN = frame.build(0x74, b"\x00")

# 自检：所有固定帧必须 SUM 正确
_FIXED = {
    "BOOT": BOOT_FRAME,
    "VERSION": VERSION_FRAME,
    "SERIAL": SERIAL_FRAME,
    "READ_OCP": READ_OCP_FRAME,
    "START": START_FRAME,
    "PAUSE": PAUSE_FRAME,
    "STOP": STOP_FRAME,
    "REVERSE": REVERSE_FRAME,
    "D0": HANDSHAKE_D0,
    "D1": HANDSHAKE_D1,
    "8B": HANDSHAKE_8B,
    "CF": HEARTBEAT_CF,
    "74": ACQ_BEGIN,
}

for _name, _f in _FIXED.items():
    if not frame.verify(_f):
        raise AssertionError(f"fixed frame {_name} has bad checksum: {frame.hexs(_f)}")


def connect_sequence() -> list[bytes]:
    """建链帧序列（S1–S3）。"""
    return [HANDSHAKE_D0, HANDSHAKE_D0, HANDSHAKE_D1, HANDSHAKE_D1, HANDSHAKE_D1,
            HANDSHAKE_8B, HANDSHAKE_8B, HANDSHAKE_8B]


def start_sequence() -> list[bytes]:
    """启动帧序列（S4–S6）。"""
    return [START_FRAME, START_FRAME, START_FRAME,
            SERIAL_FRAME, SERIAL_FRAME, SERIAL_FRAME,
            READ_OCP_FRAME]


def stop_sequence() -> list[bytes]:
    """停止帧序列。"""
    return [STOP_FRAME, STOP_FRAME, STOP_FRAME]