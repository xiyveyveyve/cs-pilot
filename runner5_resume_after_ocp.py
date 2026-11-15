# -*- coding: utf-8 -*-
"""runner5_resume_after_ocp.py —— 5 版续跑：跳过 OCP，直接阻抗 → 动电位。

场景：OCP 已经跑够（判稳或 1800 s 到点自动停），但 runner5 收尾时「停止」
没停住、按 S_ERROR 退出；OCP 数据文件已足够，用本脚本从「阻抗」续跑。

用法：
    python runner5_resume_after_ocp.py [样品] [面积] [hwnd] [sn] [--no-eis] [--no-tafel]

必须条件：CS Studio5 处于空闲（没有运行窗），OCP 数据已落盘。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import graceful_exit
import runner5 as R5

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG = None


def log(m):
    global LOG
    if LOG is None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        LOG = os.path.join(_LOG_DIR, "resume_ocp_%s.log" % time.strftime("%m%d_%H%M"))
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
    eis = "--no-eis" not in sys.argv
    tafel = "--no-tafel" not in sys.argv

    cfg = R5.RunConfig5(
        sample=sample,
        area_cm2=area,
        item="Tafel",
        sn=sn,
        cs_hwnd=hwnd,
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=eis,
        ocp_time_sec=1800.0,
        ocp_freq_hz=10.0,
        max_ocp_sec=1800.0,
        ocp_max_rounds=3,
        tafel_init_v=-0.5,
        tafel_final_v=1.5,
        tafel_scan_mv_s=0.33,
        tafel_interval_s=0.5,
    )
    # 5 版动电位「自动停止」：软件侧扫描停止电流 = 绝对电流 mA（1e-3 A = 1 mA，不乘面积）
    cfg.tafel_stop_ma = float(cfg.test_stop_i_density or 1e-3) * 1000.0

    r = R5.Runner5(cfg, log=log)
    log("=" * 60)
    log("5 版续跑：跳过 OCP，直接%s（%s / %g cm²）"
        % ("阻抗→动电位" if eis else "动电位", sample, area))
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)

    # 等连接完成（runner5 没有独立的清场状态，连接后直接进 S_OCP_OPEN）
    t_end = time.time() + 240
    while r.running and r.state == R5.S_CONNECT and time.time() < t_end:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        time.sleep(0.25)
    if r.state == R5.S_OCP_OPEN:
        target = R5.S_EIS_OPEN if eis else R5.S_T_OPEN
        log("清场完成 → 跳过 OCP，直接进入「%s」" % target)
        r.set_state(target)
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
