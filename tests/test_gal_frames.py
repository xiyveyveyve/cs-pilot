# -*- coding: utf-8 -*-
"""test_gal_frames.py —— 恒电流族方法帧回归（2026-11-13/14 扩展）。

基准 = tests/golden/gal_frames.json：从 logs/t4_gal4_sim.jsonl / t4b_gal_diff_sim.jsonl
**程序化提取**的实捕帧（headless 链路 SendMethodBytes，两轮变参差分定案布局），
a/b 两组参数不同——解码断言同时验证换算与变参响应。
覆盖：四实验解码器换算 + 构造器逐字节复刻 + 命令互异。
运行：python tests/test_gal_frames.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "code", "sim"))

import simdevice as SD

GOLDEN = json.load(open(os.path.join(HERE, "golden", "gal_frames.json"), encoding="utf-8"))

PASSED = 0
FAILS = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("PASS %s" % name)
    else:
        FAILS.append(name)
        print("FAIL %s  %s" % (name, detail))


def raw_of(tag):
    return bytes.fromhex(GOLDEN[tag])


def close(a, b, tol=1e-9):
    """绝对 + 相对混合容差（f32 值的 double 表示误差随量级缩放）。"""
    return abs(a - b) <= max(tol, 1e-6 * max(abs(a), abs(b), 1e-30))


def test_gal_square():
    for tag, init_gal, init_t, cycles in (("a", 5e-4, 2.0, 1), ("b", 1e-3, 4.0, 2)):
        raw = raw_of("gal_square_" + tag)
        info = SD.decode_gal_square(raw[5:-1])
        check("0x57[%s] 量程=5.0" % tag, info["range_v"] == 5.0, info["range_v"])
        check("0x57[%s] Initial_Gal mA→A" % tag, close(info["initial_gal_a"], init_gal),
              info["initial_gal_a"])
        check("0x57[%s] InitialTime ms→s" % tag, close(info["initial_time_s"], init_t),
              info["initial_time_s"])
        check("0x57[%s] Step1=-0.5mA→-5e-4A" % tag,
              close(info["steps_a"][0], -5e-4), info["steps_a"][0])
        check("0x57[%s] 未启用步 Time=0.0" % tag,
              all(t == 0.0 for t in info["times_s"][1:]), info["times_s"][1:])
        check("0x57[%s] Final_Gal=-0.1mA" % tag, close(info["final_gal_a"], -1e-4),
              info["final_gal_a"])
        check("0x57[%s] Cycles=%d" % (tag, cycles), info["cycles"] == cycles,
              info["cycles"])
        check("0x57[%s] Frq=10" % tag, info["frq"] == 10.0, info["frq"])
        steps_mA = [-0.5, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4, 0.5, -0.5, 0.6]
        times_ms = [2000.0] + [0.0] * 9              # Time1=2000ms（两轮同），未启用步落 0
        built = SD.gal_square_frame(5.0, init_gal * 1000.0, init_t * 1000.0,
                                    steps_mA, times_ms, -0.1, 100.0,
                                    cycles, 10.0)
        rt = SD.decode_gal_square(built[5:-1])
        ok = (len(built) == len(raw)
              and close(rt["initial_gal_a"], init_gal)
              and close(rt["initial_time_s"], init_t)
              and all(close(x, y) for x, y in zip(rt["steps_a"], info["steps_a"]))
              and all(close(x, y) for x, y in zip(rt["times_s"], info["times_s"]))
              and rt["cycles"] == cycles and close(rt["frq"], 10.0))
        check("0x57[%s] 构造器往返等价" % tag, ok,
              " ".join("%d:%02X/%02X" % (i, built[i], raw[i])
                       for i in range(min(len(built), len(raw)))
                       if built[i] != raw[i]))


def test_gal_static():
    for tag, cur, tt in (("a", 1e-3, 60.0), ("b", 2e-3, 120.0)):
        raw = raw_of("gal_static_" + tag)
        info = SD.decode_gal_static(raw[5:-1])
        check("0x53[%s] 量程=5.0" % tag, info["range_v"] == 5.0, info["range_v"])
        check("0x53[%s] PorCurr mA→A" % tag, close(info["por_curr_a"], cur),
              info["por_curr_a"])
        check("0x53[%s] Frq 字段=10（恒定）" % tag, info["frq"] == 10.0,
              info["frq"])
        check("0x53[%s] TestTime×2（×2 因子待真机核对）" % tag,
              close(info["test_time_x2_s"], tt), info["test_time_x2_s"])
        built = SD.gal_static_frame(5.0, cur * 1000.0, tt / 2.0)
        rt = SD.decode_gal_static(built[5:-1])
        ok = (len(built) == len(raw) and close(rt["por_curr_a"], cur)
              and rt["frq"] == 10.0 and close(rt["test_time_x2_s"], tt))
        check("0x53[%s] 构造器往返等价" % tag, ok, built.hex(" "))


def test_gal_dynamic():
    for tag, init, fin, rate in (("a", -5e-4, 5e-4, 5e-5), ("b", -1e-3, 1e-3, 1e-4)):
        raw = raw_of("gal_dynamic_" + tag)
        info = SD.decode_gal_dynamic(raw[5:-1])
        check("0x55[%s] Initial→A" % tag, close(info["initial_a"], init),
              info["initial_a"])
        check("0x55[%s] 未启用 Vertex 填 Initial" % tag,
              close(info["vertex_one_a"], init) and close(info["vertex_two_a"], init),
              (info["vertex_one_a"], info["vertex_two_a"]))
        check("0x55[%s] Final→A" % tag, close(info["final_a"], fin), info["final_a"])
        check("0x55[%s] ScanRate mA/s→A/s" % tag,
              close(info["scan_rate_a_per_s"], rate, 1e-12), info["scan_rate_a_per_s"])
        check("0x55[%s] Frq=10" % tag, info["frq"] == 10.0, info["frq"])
        built = SD.gal_dynamic_frame(5.0, init * 1000.0, init * 1000.0,
                                     init * 1000.0, fin * 1000.0,
                                     rate * 1000.0, 10.0)
        rt = SD.decode_gal_dynamic(built[5:-1])
        ok = (len(built) == len(raw) and close(rt["initial_a"], init)
              and close(rt["final_a"], fin)
              and close(rt["scan_rate_a_per_s"], rate)
              and rt["frq"] == 10.0)
        check("0x55[%s] 构造器往返等价" % tag, ok,
              " ".join("%d:%02X/%02X" % (i, built[i], raw[i])
                       for i in range(min(len(built), len(raw)))
                       if built[i] != raw[i]))


def test_gal_charge():
    for tag, cur, ct in (("a", 1e-3, 30.0), ("b", 2e-3, 45.0)):
        raw = raw_of("gal_charge_" + tag)
        info = SD.decode_gal_charge(raw[5:-1])
        check("0x88[%s] 引导字段=0" % tag, info["lead_zero"] == 0.0, info["lead_zero"])
        check("0x88[%s] ChargeCur mA→A" % tag, close(info["charge_cur_a"], cur),
              info["charge_cur_a"])
        check("0x88[%s] UnChargeCur=-1mA→-1e-3A" % tag,
              close(info["uncharge_cur_a"], -1e-3), info["uncharge_cur_a"])
        check("0x88[%s] 2B 间隙=00 00" % tag, info["gap_hex"] == "00 00", info["gap_hex"])
        check("0x88[%s] ChargeTime" % tag, close(info["charge_time_s"], ct),
              info["charge_time_s"])
        check("0x88[%s] UnChargeTime=30" % tag, info["uncharge_time_s"] == 30.0,
              info["uncharge_time_s"])
        check("0x88[%s] HighE（b 轮 3.0 变参响应）" % tag,
              (info["high_e"] == 4.5) if tag == "a" else (info["high_e"] == 3.0),
              info["high_e"])
        check("0x88[%s] LowE=0.8（f32 精度）" % tag, close(info["low_e"], 0.8),
              info["low_e"])
        check("0x88[%s] RestTime=0" % tag, info["rest_time_s"] == 0.0, info["rest_time_s"])
        check("0x88[%s] marker u16=5000" % tag, info["marker_u16"] == 5000,
              info["marker_u16"])
        check("0x88[%s] 尾 f32 恒定 30（疑 UnChargeTime 重复字段）" % tag,
              info["tail_f32"] == 30.0, info["tail_f32"])
        built = SD.gal_charge_frame(cur * 1000.0, -1.0, ct, 30.0,
                                    4.5 if tag == "a" else 3.0, 0.8, 0.0)
        rt = SD.decode_gal_charge(built[5:-1])
        ok = (len(built) == len(raw) and close(rt["charge_cur_a"], cur)
              and close(rt["uncharge_cur_a"], -1e-3)
              and close(rt["charge_time_s"], ct) and rt["uncharge_time_s"] == 30.0
              and close(rt["high_e"], 4.5 if tag == "a" else 3.0)
              and rt["marker_u16"] == 5000)
        check("0x88[%s] 构造器往返等价" % tag, ok,
              " ".join("%d:%02X/%02X" % (i, built[i], raw[i])
                       for i in range(min(len(built), len(raw)))
                       if built[i] != raw[i]))


def test_distinct_cmds():
    check("四命令互不相同：0x57/0x53/0x55/0x88",
          len({SD.CMD["CSGalSquare"], SD.CMD["NoiseStop"],
               SD.CMD["CSGalDynamic"], SD.CMD["CSGalCharge"]}) == 4)


if __name__ == "__main__":
    test_gal_square()
    test_gal_static()
    test_gal_dynamic()
    test_gal_charge()
    test_distinct_cmds()
    print()
    if FAILS:
        print("FAIL %d 项：%r" % (len(FAILS), FAILS))
        sys.exit(1)
    print("全部 %d 项 PASS" % PASSED)
