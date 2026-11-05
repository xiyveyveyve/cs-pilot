# -*- coding: utf-8 -*-
"""selftest_runner.py —— 不走 GUI，直接驱动 Runner 跑完整流程，验证状态机。

用法：python selftest_runner.py
短扫描模式：Tafel 只扫 ±0.05 V（0.5 mV/s -> 约 200 s），几分钟就能跑完全流程。
"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner as R
from stabilizer import StabConfig

OUT = r"D:\deepseek\_probe\e2e"
os.makedirs(OUT, exist_ok=True)

T0 = time.time()
def log(m):
    print("%7.1fs %s" % (time.time() - T0, m), flush=True)

cfg = R.RunConfig(
    sample="SELFTEST",
    area_cm2=2.0,
    item="Tafel",
    eis_enabled=False,      # 序列里没有阻抗行；EIS 流程由直开模式与 5 版覆盖
    out_dir=OUT,
    ocp_time_sec=600,
    ocp_freq_hz=10.0,
    stab=StabConfig(slope_limit_mv_per_min=5.0, window_sec=20.0,
                    peak_to_peak_mv=5.0, hold_sec=15.0, min_points=20),
    max_ocp_sec=300.0,
    tafel_init_v=-0.05,
    tafel_final_v=0.05,
    tafel_scan_mv_s=0.5,
    tafel_interval_s=0.5,
    test_timeout_sec=1200.0,
)

r = R.Runner(cfg, log=log, on_state=lambda s, d: log("STATE=%s %s" % (s, d)))

# 若上一轮实验还在跑，先停掉（实验运行中序列是锁定的，双击打不开参数窗）
try:
    from studio_ui import Studio
    from driver import ParasiteDriver
    u = Studio(); u.log = log
    d = ParasiteDriver(u, log=log)
    for i in range(60):
        pnl = u.open_row_panel(0)
        if pnl is not None:
            u.press_cancel(pnl)
            time.sleep(0.5)
            u.clear_modals(2)
            log("序列可编辑（等待 %d 轮）" % i)
            break
        log("  序列锁定，尝试停止上一轮实验…（第 %d 轮）" % (i + 1))
        d.stop_current()
        time.sleep(6)
    else:
        log("警告：等不到空闲状态，仍继续尝试")
except Exception as e:
    log("预检查跳过：%s" % e)

log("输出文件：%r" % R.build_filenames(cfg))
r.start()

deadline = time.time() + 1800
while r.running and time.time() < deadline:
    r.tick()
    time.sleep(0.25)

log("=== 结束 ===")
for line in r.summary():
    log("  " + line)
log("最终状态：%s  错误：%s" % (r.state, r.error or "-"))
for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    log("  文件 %s  %d B" % (f, os.path.getsize(p)))
