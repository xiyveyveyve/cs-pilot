"""CS350 恒电流极化（GalStatic）——参数、换算与指令帧。

对应厂商 CorrTest.CorrData.MethodParams.GalStaticParams。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import frame
from .da import volt_to_bytes

# 电流单位 -> 10 的幂（A 基准）
CURR_UNIT_EXP = {"A": 0, "mA": 1, "uA": 2, "nA": 3, "pA": 4}

# CS350 恒电流极化固定手动量程 3（1 kΩ 跨阻）
MANUAL_CURR_RANGE = 3

# IO 位域初始值：SYS_BAND=4, voltRange=2, currRange=0
IO_BASE = 0x90
VOLT_RANGE = 2

CMD_IO = 0x85
CMD_DA_POINT = 0x72


def curr_to_volt(por_curr: float, curr_unit: str, curr_range: int = MANUAL_CURR_RANGE) -> float:
    """恒电流设定的电流值换算成 DA 输出电压。

    实测厂商式：volt = current_A * 10^currRange
    """
    exp = CURR_UNIT_EXP[curr_unit]
    current_a = por_curr / (10.0 ** (exp * 3))
    return current_a * (10.0 ** curr_range)


def io_bytes(curr_range: int = MANUAL_CURR_RANGE) -> bytes:
    """构造 3 字节 IO 位域。"""
    b0 = (IO_BASE & 0xF8) | (curr_range & 0x07)  # 0x90 -> 0x93
    return bytes((b0, VOLT_RANGE, 0x00))


def io_frame(curr_range: int = MANUAL_CURR_RANGE) -> bytes:
    """写 IO 配置帧：AA 85 [io0 io1 io2] 00…00 SUM"""
    return frame.build(CMD_IO, io_bytes(curr_range))


def da_point_frame(volt: float, channel: int = 0) -> bytes:
    """单点 DA 输出帧：AA 72 00 [u16BE] 00…00 SUM"""
    return frame.build(CMD_DA_POINT, bytes((channel,)) + volt_to_bytes(volt))


@dataclass
class GalStaticParams:
    """恒电流极化参数，字段默认值与厂商 GalStaticParams 一致。"""

    por_curr: float = 0.2
    curr_unit: str = "mA"
    test_time: float = 200.0
    time_unit: str = "s"
    sample_frq: float = 5.0
    use_stop_by_volt: bool = False
    use_stop_by_charge: bool = False
    less_volt: float = -2.0
    more_volt: float = 2.0
    less_charge: float = -2.0
    more_charge: float = 2.0
    stop_vs_ocp: bool = False  # False = vs Ref，True = vs OCP
    curr_range: int = MANUAL_CURR_RANGE

    def __post_init__(self) -> None:
        if self.curr_unit not in CURR_UNIT_EXP:
            raise ValueError(f"unsupported current unit: {self.curr_unit}")
        if self.test_time <= 0:
            raise ValueError("test_time must be positive")
        if self.sample_frq <= 0:
            raise ValueError("sample_frq must be positive")

    @property
    def test_time_s(self) -> float:
        """把测试时长统一成秒。"""
        factor = {"s": 1.0, "min": 60.0, "h": 3600.0}[self.time_unit]
        return self.test_time * factor

    @property
    def current_a(self) -> float:
        return self.por_curr / (10.0 ** (CURR_UNIT_EXP[self.curr_unit] * 3))

    @property
    def da_volt(self) -> float:
        return curr_to_volt(self.por_curr, self.curr_unit, self.curr_range)

    def method_frames(self) -> list[bytes]:
        """恒电流极化下发帧序列（对应 GetMethodBytes）。"""
        return [self.io_frame(), self.da_point_frame()]

    def io_frame(self) -> bytes:
        return io_frame(self.curr_range)

    def da_point_frame(self) -> bytes:
        return da_point_frame(self.da_volt)

    def expected_points(self) -> int:
        """按采样率估算总点数。"""
        return max(1, int(round(self.test_time_s * self.sample_frq)))

    def summary(self) -> str:
        """写进 .cor 头部的一行实验摘要。"""
        return (
            f"The polarization current({self.curr_unit}):{self.por_curr},"
            f"Hold time(s):{self.test_time_s:g},"
            f"Frq(Hz):{self.sample_frq:g}"
        )