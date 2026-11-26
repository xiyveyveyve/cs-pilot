"""无硬件自测：帧、量化、恒电流极化帧、模拟器端到端。"""

from __future__ import annotations

import csv
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cs5 import da, datalog, frame, galstatic, protocol  # noqa: E402
from cs5.session import CS350Session, parse_data_frame  # noqa: E402
from cs5.transport import LoopbackTransport  # noqa: E402
from sim.device import SimDevice  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def t_frames() -> None:
    print("[1] 固定帧校验和")
    for name, f in protocol._FIXED.items():
        check(f"{name} len=16", len(f) == 16)
        check(f"{name} sum ok", frame.verify(f), frame.hexs(f))
    check("GetCMDBytes(0x53,[1])",
          frame.build(0x53, b"\x01") == protocol.READ_OCP_FRAME,
          frame.hexs(frame.build(0x53, b"\x01")))


def t_da() -> None:
    print("[2] DA 量化对照厂商映射表")
    table = ROOT / "data" / "da_map.csv"
    if not table.exists():
        check("da_map.csv 存在", False, str(table))
        return
    worst = 0
    n = 0
    with table.open() as fh:
        for row in csv.reader(fh):
            if not row:
                continue
            v, raw = float(row[0]), int(row[1])
            n += 1
            worst = max(worst, abs(da.volt_to_dac(v) - raw))
    check(f"扫表 {n} 点", n > 3000)
    check("最大偏差 <= 1 LSB", worst <= 1, f"worst={worst}")
    check("0V -> 0x8000", da.volt_to_dac(0.0) == 0x8000)
    check("-10V -> 0", da.volt_to_dac(-10.0) == 0)
    check("10V -> 0xFFFF", da.volt_to_dac(10.0) == 0xFFFF)


def t_galstatic() -> None:
    print("[3] 恒电流极化帧")
    p = galstatic.GalStaticParams(por_curr=0.2, curr_unit="mA", test_time=200)
    check("电流 0.2mA -> 0.0002A", abs(p.current_a - 0.0002) < 1e-12)
    check("DA 输出 0.2V", abs(p.da_volt - 0.2) < 1e-9, f"{p.da_volt}")
    io = p.io_frame()
    check("IO 帧 = AA 85 93 02 00…C4",
          frame.hexs(io) == "AA 85 93 02 00 00 00 00 00 00 00 00 00 00 00 C4",
          frame.hexs(io))
    daf = p.da_point_frame()
    check("DA 帧 cmd=0x72 ch=0", daf[1] == 0x72 and daf[2] == 0x00)
    check("DA 帧电压 = 0.2V", abs(da.dac_to_volt((daf[3] << 8) | daf[4]) - 0.2) < 0.001)
    check("DA 帧校验和", frame.verify(daf))
    check("摘要串", "The polarization current(mA):0.2" in p.summary(), p.summary())
    check("预计点数 1000", p.expected_points() == 1000, str(p.expected_points()))

    p2 = galstatic.GalStaticParams(por_curr=25, curr_unit="uA")
    check("25uA -> 0.025V", abs(p2.da_volt - 0.025) < 1e-9, f"{p2.da_volt}")


def t_dataframe() -> None:
    print("[4] 数据帧解析")
    raw = bytes.fromhex("60F3500EBE0000D63800")
    p = parse_data_frame(raw)
    check("解析非空", p is not None)
    if p:
        check("E ≈ -0.139", abs(p.e + 0.139) < 0.005, f"{p.e}")
        check("I ≈ 1.02e-4", abs(p.i - 1.02e-4) < 1e-5, f"{p.i}")
        check("seq = 0", p.seq == 0)


def t_end_to_end() -> None:
    print("[5] 模拟器端到端（0.5s 短跑）")
    dev = SimDevice()
    tp = LoopbackTransport(dev.handle)
    sess = CS350Session(tp)
    sess.connect()
    check("已连接", sess.connected)
    ocp = sess.read_ocp()
    check("OCP 解析 ≈ -0.139", abs(ocp + 0.139) < 0.01, f"{ocp}")

    p = galstatic.GalStaticParams(por_curr=0.2, test_time=200, sample_frq=5.0)
    cor = sess.run_galstatic(p, stop_early_after=0.5)
    check("采集到数据点", len(cor.points) > 0, f"n={len(cor.points)}")
    check("设备收到 IO 帧", dev.io_bytes == bytes((0x93, 0x02, 0x00)), str(dev.io_bytes))
    check("设备收到 DA 电压 ≈0.2V",
          dev.da_volt is not None and abs(dev.da_volt - 0.2) < 0.001, str(dev.da_volt))
    check("采集结束设备已停", not dev.acquiring)

    out = ROOT / "out" / "selftest.cor"
    cor.save(out)
    check("落盘 .cor", out.exists())
    back = datalog.CorFile.load(out)
    check(".cor 往返点数一致", len(back.points) == len(cor.points),
          f"{len(back.points)} vs {len(cor.points)}")
    check(".cor 方法名", back.method == "ID_GalStatic", back.method)


def main() -> int:
    print("=== CS5Pilot 自测 ===")
    t_frames()
    t_da()
    t_galstatic()
    t_dataframe()
    t_end_to_end()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())