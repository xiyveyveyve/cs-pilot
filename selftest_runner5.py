# -*- coding: utf-8 -*-
"""selftest_runner5.py —— 用 Runner5 跑一遍 CS Studio5 的完整流程。

演示模式下 5 版数据会在 20 多秒后剧烈跳变，所以判稳一定失败；
这里把 max_ocp_sec 设小，验证「判稳失败 → 到时不候 → 强制切到动电位」这条兜底路径。
正式运行用 1800 s 兜底。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from runner5 import Runner5, RunConfig5
from stabilizer import StabConfig

OUT = r"D:\deepseek\_probe\e2e5"


def log(m):
    print("%7.1fs  %s" % (time.time() - T0, m), flush=True)


T0 = time.time()

cfg = RunConfig5(
    sample="SELFTEST5R",
    area_cm2=1.0,
    item="Tafel",
    out_dir=OUT,
    ocp_time_sec=120.0,
    ocp_freq_hz=10.0,
    stab=StabConfig(strict_until_sec=30.0),
    max_ocp_sec=75.0,
    tafel_init_v=-0.05,
    tafel_final_v=0.05,
    tafel_scan_mv_s=1.0,
    tafel_interval_s=1.0,
    test_timeout_sec=600.0,
)

r = Runner5(cfg, log=log)
r.start()

last_state = None
t_end = time.time() + 600
while time.time() < t_end:
    r.tick()
    if r.state != last_state:
        log("STATE -> %s  %s" % (r.state, r.detail))
        last_state = r.state
    if r.state in ("完成", "出错", "已中止"):
        break
    time.sleep(0.3)

log("")
log("=" * 52)
for line in r.summary():
    log("  " + line)
log("DONE")
