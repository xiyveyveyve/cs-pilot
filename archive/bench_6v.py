# -*- coding: utf-8 -*-
"""bench_6v.py —— 6 版全链综合台一键装配。

步骤：
  1. DOS 别名 COM16 → CNCA0（软件存的 ComName=COM16 无需改）
  2. 启动 CS Studio6（自动连接 COM16 → 虚拟对 A 端）
  3. 提示：另开 testbed/simdevice.py CNCB0 --replay <数据文件> 当设备端
本脚本只做 1-2 与连接验证（GetPstType 探针由 simdevice 端观察）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"


def main():
    # 1) 别名
    r = subprocess.run([sys.executable,
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "make_alias2.py"), "COM16"],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    # 2) 启动软件（若未运行）
    import win32gui
    running = []

    def cb(h, _):
        try:
            t = win32gui.GetWindowText(h)
            if win32gui.IsWindowVisible(h) and t.startswith("CS Studio6"):
                running.append(h)
        except Exception:
            pass
        return True
    win32gui.EnumWindows(cb, None)
    if not running:
        subprocess.Popen([EXE6])
        print("CS Studio6 启动中…")
        time.sleep(25)
    print("CS Studio6 窗口:", running)
    print("完成。下一步：testbed/simdevice.py CNCB0 --replay <数据文件> 当设备端")
    return 0


if __name__ == "__main__":
    sys.exit(main())
