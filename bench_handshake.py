# -*- coding: utf-8 -*-
"""bench_handshake.py —— 模拟器在线 + runner 启动 OCP，抓完整握手流量。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
CAP = r"D:\deepseek\_probe\live\handshake6.jsonl"
EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"


def main():
    time.sleep(1)
    # 1) 模拟器（CNCB0，帧捕获开）
    sim = subprocess.Popen([sys.executable,
                            os.path.join(ROOT, "testbed", "simdevice.py"),
                            "--port", "CNCB0",
                            "--log", r"D:\deepseek\_probe\live\handshake6.jsonl"],
                           cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    time.sleep(3)
    # 2) 软件
    sw = subprocess.Popen([EXE6])
    time.sleep(30)
    # 3) runner：OCP 快速启动（ press_ok 触发软件的设备连接与握手）
    r = subprocess.run([sys.executable, "runner6_live.py", "握手测试", "1.0",
                        "Tafel", "no-eis", "--max-ocp", "60", "--ocp-time", "120"],
                       cwd=ROOT, capture_output=True, text=True,
                       timeout=240, encoding="utf-8", errors="replace")
    print(r.stdout[-2000:])
    time.sleep(3)
    try:
        sim.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
