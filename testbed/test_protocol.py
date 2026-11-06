# -*- coding: utf-8 -*-
"""testbed/test_protocol.py —— CS350M 协议级回归（无串口可跑，Phase 2 固化资产）。

golden 数据来源（单一真相，不内嵌重复 hex）：
  * testbed/frames_tafel.txt / frames_eis.txt / frames_step.txt 的 === RAW === 段
    （Agent C 2026-11-07 实捕，机读格式 `cmdname<TAB>LEN<TAB>hex`）
  * testbed/simdevice.py 的 REAL_FRAMES（真机日志样本）与构造器
    （potdynamic_frame / ocp_frame / potsquare_frame / eis_scan_start / eis_setup_frame）

覆盖：
  P 组  帧编解码基础：build/parse 往返、累加和、坏校验拒绝、坏 LEN 拒绝、粘包/半帧、杂字节重同步
  T 组  Tafel golden：帧表 RAW 逐帧解析 + 0x54 七字段断言 + potdynamic_frame 逐字节复刻
  E 组  EIS golden：帧表 RAW（0x45/0x40/0x41/0x70）+ 解码器字段断言 + 构造器复刻
  S 组  阶梯波 golden：帧表 RAW（0x56）+ ms 陷阱/Cycles=i32 + potsquare_frame 复刻
  O 组  OCP golden：REAL_FRAMES 单点/批量 126B/参数帧 + 数据码 0x60 断言
  R 组  SimDevice 分发回归：识别→下载→启停→NAck 全对话（离线，不碰串口）

用法：
    python testbed/test_protocol.py                 # 纯协议级，不占任何串口
    python testbed/test_protocol.py --com CNCB0     # 追加串口冒烟（GetPstType 往返，默认关闭）

安全：--com 只允许虚拟对 CNCA0/CNCB0(COM90)、CNCA1/CNCB1(COM91)；真实设备口由
simdevice.validate_port 硬拒绝。本脚本默认完全离线。
"""
from __future__ import annotations

import argparse
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import simdevice as sd  # noqa: E402  （同目录正式资产）

TESTBED = os.path.dirname(os.path.abspath(__file__))


# ================================================================ 帧表 RAW 解析

def parse_frames_file(path):
    """解析帧表 RAW 段 → [(run_label, [(cmdname, bytes), ...]), ...]。
    RAW 行格式：`cmdname<TAB>LEN<TAB>hex(空格分隔)`；RUN 标签取最近的 `== RUN: ` 行。"""
    runs = []
    label = None
    in_raw = False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("== RUN: "):
            label = line[len("== RUN: "):].strip()
            in_raw = False
            continue
        if line.startswith("--- RAW"):
            in_raw = True
            continue
        if in_raw:
            if not line.strip() or "\t" not in line:
                if line and not line.startswith(("=", "#", "-")):
                    in_raw = False
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                name, ln, hx = parts[0].strip(), parts[1].strip(), parts[2].strip()
                try:
                    blob = bytes(int(x, 16) for x in hx.split())
                except ValueError:
                    continue
                if len(blob) != int(ln):
                    raise AssertionError("%s RAW 长度不符: %s 声明 %s 实得 %d"
                                         % (os.path.basename(path), name, ln, len(blob)))
                if not runs or runs[-1][0] != label:
                    runs.append((label, []))
                runs[-1][1].append((name, blob))
    return runs


FRAMES_FILES = {
    "tafel": os.path.join(TESTBED, "frames_tafel.txt"),
    "eis": os.path.join(TESTBED, "frames_eis.txt"),
    "step": os.path.join(TESTBED, "frames_step.txt"),
}


def all_golden(cmd_name, path_key=None):
    """从帧表收集某命令名的全部 golden 帧 [(file_key, run_label, bytes)]。"""
    out = []
    for key, path in FRAMES_FILES.items():
        if path_key and key != path_key:
            continue
        for label, frames in parse_frames_file(path):
            for nm, blob in frames:
                if nm == cmd_name:
                    out.append((key, label, blob))
    return out


# ================================================================ 检查器

class Checks:
    def __init__(self):
        self.passed, self.failed = [], []

    def check(self, name, fn):
        try:
            fn()
            self.passed.append(name)
            print("  PASS  %s" % name)
        except Exception as e:
            self.failed.append((name, repr(e)))
            print("  FAIL  %s  ->  %r" % (name, e))

    @property
    def ok(self):
        return not self.failed


def eq(a, b, msg=""):
    assert a == b, "%s\n  实际: %r\n  期望: %r" % (msg, a, b)


def near(a, b, tol=1e-6, msg=""):
    assert abs(a - b) <= tol, "%s 实际 %r 期望 %r (tol %g)" % (msg, a, b)


def f32s(data):
    return [struct.unpack("<f", data[k:k + 4])[0] for k in range(0, len(data) - 3, 4)]


# ================================================================ P 组：帧编解码基础

def group_p(ck):
    def p1_roundtrip():
        for name in ("CSStart", "CSStop", "GetPstType", "GetSerialNumber", "CSApply"):
            f = sd.build(name)
            p = sd.parse(f)
            eq(p["cmd_name"], name)
            eq(p["frame"], f, name + " 往返重建")
            eq(p["length"], 6)
            eq(p["data"], b"")
    ck.check("P1 build/parse 往返（无载荷命令 5 种）", p1_roundtrip)

    def p2_checksum():
        # SUM = 前 LEN-1 字节累加和 & 0xFF；坏 SUM 必须被拒
        f = sd.build("GetPstType", bytes([8]))
        eq(f[-1], sd.checksum(f[:-1]))
        bad = bytearray(f)
        bad[-1] ^= 0xFF
        eq(sd.parse(bytes(bad)), None, "坏校验和帧解析失败")
        ps = sd.Parser()
        frames = ps.feed(bytes(bad) + sd.build("CSStart"))
        eq(len(frames), 1, "坏帧后恢复同步")
        eq(frames[0]["cmd"], 0x30)
        eq(ps.stats["bad_sum"], 1)
    ck.check("P2 累加和构造/校验/坏帧拒绝并恢复同步", p2_checksum)

    def p3_bad_len():
        ps = sd.Parser()
        frames = ps.feed(b"\x55\xAA\xFF\xFF\x30" + b"\x00" * 20 + sd.build("CSStart"))
        eq(len(frames), 1)
        eq(ps.stats["bad_len"], 1, "LEN 非法拒绝计数")
        # LEN 边界：MIN=6
        eq(sd.parse(b"\x55\xAA\x00\x05\x30\x00"), None, "LEN<6 拒绝")
    ck.check("P3 坏 LEN 帧拒绝（含 LEN<6 边界）", p3_bad_len)

    def p4_sticky_and_garbage():
        ps = sd.Parser()
        blob = (b"\x07\x00\xAB" + sd.build("CSStart") + sd.build("GetPstType")
                + sd.rx("data_e_single")[:3])
        got = ps.feed(blob)
        got += ps.feed(sd.rx("data_e_single")[3:])
        eq([f["cmd"] for f in got], [0x30, 0x14, 0x60], "杂字节+粘包+半帧跨块")
        eq(ps.stats["dropped"], 3, "前置杂字节计数")
    ck.check("P4 杂字节重同步/粘包/半帧跨块", p4_sticky_and_garbage)

    def p5_len_consistency():
        # golden 帧全部满足 LEN 自洽：LEN=整帧字节数
        samples = (["data_e_single", "data_ei", "data_batch126", "noise_start",
                    "pot_dynamic", "cs_output", "dev_setup", "pot_square56",
                    "eis_scan41", "eis_setup70", "eis_setup70_var", "eis_scan41_var",
                    "pot_square56_step1"])
        for nm in samples:
            blob = sd.rx(nm)
            declared = (blob[2] << 8) | blob[3]
            eq(declared, len(blob), nm + " LEN 自洽")
            p = sd.parse(blob)
            assert p is not None, nm + " 应能解析"
    ck.check("P5 全部 golden 样本 LEN 自洽且可解析（13 帧）", p5_len_consistency)


# ================================================================ T 组：Tafel golden

def group_t(ck):
    def t1_frames_file():
        runs = parse_frames_file(FRAMES_FILES["tafel"])
        eq(len(runs), 3, "Tafel 帧表 3 个 RUN")
        names = [nm for _l, fr in runs for nm, _b in fr]
        assert names.count("CSPotDynamic") == 3
        assert names.count("CSOutput") >= 3
        assert names.count("DevSetup") >= 3
    ck.check("T1 frames_tafel.txt RAW 段解析（3 RUN 全部帧长度自洽）", t1_frames_file)

    def t2_potdynamic_fields():
        for key, label, blob in all_golden("CSPotDynamic", "tafel"):
            p = sd.parse(blob)
            eq(p["cmd"], 0x54, label)
            eq(p["length"], 34, label + " LEN=34")
            eq(len(p["data"]), 28, label + " DATA=28B=7×f32")
            v = f32s(p["data"])
            eq(len(v), 7, label)
            near(v[0], 5.0, 1e-6, label + " 量程 5.0")
            # Frq = 参数对象 get_Frq() 原值拷贝：主捕获/中点变体=1.0(mV/s×2 GUI 规则)、
            # 默认参数对照 RUN=2.0(SampleFrq*BaseFreqRate，未被 GUI 规则改写)——
            # 无统一换算式，只断言正值有限（2026-11-07 审查修正：原断言系自比较空转）
            assert math.isfinite(v[6]) and v[6] > 0, label + " Frq 应为正有限值"
            # ScanRate V/s 在 1e-4 量级
            assert 1e-5 < abs(v[5]) < 1e-2, label + " ScanRate 合理区间"
    ck.check("T2 golden 0x54 帧结构断言（LEN/DATA/量程/速率量级）", t2_potdynamic_fields)

    def t3_primary_fields():
        # 主捕获：InitE=-0.05 FinalE=+0.05 Rate=0.5mV/s Frq=1.0 Mid 未启用=InitE
        _key, _label, blob = all_golden("CSPotDynamic", "tafel")[0]
        info = sd.decode_potdynamic(sd.parse(blob)["data"])
        near(info["init_e_ocp"], -0.05, 1e-6)
        near(info["mid1_e_ocp"], -0.05, 1e-6, "Mid1 未启用=InitE")
        near(info["mid2_e_ocp"], -0.05, 1e-6)
        near(info["final_e_ocp"], 0.05, 1e-6)
        near(info["scan_rate_v_per_s"], 0.0005, 1e-9)
        near(info["scan_rate_mv_per_s"], 0.5, 1e-6)
        near(info["frq"], 1.0, 1e-6, "Frq=对象 get_Frq() 原值")
    ck.check("T3 Tafel 主捕获字段值断言（Init/Mid/Final/Rate/Frq）", t3_primary_fields)

    def t4_mid_variant():
        # 中点变体：Mid1=+0.1 Mid2=+0.2（启用槽）
        _key, _label, blob = all_golden("CSPotDynamic", "tafel")[1]
        info = sd.decode_potdynamic(sd.parse(blob)["data"])
        near(info["mid1_e_ocp"], 0.1, 1e-6, "Mid1 启用=MidEOne")
        near(info["mid2_e_ocp"], 0.2, 1e-6, "Mid2 启用=MidETwo")
    ck.check("T4 Tafel 中点变体（Mid 槽启用差分）", t4_mid_variant)

    def t5_builder_replica():
        # potdynamic_frame 应逐字节复刻主捕获与中点变体
        primaries = all_golden("CSPotDynamic", "tafel")
        got0 = sd.potdynamic_frame(-0.05, 0.05, 0.5, 0.0)
        eq(got0, primaries[0][2], "复刻主捕获帧")
        got1 = sd.potdynamic_frame(-0.05, 0.05, 0.5, 0.0, mid1=0.1, mid2=0.2)
        eq(got1, primaries[1][2], "复刻中点变体帧")
        # 对照真机样本（00 文档 3.5，REAL_FRAMES 内嵌）：InitE=-0.2 FinalE=1 0.33mV/s
        got2 = sd.potdynamic_frame(-0.2, 1.0, 0.33, -0.104628562927246)
        eq(got2, sd.rx("pot_dynamic"), "复刻真机样本帧")
    ck.check("T5 potdynamic_frame 逐字节复刻（帧表 2 帧+真机样本）", t5_builder_replica)

    def t6_prefix_constancy():
        # 0x45 CSOutput：全部 RUN 恒定（u16BE=100+3 零）；0x40 长度恒 32
        outs = all_golden("CSOutput")
        assert len(outs) >= 6
        blobs = set(b.hex() for _k, _l, b in outs)
        eq(len(blobs), 1, "0x45 全实验恒定单形态")
        info = sd.decode_cs_output(outs[0][2][5:-1])
        eq(info["u16be"], 100)
        devs = all_golden("DevSetup")
        assert all(len(b) == 32 for _k, _l, b in devs), "0x40 恒 32B"
        variants = set(b.hex() for _k, _l, b in devs)
        assert len(variants) >= 2, "0x40 随实验 DevParam 存在差异（C 帧表结论）"
    ck.check("T6 前缀帧语义：0x45 恒定 / 0x40 恒 32B 且随实验差异", t6_prefix_constancy)


# ================================================================ E 组：EIS golden

def group_e(ck):
    def e1_frames_file():
        runs = parse_frames_file(FRAMES_FILES["eis"])
        eq(len(runs), 4, "EIS 帧表 4 个 RUN")
        names = [nm for _l, fr in runs for nm, _b in fr]
        eq(names.count("ScanStart"), 4, "0x41 每 RUN 一帧")
        eq(names.count("EisSetup?"), 3, "0x70 三次（SendEisSetup 路径只发 0x41）")
    ck.check("E1 frames_eis.txt RAW 段解析（4 RUN/0x41×4/0x70×3）", e1_frames_file)

    def e2_scan41_fields():
        for key, label, blob in all_golden("ScanStart", "eis"):
            p = sd.parse(blob)
            eq(p["cmd"], 0x41, label)
            eq(p["length"], 45, label)
            info = sd.decode_scan_start(p["data"])
            eq(len(p["data"]), 39, label + " DATA=39B")
            eq(info["const_01"], 1, label)
            eq(info["const_minus1"], -1, label)
            near(info["init_fre_hz"], 1000.0, 1e-4, label + " Init_Fre=1000")
            near(info["sine_amp_mv"], 10.0, 1e-4, label + " SineAmp=10")
        # 主捕获 vs 变体差分
        infos = [sd.decode_scan_start(sd.parse(b)["data"]) for _k, _l, b in all_golden("ScanStart", "eis")]
        eq(infos[0]["integral_time"], 1)
        eq(infos[0]["delay_time"], 500)
        eq(infos[2]["integral_time"], 77, "变体 Integral_Time=77")
        eq(infos[2]["integral_period"], 78)
        eq(infos[2]["delay_time"], 88)
        eq(infos[3]["auto_delay_flag"], 1, "IsAutoDelayTime=false 单变量差分")
    ck.check("E2 golden 0x41 字段断言（主捕获+差分变体）", e2_scan41_fields)

    def e3_setup70_fields():
        for key, label, blob in all_golden("EisSetup?", "eis"):
            p = sd.parse(blob)
            eq(p["cmd"], 0x70, label)
            eq(p["length"], 31, label)
            eq(len(p["data"]), 25, label + " DATA=25B")
            info = sd.decode_eis_setup(p["data"])
            near(info["init_fre_hz"], 1000.0, 1e-4, label)
            near(info["final_fre_hz"], 0.1, 1e-6, label + " Final_Fre=0.1")
            near(info["const_0p01"], 0.01, 1e-9, label + " 常量 0.01")
        infos = [sd.decode_eis_setup(sd.parse(b)["data"]) for _k, _l, b in all_golden("EisSetup?", "eis")]
        eq(infos[0]["speed_mode"], 0)
        eq(infos[0]["pre_pol_time"], 0)
        eq(infos[1]["sine_bias_v"], 0.25, "变体 Bias=0.25")
        eq(infos[1]["four_x_ten_twice"], 80.0, "TenTwice=20→80")
        eq(infos[1]["pre_pol_time"], 66)
        eq(infos[1]["speed_mode"], 3)
    ck.check("E3 golden 0x70 字段断言（主捕获+差分变体）", e3_setup70_fields)

    def e4_builder_replica():
        got41 = sd.eis_scan_start()
        eq(got41, all_golden("ScanStart", "eis")[0][2], "0x41 复刻主捕获")
        got41v = sd.eis_scan_start(integral_time=77, integral_period=78, delay_time=88)
        eq(got41v, sd.rx("eis_scan41_var"), "0x41 复刻 Tafel-mid 变体")
        got70 = sd.eis_setup_frame()
        eq(got70, all_golden("EisSetup?", "eis")[0][2], "0x70 复刻主捕获")
        got70v = sd.eis_setup_frame(sine_bias=0.25, ten_twice=20, pre_pol_time=66, speed_mode=3)
        eq(got70v, sd.rx("eis_setup70_var"), "0x70 复刻差分变体")
    ck.check("E4 eis_scan_start/eis_setup_frame 逐字节复刻帧表 golden", e4_builder_replica)

    def e5_eissetup_path():
        # SendEisSetup 路径对照 RUN：只发 0x41，不发 0x45/0x40/0x70（C 实测结论）
        runs = parse_frames_file(FRAMES_FILES["eis"])
        solo = [fr for _l, fr in runs if [nm for nm, _b in fr] == ["ScanStart", "CSStart", "CSStop"]]
        eq(len(solo), 1, "存在只含 0x41+启停 的 RUN（SendEisSetup 单发路径）")
    ck.check("E5 SendEisSetup 单发路径对照（只 0x41，不发 0x70）", e5_eissetup_path)


# ================================================================ S 组：阶梯波 golden

def group_s(ck):
    def s1_frames_file():
        runs = parse_frames_file(FRAMES_FILES["step"])
        eq(len(runs), 2, "Step 帧表 2 个 RUN")
        for _l, fr in runs:
            eq(fr[2][0], "0x56", "方法帧命令名 0x56")
            eq(len(fr[2][1]), 114, "LEN=114")
    ck.check("S1 frames_step.txt RAW 段解析（2 RUN/0x56 LEN=114）", s1_frames_file)

    def s2_fields():
        blobs = [b for _k, _l, b in all_golden("0x56", "step")]
        info0 = sd.decode_potsquare(sd.parse(blobs[0])["data"])
        eq(len(sd.parse(blobs[0])["data"]), 108, "DATA=108B")
        near(info0["initial_e_ocp"], 0.01, 1e-6)
        near(info0["initial_time_s"], 0.002, 1e-6, "ms 陷阱 2ms→0.002s")
        eq(info0["cycles"], 20, "Cycles i32 LE")
        near(info0["frq"], 100.0, 1e-4)
        near(info0["final_time_s"], 0.1, 1e-6, "100ms→0.1s")
        # 主捕获：全部 Step 未启用 → steps=对象当前值，times=0
        eq(info0["times_s"], [0.0] * 10, "未启用 Time_k=0")
        near(info0["steps_e_ocp"][0], -0.01, 1e-6)
        near(info0["steps_e_ocp"][9], 0.06, 1e-6)
        # Step1 变体
        info1 = sd.decode_potsquare(sd.parse(blobs[1])["data"])
        near(info1["steps_e_ocp"][0], 0.03, 1e-6, "Step1 启用=+0.03")
        near(info1["times_s"][0], 0.05, 1e-6, "Time1 50ms→0.05s")
        near(info1["steps_e_ocp"][1], 0.02, 1e-6, "其余槽不变")
    ck.check("S2 golden 0x56 字段断言（ms 陷阱/Cycles/启用差分）", s2_fields)

    def s3_builder_replica():
        blobs = [b for _k, _l, b in all_golden("0x56", "step")]
        got0 = sd.potsquare_frame(0.01, -0.01, 2.0, 100.0, 20, 100.0, ocp=0.0)
        eq(got0, blobs[0], "复刻主捕获帧")
        defaults = [-0.01, 0.02, -0.02, 0.03, -0.03, 0.04, -0.04, 0.05, -0.05, 0.06]
        got1 = sd.potsquare_frame(0.01, -0.01, 2.0, 100.0, 20, 100.0, ocp=0.0,
                                  steps=[0.03] + defaults[1:],
                                  times_ms=[50.0] + [0.0] * 9)
        eq(got1, blobs[1], "复刻 Step1 变体帧")
    ck.check("S3 potsquare_frame 逐字节复刻帧表 golden（2 帧）", s3_builder_replica)


# ================================================================ O 组：OCP golden

def group_o(ck):
    def o1_single():
        p = sd.parse(sd.rx("data_e_single"))
        eq(p["cmd"], 0x60, "真实单点电位帧命令=0x60 CSDataE")
        eq(p["length"], 10)
        near(f32s(p["data"])[0], -0.139144, 1e-4)
    ck.check("O1 真实单点电位帧（-0.139V @0x60）", o1_single)

    def o2_batch126():
        raw = sd.rx("data_batch126")
        eq(len(raw), 126)
        p = sd.parse(raw)
        eq(p["cmd"], 0x60, "真机 OCP 批量帧也是 0x60（A/B 互证）")
        eq(p["length"], 0x7E)
        eq(len(f32s(p["data"])), 30, "30 点/帧")
        # 模拟器默认模式与真机帧同构（LEN 与点数；信号值不同）
        dev = sd.SimDevice(None, verbose=False)
        f = dev.make_ocp_frame()
        eq(len(f), len(raw), "模拟器批量帧与真机帧等长")
        eq(f[4], raw[4], "数据命令码一致（0x60）")
    ck.check("O2 真机批量帧 126B=30 点@0x60 + 模拟器同构", o2_batch126)

    def o3_params():
        info = sd.decode_ocp_params(sd.parse(sd.rx("noise_start"))["data"])
        near(info["sample_hz"], 10.0)
        near(info["test_time"], 200.0)
        got = sd.ocp_frame(200.0, 10.0, 0.0)
        eq(got, sd.rx("noise_start"), "ocp_frame 复刻 sim13 实收帧")
    ck.check("O3 OCP 参数帧解码+构造器复刻（hz=10 t=200）", o3_params)

    def o4_ei_frame():
        p = sd.parse(sd.rx("data_ei"))
        eq(p["cmd"], 0x62)
        eq(len(f32s(p["data"])), 2, "(E,i) 双 float")
    ck.check("O4 真实 0x62 电位+电流帧", o4_ei_frame)


# ================================================================ R 组：分发回归（离线）

def group_r(ck):
    def r1_full_dialog():
        dev = sd.SimDevice(None, verbose=False)
        outs = []
        for nm in ("get_pst_type", "get_serial_number", "cs_output", "dev_setup",
                   "noise_start", "cs_start", "cs_stop"):
            resp, _n = dev.handle_frame(sd.rx(nm))
            outs.extend(resp)
        names = [sd.parse(r)["cmd_name"] for r in outs]
        eq(names[0], "GetPstType")
        eq(sd.parse(outs[0])["data"], bytes([8]), "Type_CS350M=8")
        eq(names[4], "NoiseStart")
        eq(names[5], "StartCellYWGet")
        eq(names[-1], "CSStop")
        s = dev.summary()
        eq(s["unknown"], 0, "全程无未知命令")
    ck.check("R1 完整对话回归：识别→方法下载→启停（零 NAck）", r1_full_dialog)

    def r2_method_frame_dialogs():
        # 四实验方法帧（golden）逐一下发：全部确认、不再 NAck
        dev = sd.SimDevice(None, verbose=False, wait_start=True)
        seq = [("pot_dynamic", 0x54), ("pot_square56", 0x56),
               ("eis_scan41", 0x41), ("eis_setup70", 0x70)]
        for nm, cmd in seq:
            resp, _n = dev.handle_frame(sd.rx(nm))
            eq(sd.parse(resp[0])["cmd"], cmd, nm + " 确认帧命令号")
        eq(dev.n_unknown, 0, "四方法帧全部识别（0x56/0x70 不再 NAck）")
        assert dev.mode == "eis", "最后一帧 0x70 决定模式"
        # 启停
        dev.handle_frame(sd.build("CSStart"))
        assert dev.streaming
        dev.handle_frame(sd.build("CSStop"))
        assert not dev.streaming and dev.mode is None
    ck.check("R2 四实验方法帧下发全识别（golden 序列离线对话）", r2_method_frame_dialogs)

    def r3_nack_unknown():
        dev = sd.SimDevice(None, verbose=False)
        resp, _n = dev.handle_frame(sd.build(0x77, b"\x01"))
        p = sd.parse(resp[0])
        eq(p["cmd"], 0xFF)
        eq(p["data"], bytes([0x77]), "NAck 载荷=原命令号")
        # 数据命令方向颠倒：忽略不应答
        resp2, _n2 = dev.handle_frame(sd.rx("data_e_single"))
        eq(resp2, [], "主机发 0x60 忽略（防回环）")
    ck.check("R3 NAck 约定+数据命令防回环", r3_nack_unknown)

    def r4_stream_frames():
        # 数据流生成：批量 0x60 形状 + 0x62 (E,i) 形状
        dev = sd.SimDevice(None, verbose=False, points_per_frame=30)
        f = dev.make_ocp_frame()
        eq(len(f), 126)
        eq(f[4], 0x60)
        dev2 = sd.SimDevice(None, verbose=False)
        dev2.handle_frame(sd.rx("pot_dynamic"))
        g = dev2.make_ei_frame(0.5)
        eq(g[4], 0x62)
        eq(len(f32s(sd.parse(g)["data"])), 2)
    ck.check("R4 数据流生成形状（0x60 批量/0x62 单点）", r4_stream_frames)


# ================================================================ 可选串口冒烟

def com_smoke(port):
    """GetPstType 往返冒烟：期待 55 AA 00 07 14 08 22（simdevice live 或真机同响应）。"""
    import serial
    port = sd.validate_port(port)
    print("-" * 72)
    print("串口冒烟：%s @115200（GetPstType 往返）" % port)
    ok = False
    try:
        ser = serial.Serial(sd.win_port(port), 115200, timeout=0.2)
        ser.reset_input_buffer()
        ser.write(sd.build("GetPstType"))
        ser.flush()
        ps = sd.Parser()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            data = ser.read(64)
            if data:
                for p in ps.feed(data):
                    print("  <- %s %s" % (p["cmd_name"], p["frame"].hex(" ").upper()))
                    if p["cmd"] == 0x14 and p["data"] == bytes([8]):
                        ok = True
            if ok:
                break
        ser.close()
    except Exception as e:
        print("  串口异常: %r" % (e,))
    print("  %s  %s GetPstType 往返" % ("PASS" if ok else "FAIL", port))
    return ok


# ================================================================ main

def main():
    ap = argparse.ArgumentParser(description="CS350M 协议级回归（无串口可跑）")
    ap.add_argument("--com", default=None,
                    help="可选串口冒烟（如 CNCB0 / COM90；默认关闭不占口）")
    args = ap.parse_args()

    print("=" * 72)
    print("test_protocol.py 协议级回归（golden=frames_*.txt + simdevice 构造器/真机样本）")
    print("=" * 72)
    ck = Checks()
    for group in (group_p, group_t, group_e, group_s, group_o, group_r):
        group(ck)

    com_ok = True
    if args.com:
        com_ok = com_smoke(args.com)

    total = len(ck.passed) + len(ck.failed)
    print("-" * 72)
    print("协议回归: %d/%d 通过%s" % (len(ck.passed), total,
                                      ("；串口冒烟 %s" % ("OK" if com_ok else "FAIL")) if args.com else ""))
    if ck.failed:
        print("失败项:")
        for name, err in ck.failed:
            print("  - %s: %s" % (name, err))
    ok = ck.ok and com_ok
    if ok:
        print("全部通过 ✔")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
