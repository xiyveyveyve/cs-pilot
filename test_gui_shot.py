# -*- coding: utf-8 -*-
"""拍照验证 GUI 能正常构建（不点开始，只看界面）。"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from PIL import ImageGrab
import gui

root = tk.Tk()
app = gui.App(root)

def shot_and_quit():
    root.update_idletasks()
    root.update()
    time.sleep(0.4)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    p = r"D:\deepseek\_probe\shot_gui.png"
    ImageGrab.grab(bbox=(x - 8, y - 34, x + w + 8, y + h + 8)).save(p)
    print("截图:", p, (w, h), flush=True)
    root.destroy()

root.after(2200, shot_and_quit)
root.mainloop()
print("GUI OK", flush=True)
