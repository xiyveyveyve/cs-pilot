# -*- coding: utf-8 -*-
"""switch_to_eis.py —— 等 OCP 数据文件静默后，未判稳就杀 runner 并直接起阻抗。

用途：2026-11-14 用户要求「OCP 这轮跑完若未判稳，直接进阻抗，不再跑第 2/3 轮」。
已在跑的 runner 进程加载的还是旧配置（ocp_rounds=3），所以在它准备第 2 轮之前
由本脚本接管：杀进程 → 用续跑脚本跳过 OCP 直接开阻抗。

判稳依据：读 runner 日志最后一段，出现「开路电位判稳」= 已判稳，什么都不做；
出现「未判稳 → 准备第 / 跑满未判稳 → 再来一轮」= 未判稳，切阻抗。

用法：
  python switch_to_eis.py --file "<ocp数据文件>" --logdir logs --logkey "<样品名>"
      --key "<runner 进程 cmdline 关键字>" --resume "runner5_resume_after_ocp.py 样品 面积 hwnd sn"
"""
from __future__ import annotations

import argparse
import glob
import os
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(m):
    print("%s  %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def runner_pids(key: str):
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
        except Exception:
            continue
        if ("runner5_live.py" in cl or "runner6_live.py" in cl) and key in cl:
            out.append(p.info["pid"])
    return out


def last_log(logdir: str, key: str) -> str:
    files = sorted(glob.glob(os.path.join(logdir, "run_*%s*.log" % key)), key=os.path.getmtime)
    if not files:
        return ""
    try:
        with open(files[-1], encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--logkey", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--quiet", type=float, default=15.0)
    ap.add_argument("--wait-max", type=float, default=4200.0)
    ap.add_argument("--resume", required=True)
    a = ap.parse_args()

    log("监视 OCP 文件：%s" % a.file)
    last = -1
    t_quiet = time.time()
    t_end = time.time() + a.wait_max
    while time.time() < t_end:
        time.sleep(2.0)
        if not os.path.exists(a.file):
            continue
        try:
            s = os.path.getsize(a.file)
        except Exception:
            continue
        if s != last:
            last = s
            t_quiet = time.time()
        elif time.time() - t_quiet >= a.quiet:
            break
    else:
        log("等不到数据静默（超时），不动")
        return 1

    log("OCP 数据已静默 %g s（%d 字节）→ 判断是否判稳" % (a.quiet, last))
    txt = last_log(a.logdir, a.logkey)
    tail = txt[-6000:]
    if "开路电位判稳" in tail and "未判稳" not in tail.split("开路电位判稳")[-1][:400]:
        log("日志显示已判稳 → 不动，交给 runner 自己进阻抗")
        return 0
    log("日志显示未判稳 → 杀 runner 并直接起阻抗")
    pids = runner_pids(a.key)
    log("目标 runner pid：%s" % pids)
    import psutil
    for pid in pids:
        try:
            psutil.Process(pid).kill()
            log("已杀 %d" % pid)
        except Exception as e:
            log("杀 %d 失败：%s" % (pid, e))
    time.sleep(3.0)

    cmd = [sys.executable, "-u", "-X", "utf8"] + shlex.split(a.resume)
    log("起阻抗续跑：%s" % " ".join(cmd))
    subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)),
                     stdout=open(os.path.join("logs", "resume_eis_%s.log" % time.strftime("%H%M%S")),
                                 "w", encoding="utf-8", errors="replace"),
                     stderr=subprocess.STDOUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
