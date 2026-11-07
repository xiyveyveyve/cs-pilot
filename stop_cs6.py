# -*- coding: utf-8 -*-
"""stop_cs6.py —— 停掉 CS Studio6 上正在跑的实验（数据工具栏停止键，用户指认路径）。"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver_direct as DD
import driver as D6


def main():
    ui = S.Studio(log=print)
    if not ui.acquire(15):
        print("!! 没找到 CS Studio6 主窗")
        return 2
    print("主窗:", ui.title)
    base = D6.ParasiteDriver(ui, print)
    dd = DD.DirectDriver(ui, base, print)

    runs = dd.mdi_run_windows() + dd.run_windows()
    print("运行窗:", [t for _w, t in runs])
    if not runs:
        print("没有正在跑的实验")
        return 0

    for attempt in range(3):
        if not dd.is_running():
            break
        print("第 %d 次停止…" % (attempt + 1))
        dd.stop()
        time.sleep(1.5)
    print("停止后 is_running =", dd.is_running())
    runs = dd.mdi_run_windows() + dd.run_windows()
    print("停止后运行窗:", [t for _w, t in runs])

    # 数据文件是否仍在写
    p = r"C:\Users\xiyve\Desktop\CS-Pilot数据\2026-11-07-JK-O-动电位.txt"
    if os.path.exists(p):
        s1 = os.path.getsize(p)
        time.sleep(6)
        s2 = os.path.getsize(p)
        print("数据文件 6s 内增长: %d B → %s" % (s2 - s1, "仍在写!" if s2 > s1 else "已停 ✓"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
