# -*- coding: utf-8 -*-
"""stop_tafel_visible.py —— 置前 + 可见区点击停止（修复遮挡误点）。"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, r"D:\deepseek\cspilot-parasite")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32gui
import win32con

import studio_ui as S


def main():
    ui = S.Studio(log=print)
    if not ui.acquire(10):
        print("!! 没找到主窗")
        return 2
    main_h = ui.main.handle

    # 1) CS6 主窗挪回右半屏并置前
    win32gui.MoveWindow(main_h, 955, 0, 950, 1000, True)
    win32gui.ShowWindow(main_h, win32con.SW_RESTORE)
    ui.force_foreground()
    time.sleep(0.6)

    # 2) 找运行窗（MDI 子窗），摆到主窗客户区左上（可见处）
    run = None
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "[通道" in (c.window_text() or ""):
                run = c
                break
        except Exception:
            continue
    if run is None:
        print("!! 运行窗没找到（可能已自行结束）")
        return 0
    run_h = run.handle
    win32gui.MoveWindow(run_h, 8, 8, 840, 700, True)
    time.sleep(0.5)
    print("运行窗 rect:", run.rectangle())

    # 3) 枚举 17~18 键数据工具栏，点停止键
    tb = None
    for c in run.descendants():
        try:
            if (c.element_info.control_type == "ToolBar"
                    and (c.element_info.automation_id or "") == "toolStrip1"):
                btns = [b for b in c.descendants()
                        if b.element_info.control_type == "Button"]
                if 15 <= len(btns) <= 20:
                    tb = btns
                    break
        except Exception:
            continue
    if tb is None:
        print("!! 数据工具栏没找到")
        return 2
    r0 = tb[0].rectangle()
    print("停止键 rect:", (r0.left, r0.top, r0.right, r0.bottom))

    # 4) 确认 CS6 仍在前台（焦点守卫），再点
    fg = win32gui.GetForegroundWindow()
    fg_title = win32gui.GetWindowText(fg)
    print("前台窗口:", fg_title[:50])
    if "CS Studio6" not in fg_title:
        ui.force_foreground()
        time.sleep(0.4)
    tb[0].click_input()
    print("已点停止键")
    time.sleep(2)

    # 5) 应答弹窗 + 验证数据停写
    import os
    p = r"C:\Users\xiyve\Desktop\CS-Pilot数据\2026-11-07-JK-O-动电位.txt"
    for _ in range(3):
        r = ui.close_win32_modal(prefer=("是(Y)", "是", "确定"))
        if r is None:
            break
        print("应答弹窗:", r)
        time.sleep(1)
    s1 = os.path.getsize(p) if os.path.exists(p) else 0
    time.sleep(6)
    s2 = os.path.getsize(p) if os.path.exists(p) else s1
    print("数据 6s 增长: %d B → %s" % (s2 - s1, "仍在写!" if s2 > s1 else "已停 ✓"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
