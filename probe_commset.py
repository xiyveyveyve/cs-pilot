# -*- coding: utf-8 -*-
"""probe_commset.py —— 打开「通讯设置」对话框并完整 dump 其结构。

前置：模拟器已在 CNCB0 运行（--port CNCB0）。
流程：CS6 启动 → 系统设置(S)→通讯设置 → dump 全控件 → 尝试连接。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"


def dump_tree(c, depth=0, max_depth=6):
    try:
        ei = c.element_info
        t = (c.window_text() or "").strip()
        aid = ei.automation_id or ""
        if depth <= max_depth and (t or aid or depth <= 2):
            print("  " * depth + "%s aid=%r name=%r" % (ei.control_type, t[:28], aid[:20]))
    except Exception:
        return
    if depth >= max_depth:
        return
    try:
        for ch in c.children():
            dump_tree(ch, depth + 1, max_depth)
    except Exception:
        pass


def main():
    os.system('taskkill /F /IM CorrTest.CSStudio.exe >nul 2>&1')
    time.sleep(2)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        print("!! 没等到主窗")
        return 2
    print("主窗:", ui.title[:60])
    base = D6.ParasiteDriver(ui, print)

    # 系统设置(S) → 通讯设置
    if not ui.open_menu("%s"):
        print("!! 系统设置打不开")
        return 2
    time.sleep(0.4)
    target = None
    for t, c, r in ui.menu_items():
        if t == "通讯设置":
            print("找到菜单项「通讯设置」@(%d,%d)" % (r.left, r.top))
            c.click_input()
            target = "clicked"
            break
    if target is None:
        print("菜单里没有「通讯设置」，列出全部项：")
        for t, c, r in ui.menu_items():
            if r.top > 0:
                print("  %r @(%d,%d)" % (t, r.left, r.top))
        return 2
    time.sleep(1.5)

    # dump 新出现的窗口
    print("=== 通讯设置对话框结构 ===")
    dlg = None
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "通讯" in (c.window_text() or ""):
                dlg = c
                break
        except Exception:
            continue
    if dlg is None:
        # 泛找：最大的新 Pane/Dialog
        for t, c in ui.panels():
            print("可见面板: %r" % t[:40])
        print("!! 没找到通讯设置对话框")
        return 2
    dump_tree(dlg, 0, 4)
    print("=== dump 完成（不点任何按钮，人工确认结构）===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
