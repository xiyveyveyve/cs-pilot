# -*- coding: utf-8 -*-
"""runner6_live.py —— 首次真机端到端：JK-F / 1cm² / OCP→阻抗→动电位（6 版直开）。

与 gui.py 同一套 runner6（直开模式），只是用命令行驱动并把全部日志落盘。
用法：python runner6_live.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import runner6 as R6
import graceful_exit

LOG = r"D:\deepseek\_probe\live_jkf\run.log"
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
    # 参数化：python runner6_live.py [样品型号] [面积cm2] [测试项目] [no-eis]
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-F"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    item = sys.argv[3] if len(sys.argv) > 3 else "Tafel"
    no_eis = "no-eis" in sys.argv
    cfg = R6.RunConfig6(
        sample=sample,
        area_cm2=area,
        item=item,
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=not no_eis,
    )
    r = R6.Runner6(cfg, log=log)
    log("=" * 60)
    chain = "OCP→%s" % (item if no_eis else "阻抗→" + item)
    log("真机运行：%s / %g cm² / %s（6 版直开）" % (sample, area, chain))
    for k, v in cfg.__dict__.items():
        if not k.startswith("_"):
            log("  cfg.%s = %r" % (k, v))
    log("=" * 60)
    r.start()
    # 优雅退出：Ctrl+C / 关控制台 → 自动中止实验并收尾（真机首跑事故教训；
    # taskkill /F 任何程序都拦不住，属管理动作）
    graceful_exit.install(lambda: r, log)
    t0 = time.time()
    last_beat = 0.0
    while r.running:
        r.tick()
        time.sleep(0.25)
        # 每 60s 一条心跳，便于远端观察
        if time.time() - last_beat > 60.0:
            last_beat = time.time()
            log("[心跳] state=%s detail=%s 运行 %.0f s" % (r.state, r.detail, time.time() - t0))
    if r.running:
        graceful_exit.drain(r, log, lambda: r.tick())
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
