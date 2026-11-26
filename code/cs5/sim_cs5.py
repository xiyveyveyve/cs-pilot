# -*- coding: utf-8 -*-
"""code/cs5/sim_cs5.py —— CS5 应答语义实验台（**不修改** simdevice.py 本体）

背景
----
`code/sim/simdevice.py` 是 testbed 的只读副本（sha256 记录在 MANIFEST.txt），
其中 `_cs5_handle` 有两处是"ACK 未定：先回显"的临时实现：

    if cmd == 0x85:  return [frame]     # 参数帧，原样回显
    if cmd == 0x74:  return [frame]     # 方法下载起始，原样回显

实测（2026-11-10）回显 0x85 会让软件直接 RST 断连。本文件用**子类覆盖**
`_cs5_handle` 的方式做变体扫描，找出软件真正接受的应答格式。

用法
----
    # 单次跑某个变体（起 sim + 挂起等软件连入）
    python -I code/cs5/sim_cs5.py --port 0.0.0.0:31050 --ack85 echo
    python -I code/cs5/sim_cs5.py --port 0.0.0.0:31050 --ack85 cf00
    ...

    # 离线自检（不发真连接，只打各变体生成的字节）
    python -I code/cs5/sim_cs5.py --selftest
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sim"))

import simdevice  # noqa: E402  （只读复用）

SimDevice = simdevice.SimDevice


# ------------------------------------------------------------------ 变体定义
# 每个变体是一个函数 (sim, frame) -> list[bytes]
# frame 是收到的 16B 帧（AA + cmd + 13B data + SUM）

def _f(sim, cmd, data=b""):
    return sim._cs5_frame(cmd, data)


VARIANTS_85 = {
    # 原样回显（已知会断连，留作对照）
    "echo": lambda sim, fr: [fr],

    # 工作模式帧：CF 后带 1 字节状态
    "cf00": lambda sim, fr: [_f(sim, 0xCF, b"\x00")],
    "cf01": lambda sim, fr: [_f(sim, 0xCF, b"\x01")],

    # 裸 ACK：只回命令字节、无 data
    "bare85": lambda sim, fr: [_f(sim, 0x85, b"")],

    # 原值 + 确认位（frame[2] 是 0x63，第三字节 0x02 是子命令）
    "85_echo_plus_cf": lambda sim, fr: [fr, _f(sim, 0xCF, b"\x00")],
    "85_bare_plus_cf": lambda sim, fr: [_f(sim, 0x85, b""), _f(sim, 0xCF, b"\x00")],

    # 回 0x63 子命令 + 参数数
    "63": lambda sim, fr: [_f(sim, 0x63, fr[2:3] + b"\x00")],

    # 回 0x80 0x53（Stop 的成功形态，有些设备用它表示"命令已收"）
    "8053": lambda sim, fr: [_f(sim, 0x80, b"\x53")],

    # 什么都不回（对照：软件可能自己继续）
    "silent": lambda sim, fr: [],
}

# 工作模式查询 AA CF xx —— 模拟器原本**没有这个分支**（直接落到默认，不回任何东西），
# 而软件会连发 9 次。这是 StartMethod 挂起的重要嫌疑。
VARIANTS_CF = {
    "echo": lambda sim, fr: [fr],
    "cf00": lambda sim, fr: [_f(sim, 0xCF, bytes([0]))],
    "cf01": lambda sim, fr: [_f(sim, 0xCF, bytes([1]))],
    "cf01_plus_mode": lambda sim, fr: [_f(sim, 0xCF, bytes([1])), _f(sim, 0xCF, bytes([1]))],
    "silent": lambda sim, fr: [],
}

VARIANTS_74 = {
    "echo": lambda sim, fr: [fr],
    "bare74": lambda sim, fr: [_f(sim, 0x74, b"")],
    "cf00": lambda sim, fr: [_f(sim, 0xCF, b"\x00")],
    "silent": lambda sim, fr: [],
}


class Cs5Sim(SimDevice):
    """在 simdevice.SimDevice 之上只覆盖 `_cs5_handle`，其它行为完全继承。"""

    ack85 = "silent"
    ack74 = "echo"
    ackcf = "echo"
    ack53 = "53le"
    ack85sub = None
    verbose_ack = True

    def _cs5_reader(self):
        """★ 2026-11-10 覆盖基类读线程：唯一差异=应答帧 write 后 sleep(0.04)。

        依据（t_cs5pack 黑盒）：CS5 SockectCom.GetUninPack 原样吐接收缓冲、不切帧；
        软件侧 SendReturnPackage(pkg, timeout, dataLen=7, head=0xAA, repeat) 从缓冲取包。
        基类里应答 write 与推流 write 间隔 <1ms → TCP 两帧粘包 → 软件拿到
        「应答+推流」拼接 16B → WatiFun len==7 永不命中（实测 16B=7E..+推流10B）。
        应答后隔 40ms 再推流，保证分包。其余逻辑与基类逐行一致（simdevice.py 只读）。
        """
        buf = bytearray()
        last_tx = 0.0
        while self.running:
            if self.ser is None:
                time.sleep(0.1)
                continue
            # ★ --no-stream：停掉主动推流，让应答帧独占缓冲
            #   （SendReturnPackage(dataLen=7) 即可拿到纯 7B，WatiFun 走 len==7 decode 路径）
            if (getattr(self, "_cs5_streaming", False) and self.sample_hz > 0
                    and not getattr(self, "no_stream", False)):
                now = time.time()
                if now - last_tx >= 1.0 / self.sample_hz:
                    try:
                        self.ser.write(self._cs5_data_frame())
                        last_tx = now
                    except Exception:
                        pass
            try:
                data = self.ser.read(4096)
            except Exception as e:
                self._log("CS5 连接断开: %r" % (e,))
                self.ser = None
                continue
            if not data:
                continue
            buf.extend(data)
            self._log("CS5 RAW %dB: %s" % (len(data), data.hex(" ").upper()[:80]))
            while True:
                idx = None
                for i in range(len(buf) - 15):
                    if buf[i] == 0xAA and (sum(buf[i:i + 15]) & 0xFF) == buf[i + 15]:
                        idx = i
                        break
                if idx is None:
                    if len(buf) > 64:
                        del buf[:-16]
                    break
                frame = bytes(buf[idx:idx + 16])
                del buf[:idx + 16]
                for r in self._cs5_handle(frame):
                    try:
                        self.ser.write(r)
                        time.sleep(0.04)   # ★ 应答与后续推流强制分包（防 TCP 粘包毁帧）
                    except Exception as e:
                        self._log("CS5 发送失败: %r" % (e,))

    def _cs5_handle(self, frame):
        cmd = frame[1]
        if cmd == 0x85:
            if self.ack85sub:
                # 帧结构 AA 85 63 0A ...：frame[2]=0x63（族码），frame[3]=子命令（0x0A 参数帧 / 0x02 探测帧）
                # 2026-11-10 修正：旧版读 frame[2] 恒为 0x63，导致所有 0a_* 变体静默失效
                sub = frame[3] if len(frame) > 3 else (frame[2] if len(frame) > 2 else 0)
                fn2 = VARIANTS_85_SUB.get(self.ack85sub)
                if fn2 is not None:
                    out = fn2(self, sub, frame)
                    if self.verbose_ack:
                        self._log("ACK85SUB[%s] sub=0x%02X -> %s" % (
                            self.ack85sub, sub,
                            " + ".join(b.hex(" ").upper() for b in out) or "<空>"))
                    return out
            fn = VARIANTS_85.get(self.ack85)
            if fn is None:
                self._log("!! 未知 ack85 变体 %r，退回 silent" % (self.ack85,))
                fn = VARIANTS_85["silent"]
            out = fn(self, frame)
            if self.verbose_ack:
                self._log("ACK85[%s] → %s" % (self.ack85,
                                              " + ".join(b.hex(" ").upper() for b in out) or "<空>"))
            return out
        if cmd == 0x53:
            fn = VARIANTS_READOCP.get(self.ack53)
            if fn is None:
                fn = VARIANTS_READOCP["legacy"]
            out = fn(self, frame)
            if self.verbose_ack:
                self._log("ACK53[%s] → %s" % (self.ack53,
                                              " + ".join(b.hex(" ").upper() for b in out) or "<空>"))
            # 按原逻辑维护推流状态（先置定，再管 ACK）
            prev = getattr(self, "_cs5_exp", None)
            self._cs5_exp = "potdyn" if prev in ("ocp", "potdyn") else "ocp"
            self._cs5_streaming = True
            self._cs5_t0 = time.time()
            self._cs5_seq = 0
            return out
        if cmd == 0xCF:
            fn = VARIANTS_CF.get(self.ackcf)
            if fn is None:
                fn = VARIANTS_CF["echo"]
            out = fn(self, frame)
            if self.verbose_ack:
                self._log("ACKCF[%s] → %s" % (self.ackcf,
                                              " + ".join(b.hex(" ").upper() for b in out) or "<空>"))
            return out
        if cmd == 0x74:
            fn = VARIANTS_74.get(self.ack74)
            if fn is None:
                fn = VARIANTS_74["echo"]
            out = fn(self, frame)
            if self.verbose_ack:
                self._log("ACK74[%s] → %s" % (self.ack74,
                                              " + ".join(b.hex(" ").upper() for b in out) or "<空>"))
            return out
        if cmd == 0x52:
            # ★ 2026-11-10 实锤：AA 52 07 D2 00 03 ... 16B = GetDoubleChannelSampleBytes
            #   动态构造的采样参数帧（S4 SendMethodParams 帧2 / S6 StartMethod 内），
            #   旧版无此分支全静默 → 软件重试 ×9 全败 → S4=False / S6「指令下发失败」。
            #   先回显（16B，CheckPack len≥5 安全）。
            out = [bytes(frame)]
            if self.verbose_ack:
                self._log("ACK52[echo] → %s" % out[0].hex(" ").upper())
            return out
        # 其余命令沿用原实现（0x53 启动双帧、0x80 0x53 Stop=CF00 等）
        return SimDevice._cs5_handle(self, frame)



# ---------------------------------------------------------------------------
# ReadOcpBytes（AA 53 01）的应答 —— StartMethod 挂起的真正关卡
#
# 2026-11-10 反汇编定案：ExpCallWatiFun 在 +219/+236 处 ldsfld CommandPackage.ReadOcpBytes
# 然后 callvirt ICorrCom.SendReturnPackage（**同步请求/应答**），随后用
# IParsingParams.GetVoltValue / GetCurrValue 取值。设备不回带数值的应答就永久阻塞。
#
# 关键：ReadOcpBytes 的字节模板本身就是 AA 53 01 00 .. FE（≠ StartBytes=AA 80 51）。
# 所以这条命令是"读 OCP 值"，必须回一个**能被 IParsingParams 解析出电位**的帧。
#
# 候选格式来自 CS6 的 5 版回读实证（00 号文档 §3.6）：
#   7 字节  55 RR RR RR 80 04 CHK ，Volt = (2^23 - raw24)/2^23 * 9.8
# CS5 的 16B AA 帧族下，数值可能放在 data 区（多字节序都试）。
# ---------------------------------------------------------------------------

OCP_VALUE = -0.123456          # 测试用 OCP 值（V）

def _pack_le_f32(v, n=4):
    import struct as _s
    return _s.pack("<f", v) + bytes(max(0, n - 4))

def _pack_be_f32(v, n=4):
    import struct as _s
    return _s.pack(">f", v) + bytes(max(0, n - 4))

def _pack_le_f64(v):
    import struct as _s
    return _s.pack("<d", v)

def _pack_be_f64(v):
    import struct as _s
    return _s.pack(">d", v)

def _cs6_style(sim, v):
    """CS6 5 版 7 字节回读：55 raw24 80 04 CHK，Volt=(2^23-raw24)/2^23*9.8"""
    raw24 = int(round((1 - v / 9.8) * (2 ** 23))) & 0xFFFFFF
    body = bytes([0x55, (raw24 >> 16) & 0xFF, (raw24 >> 8) & 0xFF, raw24 & 0xFF, 0x80, 0x04])
    return body + bytes([sum(body) & 0xFF])

VARIANTS_READOCP = {
    # A. 同命令回，data 前 4B 是 LE float32
    "53le":      lambda sim, fr: [_f(sim, 0x53, _pack_le_f32(OCP_VALUE))],
    # B. 同命令回，BE float32
    "53be":      lambda sim, fr: [_f(sim, 0x53, _pack_be_f32(OCP_VALUE))],
    # C. 同命令回，LE float64
    "53le64":    lambda sim, fr: [_f(sim, 0x53, _pack_le_f64(OCP_VALUE))],
    # D. CF 帧带 LE float32（工作模式帧里塞值）
    "cfle":      lambda sim, fr: [_f(sim, 0xCF, _pack_le_f32(OCP_VALUE))],
    # E. CF 帧带 BE float32
    "cfbe":      lambda sim, fr: [_f(sim, 0xCF, _pack_be_f32(OCP_VALUE))],
    # F. 双帧：echo + CF 带 LE float32
    "echo_cfle": lambda sim, fr: [fr, _f(sim, 0xCF, _pack_le_f32(OCP_VALUE))],
    # G. 双帧：53 带 LE float32 + CF01
    "53le_cf01": lambda sim, fr: [_f(sim, 0x53, _pack_le_f32(OCP_VALUE)),
                                  _f(sim, 0xCF, bytes([1]))],
    # H. CS6 式 7 字节回读（原始字节，不经 AA 帧）
    "cs6style":  lambda sim, fr: [_cs6_style(sim, OCP_VALUE)],
    # I. 双帧：echo + CS6 式
    "echo_cs6":  lambda sim, fr: [fr, _cs6_style(sim, OCP_VALUE)],
    # J. 老实现对照：echo + CF01（不含数值，已知会挂）
    "legacy":    lambda sim, fr: [fr, _f(sim, 0xCF, bytes([1]))],
    # K. 只 echo
    "echo":      lambda sim, fr: [fr],
    # L. ★ 2026-11-10 WatiFun 应答终版（v5=v2 结构正名）：8B = AA 53 + volt3B + curr2B + SUM。
    #    收帧规则（echo 实验实锤）：软件收线程对 AA 帧剥 AA、其余原样入 m_DataBuffer；
    #    SendReturnPackage(pkg,1500,7,0xAA,3) 从缓冲取 dataLen=7 → 应答必须 AA+cmd+7B。
    #    WatiFun 拿到 7B：data[0]=0x53(cmd)、GetVoltValue(data,1,3)=volt、
    #    GetCurrValue(data,4,3)=curr（data[6] 兼 SUM，curr 误差 ~0.3μA/LSB）。
    #    volt=(raw24-2^23)/2^23*10 偏移二进制 ±10V，大端 3B。
    #    （v3「无 cmd 7B」缓冲只剩 6B，凑推流成 16B；v4「无 AA 裸帧」被收线程整丢。）
    "wati7":     lambda sim, fr: [_wati7_frame(sim, OCP_VALUE)],
}

def _wati7_frame(sim, volt_v):
    """WatiFun 专用 8B 应答：AA 53 + volt3B(大端偏移二进制) + curr2B + SUM"""
    raw24 = int(round((volt_v / 10.0 + 1.0) * (2 ** 23))) & 0xFFFFFF
    body = bytes([0xAA, 0x53,
                  (raw24 >> 16) & 0xFF, (raw24 >> 8) & 0xFF, raw24 & 0xFF,
                  0x7F, 0xFF])
    return body + bytes([sum(body) & 0xFF])


# ---------------------------------------------------------------------------
# 0x85 的**子命令**区分（2026-11-10 新发现）
#
# 之前把 0x85 一律定案为「不应答」，但那是对 0x85 63 02（早期探测帧）。
# 实测细看：软件在 SendMethodParams 阶段发的是 `AA 85 63 0A`，
# 且连发 27 次（GetDoubleSingleSampleBytes → ICorrCom.SendReturnBoolThree 同步等 ACK）。
# 一直静默 ⇒ SendMethodParams 返回 False ⇒ StartMethod 报「指令下发失败」。
# 所以 sub=0x0A 时必须应答，sub=0x02 时保持静默。
# ---------------------------------------------------------------------------

def _echo(sim, fr):
    return [fr]

def _pad16_echo(fr):
    """原帧补零到 16B 并重算 SUM 后回显（16B 定长假说）。"""
    body = bytearray(fr[:16])
    while len(body) < 16:
        body.append(0)
    body[0] = 0xAA
    body[-1] = sum(body[:-1]) & 0xFF
    return [bytes(body)]

def _cf(sim, fr, v=bytes([0])):
    return [sim._cs5_frame(0xCF, v)]

VARIANTS_85_SUB = {
    # 默认（早期定案）：全静默
    "all_silent":      lambda sim, sub, fr: [],
    # 只对 0x0A 回显，0x02 静默
    "0a_echo":         lambda sim, sub, fr: [fr] if sub == 0x0A else [],
    # 只对 0x0A 回 CF00
    "0a_cf00":         lambda sim, sub, fr: [_f(sim, 0xCF, bytes([0]))] if sub == 0x0A else [],
    # 只对 0x0A 回 CF01
    "0a_cf01":         lambda sim, sub, fr: [_f(sim, 0xCF, bytes([1]))] if sub == 0x0A else [],
    # 只对 0x0A 回「回显 + CF00」双帧
    "0a_echo_cf":      lambda sim, sub, fr: [fr, _f(sim, 0xCF, bytes([0]))] if sub == 0x0A else [],
    # 0x0A 回裸 ACK（AA 85 无 data）
    "0a_bare":         lambda sim, sub, fr: [_f(sim, 0x85, b"")] if sub == 0x0A else [],
    # 所有 0x85 都回显（回归对照，已知会断连）
    "all_echo":        lambda sim, sub, fr: [fr],
    # 所有 0x85 都回 CF00
    "all_cf00":        lambda sim, sub, fr: [_f(sim, 0xCF, bytes([0]))],
    # ---- 2026-11-10 补长变体族（CheckPack 对 <5B 帧抛越界；16B 定长假说）----
    # 16B 标准形态应答：AA 85 63 0A + 00*12 + SUM（与查询帧同构，data=13B）
    "0a_pad16":        lambda sim, sub, fr: [_f(sim, 0x85, bytes([0x63, 0x0A] + [0] * 11))] if sub == 0x0A else [],
    # 12B 应答
    "0a_pad12":        lambda sim, sub, fr: [_f(sim, 0x85, bytes([0x0A] + [0] * 7))] if sub == 0x0A else [],
    # 8B 应答
    "0a_pad8":         lambda sim, sub, fr: [_f(sim, 0x85, bytes([0x0A, 0, 0, 0]))] if sub == 0x0A else [],
    # 6B 应答
    "0a_pad6":         lambda sim, sub, fr: [_f(sim, 0x85, bytes([0x0A, 0, 0]))] if sub == 0x0A else [],
    # 5B 应答（CheckPack 安全线最小）
    "0a_pad5":         lambda sim, sub, fr: [_f(sim, 0x85, bytes([0x0A, 0]))] if sub == 0x0A else [],
    # 原帧补齐/截断到 16B 再回显（SUM 重算）
    "0a_echo16":       lambda sim, sub, fr: _pad16_echo(fr) if sub == 0x0A else [],
}

# ------------------------------------------------------------------ 自检
def selftest():
    """离线校验各变体生成的字节合法（校验和 / 长度）。"""
    sim = Cs5Sim(None)
    frame85 = bytes([0xAA, 0x85, 0x63, 0x02] + [0] * 11)
    # 补校验和
    body = bytearray(frame85)
    body[-1] = sum(body[:-1]) & 0xFF
    frame85 = bytes(body)

    frame74 = bytes([0xAA, 0x74] + [0] * 13)
    body = bytearray(frame74)
    body[-1] = sum(body[:-1]) & 0xFF
    frame74 = bytes(body)

    fails = 0
    print("=== ACK85 变体（输入 %s）===" % frame85.hex(" ").upper())
    for name in VARIANTS_85:
        sim.ack85 = name
        out = VARIANTS_85[name](sim, frame85)
        ok = True
        for b in out:
            if len(b) < 3:
                ok = False
            else:
                if b[0] != 0xAA:
                    ok = False
                if (sum(b[:-1]) & 0xFF) != b[-1]:
                    ok = False
        if not ok:
            fails += 1
        print("  %-16s %s  %s" % (name, "OK  " if ok else "BAD ",
                                  " + ".join(x.hex(" ").upper() for x in out) or "<空>"))

    print("\n=== ACK74 变体（输入 %s）===" % frame74.hex(" ").upper())
    for name in VARIANTS_74:
        sim.ack74 = name
        out = VARIANTS_74[name](sim, frame74)
        ok = all(len(b) >= 3 and b[0] == 0xAA and (sum(b[:-1]) & 0xFF) == b[-1] for b in out)
        if not ok:
            fails += 1
        print("  %-16s %s  %s" % (name, "OK  " if ok else "BAD ",
                                  " + ".join(x.hex(" ").upper() for x in out) or "<空>"))

    print("\n==== 变体自检：%d 个不合法 ====" % fails)
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="0.0.0.0:31050")
    ap.add_argument("--sn", default="CS1201312168")
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--ack85", default="silent", choices=sorted(VARIANTS_85.keys()))
    ap.add_argument("--ack74", default="echo", choices=sorted(VARIANTS_74.keys()))
    ap.add_argument("--ackcf", default="echo", choices=sorted(VARIANTS_CF.keys()))
    ap.add_argument("--ack53", default="53le", choices=sorted(VARIANTS_READOCP.keys()))
    ap.add_argument("--ack85sub", default=None, choices=sorted(VARIANTS_85_SUB.keys()),
                    help="按 0x85 子命令区分应答（覆盖 --ack85）")
    ap.add_argument("--log", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-stream", action="store_true",
                    help="停掉主动推流（WatiFun 7B 应答实验用）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    dev = Cs5Sim(a.port, 115200, a.sn, a.hz, verbose=not a.quiet,
                 points_per_frame=30, proto="tcp", lan=True, lan_off=12,
                 log_path=a.log)
    dev.no_stream = a.no_stream
    dev.ack85 = a.ack85
    dev.ack74 = a.ack74
    dev.ackcf = a.ackcf
    dev.ack53 = a.ack53
    dev.ack85sub = a.ack85sub
    dev.start()
    print("CS5 sim 运行中（ack85=%s ack74=%s ackcf=%s ack53=%s），Ctrl+C 退出 ..."
          % (a.ack85, a.ack74, a.ackcf, a.ack53), flush=True)
    try:
        import time
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            dev.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
