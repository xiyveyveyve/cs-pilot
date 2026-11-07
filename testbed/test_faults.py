# -*- coding: utf-8 -*-
"""test_faults.py —— simdevice 故障注入与并发回归（2026-11-07 审查修复配套）。

覆盖：
  G. 发射节拍：0x51 改率必须生效（含夹紧）、停顿欠账丢弃语义
  H. Parser 恶劣流：半帧跨 feed/粘包、坏帧内嵌合法帧的恢复、巨 LEN 拒绝、垃圾洪水
  I. JSONL 落盘健壮性：目录不存在自动建
  J. 并发与状态机：多线程 handle_frame、wait_start 生命周期、ReadOcp 并发冒烟

运行：python testbed/test_faults.py （全程离线，不碰串口）
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simdevice as sd   # noqa: E402


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


def near(a, b, tol=1e-9, msg=""):
    assert abs(a - b) <= tol, "%s 实际 %r 期望 %r (tol %g)" % (msg, a, b)


def mkdev(**kw):
    kw.setdefault("verbose", False)
    return sd.SimDevice(None, **kw)


def noise_start(hz, test_time=200.0):
    return sd.build("NoiseStart", struct.pack("<3f", float(hz), float(test_time), 0.0))


def group_g(ck):
    def g1_rate_applies():
        dev = mkdev()
        near(dev._emitter_period(), 0.1, msg="默认 hz=10 → 0.1s")
        dev.handle_frame(noise_start(2.0))
        near(dev._emitter_period(), 0.5, msg="0x51 hz=2 → 0.5s（旧版不生效，本次修复）")
        dev.handle_frame(noise_start(5.0))
        near(dev._emitter_period(), 0.2, msg="再次改率仍生效")
    ck.check("G1 0x51 改采样率后发射节拍立即生效", g1_rate_applies)

    def g2_clamp():
        dev = mkdev()
        dev.handle_frame(noise_start(0.05))     # 低于下限
        near(dev._emitter_period(), 10.0, msg="hz=0.05 夹紧到 0.1Hz → 10s")
        dev.handle_frame(noise_start(2000.0))   # 高于上限
        near(dev._emitter_period(), 0.001, msg="hz=2000 夹紧到 1000Hz → 1ms")
    ck.check("G2 采样率夹紧 0.1~1000Hz 在节拍上生效", g2_clamp)

    def g3_advance():
        now = 1000.0
        p = 0.1
        near(sd.SimDevice._emitter_advance(999.97, now, p), 1000.07,
             msg="正常：next_t += period")
        near(sd.SimDevice._emitter_advance(now - 3 * p, now, p), now,
             msg="欠账 >2 周期：丢弃（防补帧风暴）")
        near(sd.SimDevice._emitter_advance(now - 2 * p, now, p), now - p,
             msg="欠账恰 2 周期：不丢（严格小于才丢）")
    ck.check("G3 发射时刻表推进：停顿欠账超 2 周期丢弃", g3_advance)

    def g4_simrx_inherits():
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import sim_rx
        dev = sim_rx.SimRx(None, verbose=False)
        dev.handle_frame(noise_start(4.0))
        near(dev._emitter_period(), 0.25, msg="SimRx 同样吃 0x51 改率")
    ck.check("G4 sim_rx.SimRx 继承修复后的节拍语义", g4_simrx_inherits)


def group_h(ck):
    def h1_split_and_sticky():
        ps = sd.Parser()
        f1 = sd.build("GetPstType", bytes([8]))
        f2 = sd.build("CSStart")
        stream = f1 + f2
        out = []
        for i in range(0, len(stream), 3):       # 3 字节一喂，强制跨帧切分
            out += ps.feed(stream[i:i + 3])
        eq(len(out), 2)
        eq(out[0]["cmd"], 0x14)
        eq(out[1]["cmd"], 0x30)
        eq(ps.buf, b"", "流尽后无残留")
    ck.check("H1 半帧跨 feed + 粘包切分", h1_split_and_sticky)

    def h2_embedded_frame_recovery():
        # 坏帧（SUM 损坏）体内嵌一个合法帧 → 修复后必须被找回（旧实现整段丢弃）
        inner = sd.build("GetPstType", bytes([8]))
        outer = bytearray(sd.build(0x77, inner + b"\x00" * 4))
        outer[-1] ^= 0xFF                        # 损坏 SUM
        tail = sd.build("CSStart")
        ps = sd.Parser()
        frames = ps.feed(bytes(outer) + tail)
        cmds = [f["cmd"] for f in frames]
        eq(cmds.count(0x14), 1, "内嵌合法帧被找回（旧实现丢失）")
        eq(cmds.count(0x30), 1, "尾部正常帧也在")
        eq(ps.stats["bad_sum"], 1)
    ck.check("H2 坏帧体内嵌合法帧：重扫恢复不丢失", h2_embedded_frame_recovery)

    def h3_giant_len():
        ps = sd.Parser()
        junk = b"\x55\xAA\xFF\xFF\x30\x00" * 3 + sd.build("CSStart")
        frames = ps.feed(junk)
        eq(len(frames), 1, "巨 LEN 拒绝后流恢复")
        eq(frames[0]["cmd"], 0x30)
        assert ps.stats["bad_len"] >= 1
    ck.check("H3 LEN=0xFFFF 巨帧拒绝并恢复", h3_giant_len)

    def h4_garbage_flood():
        ps = sd.Parser()
        frames = ps.feed(b"\x01\x02\x03" * 1365 + sd.build("CSStart"))   # 4095B 垃圾
        eq(len(frames), 1)
        eq(ps.stats["dropped"], 4095, "垃圾字节全计数")
    ck.check("H4 无头垃圾洪水：全量丢弃并计数", h4_garbage_flood)

    def h5_no_hang_on_hostile_stream():
        ps = sd.Parser()
        rng = __import__("random").Random(7)
        blob = bytes(rng.randrange(256) for _ in range(8192))
        blob += sd.build("CSStart")
        t0 = time.time()
        frames = ps.feed(blob)
        dt = time.time() - t0
        assert dt < 2.0, "敌意流解析必须在有限时间完成（实测 %.2fs）" % dt
        assert any(f["cmd"] == 0x30 for f in frames), "尾部合法帧仍被找到"
    ck.check("H5 8KB 敌意随机流：有界时间完成且不错杀合法帧", h5_no_hang_on_hostile_stream)


def group_i(ck):
    def i1_logdir_autocreate():
        dev = mkdev()
        with tempfile.TemporaryDirectory() as td:
            dev.log_path = os.path.join(td, "not", "yet", "created", "frames.jsonl")
            dev.handle_frame(sd.build("CSStart"))
            dev.handle_frame(sd.build("GetPstType", bytes([8])))
            dev.close_log()
            with open(dev.log_path, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            eq(len(lines), 4, "CSStart rx+tx(2) + GetPstType rx+tx(2)")
            eq(lines[0]["dir"], "rx")
    ck.check("I1 JSONL 目录不存在：自动创建并完整落盘", i1_logdir_autocreate)

    def i2_bad_logdir_no_crash():
        dev = mkdev()
        # 指向一个必然失败的路径（Windows 保留名）——不允许炸掉调用线程
        dev.log_path = r"\\\\.\\COM90\\x.jsonl"
        try:
            dev.handle_frame(sd.build("CSStart"))
            dev.handle_frame(sd.build("GetPstType", bytes([8])))
        except Exception as e:
            raise AssertionError("落盘失败不应影响帧处理: %r" % (e,))
        eq(len(dev.records) >= 2, True, "内存镜像不受影响")
        dev.log_path = None
    ck.check("I2 JSONL 落盘失败：帧处理不受影响、只报一次", i2_bad_logdir_no_crash)


def group_j(ck):
    def j1_concurrent_dispatch():
        dev = mkdev()
        cmds = [sd.build("GetPstType", bytes([8])),
                sd.build("CSStart"),
                sd.build("ReadOcp"),
                sd.build(0x77, b"\x01"),
                sd.build("CSStop")]
        errors = []

        def worker():
            try:
                for _ in range(150):
                    dev.handle_frame(cmds[__import__("random").randrange(len(cmds))])
            except Exception as e:      # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        eq([t.is_alive() for t in threads], [False] * 4, "无死锁（30s 内全部结束）")
        eq(errors, [], "并发帧处理零异常")
        eq(dev.summary()["recv"], 4 * 150, "recv 计数精确")
    ck.check("J1 4 线程并发 handle_frame 600 帧：零异常零死锁、计数精确", j1_concurrent_dispatch)

    def j2_waitstart_lifecycle():
        dev = mkdev(wait_start=True)
        dev.handle_frame(noise_start(10.0))
        assert not dev.streaming, "wait_start：参数帧不推流"
        dev.handle_frame(sd.build("CSStart"))
        assert dev.streaming and dev.mode == "ocp"
        dev.handle_frame(sd.build("CSPause"))
        assert dev.paused and not dev.streaming
        dev.handle_frame(sd.build("CSStart"))
        assert dev.streaming, "暂停后 CSStart 恢复"
        dev.handle_frame(sd.build("CSStop"))
        assert dev.mode is None and not dev.streaming
    ck.check("J2 --wait-start 生命周期：参数帧→CSStart→暂停→恢复→停止", j2_waitstart_lifecycle)

    def j3_readocp_vs_emitter_rng():
        # ReadOcp（锁内 ocp_point）与模拟发射生成（锁内 make_ei_frame）并发冒烟：
        # 验证互斥不重入死锁、Random 并发不炸
        dev = mkdev()
        dev.handle_frame(sd.build("CSPotDynamic",
                                  struct.pack("<7f", 5.0, -0.3, 0.0, 0.0,
                                              0.9, 0.00033, 0.66)))
        stop = threading.Event()
        errs = []

        def reader():
            while not stop.is_set():
                try:
                    dev.handle_frame(sd.build("ReadOcp"))
                except Exception as e:      # noqa: BLE001
                    errs.append(repr(e))

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        for _ in range(2000):
            try:
                with dev._lock:
                    dev.make_ei_frame()
            except Exception as e:          # noqa: BLE001
                errs.append(repr(e))
                break
        stop.set()
        th.join(timeout=10)
        eq(errs[:3], [], "rng/共享状态并发零异常")
    ck.check("J3 ReadOcp × 发射生成并发 2000 次：互斥正确无异常", j3_readocp_vs_emitter_rng)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ck = Checks()
    print("== G 发射节拍 ==")
    group_g(ck)
    print("== H Parser 恶劣流 ==")
    group_h(ck)
    print("== I JSONL 落盘 ==")
    group_i(ck)
    print("== J 并发与状态机 ==")
    group_j(ck)
    print()
    print("PASS %d / FAIL %d" % (len(ck.passed), len(ck.failed)))
    for name, err in ck.failed:
        print("  FAIL %s -> %s" % (name, err))
    return 0 if ck.ok else 1


if __name__ == "__main__":
    sys.exit(main())
