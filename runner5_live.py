# -*- coding: utf-8 -*-
"""runner5_live.py —— 真机运行入口（CS Studio5 链路：OCP→动电位，无阻抗）。

用法：python runner5_live.py [样品型号] [面积cm2]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from runner5 import Runner5, RunConfig5
import graceful_exit
from stabilizer import StabConfig

_LOG_DIR = r"D:\deepseek\_probe\live_jkn"
LOG = None          # 运行时按 样品+时间 生成（避免多轮日志交织）
_lines = []


def log(m):
    global LOG
    if LOG is None:
        LOG = os.path.join(_LOG_DIR, "run_%s.log" % time.strftime("%H%M%S"))
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    _lines.append(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass




def _single_instance_guard(lock_name: str) -> bool:
    """单实例锁：同一套软件上绝不允许第二个 runner（真机上两个 runner
    会互相停/开实验——对真实电解池是危险操作）。锁文件放临时目录，
    进程存活即视为持锁；残留锁检测到进程已死时自动接管。"""
    import os
    import tempfile
    lock = os.path.join(tempfile.gettempdir(), lock_name)
    if os.path.exists(lock):
        try:
            pid = int(open(lock).read().strip())
            import ctypes
            k32 = ctypes.WinDLL("kernel32")
            h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                k32.CloseHandle(h)
                print("!! 已有实例在运行 (pid=%d)，拒绝启动。确认后再关掉旧的。" % pid)
                return False
        except (ValueError, OSError):
            pass
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    return True

def main():
    if not _single_instance_guard("cspilot_cs5_runner.lock"):
        return 1
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-N"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    global LOG
    LOG = os.path.join(_LOG_DIR, "run_%s_%s.log" % (sample, time.strftime("%m%d_%H%M")))
    cfg = RunConfig5(
        sample=sample,
        area_cm2=area,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=False,          # 本次不测阻抗
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
    log("真机运行（5 版 CS120）：JK-N / %g cm² / OCP→动电位（无阻抗）" % area)
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)
    t0 = time.time()
    last_beat = 0.0
    last_state = ""
    while r.running:
        r.tick()
        time.sleep(0.25)
        if r.state != last_state:
            last_state = r.state
            log("[状态] %s  %s" % (r.state, r.detail))
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
