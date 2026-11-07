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

_LOG_DIR = r"D:\deepseek\_probe\live"
LOG = None          # 运行时按 样品+时间 生成（旧版固定 run.log，多轮日志互相交织）
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
    if not _single_instance_guard("cspilot_cs6_runner.lock"):
        return 1
    # 参数化：python runner6_live.py [样品型号] [面积cm2] [测试项目] [no-eis]
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-F"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    item = sys.argv[3] if len(sys.argv) > 3 else "Tafel"
    no_eis = "no-eis" in sys.argv
    # 可选加速参数：--max-ocp 秒 --ocp-time 秒 --init V --final V --rate mV/s
    args = sys.argv

    def _argval(name, default):
        return float(args[args.index(name) + 1]) if name in args else default
    global LOG
    LOG = os.path.join(_LOG_DIR, "run_%s_%s.log" % (sample, time.strftime("%m%d_%H%M")))
    cfg = R6.RunConfig6(
        sample=sample,
        area_cm2=area,
        item=item,
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=not no_eis,
        max_ocp_sec=_argval("--max-ocp", 1800.0),
        ocp_time_sec=_argval("--ocp-time", 1800.0),
        tafel_init_v=_argval("--init", -0.5),
        tafel_final_v=_argval("--final", 1.5),
        tafel_scan_mv_s=_argval("--rate", 0.33),
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
