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

HB_DIR = r"D:\deepseek\cspilot-parasite\_auto\hb"


def _write_hb(sample, r):
    import json
    try:
        os.makedirs(HB_DIR, exist_ok=True)
        hb = {"machine": sample, "pid": os.getpid(), "ts": time.time(),
              "stage": r.state, "detail": getattr(r, "detail", "")}
        p = os.path.join(HB_DIR, "%s.json" % sample)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hb, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass


def _read_hb(sample):
    import json
    try:
        p = os.path.join(HB_DIR, "%s.json" % sample)
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def main():
    if not _single_instance_guard("cspilot_cs5_runner.lock"):
        return 1
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-N"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    do_resume = "--resume" in sys.argv
    skip_ocp = False
    if do_resume:
        hb = _read_hb(sample)
        if hb:
            stage = hb.get("stage", "")
            if any(k in stage for k in ("动电位", "测试", "阶梯")):
                skip_ocp = True
                print("断点续跑：上一轮阶段「%s」→ 本轮跳过 OCP" % stage)
            else:
                print("上一轮阶段「%s」→ 正常从头跑" % stage)
    global LOG
    LOG = os.path.join(_LOG_DIR, "run_%s_%s.log" % (sample, time.strftime("%m%d_%H%M")))
    args = sys.argv

    def _argval(name, default):
        return float(args[args.index(name) + 1]) if name in args else default

    cfg = RunConfig5(
        sn=(args[args.index("--sn") + 1] if "--sn" in args else ""),
        sample=sample,
        area_cm2=area,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=False,          # 本次不测阻抗
        ocp_time_sec=_argval("--ocp-time", 1800.0),
        ocp_freq_hz=10.0,
        max_ocp_sec=_argval("--max-ocp", 1800.0),
        tafel_init_v=_argval("--init", -0.5),
        tafel_final_v=_argval("--final", 1.5),
        tafel_scan_mv_s=_argval("--rate", 0.33),
        tafel_interval_s=0.5,
    )
    r = Runner5(cfg, log=log)
    log("=" * 60)
    log("真机运行（5 版 CS120）：%s / %g cm² / OCP→动电位（无阻抗%s）"
        % (sample, area, "，断点续跑" if do_resume else ""))
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)
    t0 = time.time()
    last_beat = 0.0
    last_state = ""
    while r.running:
        r.tick()
        # 断点跳转：连接完成进入 OCP 前改道直奔动电位
        if skip_ocp and r.state == "打开开路电位参数窗":
            log("断点续跑：跳过 OCP，直接动电位")
            r.set_state("打开动电位参数窗")
            skip_ocp = False
        time.sleep(0.25)
        if r.state != last_state:
            last_state = r.state
            log("[状态] %s  %s" % (r.state, r.detail))
        if time.time() - last_beat > 60.0:
            last_beat = time.time()
            log("[心跳] state=%s detail=%s 运行 %.0f s" % (r.state, r.detail, time.time() - t0))
        _write_hb(sample, r)
    if r.running:
        graceful_exit.drain(r, log, lambda: r.tick())
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
