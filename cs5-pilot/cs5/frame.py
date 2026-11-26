"""16 字节定长命令帧的构造与校验。

帧结构：AA | cmd | data[13] | SUM
SUM = sum(frame[0..14]) & 0xFF
"""

from __future__ import annotations

HEAD = 0xAA
FRAME_LEN = 16
DATA_LEN = 13

# 设备应答/心跳里出现的数据帧首字节
DATA_FRAME_HEAD = 0x60
DATA_FRAME_LEN = 10


def checksum(body: bytes | bytearray) -> int:
    """对前 15 字节求和取低 8 位。"""
    return sum(body[: FRAME_LEN - 1]) & 0xFF


def build(cmd: int, data: bytes = b"") -> bytes:
    """构造一条 16 字节命令帧。

    data 从第 2 字节开始填充，最多 13 字节，不足补 0。
    """
    if len(data) > DATA_LEN:
        raise ValueError(f"payload too long: {len(data)} > {DATA_LEN}")
    buf = bytearray(FRAME_LEN)
    buf[0] = HEAD
    buf[1] = cmd & 0xFF
    buf[2 : 2 + len(data)] = data
    buf[FRAME_LEN - 1] = checksum(buf)
    return bytes(buf)


def verify(frame: bytes) -> bool:
    """校验一条完整帧的累加和。"""
    return len(frame) == FRAME_LEN and frame[0] == HEAD and checksum(frame) == frame[FRAME_LEN - 1]


def is_data_frame(buf: bytes) -> bool:
    """是否是设备返回的 10 字节测量数据帧。"""
    return len(buf) >= DATA_FRAME_LEN and buf[0] == DATA_FRAME_HEAD


def hexs(frame: bytes) -> str:
    """便于日志阅读的十六进制串。"""
    return " ".join(f"{b:02X}" for b in frame)