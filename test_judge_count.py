# -*- coding: utf-8 -*-
"""test_judge_count.py —— 电流判停"只计新点"修复的回归测试。

背景（2026-11-07 审查 P1）：数据约 3s 才 flush 一次而 tick 250ms 一次，
按 tick 对同一个 samples[-1] 反复 +1 的话，单点尖峰一次 flush 间隔内就
攒满 2 → 防噪设计失效。修复后只有"新到的点"才参与计数。

运行：python test_judge_count.py （离线，不碰软件）
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner6 as R6
from watch import Sample

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


class FakeTail:
    def __init__(self, samples):
        self.samples = samples

    def poll(self):
        return []

    def size(self):
        return 100

    def finished_quiet(self, quiet_sec=10.0):
        return False


class FakeDD:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


def make_runner(samples):
    cfg = R6.RunConfig6(item="Tafel", test_stop_i_density=1e-3,
                        test_timeout_sec=1e9)
    r = R6.Runner6(cfg, log=lambda m: None)
    r.running = True
    r.state = R6.S_MON_TEST
    r.tail_test = FakeTail(samples)
    r.dd = FakeDD()
    r.test_first_data_at = time.time() - 30     # 越过 15s 等待期
    # 本回归只测判停计数；收尾闸门（菜单未恢复→S_ERROR）由
    # test_cs6_settle_gate.py 覆盖。假环境无 ui，真收尾会空等 60s 菜单。
    # 2026-11-14 审查 #13：判停分支不再锁外裸 stop，停止统一在
    # _settle_after_stop（持 UI 锁）里完成 → 这里记录 settle 调用。
    r._settle_calls = []
    r._settle_after_stop = lambda label, idle=0: r._settle_calls.append(label) or True
    return r


def ticked(r, n=1):
    for _ in range(n):
        r.tick()


def t_single_spike_not_double_counted():
    """同一个点被 tick 多次只能计 1 次——旧实现一次 flush 间隔就攒满 2。"""
    r = make_runner([Sample(t=1.0, e=0.1, i=2e-3)])      # 单点超阈值
    ticked(r, 12)                                        # ~3s 的 tick 量
    check("单点尖峰连 tick 12 次不触发停止", r.state != R6.S_DONE,
          "state=%r stops=%d" % (r.state, r.dd.stops))
    check("单点尖峰不产生 stop 调用", r.dd.stops == 0, "stops=%d" % r.dd.stops)


def t_two_new_points_stop():
    """两个"新到的点"连续达标才停（设计语义）。"""
    r = make_runner([Sample(t=1.0, e=0.1, i=2e-3)])
    ticked(r, 3)
    r.tail_test.samples.append(Sample(t=4.0, e=0.1, i=2e-3))   # 新点（模拟 flush）
    ticked(r, 3)
    check("两个新点连续达标 → 停止", r.state == R6.S_DONE,
          "state=%r i_hit=%r" % (r.state, getattr(r, "_i_hit", None)))
    check("停止经 settle 在锁内完成（不再锁外裸 stop）",
          r._settle_calls == ["测试项"] and r.dd.stops == 0,
          "settle=%r stops=%d" % (r._settle_calls, r.dd.stops))


def t_below_threshold_resets():
    """新点低于阈值必须清零计数（尖峰后回落不误停）。"""
    r = make_runner([Sample(t=1.0, e=0.1, i=2e-3)])
    ticked(r, 3)                                          # hit=1
    r.tail_test.samples.append(Sample(t=4.0, e=0.1, i=1e-5))   # 新点低于阈值
    ticked(r, 3)
    check("低于阈值的新点清零计数", getattr(r, "_i_hit", 0) == 0,
          "i_hit=%r" % getattr(r, "_i_hit", None))
    check("未触发停止", r.state != R6.S_DONE)


def t_spike_then_new_spike():
    """尖峰→(低于阈值新点)→尖峰：不得累积成连续 2 点。"""
    r = make_runner([Sample(t=1.0, e=0.1, i=2e-3)])
    ticked(r, 2)
    r.tail_test.samples.append(Sample(t=4.0, e=0.1, i=1e-5))
    ticked(r, 2)
    r.tail_test.samples.append(Sample(t=7.0, e=0.1, i=3e-3))
    ticked(r, 2)
    check("隔一个低点后 hit 不累积到 2", r.state != R6.S_DONE,
          "state=%r i_hit=%r" % (r.state, getattr(r, "_i_hit", None)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t_single_spike_not_double_counted()
    t_two_new_points_stop()
    t_below_threshold_resets()
    t_spike_then_new_spike()
    print()
    if FAILS:
        print("FAIL %d 项：%r" % (len(FAILS), FAILS))
        sys.exit(1)
    print("全部 %d 项 PASS" % PASSED)
