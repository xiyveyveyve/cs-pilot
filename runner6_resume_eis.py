# -*- coding: utf-8 -*-
"""runner6_resume_eis.py —— 6 版续跑：跳过 OCP，直接阻抗 → 动电位。

场景：OCP 跑满整轮（1800 s）仍判不稳，用户决定不再重跑 OCP，直接用现有
开路电位数据接阻抗与动电位（2026-11-13 进口老DC18V 实测）。

流程：连接 CS Studio6（按 hwnd/sn 锁定实例）→ 清场完成（S_OCP_OPEN）
      → 跳转 S_EIS_OPEN → 阻抗 → 动电位。
用法：python runner6_resume_eis.py [样品] [面积] [hwnd] [sn] [--no-tafel]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import graceful_exit
import runner6 as R6

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG = None


def log(m):
    global LOG
    if LOG is None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        LOG = os.path.join(_LOG_DIR, "resume_eis_%s.log" % time.strftime("%m%d_%H%M"))
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-F"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    hwnd = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    sn = sys.argv[4] if len(sys.argv) > 4 else ""
    no_tafel = "--no-tafel" in sys.argv
    cfg = R6.RunConfig6(
        sample=sample,
        area_cm2=area,
        item="Tafel",
        sn=sn,
        cs_hwnd=hwnd,
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=True,
        tafel_enabled=not no_tafel,
        tafel_init_v=-0.5,
        tafel_final_v=1.5,
        tafel_scan_mv_s=0.33,
        tafel_vs_ocp=True,
    )
    r = R6.Runner6(cfg, log=log)
    log("=" * 60)
    log("6 版续跑：跳过 OCP，直接阻抗→动电位（%s / %g cm²）" % (sample, area))
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)

    # 等连接 + 清场完成（S_OCP_OPEN）→ 跳到阻抗
    t_end = time.time() + 240
    while r.running and r.state in (R6.S_CONNECT, R6.S_PREPARE) and time.time() < t_end:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        time.sleep(0.25)
    if r.state == R6.S_OCP_OPEN:
        log("清场完成 → 跳过 OCP，直接进入阻抗阶段")
        r.set_state(R6.S_EIS_OPEN)
        r._step_at = time.time()
    else:
        log("!! 状态异常：%s %s" % (r.state, r.detail))
        return 1

    last_state = None
    while r.running:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        time.sleep(0.25)
        if r.state != last_state:
            log("[状态] %s  %s" % (r.state, r.detail))
            last_state = r.state
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
