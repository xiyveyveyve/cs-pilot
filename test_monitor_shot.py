# -*- coding: utf-8 -*-
"""test_monitor_shot.py —— 造 3 台假机器的状态（运行中/完成/失联），截看板全窗。

运行：python test_monitor_shot.py [输出png]
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\deepseek\_probe\shot_monitor.png"


def make_fake_board():
    """三台假机器：A 运行中 / B 已完成 / C 失联（心跳 60s 前）。"""
    import json
    board = tempfile.mkdtemp(prefix="cspilot_board_")
    now = time.time()

    def put(name, rec):
        with open(os.path.join(board, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)

    put("LAB-PC01", {
        "machine": "LAB-PC01", "ts": now - 2, "state": "监视开路电位",
        "detail": "判稳器两阶段运行中", "step": "开路电位·判稳",
        "sample": "CS350M-1107", "area": "1.0", "item": "Tafel", "ver": "CS Studio6直开",
        "metrics": {"E": -0.1512, "slope": 0.42, "ppt": 0.88, "held": 63.0},
        "files": ["2026-11-07-CS350M-1107-开路电位.txt（44 616 B）"],
        "log_tail": ["00:41:21 判稳器：阶段 B（放宽）",
                     "00:41:22 收到数据点 600 个"]})
    put("LAB-PC02", {
        "machine": "LAB-PC02", "ts": now - 4, "state": "完成",
        "detail": "测试完成", "step": "完成",
        "sample": "JK-E-1107", "area": "2.5", "item": "Step", "ver": "CS Studio6直开",
        "metrics": {"E": 0.3709, "slope": 0.41, "ppt": 0.41, "held": 120.0},
        "files": ["2026-11-07-JK-E-1107-阶梯波.txt（81 224 B）"],
        "log_tail": ["01:12:09 判稳 E=+0.370988 V",
                     "01:12:10 阶梯波已启动"]})
    put("LAB-PC03", {
        "machine": "LAB-PC03", "ts": now - 60, "state": "监视测试项",
        "detail": "电流密度 9.8e-4 A/cm²", "step": "测试项",
        "sample": "CS120-1107", "area": "1.2", "item": "Tafel", "ver": "CS Studio5",
        "metrics": {}, "files": [],
        "log_tail": ["23:58:01 动电位已启动"]})
    return board


def main():
    import tkinter as tk
    board = make_fake_board()
    import monitor as M
    root = tk.Tk()
    mon = M.Monitor(root, board)
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.update_idletasks()
    root.update()
    time.sleep(0.5)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    from PIL import ImageGrab
    ImageGrab.grab(bbox=(x - 8, y - 34, x + w + 8, y + h + 8)).save(OUT)
    print("SHOT:", OUT)
    print("BOARD:", board)
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
