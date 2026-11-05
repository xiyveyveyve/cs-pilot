# -*- coding: utf-8 -*-
"""test_gui_shot.py v2 —— 不启动软件、注入假运行状态、截全窗 PNG 供验收。

用法：python test_gui_shot.py [输出png]
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\deepseek\_probe\shot_gui.png"


def main():
    import tkinter as tk
    import gui as G

    root = tk.Tk()
    app = G.App(root)
    # 置顶：桌面上可能有别的窗口（CS Studio 探针等），不置顶会截到别人
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.update_idletasks()
    root.update()
    time.sleep(0.4)
    root.update()

    # 注入：进入"监视开路电位"状态 + 一条合成 E-t 曲线
    import math
    for i in range(600):
        t = i * 0.5
        e = -0.15 + 0.02 * math.exp(-t / 120.0) + 0.0006 * math.sin(t / 7.0)
        app.pts.append((t, e))
    st = type("S", (), {"slope_mv_per_min": 0.42, "ppt_mv": 0.88, "held_sec": 63.0})()
    app._on_sample(300.0, -0.1512, st)
    app._on_state("监视开路电位", "判稳器两阶段运行中")
    app.lbl_clock.configure(text="00:05:12")
    app._log("开路电位已启动")
    app._log("判稳器：阶段 B（放宽）· 窗口 60 s · 保持 120 s")
    app._log("收到数据点 600 个")
    root.update()
    time.sleep(0.3)
    root.update()

    x = root.winfo_rootx()
    y = root.winfo_rooty()
    w = root.winfo_width()
    h = root.winfo_height()
    from PIL import ImageGrab
    ImageGrab.grab(bbox=(x - 8, y - 34, x + w + 8, y + h + 8)).save(OUT)
    print("SHOT:", OUT)
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
