# -*- coding: utf-8 -*-
"""runner5_resume_tafel.py —— 5 版续跑：跳过 OCP，直接动电位（JK-N 下次会话用）。

前置：OCP 已测完（如 2026-11-07-JK-N-开路电位.cor 已在数据目录）。
流程：连接 CS Studio5 → 状态一到 S_OCP_OPEN（连接完成）→ 跳转 S_T_OPEN
→ 填动电位参数 → 启动 → 监视（UI 读数判流，1e-3 A/cm² 自动停）。
用法：python runner5_resume_tafel.py [样品型号] [面积cm2]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from runner5 import Runner5, RunConfig5, S_CONNECT, S_OCP_OPEN, S_T_OPEN
import graceful_exit
from stabilizer import StabConfig

_LOG_DIR = r"D:\deepseek\_probe\live_jkn"
LOG = None
_lines = []


def log(m):
    global LOG
    if LOG is None:
        LOG = os.path.join(_LOG_DIR, "tafel_%s.log" % time.strftime("%H%M%S"))
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
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-N"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    cfg = RunConfig5(
        sample=sample,
        area_cm2=area,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=False,
        ocp_time_sec=1800.0,
        ocp_freq_hz=10.0,
        max_ocp_sec=1800.0,
        tafel_init_v=-0.5,
        tafel_final_v=1.5,
        tafel_scan_mv_s=0.33,
        tafel_interval_s=0.5,
    )
    r = Runner5(cfg, log=log)
    log("=" * 60)
    log("5 版续跑：跳过 OCP，直接动电位（%s / %g cm²）" % (sample, area))
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)

    # 等连接完成（状态到 S_OCP_OPEN）→ 跳转到动电位
    t_end = time.time() + 180
    while r.running and r.state == S_CONNECT and time.time() < t_end:
        r.tick()
        time.sleep(0.25)
    if r.state == S_OCP_OPEN:
        log("连接完成 → 直接进入动电位阶段（跳过 OCP）")
        r.set_state(S_T_OPEN)
        r._step_at = time.time()
    else:
        log("!! 状态异常：%s" % r.state)
        return 1

    last_state = None
    while r.running:
        r.tick()
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
