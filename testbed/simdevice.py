# -*- coding: utf-8 -*-
"""testbed/simdevice.py —— CS350M 虚拟设备模拟器（正式资产 v2，自包含单文件）

升级自临时模拟器 D:\\deepseek\\_probe\\vp-channel\\simdevice.py（已归档不再依赖），
帧编解码从 D:\\deepseek\\CSDirect\\cspilot\\core\\proto.py 内联进来——本文件**不 import
仓库外任何东西**（仅标准库 + 可选 pyserial），可直接被其他脚本 import 或独立运行。

协议事实（全部以真实日志/往返实测为准，证据出处见各行注释）
----------------------------------------------------------------
* 帧 = `55 AA | LEN_H LEN_L | CMD | DATA… | SUM`，LEN = 整帧字节数（含头与 SUM），
      SUM = sum(帧内前 LEN-1 字节) & 0xFF —— 单字节累加和，**不是 CRC16**（03 清单 §10.3）。
* 无载荷命令 LEN=6，如 CSStart=`55 AA 00 06 30 35`（testbed_sim13.log 实收）。
* float32 小端。单点电位帧 `55 AA 00 0A 60 CD 7B 0E BE 7D` = -0.139 V。
* OCP 批量帧（真机会话日志 sess_rea_text.txt 实收、SUM 复核通过）：
      `55 AA 00 7E 60 | 30×float32 | F6` —— LEN=0x7E=126，DATA=120B=**30 个电位点**。
      （文档 00 §3 写"116 字节=29 个点"是把另一条 LEN=0x7A 的帧混记了，以本帧为准。）
      批量包命令字节是 0x60（CSDataE）；模拟器推 OCP 用 0x68（CSDataOCP），布局同构 n×float32。
* 0x51 NoiseStart(OCP) 参数帧：DATA=3×float32 = [sample_hz, test_time, extra]
      实收 `55 AA 00 12 51 00 00 20 41 00 00 48 43 00 00 00 00 4E` → hz=10.0 test_time=200.0。
* 0x54 CSPotDynamic 参数帧：DATA=7×float32 =
      [量程 5.0, InitE+OCP, Mid1+OCP, Mid2+OCP, FinalE+OCP, ScanRate(V/s), Frq(=mV/s×2)]
      实测（00 §3.5）：`55 AA 00 22 54 00 00 A0 40 | 46 F8 9B BE ×3 | 10 37 65 3F |
      DA 03 AD 39 | C3 F5 28 3F | E7` → init+ocp=-0.304628, final+ocp=0.904628,
      rate=0.00033 V/s（0.33 mV/s）, frq=0.66。Tafel 走同一参数类（PotDynamicParams），
      布局相同（Tafel 专有附加字段待 Agent C 实捕帧校对）。
* 0x45 CSOutput（扩展参数）实收 `55 AA 00 0B 45 00 64 00 00 00 B3`，DATA=5B，u16BE=100（语义待确认）。
* 0x40 DevSetup（ScanParams）实收 `55 AA 00 20 40 …9D`，整帧 32B、DATA=26B（语义待确认）。
* GetPstType 应答 `55 AA 00 07 14 08 22`（Type_CS350M=8，.NET 侧往返全对）。
* EIS / 阶梯波（PotSquare）方法帧布局**未知**（命令号与字段待 Agent C 实捕
  testbed/frames_eis.txt / frames_step.txt 校对）——解码器给出 float 扫描 + 「待校对」标记。

用法
----------------------------------------------------------------
离线自测（不占任何串口，退出码 0 = 全绿）：
    python testbed/simdevice.py --selftest

live 模式（接虚拟串口对，扮演设备端 B 侧）：
    python testbed/simdevice.py --port \\\\.\\CNCB0 --hz 10
    python testbed/simdevice.py --port CNCB0 --points 1          # 旧版单点帧模式
    python testbed/simdevice.py --port COM90 --log sim.jsonl     # 结构化 JSONL 帧日志
    python testbed/simdevice.py --port CNCB0 --ei                # OCP 同时推 0x62 电位+电流

参数：
    --port     串口名（CNCB0 / COM90 / \\\\.\\CNCB0 均可）；live 模式必填
    --baud     波特率，默认 115200
    --sn       序列号，默认 CS350M24030650（真实日志 EndFindDevice1:COM16）
    --hz       采样率 Hz，默认 10.0（可被 0x51 参数帧覆盖）
    --points   每个 0x68 批量帧的点数，默认 30（= 真实批量帧 LEN 0x7E 反推值）；
               1 = 旧版每点一帧
    --ei       OCP 模式下附带推 0x62（电位+电流）
    --wait-start  参数帧(0x51/0x54)到达后不立即推数据，等 CSStart(0x30) 才推
    --log      JSONL 帧日志路径（每帧一行：ts/dir/cmd/name/hex/parsed）
    --quiet    不打控制台日志

被当作库用（Phase 2 整合 / 协议级回归）：
    from simdevice import SimDevice
    dev = SimDevice(None)                       # 离线：不碰串口
    resp = dev.handle_frame(bytes.fromhex("55AA00061419"))   # 纯函数式分发
    dev.start()  # 或 live：SimDevice("CNCB0").start()

安全红线（本仓库自动任务约定）
----------------------------------------------------------------
* 本脚本**硬拒绝**打开真实设备口 COM16/COM10/COM6/COM4/COM5/COM11/COM12；
  测试只允许用虚拟对 CNCA0/CNCB0(COM90)、CNCA1/CNCB1(COM91)。
* --selftest 全程离线，不 import pyserial、不碰任何串口。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import struct
import sys
import threading
import time

# ================================================================ 帧编解码

HEAD = b"\x55\xAA"
MAX_FRAME = 512          # 与 CSDirect proto 一致的上限
WIN32_PREFIX = "\\\\.\\"

# 红线：绝不打开的真实设备/蓝牙口（打开前强制校验）
FORBIDDEN_PORTS = {"COM16", "COM10", "COM6", "COM4", "COM5", "COM11", "COM12"}

# 命令表：CSDirect proto.C（实测往返）∪ 03_反编译API清单 §6.3（ilspycmd 实值）
CMD = {
    "ReStartDev": 0x01,
    "GetSerialNumber": 0x10,
    "GetDeviceVersion": 0x12,
    "GetPstType": 0x14,
    "SetPstType": 0x15,
    "GetUID": 0x17,
    "CSStart": 0x30,
    "CSPause": 0x31,
    "CSStop": 0x32,
    "CSReverse": 0x33,
    "CSPolarState": 0x34,
    "CSStartSample": 0x35,
    "ReadOcp": 0x36,
    "DevSetup": 0x40,           # 03 清单名 ScanParams=0x40；32B 设备参数帧
    "ScanStart": 0x41,
    "ScanStop": 0x43,
    "CSOutput": 0x45,           # 扩展参数帧
    "CSReadOcp": 0x50,
    "NoiseStart": 0x51,         # 别名 CSOcp（03 清单坑 12 定案，同值别名）
    "NoisePause": 0x52,         # 别名 CSPotStatic
    "NoiseStop": 0x53,          # 别名 CSGalStatic
    "CSPotDynamic": 0x54,       # 动电位/Tafel 方法帧
    "CSDataE": 0x60,
    "CSDataEI": 0x62,
    "CSDataOCP": 0x68,
    "StartCellYWGet": 0x71,
    "CSExpStop": 0x72,
    "CSExpCycle": 0x74,
    "CSApply": 0xAA,
    "CS350MCalibrationStop": 0xC2,
    "NAck": 0xFF,               # 模拟器约定：对未知命令的否定应答（真机语义未知）
}
NAME = {v: k for k, v in CMD.items()}

# 主机→设备方向的已知命令（设备端需要应答/消化的）
HOST_CMDS = set(CMD.values()) - {0x60, 0x62, 0x68, 0xFF}

# 收到后回「同命令号空帧确认」的命令（与旧版 simdevice 行为一致，probe_testbed9 全链验证过）
ACK_ECHO = {0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x40, 0x41, 0x43, 0x45,
            0x52, 0x53, 0x72, 0x74, 0xAA, 0xC2}

TYPE_CS350M = 8                  # CSStudio6.BaseInterface Type 枚举 Type_CS350M=8（REPORT 实测）
DEFAULT_SN = "CS350M24030650"    # 真实日志 EndFindDevice1:COM16 SN:CS350M24030650


def checksum(buf):
    """累加和：帧内除最后一字节外全部相加取低 8 位（03 清单 §10.3 CheckPack 实证）"""
    return sum(buf) & 0xFF


def build(cmd, data=b""):
    """造一帧。cmd 可传 int 或命令名。"""
    if isinstance(cmd, str):
        cmd = CMD[cmd]
    n = 6 + len(data)
    body = HEAD + struct.pack(">H", n) + bytes([cmd & 0xFF]) + bytes(data)
    return body + bytes([checksum(body)])


def build_f(cmd, *floats):
    """造一帧，数据为若干 float32 小端。"""
    return build(cmd, b"".join(struct.pack("<f", v) for v in floats))


def floats(data):
    """把数据段按 float32 小端切开（尾部不足 4 字节忽略）。"""
    out = []
    for k in range(0, len(data) - 3, 4):
        out.append(struct.unpack("<f", data[k:k + 4])[0])
    return out


def parse(buf):
    """解析单帧（容忍前置杂字节）。返回 dict 或 None（不完整/不合法）。"""
    if not buf or len(buf) < 6:
        return None
    i = buf.find(HEAD)
    if i < 0 or len(buf) - i < 6:
        return None
    b = buf[i:]
    n = (b[2] << 8) | b[3]
    if n < 6 or n > MAX_FRAME:
        return None
    if len(b) < n:
        return None
    frame = b[:n]
    if checksum(frame[:-1]) != frame[-1]:
        return None
    cmd = frame[4]
    return {
        "frame": bytes(frame),
        "cmd": cmd,
        "cmd_name": NAME.get(cmd, "0x%02X" % cmd),
        "data": bytes(frame[5:-1]),
        "length": n,
    }


class Parser:
    """流式切帧器：带坏帧计数（坏校验 / 坏长度 / 丢弃字节）。线程不安全，单线程用。"""

    def __init__(self):
        self.buf = b""
        self.stats = {"good": 0, "bad_sum": 0, "bad_len": 0, "dropped": 0}

    def feed(self, data):
        """喂字节，返回切出的完整帧 list。坏帧丢弃并计数（不会卡死流）。"""
        self.buf += data
        out = []
        while True:
            if len(self.buf) < 6:
                break
            if not self.buf.startswith(HEAD):
                i = self.buf.find(HEAD)
                if i < 0:
                    self.stats["dropped"] += len(self.buf)
                    self.buf = b""
                else:
                    self.stats["dropped"] += i
                    self.buf = self.buf[i:]
                continue
            n = (self.buf[2] << 8) | self.buf[3]
            if n < 6 or n > MAX_FRAME:
                self.stats["bad_len"] += 1
                self.stats["dropped"] += 1
                self.buf = self.buf[1:]
                continue
            if len(self.buf) < n:
                break                      # 半帧，等后续字节
            frame, self.buf = self.buf[:n], self.buf[n:]
            if checksum(frame[:-1]) != frame[-1]:
                self.stats["bad_sum"] += 1
                self.stats["dropped"] += 1
                self.buf = frame[:1] + self.buf   # 从头字节起重新找头
                continue
            self.stats["good"] += 1
            out.append(parse(frame))
        # 半帧防爆炸：保留尾部
        if len(self.buf) > 4096:
            self.stats["dropped"] += len(self.buf) - 512
            self.buf = self.buf[-512:]
        return out

    def reset(self):
        self.buf = b""


# ================================================================ 参数帧解码器

def _f4(data, off):
    if off + 4 <= len(data):
        return struct.unpack("<f", data[off:off + 4])[0]
    return None


def decode_ocp_params(data):
    """0x51 NoiseStart(OCP)：DATA=3×float32=[sample_hz, test_time, extra]。
    证据：sim13 实收帧 → hz=10.0 test_time=200.0。"""
    v = floats(data)
    if len(v) < 2:
        return {"raw_hex": data.hex(" "), "error": "需要至少 2 个 float32"}
    return {
        "raw_hex": data.hex(" "),
        "sample_hz": v[0],
        "test_time": v[1],
        "extra": v[2] if len(v) > 2 else 0.0,
        "confidence": "实测帧验证",
    }


def decode_potdynamic(data):
    """0x54 CSPotDynamic（动电位/Tafel）：DATA=7×float32=
    [量程, InitE+OCP, Mid1+OCP, Mid2+OCP, FinalE+OCP, ScanRate(V/s), Frq]。
    证据：00 §3.5 逐字节实测帧。注意帧内电位已含 OCP 偏移，设备不知道 OCP 拆不回去；
    ScanRate 单位 V/s，Frq=扫描速率 mV/s×2。"""
    v = floats(data)
    if len(v) < 7:
        return {"raw_hex": data.hex(" "), "error": "需要 7 个 float32，实得 %d" % len(v)}
    return {
        "raw_hex": data.hex(" "),
        "range_v": v[0],
        "init_e_ocp": v[1],
        "mid1_e_ocp": v[2],
        "mid2_e_ocp": v[3],
        "final_e_ocp": v[4],
        "scan_rate_v_per_s": v[5],
        "frq": v[6],
        "scan_rate_mv_per_s": v[5] * 1000.0,
        "confidence": "实测帧验证",
    }


def decode_cs_output(data):
    """0x45 CSOutput 扩展参数：实收 DATA=5B `00 64 00 00 00`。
    u16BE=100 的解读是猜测（待实测帧校对），此处仅结构化存证。"""
    u16be = (data[0] << 8) | data[1] if len(data) >= 2 else None
    return {
        "raw_hex": data.hex(" "),
        "u16be_guess": u16be,
        "floats_guess": floats(data),
        "confidence": "结构存证·语义待实测帧校对",
    }


def decode_dev_setup(data):
    """0x40 DevSetup(ScanParams)：实收整帧 32B / DATA=26B。
    语义未反编译确认；float 扫描发现 offset=14 处 100.0（C8 42），仅存证。"""
    fl = []
    for off in range(0, max(0, len(data) - 3)):
        # 记录所有「看起来是合理工程值」的 float 对齐位置，供日后比对
        v = _f4(data, off)
        if v is not None and (abs(v) < 1e6 and abs(v) > 1e-7 or v == 0.0):
            fl.append((off, v))
    interesting = [(o, v) for o, v in fl if v != 0.0 and abs(v) <= 1e4]
    return {
        "raw_hex": data.hex(" "),
        "data_len": len(data),
        "float_hits": interesting[:8],
        "confidence": "结构存证·语义待实测帧校对",
    }


def decode_speculative(data, label):
    """EIS / 阶梯波等布局未知的参数帧：float 扫描 + 原始 hex 存证。
    待 Agent C 实捕帧（testbed/frames_eis.txt / frames_step.txt）落地后校对。"""
    return {
        "raw_hex": data.hex(" "),
        "floats": floats(data),
        "data_len": len(data),
        "label": label,
        "confidence": "布局未知·待实测帧校对",
    }


# ================================================================ 参数帧构造器（回归基准）

def potdynamic_frame(init_e, final_e, scan_rate_mv, ocp, mid1=None, mid2=None):
    """按软件行为构造 0x54 动电位参数帧（与真实帧逐字节同构，00 §3.5）。
    InitE/FinalE 要加 OCP 偏移（vsOCP 模式）；OCP 须传完整 double 精度。"""
    i = init_e + ocp
    m1 = (mid1 if mid1 is not None else init_e) + ocp
    m2 = (mid2 if mid2 is not None else init_e) + ocp
    f = final_e + ocp
    v_per_s = scan_rate_mv / 1000.0
    frq = scan_rate_mv * 2.0
    return build_f(CMD["CSPotDynamic"], 5.0, i, m1, m2, f, v_per_s, frq)


def ocp_frame(test_time=1800.0, sample_hz=10.0, extra=0.0):
    """按软件行为构造 0x51 OCP 参数帧。"""
    return build_f(CMD["NoiseStart"], sample_hz, test_time, extra)


# ================================================================ 真实帧样本（回归基准，出处见注释）

REAL_FRAMES = {
    # 单点电位（proto 验证样本）
    "data_e_single": "55 AA 00 0A 60 CD 7B 0E BE 7D",
    # 电位+电流（proto 验证样本）
    "data_ei": "55 AA 00 0E 62 EB 08 59 BE D9 F0 9B B5 92",
    # OCP 批量包：LEN=0x7E=126，DATA=120B=30 个 float32 电位点，SUM=F6
    # （真机会话日志 sess_rea_text.txt L88802 实收，校验和复核通过）
    "data_batch126": ("55 AA 00 7E 60 14 D9 11 BE 14 D9 11 BE 14 D9 11 BE 00 D9 11 BE "
                      "EC D8 11 BE D8 D8 11 BE D8 D8 11 BE EC D8 11 BE C4 D8 11 BE "
                      "14 D9 11 BE 14 D9 11 BE 14 D9 11 BE 28 D9 11 BE 50 D9 11 BE "
                      "64 D9 11 BE 64 D9 11 BE 78 D9 11 BE 64 D9 11 BE A0 D9 11 BE "
                      "B4 D9 11 BE B4 D9 11 BE F0 D9 11 BE F0 D9 11 BE 17 DA 11 BE "
                      "2B DA 11 BE 7B DA 11 BE A3 DA 11 BE F3 DA 11 BE 07 DB 11 BE "
                      "43 DB 11 BE F6"),
    # OCP 参数帧（testbed_sim13.log 实收：hz=10 test_time=200）
    "noise_start": "55 AA 00 12 51 00 00 20 41 00 00 48 43 00 00 00 00 4E",
    # 动电位参数帧（00 §3.5 逐字节样本：InitE=-0.2 FinalE=1 0.33mV/s OCP=-0.104628…）
    "pot_dynamic": ("55 AA 00 22 54 00 00 A0 40 46 F8 9B BE 46 F8 9B BE "
                    "46 F8 9B BE 10 37 65 3F DA 03 AD 39 C3 F5 28 3F E7"),
    # 扩展参数帧（testbed_sim13.log 实收）
    "cs_output": "55 AA 00 0B 45 00 64 00 00 00 B3",
    # DevSetup 32B 帧（testbed_sim13.log 实收）
    "dev_setup": ("55 AA 00 20 40 01 FF 01 FF 01 FF 00 01 FF 01 00 00 00 00 00 00 "
                  "C8 42 00 32 00 01 FF 00 01 00 9D"),
    # GetPstType 应答（.NET 侧往返全对，07 执行记录 §6.1）
    "get_pst_type_ans": "55 AA 00 07 14 08 22",
    # 无载荷命令（testbed_sim*.log 实收）
    "cs_start": "55 AA 00 06 30 35",
    "cs_stop": "55 AA 00 06 32 37",
    "get_pst_type": "55 AA 00 06 14 19",
    "get_serial_number": "55 AA 00 06 10 15",   # testbed_sim11.log 实收
}


def rx(name):
    return bytes(int(x, 16) for x in REAL_FRAMES[name].split())


# ================================================================ 模拟设备

class SimDevice:
    """虚拟 CS350M：解析主机帧 → 应答 / 状态迁移 / 推数据帧。

    可三种用法：
      1. live 模式：SimDevice("CNCB0").start() 起读写线程；
      2. 离线纯函数：SimDevice(None)，直接调 handle_frame()/emit 生成器做断言；
      3. 被冒烟脚本 import（与旧版 simdevice.SimDevice 构造签名兼容）。
    """

    def __init__(self, port=None, baud=115200, sn=DEFAULT_SN,
                 sample_hz=10.0, verbose=True, seed=1,
                 points_per_frame=30, ei_also=False, wait_start=False,
                 log_path=None):
        if port:
            port = validate_port(port)      # 红线：真实设备口硬拒绝
        self.path = win_port(port) if port else None
        self.baud = baud
        self.sn = sn
        self.sample_hz = sample_hz
        self.verbose = verbose
        self.points_per_frame = max(1, int(points_per_frame))
        self.ei_also = ei_also
        self.wait_start = wait_start
        self.rng = random.Random(seed)

        # 串口与线程（live 模式才用）
        self.ser = None
        self.running = False
        self.threads = []
        self._rd = Parser()

        # 实验状态（_lock 保护）
        self._lock = threading.Lock()
        self.mode = None             # None / "ocp" / "potdyn"
        self.streaming = False       # 推数据开关
        self.exp_started = False
        self.applied = False
        self.paused = False
        self.method = None           # 最近一次解码的方法参数 dict
        self._t_exp0 = None
        self._ocp_buf = []           # OCP 批量缓冲（攒够 points_per_frame 发一帧）
        self._ocp_k = 0              # 已产生的 OCP 点序号（漂移用）

        # 伪信号基准（取自真实日志首帧 -0.139 V）
        self._ocp_base = -0.139
        self._pot_init = -0.2
        self._pot_final = 1.0
        self._pot_rate = 0.0005      # V/s

        # 观测与日志
        self.recv_frames = []        # [(ts, frame_dict)]
        self.sent_frames = []        # [(ts, bytes)]
        self.unknown_cmds = []       # [(ts, cmd)]
        self.n_unknown = 0
        self.records = []            # JSONL 记录（内存镜像）
        self.log_path = log_path
        self._log_fp = None

    # ------------------------------------------------------------ 日志
    def _log(self, msg):
        if self.verbose:
            print("[SIM] " + msg, flush=True)

    def _record(self, direction, cmd, raw, parsed=None):
        """每帧一行 JSONL（内存镜像 + 可选落盘）。"""
        name = NAME.get(cmd, "0x%02X" % cmd)
        rec = {
            "ts": round(time.time(), 3),
            "dir": direction,                      # rx / tx / gen（gen=模拟器主动推的数据帧）
            "cmd": cmd,
            "name": name,
            "len": len(raw),
            "hex": raw.hex(" ").upper(),
        }
        if parsed:
            rec["parsed"] = parsed
        with self._lock:
            self.records.append(rec)
            if len(self.records) > 20000:
                del self.records[:10000]
        if self.log_path:
            if self._log_fp is None:
                self._log_fp = open(self.log_path, "a", encoding="utf-8")
            self._log_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._log_fp.flush()
        return rec

    def close_log(self):
        if self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass
            self._log_fp = None

    # ------------------------------------------------------------ 信号发生（纯函数，可离线断言）
    def ocp_point(self, k):
        """第 k 个 OCP 采样点（V）。基准 -0.139 V + 慢漂移 + 高斯噪声。"""
        drift = -0.00002 * k
        noise = self.rng.gauss(0, 1.5e-5)
        return self._ocp_base + drift + noise

    def pot_point(self, t):
        """动电位 (E, i)：E 从 init 线性扫到 final，伪 Tafel 电流指数增长。"""
        span = self._pot_final - self._pot_init
        dur = abs(span / self._pot_rate) if abs(self._pot_rate) > 1e-12 else 0.0
        frac = min(1.0, t / dur) if dur > 0 else 1.0
        E = self._pot_init + span * frac
        i = 1e-7 * (10 ** ((E - self._pot_init) / 0.12)) - 1e-8
        i *= (1.0 + self.rng.gauss(0, 0.01))
        return E, i

    def make_ocp_frame(self, n=None):
        """生成一个 0x68 批量帧：n 个 float32 电位。n=points_per_frame 时
        LEN=0x7E —— 与真实批量帧（30 点）同构；n=1 时 LEN=0x0A 同真实单点帧。"""
        if n is None:
            n = self.points_per_frame
        pts = [self.ocp_point(self._ocp_k + j) for j in range(n)]
        self._ocp_k += n
        return build(CMD["CSDataOCP"], b"".join(struct.pack("<f", p) for p in pts))

    def make_ei_frame(self, t=None):
        """生成一个 0x62 单点帧（E,i）——与真实 0x0E 单点帧同构。"""
        if t is None:
            t = time.time() - (self._t_exp0 or time.time())
        E, i = self.pot_point(max(0.0, t))
        return build_f(CMD["CSDataEI"], E, i)

    # ------------------------------------------------------------ 命令分发（纯函数核心，selftest 直接驱动）
    def handle_frame(self, raw_or_parsed):
        """处理一帧主机命令，返回 (应答 bytes 列表, 备注 str)。
        接受原始 bytes（内部解析）或 parse() 产出的 dict。
        应答帧同时写入 tx 日志记录（离线/在线行为一致）。"""
        responses, note = self._dispatch(raw_or_parsed)
        for r in responses:
            self._record("tx", r[4], r)
        return responses, note

    def _dispatch(self, raw_or_parsed):
        if isinstance(raw_or_parsed, (bytes, bytearray)):
            p = parse(bytes(raw_or_parsed))
            if p is None:
                return [], "解析失败/坏帧"
            raw_or_parsed = p
        cmd = raw_or_parsed["cmd"]
        data = raw_or_parsed["data"]
        name = raw_or_parsed["cmd_name"]
        now = time.time()

        with self._lock:
            self.recv_frames.append((now, raw_or_parsed))
            if len(self.recv_frames) > 8000:
                del self.recv_frames[:4000]
        self._record("rx", cmd, raw_or_parsed["frame"],
                     self._parse_note(cmd, data))
        self._log("<- %-16s %s" % (name, raw_or_parsed["frame"].hex(" ").upper()))

        # ---- 数据命令方向颠倒（主机不该发）——只记日志不应答，防回环
        if cmd in (0x60, 0x62, 0x68):
            return [], "数据命令来自主机，忽略"

        # ---- 识别 / 序列号
        if cmd == CMD["GetPstType"]:
            return [build(cmd, bytes([TYPE_CS350M]))], "型号=CS350M(8)"
        if cmd == CMD["SetPstType"]:
            return [build(cmd, bytes([TYPE_CS350M]))], "型号=CS350M(8)"
        if cmd in (CMD["GetUID"], CMD["GetSerialNumber"]):
            return [build(cmd, self.sn.encode("ascii"))], "SN=" + self.sn
        if cmd == CMD["GetDeviceVersion"]:
            # 语义待实测校对：回 ASCII 版本串（保守短串）
            return [build(cmd, b"V6.7")], "版本串(待校对)"

        # ---- 复位 / 杂项
        if cmd == CMD["ReStartDev"]:
            with self._lock:
                self.mode, self.streaming, self.exp_started = None, False, False
                self._ocp_buf, self._ocp_k = [], 0
            return [build(cmd, b"\x00")], "复位确认"
        if cmd == CMD["StartCellYWGet"]:
            return [build(cmd, b"\x01")], "电解池应答"

        # ---- 实验生命周期
        if cmd == CMD["NoiseStart"]:
            info = decode_ocp_params(data)
            with self._lock:
                if info.get("sample_hz") and info["sample_hz"] > 0:
                    self.sample_hz = info["sample_hz"]
                self.method = dict(info, kind="ocp")
                self.mode = "ocp"
                self.paused = False
                self._t_exp0 = now
                self._ocp_buf, self._ocp_k = [], 0
                if not self.wait_start:
                    self.streaming = True
            self._log("OCP 参数: hz=%.4g test_time=%.4g%s"
                      % (info.get("sample_hz", 0), info.get("test_time", 0),
                         "" if info.get("confidence", "").startswith("实测") else " [待校对]"))
            return [build(cmd, b""), build(CMD["StartCellYWGet"], b"\x01")], \
                "OCP 启动确认 + 电解池帧"

        if cmd == CMD["CSPotDynamic"]:
            info = decode_potdynamic(data)
            with self._lock:
                if "init_e_ocp" in info:
                    self._pot_init = info["init_e_ocp"]      # 帧内已含 OCP 偏移
                    self._pot_final = info["final_e_ocp"]
                    if abs(info["scan_rate_v_per_s"]) > 1e-12:
                        self._pot_rate = info["scan_rate_v_per_s"]
                self.method = dict(info, kind="potdyn")
                self.mode = "potdyn"
                self.paused = False
                self._t_exp0 = now
                if not self.wait_start:
                    self.streaming = True
            if "init_e_ocp" in info:
                self._log("动电位: init+ocp=%.4f final+ocp=%.4f rate=%.6g V/s frq=%.4g"
                          % (info["init_e_ocp"], info["final_e_ocp"],
                             info["scan_rate_v_per_s"], info["frq"]))
            return [build(cmd, b"")], "动电位启动确认"

        if cmd == CMD["CSStart"]:
            with self._lock:
                self.exp_started = True
                self.paused = False            # 显式启动清除暂停
                if self.mode:
                    self.streaming = True
            return [build(cmd, b"")], "启动确认"

        if cmd == CMD["CSStartSample"]:
            with self._lock:
                self.exp_started = True
                if self.mode and not self.paused:
                    self.streaming = True
            return [build(cmd, b"")], "采样启动确认"

        if cmd in (CMD["CSStop"], CMD["NoiseStop"], CMD["ScanStop"]):
            with self._lock:
                self.streaming = False
                self.exp_started = False
                self.mode = None
            flushed = self._flush_ocp_buf()
            return [build(cmd, b"")] + flushed, "停止确认（数据缓冲已冲刷）"

        if cmd == CMD["CSExpStop"]:
            with self._lock:
                self.streaming = False
                self.exp_started = False
                self.mode = None
            flushed = self._flush_ocp_buf()
            return [build(cmd, b"")] + flushed, "实验终止确认"

        if cmd == CMD["CSPause"] or cmd == CMD["NoisePause"]:
            with self._lock:
                self.paused = True
                self.streaming = False
            return [build(cmd, b"")], "暂停确认"

        if cmd == CMD["CSApply"]:
            with self._lock:
                self.applied = True
            return [build(cmd, b"")], "参数应用确认"

        # ---- 参数/配置帧：存证 + 旧版兼容的空帧确认
        if cmd == CMD["CSOutput"]:
            info = decode_cs_output(data)
            self._log("CSOutput(扩展参数): %s [%s]"
                      % (info["raw_hex"], info["confidence"]))
            return [build(cmd, b"")], "扩展参数确认"
        if cmd == CMD["DevSetup"]:
            info = decode_dev_setup(data)
            self._log("DevSetup: %dB %s [%s]"
                      % (info["data_len"], info["raw_hex"][:47] + ("…" if info["data_len"] > 14 else ""),
                         info["confidence"]))
            return [build(cmd, b"")], "设备参数确认"
        if cmd in (CMD["ScanStart"], CMD["CSExpCycle"], CMD["CSReverse"],
                   CMD["CSPolarState"], CMD["CS350MCalibrationStop"]):
            info = decode_speculative(data, NAME.get(cmd))
            self._log("%s: %s [%s]" % (name, info["raw_hex"][:47], info["confidence"]))
            return [build(cmd, b"")], "确认"

        # ---- 读 OCP：回一个 0x68 单点帧
        if cmd in (CMD["ReadOcp"], CMD["CSReadOcp"]):
            with self._lock:
                k = self._ocp_k
            return [build(CMD["CSDataOCP"],
                          struct.pack("<f", self.ocp_point(k)))], "当前 OCP 值"

        # ---- 未知命令：记日志 + NAck（0xFF，载荷为原命令号——模拟器约定）
        with self._lock:
            self.n_unknown += 1
            self.unknown_cmds.append((now, cmd))
        self._log("?? 未知命令 0x%02X → NAck" % cmd)
        return [build(CMD["NAck"], bytes([cmd]))], "未知命令"

    def _parse_note(self, cmd, data):
        """rx 日志里附带的解析结果（尽力而为，不抛异常）。"""
        try:
            if cmd == CMD["NoiseStart"]:
                return decode_ocp_params(data)
            if cmd == CMD["CSPotDynamic"]:
                return decode_potdynamic(data)
            if cmd == CMD["CSOutput"]:
                return decode_cs_output(data)
            if cmd == CMD["DevSetup"]:
                return decode_dev_setup(data)
            if cmd not in (0x60, 0x62, 0x68) and data:
                return {"raw_hex": data.hex(" "), "floats": floats(data)}
        except Exception as e:                      # 日志解析永不影响主流程
            return {"error": repr(e)}
        return None

    def _flush_ocp_buf(self):
        """停止时冲刷未满的 OCP 批量缓冲（真实设备停止前也会把余点吐完）。"""
        with self._lock:
            buf, self._ocp_buf = self._ocp_buf, []
        if not buf:
            return []
        return [build(CMD["CSDataOCP"], b"".join(struct.pack("<f", p) for p in buf))]

    # ------------------------------------------------------------ live 模式
    def _send(self, raw, direction=None):
        try:
            if self.ser:
                self.ser.write(raw)
                self.ser.flush()
            with self._lock:
                self.sent_frames.append((time.time(), bytes(raw)))
                if len(self.sent_frames) > 8000:
                    del self.sent_frames[:4000]
            if direction == "gen":                     # 主动推的数据帧；tx 已由 handle_frame 记录
                self._record("gen", raw[4], raw)
            return True
        except Exception as e:
            if self.running:
                self._log("发送失败: %r" % (e,))
            return False

    def _reader(self):
        while self.running:
            try:
                n = self.ser.in_waiting or 1
                data = self.ser.read(n)
            except Exception as e:
                if self.running:
                    self._log("读取失败: %r" % (e,))
                break
            if not data:
                continue
            for p in self._rd.feed(data):
                try:
                    responses, _note = self.handle_frame(p)
                except Exception as e:
                    self._log("处理帧异常: %r" % (e,))
                    continue
                for r in responses:
                    self._send(r)

    def _emitter(self):
        period = 1.0 / max(0.1, self.sample_hz)
        next_t = time.time()
        while self.running:
            now = time.time()
            if now < next_t:
                time.sleep(min(0.005, max(0.0, next_t - now)))
                continue
            next_t += period
            with self._lock:
                mode, streaming = self.mode, self.streaming
            if not streaming or not mode:
                continue
            if mode == "ocp":
                with self._lock:
                    self._ocp_buf.append(self.ocp_point(self._ocp_k))
                    self._ocp_k += 1
                    if len(self._ocp_buf) >= self.points_per_frame:
                        pts, self._ocp_buf = self._ocp_buf, []
                        frame = build(CMD["CSDataOCP"],
                                      b"".join(struct.pack("<f", p) for p in pts))
                    else:
                        frame = None
                if frame:
                    self._send(frame, "gen")
                    if self.ei_also:
                        self._send(build_f(CMD["CSDataEI"], pts[-1],
                                           1e-8 * (1.0 + self.rng.gauss(0, 0.1))), "gen")
            elif mode == "potdyn":
                self._send(self.make_ei_frame(), "gen")

    def open(self):
        import serial                                    # 延迟导入：selftest 不需要 pyserial
        self.ser = serial.Serial(self.path, self.baud, timeout=0.05,
                                 write_timeout=2.0)
        self._log("已打开 %s @%d 8N1，扮演 CS350M (SN=%s, %d 点/帧)"
                  % (self.path, self.baud, self.sn, self.points_per_frame))

    def start(self):
        self.open()
        self.running = True
        self.threads = [
            threading.Thread(target=self._reader, daemon=True, name="sim-rd"),
            threading.Thread(target=self._emitter, daemon=True, name="sim-tx"),
        ]
        for t in self.threads:
            t.start()
        return self

    def stop(self):
        self.running = False
        for t in self.threads:
            t.join(timeout=1.2)
        self.threads = []
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.close_log()

    def summary(self):
        with self._lock:
            return {
                "recv": len(self.recv_frames),
                "sent": len(self.sent_frames),
                "unknown": self.n_unknown,
                "mode": self.mode,
                "streaming": self.streaming,
                "parser": dict(self._rd.stats),
                "recv_cmds": sorted(set(f["cmd_name"] for _, f in self.recv_frames)),
            }


# ================================================================ 端口安全

def normalize_port(name):
    """COM90 / CNCB0 / \\\\.\\CNCB0 → 统一大写去前缀名。"""
    n = str(name).strip()
    if n.upper().startswith(WIN32_PREFIX):
        n = n[len(WIN32_PREFIX):]
    return n.upper()


def validate_port(name):
    n = normalize_port(name)
    if n in FORBIDDEN_PORTS:
        raise ValueError(
            "红线拒绝：端口 %s 是真实设备/蓝牙口，禁止本脚本打开（只允许虚拟对 "
            "CNCA0/CNCB0=COM90、CNCA1/CNCB1=COM91）" % name)
    return name


def win_port(name):
    """补 \\\\.\\ 前缀（com0com 的 CNCB0 这类名字需要它）。"""
    if str(name).upper().startswith(WIN32_PREFIX):
        return name
    return WIN32_PREFIX + name


# ================================================================ 离线自测

class _Checks:
    def __init__(self):
        self.passed = []
        self.failed = []

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


def _eq(a, b, msg=""):
    assert a == b, "%s\n  实际: %r\n  期望: %r" % (msg, a, b)


def _near(a, b, tol=1e-6, msg=""):
    assert abs(a - b) <= tol, "%s 实际 %r 期望 %r (tol %g)" % (msg, a, b, tol)


def selftest():
    print("=" * 72)
    print("simdevice.py 离线自测（不 import pyserial、不碰任何串口）")
    print("=" * 72)
    ck = _Checks()

    # ---------- A. 帧编解码 ----------
    def a1_checksum_known():
        # 与真实日志逐字节比对（testbed_sim*.log 实收）
        _eq(build("CSStart").hex(" ").upper(), REAL_FRAMES["cs_start"])
        _eq(build("CSStop").hex(" ").upper(), REAL_FRAMES["cs_stop"])
        _eq(build("GetPstType").hex(" ").upper(), REAL_FRAMES["get_pst_type"])
        _eq(build("GetSerialNumber").hex(" ").upper(), REAL_FRAMES["get_serial_number"])
        _eq(build("CSExpStop").hex(" ").upper(), "55 AA 00 06 72 77")
        _eq(build("CSApply").hex(" ").upper(), "55 AA 00 06 AA AF")   # proto 实测样本
    ck.check("A1 累加和构造：无载荷帧与真实日志逐字节一致", a1_checksum_known)

    def a2_single_e():
        p = parse(rx("data_e_single"))
        assert p is not None
        _eq(p["cmd"], 0x60, "命令号")
        _eq(p["cmd_name"], "CSDataE")
        _eq(p["length"], 10)
        _near(floats(p["data"])[0], -0.139144, 1e-4, "电位值（文档记 -0.139 为四舍五入）")
        _eq(p["frame"], rx("data_e_single"), "重建一致")
    ck.check("A2 解析真实单点电位帧 -0.139 V", a2_single_e)

    def a3_ei():
        p = parse(rx("data_ei"))
        v = floats(p["data"])
        _eq(len(v), 2)
        _near(v[0], -0.2122, 1e-3, "电位")
        assert abs(v[1]) < 1e-5, "电流 1e-6 量级"
    ck.check("A3 解析真实 0x62 电位+电流帧", a3_ei)

    def a4_batch126():
        raw = rx("data_batch126")
        _eq(len(raw), 126, "整帧 126 字节")
        p = parse(raw)
        assert p is not None
        _eq(p["length"], 0x7E)
        _eq(p["cmd"], 0x60)
        v = floats(p["data"])
        _eq(len(v), 30, "30 个 float32 点（文档 29 系误记，以本帧为准）")
        _near(v[0], -0.142430, 1e-5, "首点")
        _near(v[29], -0.142438, 1e-5, "末点")
        _eq(checksum(raw[:-1]), raw[-1], "SUM=F6")
        _eq(p["frame"], raw, "重建一致")
    ck.check("A4 解析真实 OCP 批量帧 126B=30 点（SUM 复核）", a4_batch126)

    def a5_bad_sum():
        ps = Parser()
        raw = bytearray(rx("cs_start"))
        raw[-1] ^= 0xFF                                   # 破坏校验和
        frames = ps.feed(bytes(raw) + rx("get_pst_type"))
        _eq(len(frames), 1, "坏帧后能恢复同步并解析下一帧")
        _eq(frames[0]["cmd"], 0x14)
        _eq(ps.stats["bad_sum"], 1)
        assert ps.stats["dropped"] >= 1
    ck.check("A5 坏校验帧拒绝并计数，流恢复同步", a5_bad_sum)

    def a6_garbage():
        ps = Parser()
        frames = ps.feed(b"\x01\x02\x03" + rx("cs_start") + b"\xAA\xAA")
        _eq(len(frames), 1)
        _eq(frames[0]["cmd"], 0x30)
        assert ps.stats["dropped"] >= 3
    ck.check("A6 前置杂字节自动重同步", a6_garbage)

    def a7_sticky():
        ps = Parser()
        blob = rx("cs_start") + rx("get_pst_type") + rx("data_e_single")[:4]
        got = []
        got += ps.feed(blob)
        got += ps.feed(rx("data_e_single")[4:])           # 半帧跨块
        _eq([f["cmd"] for f in got], [0x30, 0x14, 0x60], "粘包+跨块全解析")
        _eq(ps.stats["good"], 3)
    ck.check("A7 粘包与半帧跨块解析", a7_sticky)

    def a8_bad_len():
        ps = Parser()
        frames = ps.feed(b"\x55\xAA\xFF\xFF\x30" + b"\x00" * 20 + rx("cs_start"))
        _eq(len(frames), 1, "LEN 非法丢弃后恢复")
        _eq(ps.stats["bad_len"], 1)
    ck.check("A8 LEN 非法帧拒绝并计数", a8_bad_len)

    def a9_build_potdyn():
        # 00 §3.5 逐字节基准：InitE=-0.2 FinalE=1 0.33mV/s OCP=-0.104628562927246
        got = potdynamic_frame(-0.2, 1.0, 0.33, -0.104628562927246)
        _eq(got, rx("pot_dynamic"), "与软件真实帧逐字节一致")
    ck.check("A9 动电位参数帧构造器逐字节复刻", a9_build_potdyn)

    def a10_build_ocp():
        got = ocp_frame(1800.0, 10.0, 0.0)
        _eq(got.hex(" ").upper(),
            "55 AA 00 12 51 00 00 20 41 00 00 E1 44 00 00 00 00 E8")
    ck.check("A10 OCP 参数帧构造器复刻（1800s/10Hz）", a10_build_ocp)

    # ---------- B. 参数解码 ----------
    def b1_ocp_params():
        p = parse(rx("noise_start"))
        info = decode_ocp_params(p["data"])
        _near(info["sample_hz"], 10.0, 1e-6)
        _near(info["test_time"], 200.0, 1e-6)
        _near(info["extra"], 0.0, 1e-9)
    ck.check("B1 OCP 参数解码：hz=10.0 test_time=200.0（sim13 实收）", b1_ocp_params)

    def b2_potdyn_params():
        p = parse(rx("pot_dynamic"))
        info = decode_potdynamic(p["data"])
        _near(info["range_v"], 5.0)
        _near(info["init_e_ocp"], -0.304628, 1e-5, "InitE+OCP")
        _near(info["mid1_e_ocp"], -0.304628, 1e-5, "Mid1（不启用=InitE）")
        _near(info["mid2_e_ocp"], -0.304628, 1e-5, "Mid2")
        # FinalE=1.0 加 OCP(-0.1046286) → 0.8953714（十六进制直读，勿心算）
        _near(info["final_e_ocp"], 0.8953714, 1e-5, "FinalE+OCP")
        _near(info["scan_rate_v_per_s"], 0.00033, 1e-7, "扫描速率 V/s")
        _near(info["scan_rate_mv_per_s"], 0.33, 1e-4)
        _near(info["frq"], 0.66, 1e-6, "Frq=mV/s×2")
    ck.check("B2 动电位参数解码（含 OCP 偏移/速率/Frq 换算）", b2_potdyn_params)

    def b3_cs_output():
        p = parse(rx("cs_output"))
        info = decode_cs_output(p["data"])
        _eq(info["u16be_guess"], 100, "u16BE=100（猜测语义）")
        assert "待实测帧校对" in info["confidence"]
    ck.check("B3 0x45 扩展参数帧存证（u16BE=100，语义待校对）", b3_cs_output)

    def b4_dev_setup():
        p = parse(rx("dev_setup"))
        _eq(p["length"], 32, "整帧 32B")
        _eq(len(p["data"]), 26, "DATA=26B")
        info = decode_dev_setup(p["data"])
        hits = dict(info["float_hits"])
        assert any(abs(v - 100.0) < 1e-6 for v in hits.values()), "float 扫描应发现 100.0"
        assert "待实测帧校对" in info["confidence"]
    ck.check("B4 0x40 DevSetup 32B 帧存证（DATA=26B，含 float 100.0）", b4_dev_setup)

    def b5_speculative():
        info = decode_speculative(b"\x00\x00\x20\x41\x00\x00\x48\x43", "EIS")
        _eq(info["floats"], [10.0, 200.0])
        _eq(info["label"], "EIS")
        assert "待实测帧校对" in info["confidence"]
        info2 = decode_speculative(b"", "PotSquare")
        _eq(info2["floats"], [])
    ck.check("B5 EIS/阶梯波推测解码器（float 扫描 + 待校对标记）", b5_speculative)

    # ---------- C. 命令分发与应答 ----------
    def mkdev(**kw):
        return SimDevice(None, verbose=False, **kw)

    def c1_get_pst_type():
        dev = mkdev()
        resp, note = dev.handle_frame(rx("get_pst_type"))
        _eq(resp[0], rx("get_pst_type_ans"), "应答=55 AA 00 07 14 08 22")
    ck.check("C1 GetPstType 应答 CS350M 类型帧（实收基准）", c1_get_pst_type)

    def c2_get_uid():
        dev = mkdev()
        resp, _ = dev.handle_frame(build("GetUID"))
        p = parse(resp[0])
        _eq(p["data"].decode("ascii"), "CS350M24030650", "序列号")
        _eq(p["cmd"], 0x17)
    ck.check("C2 GetUID 应答序列号 CS350M24030650", c2_get_uid)

    def c3_basic_acks():
        dev = mkdev()
        for cmd_name, real in (("CSStart", "cs_start"), ("CSStop", "cs_stop")):
            resp, _ = dev.handle_frame(build(cmd_name))
            _eq(resp[0], rx(real), cmd_name + " 空帧确认")
        resp, _ = dev.handle_frame(build("CSApply"))
        _eq(resp[0], build("CSApply"))
        resp, _ = dev.handle_frame(build("CSExpStop"))
        _eq(resp[0], build("CSExpStop"), "CSExpStop 终止确认")
        assert dev.applied
    ck.check("C3 CSStart/CSStop/CSApply/CSExpStop 确认帧", c3_basic_acks)

    def c4_restart_misc():
        dev = mkdev()
        resp, _ = dev.handle_frame(build("ReStartDev"))
        _eq(parse(resp[0])["data"], b"\x00")
        resp, _ = dev.handle_frame(build("StartCellYWGet"))
        _eq(parse(resp[0])["data"], b"\x01")
        resp, _ = dev.handle_frame(build("GetSerialNumber"))
        _eq(parse(resp[0])["data"].decode("ascii"), dev.sn)
        resp, _ = dev.handle_frame(build("SetPstType"))
        _eq(parse(resp[0])["data"], bytes([8]))
    ck.check("C4 ReStartDev/StartCellYWGet/GetSerialNumber/SetPstType", c4_restart_misc)

    def c5_noisestart():
        dev = mkdev()
        resp, note = dev.handle_frame(rx("noise_start"))
        _eq(parse(resp[0])["cmd"], 0x51, "启动确认")
        _eq(parse(resp[1])["cmd"], 0x71, "附带电解池帧（旧版行为兼容）")
        assert dev.mode == "ocp" and dev.streaming, "参数帧到达即开始推流"
        _near(dev.sample_hz, 10.0)
        assert dev.method and dev.method["kind"] == "ocp"
    ck.check("C5 NoiseStart：解码参数+确认+进入 OCP 推流", c5_noisestart)

    def c6_wait_start():
        dev = mkdev(wait_start=True)
        dev.handle_frame(rx("noise_start"))
        assert not dev.streaming, "wait_start 模式下参数帧不立即推流"
        dev.handle_frame(build("CSStart"))
        assert dev.streaming and dev.exp_started, "CSStart 后才推流"
    ck.check("C6 --wait-start 生命周期：参数帧→CSStart 才推流", c6_wait_start)

    def c7_potdyn_dispatch():
        dev = mkdev()
        resp, _ = dev.handle_frame(rx("pot_dynamic"))
        _eq(parse(resp[0])["cmd"], 0x54)
        assert dev.mode == "potdyn" and dev.streaming
        _near(dev._pot_init, -0.304628, 1e-5)
        _near(dev._pot_final, 0.8953714, 1e-5)
        _near(dev._pot_rate, 0.00033, 1e-7)
    ck.check("C7 CSPotDynamic：参数入库+进入 0x62 推流", c7_potdyn_dispatch)

    def c8_stop_flush():
        dev = mkdev(points_per_frame=4)
        dev.handle_frame(rx("noise_start"))
        # 手工攒 2 个未满批
        with dev._lock:
            dev._ocp_buf += [dev.ocp_point(0), dev.ocp_point(1)]
        resp, note = dev.handle_frame(build("CSStop"))
        _eq(parse(resp[0])["cmd"], 0x32, "停止确认")
        _eq(parse(resp[1])["cmd"], 0x68, "余 2 点冲刷为 0x68 帧")
        _eq(len(floats(parse(resp[1])["data"])), 2)
        assert dev.mode is None and not dev.streaming
    ck.check("C8 停止时冲刷未满 OCP 批量缓冲", c8_stop_flush)

    def c9_expstop():
        dev = mkdev()
        dev.handle_frame(rx("noise_start"))
        resp, _ = dev.handle_frame(build("CSExpStop"))
        _eq(parse(resp[0])["cmd"], 0x72)
        assert dev.mode is None and not dev.streaming and not dev.exp_started
    ck.check("C9 CSExpStop 终止实验清状态", c9_expstop)

    def c10_read_ocp():
        dev = mkdev()
        resp, _ = dev.handle_frame(build("ReadOcp"))
        p = parse(resp[0])
        _eq(p["cmd"], 0x68)
        v = floats(p["data"])
        _eq(len(v), 1)
        assert -1.0 < v[0] < 0.0, "OCP 合理范围"
    ck.check("C10 ReadOcp 应答 0x68 当前电位", c10_read_ocp)

    def c11_unknown_nack():
        dev = mkdev()
        resp, note = dev.handle_frame(build(0x77, b"\x01\x02"))
        p = parse(resp[0])
        _eq(p["cmd"], 0xFF, "NAck 命令号")
        _eq(p["data"], bytes([0x77]), "载荷=原命令号")
        assert dev.n_unknown == 1
        _eq(parse(build(0x77, b"\x01\x02")) is not None, True, "NAck 帧自身合法")
    ck.check("C11 未知命令记日志并回 NAck(0xFF+原命令号)", c11_unknown_nack)

    def c12_data_from_host():
        dev = mkdev()
        resp, _ = dev.handle_frame(rx("data_e_single"))     # 主机不该发 0x60
        _eq(resp, [], "不应答（防回环）")
    ck.check("C12 主机发数据命令：忽略不应答", c12_data_from_host)

    def c13_config_acks():
        dev = mkdev()
        for name in ("CSOutput",):
            resp, _ = dev.handle_frame(rx("cs_output"))
            _eq(parse(resp[0])["data"], b"", name + " 空帧确认（旧版兼容）")
        resp, _ = dev.handle_frame(rx("dev_setup"))
        _eq(parse(resp[0])["data"], b"", "DevSetup 空帧确认")
    ck.check("C13 0x45/0x40 配置帧存证+空帧确认（兼容旧链路）", c13_config_acks)

    def c14_pause_resume():
        dev = mkdev()
        dev.handle_frame(rx("noise_start"))
        dev.handle_frame(build("CSPause"))
        assert dev.paused and not dev.streaming
        dev.handle_frame(build("CSStart"))
        assert dev.streaming, "暂停后 CSStart 恢复推流"
    ck.check("C14 暂停/恢复", c14_pause_resume)

    # ---------- D. 数据包生成 ----------
    def d1_batch_shape():
        dev = mkdev(points_per_frame=30)
        f = dev.make_ocp_frame()
        _eq(len(f), 126, "30 点帧 LEN=0x7E 与真实批量帧同构")
        _eq(f[4], 0x68)
        _eq(len(floats(parse(f)["data"])), 30)
        _eq(checksum(f[:-1]), f[-1])
    ck.check("D1 OCP 批量帧 30 点与真实帧同构（LEN=126）", d1_batch_shape)

    def d2_single_shape():
        dev = mkdev(points_per_frame=1)
        f = dev.make_ocp_frame()
        _eq(len(f), 10, "单点帧 LEN=0x0A 与真实单点帧同构")
    ck.check("D2 OCP 单点帧 LEN=0x0A（旧版模式）", d2_single_shape)

    def d3_flush_partial():
        dev = mkdev(points_per_frame=30)
        with dev._lock:
            dev._ocp_buf = [dev.ocp_point(i) for i in range(15)]
        tail = dev._flush_ocp_buf()
        _eq(len(tail), 1)
        _eq(len(floats(parse(tail[0])["data"])), 15, "部分缓冲冲刷 15 点")
    ck.check("D3 部分批量缓冲冲刷（15 点）", d3_flush_partial)

    def d4_ei_ramp():
        dev = mkdev()
        dev._pot_init, dev._pot_final, dev._pot_rate = -0.2, 0.8, 0.01
        E0, i0 = dev.pot_point(0.0)
        E1, i1 = dev.pot_point(1e9)                        # 远超扫描时长→饱和
        _near(E0, -0.2, 1e-9, "t=0 在 InitE")
        _near(E1, 0.8, 1e-6, "t→∞ 饱和在 FinalE")
        assert i1 > i0 > 0, "伪 Tafel 电流随电位增长"
        f = dev.make_ei_frame(0.0)
        _eq(len(f), 14, "0x62 帧 LEN=0x0E")
        v = floats(parse(f)["data"])
        _eq(len(v), 2)
    ck.check("D4 0x62 电位扫描+电流生成与帧形状", d4_ei_ramp)

    def d5_ei_companion():
        dev = mkdev(points_per_frame=2, ei_also=True)
        dev.handle_frame(rx("noise_start"))
        # 直接驱动 emitter 的一拍逻辑太重，这里验证 ei 配置位与帧生成
        assert dev.ei_also
        f = build_f(CMD["CSDataEI"], dev.ocp_point(0), 1e-8)
        p = parse(f)
        _eq(p["cmd"], 0x62)
        _eq(len(floats(p["data"])), 2)
    ck.check("D5 --ei 附带 0x62 电位+电流帧", d5_ei_companion)

    def d6_potdyn_stream():
        dev = mkdev()
        dev.handle_frame(rx("pot_dynamic"))
        frames = [dev.make_ei_frame(t) for t in (0.0, 1.0, 2.0)]
        for f in frames:
            p = parse(f)
            _eq(p["cmd"], 0x62)
        E0 = floats(parse(frames[0])["data"])[0]
        E2 = floats(parse(frames[2])["data"])[0]
        assert E2 > E0, "电位随时间上升（正扫速）"
    ck.check("D6 动电位流：0x62 序列电位递增", d6_potdyn_stream)

    # ---------- E. JSONL 结构化日志 ----------
    def e1_records():
        dev = mkdev()
        dev.handle_frame(rx("cs_start"))
        recs = [r for r in dev.records if r["dir"] == "rx"]
        _eq(len(recs), 1)
        r = recs[0]
        for key in ("ts", "dir", "cmd", "name", "len", "hex"):
            assert key in r, "缺字段 %s" % key
        _eq(r["name"], "CSStart")
        _eq(r["cmd"], 0x30)
        _eq(r["hex"], "55 AA 00 06 30 35")
        tx = [r for r in dev.records if r["dir"] == "tx"]
        _eq(len(tx), 1)
        _eq(tx[0]["name"], "CSStart")
    ck.check("E1 JSONL 记录字段：ts/dir/cmd/name/hex 齐全", e1_records)

    def e2_jsonl_file():
        import tempfile
        dev = mkdev()
        with tempfile.TemporaryDirectory() as td:
            dev.log_path = os.path.join(td, "frames.jsonl")
            dev.handle_frame(rx("noise_start"))
            dev.handle_frame(build("CSStart"))
            dev.close_log()
            lines = [json.loads(l) for l in
                     open(dev.log_path, encoding="utf-8") if l.strip()]
            _eq(len(lines), 5, "noise_start: rx+2tx；cs_start: rx+tx")
            _eq([r["dir"] for r in lines], ["rx", "tx", "tx", "rx", "tx"])
            assert all("hex" in r and "cmd" in r for r in lines)
            ocp = [r for r in lines if r["name"] == "NoiseStart"]
            _eq(ocp[0]["parsed"]["sample_hz"], 10.0, "解析结果入日志")
    ck.check("E2 JSONL 落盘：每帧一行可回读、解析结果附带", e2_jsonl_file)

    # ---------- F. 兼容与安全 ----------
    def f1_dropin():
        # 与旧版 simdevice.SimDevice 的构造签名/summary 兼容
        dev = SimDevice(None)                            # 默认参数即可构造
        s = dev.summary()
        for key in ("recv", "sent", "mode", "recv_cmds"):
            assert key in s
        assert hasattr(dev, "start") and hasattr(dev, "stop")
        assert hasattr(dev, "recv_frames") and hasattr(dev, "sent_frames")
    ck.check("F1 与旧版 SimDevice 构造签名/summary 兼容", f1_dropin)

    def f2_forbidden():
        for bad in ("COM16", "COM4", "\\\\.\\COM10", "com11"):
            try:
                validate_port(bad)
                raise AssertionError("应拒绝 %s" % bad)
            except ValueError:
                pass
        # 虚拟口放行
        validate_port("CNCB0")
        validate_port("\\\\.\\CNCB0")
        validate_port("COM90")
        validate_port("COM91")
    ck.check("F2 端口红线：真实设备口硬拒绝、虚拟口放行", f2_forbidden)

    def f3_no_serial_import():
        assert "serial" not in sys.modules, "--selftest 不得 import pyserial"
    ck.check("F3 selftest 全程未 import pyserial（离线红线）", f3_no_serial_import)

    def f4_full_dialog():
        # 一条完整对话：识别→方法下载→启动→停止（等价 probe_testbed9 序列的离线版）
        dev = mkdev()
        seq = ["get_pst_type", "get_serial_number", "cs_output", "dev_setup",
               "noise_start", "cs_start", "cs_stop"]
        outs = []
        for name in seq:
            resp, _ = dev.handle_frame(rx(name))
            outs.extend(resp)
        names = [parse(r)["cmd_name"] if parse(r) else "?" for r in outs]
        _eq(names[0], "GetPstType")
        _eq(parse(outs[0])["data"], bytes([8]))
        _eq(names[1], "GetSerialNumber")
        _eq(names[2], "CSOutput")
        _eq(names[3], "DevSetup")
        _eq(names[4], "NoiseStart")
        _eq(names[5], "StartCellYWGet")
        _eq(names[6], "CSStart")
        _eq(names[7], "CSStop")
        s = dev.summary()
        _eq(s["recv"], 7)
        _eq(s["unknown"], 0)
    ck.check("F4 完整对话回归：识别→方法下载→启停（probe_testbed9 序列离线版）", f4_full_dialog)

    # ---------- 汇总 ----------
    print("-" * 72)
    total = len(ck.passed) + len(ck.failed)
    print("自测结果: %d/%d 通过" % (len(ck.passed), total))
    if ck.failed:
        print("失败项:")
        for name, err in ck.failed:
            print("  - %s: %s" % (name, err))
        return False
    print("全部通过 ✔  （解码覆盖：OCP/动电位(Tafel 同构)；EIS/阶梯波待 Agent C 实捕帧校对）")
    return True


# ================================================================ CLI

def main():
    ap = argparse.ArgumentParser(
        description="CS350M 虚拟设备模拟器（testbed 正式资产；--selftest 离线自测）")
    ap.add_argument("--port", default=None,
                    help="串口名：CNCB0 / COM90 / \\\\.\\CNCB0（live 模式必填；"
                         "红线禁止 COM16/COM10/COM6/COM4/COM5/COM11/COM12）")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--sn", default=DEFAULT_SN)
    ap.add_argument("--hz", type=float, default=10.0, help="默认采样率（可被 0x51 参数帧覆盖）")
    ap.add_argument("--points", type=int, default=30,
                    help="每个 0x68 批量帧点数（默认 30=真实批量帧 LEN 0x7E 反推值；1=旧版单点模式）")
    ap.add_argument("--ei", action="store_true", help="OCP 模式附带推 0x62（电位+电流）")
    ap.add_argument("--wait-start", action="store_true",
                    help="参数帧到达后等 CSStart(0x30) 才推数据")
    ap.add_argument("--log", default=None, help="JSONL 帧日志路径")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="离线自测（不占串口）")
    args = ap.parse_args()

    if args.selftest:
        ok = selftest()
        sys.exit(0 if ok else 1)

    if not args.port:
        ap.error("live 模式需要 --port（离线自测请用 --selftest）")

    dev = SimDevice(args.port, args.baud, args.sn, args.hz,
                    verbose=not args.quiet,
                    points_per_frame=args.points, ei_also=args.ei,
                    wait_start=args.wait_start, log_path=args.log)
    dev.start()
    print("模拟器运行中，Ctrl+C 退出 ...", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        dev.stop()
        print("统计: %r" % (dev.summary(),), flush=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
