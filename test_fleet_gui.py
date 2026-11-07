# -*- coding: utf-8 -*-
"""test_fleet_gui.py —— fleet_gui 离线验收：2 台假机器，自动点全部启动/急停，截图。"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import fleet as F

TEST_CFG = os.path.join(r"D:\deepseek\_probe\live", "fleet_gui_test.json")
SHOT = r"D:\deepseek\_probe\shot_fleet_gui.png"


def make_cfg():
    FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "testbed", "fake_runner.py")
    cfg = {"machines": [
        {"name": "模拟A", "script": FAKE, "version": 6, "area": 1.0},
        {"name": "模拟B", "script": FAKE, "version": 5, "area": 1.0},
    ]}
    os.makedirs(os.path.dirname(TEST_CFG), exist_ok=True)
    with open(TEST_CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return TEST_CFG


def main():
    cfg = make_cfg()
    import tkinter as tk
    import fleet_gui as G

    root = tk.Tk()
    g = G.FleetGUI(root, cfg)
    root.attributes("-topmost", True)
    root.update_idletasks()

    log_lines = []

    def shot(tag):
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x - 8, y - 34, x + w + 8, y + h + 8)).save(
            SHOT.replace(".png", "_%s.png" % tag))
        log_lines.append("截图 %s" % tag)

    def step1():
        # 全部启动
        g.on_start_all()
        root.after(5000, step2)

    def step2():
        shot("running")
        g._log = g._log  # noqa
        # 急停
        g.on_stop_all()
        root.after(12000, step3)

    def step3():
        shot("stopped")
        root.after(500, finish)

    def finish():
        ok = all(st["proc"].poll() is not None
                 for st in g.fleet.state.values()) if g.fleet else False
        print("验证: 全部停止 =", ok)
        root.destroy()

    root.after(1500, step1)
    root.mainloop()
    # 主循环退出后（急停流程结束才 destroy）
    return 0


if __name__ == "__main__":
    sys.exit(main())
