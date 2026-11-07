# -*- coding: utf-8 -*-
"""resume_tafel.py —— 续跑：只起动电位（OCP/阻抗已完成，等待用户口令后执行）。

流程：连接 → 清场（顺带收掉阻抗残留窗）→ 跳过 OCP/阻抗 → 直接 Tafel。
用法：python resume_tafel.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import runner6 as R6
import graceful_exit

LOG = r"D:\deepseek\_probe\live_jkf\resume_tafel.log"
_lines = []


def log(m):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    _lines.append(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    cfg = R6.RunConfig6(
        sample="JK-F",
        area_cm2=1.0,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
    )
    r = R6.Runner6(cfg, log=log)
    log("=" * 60)
    log("续跑：只起动电位（JK-F / 1.0 cm²，OCP/阻抗已完成）")
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)

    # 等连接+清场完成：状态一到 S_OCP_OPEN（清场完毕、OCP 窗还没开）就
    # 立即改道 S_T_OPEN——旧条件只认 S_CONNECT，在 S_PREPARE 就退出循环，
    # 跳转被错过、OCP 照跑（2026-11-07 真机纠正）
    t_end = time.time() + 120
    while r.running and r.state != R6.S_OCP_OPEN and time.time() < t_end:
        r.tick()
        time.sleep(0.25)
    if r.state == R6.S_OCP_OPEN:
        log("清场完成 → 直接进入动电位阶段（跳过 OCP）")
        r.set_state(R6.S_T_OPEN)
        r.stage_t0 = time.time()
    while r.running:
        r.tick()
        time.sleep(0.25)
    if r.state not in ("完成", "出错", "已中止") and r.running:
        graceful_exit.drain(r, log, lambda: r.tick())
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
