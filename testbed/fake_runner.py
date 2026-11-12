# -*- coding: utf-8 -*-
"""fake_runner.py —— fleet 离线测试用的假 runner。

行为：每 0.5s 写心跳 + 打印一行；--die-after N（第 N 次心跳硬退出）；
--crash（启动即未捕获异常退出）；--mark-resume（收到 --resume 时写标记文件）；
Ctrl+C / CTRL_BREAK → 优雅退出（rc=0）。
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import graceful_exit

sample = sys.argv[1] if len(sys.argv) > 1 else "FAKE"
args = sys.argv
die_after = None
if "--die-after" in args:
    die_after = int(args[args.index("--die-after") + 1])
crash = "--crash" in args
resume = "--resume" in args

HB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "_auto", "hb", "%s.json" % sample)
os.makedirs(os.path.dirname(HB), exist_ok=True)   # 心跳目录不存在会让启动即崩
running = True
beats = 0


def log(m):
    print("%7.2f %s" % (time.time() % 10000, m), flush=True)


def abort(*_a):
    global running
    log("收到退出信号 → 优雅收尾")
    running = False


def write_hb(stage):
    with open(HB, "w", encoding="utf-8") as f:
        json.dump({"machine": sample, "pid": os.getpid(), "ts": time.time(),
                   "stage": stage}, f, ensure_ascii=False)


if resume:
    # --resume 传递验证：写标记文件供测试断言
    d = os.path.join(os.path.dirname(HB), "..", "hb")
    with open(os.path.join(os.path.dirname(HB), "%s.got_resume" % sample),
              "w") as f:
        f.write("1")
log("fake runner 启动 pid=%d die_after=%r crash=%r resume=%r"
    % (os.getpid(), die_after, crash, resume))
if crash:
    raise RuntimeError("模拟启动即崩溃")

graceful_exit.install(lambda: None, log)
signal.signal(signal.SIGINT, lambda *_: abort())
signal.signal(signal.SIGBREAK, lambda *_: abort())
write_hb("运行中")
while running:
    beats += 1
    write_hb("运行中")
    time.sleep(0.5)
    if die_after is not None and beats >= die_after:
        log("模拟崩溃（硬退出，不写终态心跳）")
        os._exit(9)
write_hb("已中止")
log("正常退出 (rc=0)")
