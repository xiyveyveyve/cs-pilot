# -*- coding: utf-8 -*-
"""test_fleet.py —— fleet 编排器离线测试（假 runner，绝不碰真实软件）。

覆盖：
  T1 正常监督：两台假机器稳定运行 6s，状态表正确
  T2 崩溃复活：硬退出的机器连续复活 ≥2 次，且 --resume 标志传递到位
  T3 熔断：--crash 连死 3 次后标记熔断、不再复活
  T4 全局急停：CTRL_BREAK → 优雅退出
运行：python test_fleet.py （全程 <90s，不碰任何串口/软件）
"""
from __future__ import annotations

import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import fleet as F

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "testbed", "fake_runner.py")
HB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "_auto", "hb")
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


def t1_normal():
    machines = [
        {"name": "FAKE-A", "script": FAKE, "version": 6, "area": 1.0},
        {"name": "FAKE-B", "script": FAKE, "version": 5, "area": 1.0},
    ]
    fl = F.Fleet(machines)
    fl.launch_all(resume=False)
    t_end = time.time() + 6
    while time.time() < t_end:
        time.sleep(0.5)
        fl.supervise_round()
    ok = all(st["proc"].poll() is None for st in fl.state.values())
    check("T1 两台稳定运行 6s 无误杀", ok)
    fl.stop_all()
    time.sleep(1)
    ok2 = all(st["proc"].poll() is not None for st in fl.state.values())
    check("T1 急停后全部退出", ok2)


def t2_revive():
    """硬退出的机器被自动复活 ≥2 次，且 --resume 传到位。"""
    import subprocess
    machines = [{"name": "FAKE-DIE", "script": FAKE, "version": 6,
                 "args_extra": ["--die-after", "4"]}]
    fl = F.Fleet(machines)
    fl.launch(machines[0], resume=False)
    t_end = time.time() + 40
    marks = 0
    while time.time() < t_end:
        time.sleep(1)
        fl.supervise_round()
        st = fl.state["FAKE-DIE"]
        if st["proc"].poll() is None:
            mk = os.path.join(HB_DIR, "FAKE-DIE.got_resume")
            if os.path.exists(mk):
                marks += 1
        if st["restarts"] >= 2:
            break
    check("T2 自动复活 ≥2 次", fl.state["FAKE-DIE"]["restarts"] >= 2,
          "restarts=%d" % fl.state["FAKE-DIE"]["restarts"])
    check("T2 --resume 标志传递到位", marks >= 1, "marks=%d" % marks)
    stop_machine_safe(fl, "FAKE-DIE")
    return fl.state["FAKE-DIE"]["restarts"] >= 2


def t3_fuse():
    machines = [{"name": "FAKE-FUSE", "script": FAKE, "version": 6,
                 "args_extra": ["--crash"]}]
    fl = F.Fleet(machines)
    fl.launch(machines[0], resume=False)
    t_end = time.time() + 30
    while time.time() < t_end:
        time.sleep(1)
        fl.supervise_round()
        if fl.state["FAKE-FUSE"].get("failed"):
            break
    check("T3 连死熔断（failed=True）",
          fl.state["FAKE-FUSE"].get("failed") is True)
    return fl.state["FAKE-FUSE"].get("failed") is True


def t4_ctrl_break():
    machines = [{"name": "FAKE-STOP", "script": FAKE, "version": 6}]
    fl = F.Fleet(machines)
    fl.launch(machines[0], resume=False)
    time.sleep(2)
    proc = fl.state["FAKE-STOP"]["proc"]
    F.stop_machine(proc)
    try:
        rc = proc.wait(timeout=10)
    except Exception:
        proc.kill()
        rc = "超时"
    check("T4 CTRL_BREAK 优雅退出（rc=0）", rc == 0, "rc=%r" % rc)
    return rc == 0


def stop_machine_safe(fl, name):
    st = fl.state.get(name)
    if st and st["proc"].poll() is None:
        F.stop_machine(st["proc"])


if __name__ == "__main__":
    t1_normal()
    t2_revive()
    t3_fuse()
    t4_ctrl_break()
    print()
    if FAILS:
        print("FAIL %d 项：%r" % (len(FAILS), FAILS))
        sys.exit(1)
    print("全部 %d 项 PASS" % PASSED)
