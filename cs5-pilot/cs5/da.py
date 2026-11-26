"""DA 输出量化：电压 -> 16 位大端 DAC 码。

实测标定（反射调用厂商 SingleToBytes.SingleToUint16BigBytes，4001 点采样）：

    dac = round((volt + 10) / 20 * 65535)     volt ∈ [-10, +10]

误差 ≤1 LSB = 0.305 mV，对 16 位 DA 无实际影响。
"""

from __future__ import annotations

VOLT_MIN = -10.0
VOLT_MAX = 10.0
DAC_MAX = 0xFFFF


class VoltOutOfRange(ValueError):
    """电压超出 DA 输出范围。"""


def volt_to_dac(volt: float) -> int:
    """把 -10..+10 V 映射到 0..65535。"""
    if volt < VOLT_MIN or volt > VOLT_MAX:
        raise VoltOutOfRange(f"voltage {volt} V out of range [{VOLT_MIN}, {VOLT_MAX}]")
    raw = int((volt - VOLT_MIN) / (VOLT_MAX - VOLT_MIN) * DAC_MAX + 0.5)
    return max(0, min(DAC_MAX, raw))


def dac_to_volt(dac: int) -> float:
    """DAC 码反算回电压，用于校验。"""
    return dac / DAC_MAX * (VOLT_MAX - VOLT_MIN) + VOLT_MIN


def volt_to_bytes(volt: float) -> bytes:
    """电压 -> 2 字节大端。"""
    dac = volt_to_dac(volt)
    return bytes(((dac >> 8) & 0xFF, dac & 0xFF))