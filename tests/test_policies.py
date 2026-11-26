# -*- coding: utf-8 -*-
"""tests/test_policies.py —— 判稳/判停策略的离线回归（不碰设备、不碰端口）。

跑法：
    python -I tests/test_policies.py

三类用例：
  A. 数学正确性（合成信号，可精确断言）
  B. 真机数据标定（桌面 10.31与11.3数据 里的真实曲线，只读）
  C. 契约一致性（Python 策略的默认值 == C# 宿主里的默认值）
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code"))

import policies as P  # noqa: E402

DATA = r"C:\Users\xiyve\Desktop\10.31与11.3数据"

PASS = FAIL = 0
FAILS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        FAILS.append("%s %s" % (name, detail))
        print("  FAIL  %s   %s" % (name, detail))


def synth(n=600, dt=0.5, drift_until=200.0, drift_rate=0.0002, noise=0.00002, base=-0.16):
    s = []
    for k in range(n):
        t = k * dt
        e = base + min(t, drift_until) * drift_rate + noise * math.sin(k)
        s.append((t, e, 1e-10, math.nan))
    return s


def main():
    print("\n[A] 数学正确性")

    # A1 完全平直的电势 -> 立即可判稳（只要 hold 到点）
    flat = [(k * 0.5, -0.15 + 1e-7 * (k % 3), 1e-10, math.nan) for k in range(400)]
    hit = P.scan_stabilize(flat, window_sec=30, hold_sec=30,
                           slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
    check("A1 平直信号能判稳", hit is not None and abs(hit["E"] + 0.15) < 1e-4,
          repr(hit))

    # A2 持续大斜率漂移 -> 永不判稳
    ramp = [(k * 0.5, -0.16 + k * 0.5 * 0.01, 1e-10, math.nan) for k in range(600)]
    hit2 = P.scan_stabilize(ramp, window_sec=30, hold_sec=30,
                            slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
    check("A2 大漂移不误判", hit2 is None, repr(hit2))

    # A3 ★ 斜率抵消陷阱：正弦绕圈时斜率接近 0 但峰峰值很大 —— 必须靠峰峰值拦住
    osc = [(k * 0.5, -0.15 + 0.02 * math.sin(k * 0.05), 1e-10, math.nan) for k in range(500)]
    det = P.StabilizeDetector(window_sec=30, hold_sec=10,
                              slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
    st = det.window_stats(osc[:200])
    check("A3 振荡信号斜率可能小", st is not None,
          "窗口统计应可算")
    check("A3 峰峰值硬约束拦住振荡", st["peak_to_peak_mv"] > 5.0,
          "ptp=%.1f mV 应 > 5" % (st["peak_to_peak_mv"]))
    check("A3 不判稳", det.update(osc[:200], osc[199][0])[0] is False,
          "")

    # A4 hold_sec 必须真的等够
    good = [(k * 0.5, -0.15, 1e-10, math.nan) for k in range(400)]
    d2 = P.StabilizeDetector(window_sec=30, hold_sec=60,
                             slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
    hit_at = None
    for k in range(4, len(good)):
        done, why, _ = d2.update(good[:k + 1], good[k][0])
        if done:
            hit_at = good[k][0]
            break
    check("A4 hold_sec=60 生效", hit_at is not None and hit_at >= 60.0,
          "判稳于 t=%.1f（应 >=60）" % (hit_at or -1))

    # A5 判停：连续 confirm_n 次才触发
    def run_stop(seq, limit=5.0, confirm=2):
        d = P.CurrentDensityStopper(limit=limit, confirm_n=confirm)
        for k, i in enumerate(seq):
            done, why = d.update([(k * 0.1, 0.0, i, 0.0)], k * 0.1)
            if done:
                return k
        return None

    check("A5 单点越限不触发（confirm=2）", run_stop([0.1, 6.0, 0.1, 6.0]) is None, "")
    check("A5 连续两点越限触发", run_stop([0.1, 6.0, 6.0]) == 2, "")
    check("A5 负值取绝对值", run_stop([-6.0, -6.0]) == 1, "")

    # A6 TimeLimit
    d3 = P.TimeLimit(sec=5)
    check("A6 未到点不触发", d3.update([], 4.9)[0] is False, "")
    check("A6 到点触发", d3.update([], 5.0)[0] is True, "")

    # A7 空/短序列不炸
    check("A7 空序列安全", P.StabilizeDetector().window_stats([]) is None, "")
    check("A7 两点序列安全", P.StabilizeDetector().window_stats([(0, 0, 0, 0), (1, 0, 0, 0)]) is None, "")

    print("\n[B] 真机数据标定（只读，不占端口）")
    files = []
    if os.path.isdir(DATA):
        files = [os.path.join(DATA, f) for f in sorted(os.listdir(DATA))
                 if "OCP" in f and f.endswith(".txt")]
        files += [os.path.join(DATA, f) for f in sorted(os.listdir(DATA))
                  if "开路电位" in f and f.endswith(".txt")]
    else:
        print("  SKIP  真机数据目录不存在：%s" % DATA)

    for f in files:
        s = P.read_csstudio_txt(f)
        name = os.path.basename(f)
        check("B 可读 %s" % name, len(s) > 100, "%d 点" % len(s))
        if len(s) < 100:
            continue
        dur = s[-1][0]
        hit = P.scan_stabilize(s, window_sec=30, hold_sec=60,
                               slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
        # 真实曲线应当能在时长内判稳（若判不稳，至少要能给出合理窗口统计）
        if hit:
            check("B %s 判稳点合理" % name, 0 < hit["t"] <= dur and not math.isnan(hit["E"]),
                  "t=%.1fs E=%.6f" % (hit["t"], hit["E"]))
            print("        -> t=%.1fs E=%.6f V slope=%.2f mV/min ptp=%.2f mV"
                  % (hit["t"], hit["E"], hit["stats"]["slope_mv_per_min"],
                     hit["stats"]["peak_to_peak_mv"]))
        else:
            print("        -> 未判稳（该曲线全程漂移，属正常；靠 max_sec 兜底）")

    print("\n[C] 契约一致性（Python 默认值 vs C# 宿主）")
    d = P.StabilizeDetector()
    check("C slope 默认 5.0", d.slope_mv_per_min == 5.0, str(d.slope_mv_per_min))
    check("C ptp 默认 5.0", d.peak_to_peak_mv == 5.0, str(d.peak_to_peak_mv))
    check("C window 默认 30", d.window_sec == 30.0, str(d.window_sec))
    check("C hold 默认 60", d.hold_sec == 60.0, str(d.hold_sec))
    c = P.CurrentDensityStopper()
    check("C current limit 默认 5.0", c.limit == 5.0, str(c.limit))
    check("C confirm_n 默认 2", c.confirm_n == 2, str(c.confirm_n))

    # 与 C# 源码文本比对（避免两边改歪）
    cs = os.path.join(ROOT, "code", "cshost", "CsPilotHost.cs")
    if os.path.exists(cs):
        src = open(cs, encoding="utf-8").read()
        for probe, label in [
            ('"slope_mv_per_min", 5.0', "C# slope 默认 5.0"),
            ('"peak_to_peak_mv", 5.0', "C# ptp 默认 5.0"),
            ('"window_sec", 30', "C# window 默认 30"),
            ('"hold_sec", 60', "C# hold 默认 60"),
            ('"limit", 5.0', "C# current limit 默认 5.0"),
            ('"confirm_n", 2', "C# confirm_n 默认 2"),
        ]:
            check(label, probe in src, "C# 源码里没找到 %r" % probe)

    print("\n==== 汇总：%d PASS / %d FAIL ====" % (PASS, FAIL))
    if FAILS:
        for f in FAILS:
            print("  ! " + f)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
