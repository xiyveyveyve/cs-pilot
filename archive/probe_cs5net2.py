# -*- coding: utf-8 -*-
"""probe_cs5net2.py —— CS5 通讯设置对话框侦察（UIA 直接点菜单，不依赖 Studio）。

前置：sim CS120 实例 :30005 已在跑（probe_cs5net 启动过）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOT = r"D:\deepseek\_probe\cs5_commset2.png"


def find_main5(timeout=10):
    from pywinauto import Desktop
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in Desktop(backend="uia").windows():
            try:
                if "CS Studio5" in (w.window_text() or ""):
                    return w
            except Exception:
                continue
        time.sleep(1)
    return None


def main():
    w = find_main5()
    if w is None:
        print("!! CS Studio5 主窗不在（先跑 probe_cs5net.py）")
        return 2
    print("主窗:", repr((w.window_text() or "")[:60]))

    # Alt+S 展开 系统设置(S)（.NET 自绘 MenuStrip 必须热键）
    try:
        w.set_focus()
    except Exception:
        pass
    time.sleep(0.3)
    from pywinauto.keyboard import send_keys
    send_keys("%s")
    time.sleep(0.9)

    # 桌面级枚举浮层菜单（下拉是独立 popup 窗，不在主窗 descendants 里）
    from pywinauto import Desktop
    target = None
    for top in Desktop(backend="uia").windows():
        try:
            for mb in top.descendants():
                try:
                    if (mb.element_info.control_type == "MenuItem"
                            and (mb.window_text() or "").strip() == "通讯设置"):
                        r = mb.rectangle()
                        if r.top > 0 and r.height() > 0:
                            target = mb
                            break
                except Exception:
                    continue
            if target is not None:
                break
        except Exception:
            continue
    if target is None:
        print("!! 展开后没看到「通讯设置」（浮层枚举失败）")
        return 2
    try:
        target.invoke()
    except Exception:
        target.click_input()
    time.sleep(1.5)

    # 找新对话框（CS5 顶层新窗）
    from pywinauto import Desktop
    dlg = None
    for c in Desktop(backend="uia").windows():
        try:
            t = (c.window_text() or "").strip()
            if t and ("通讯" in t or "连接" in t or "设置" in t) and "CS Studio" not in t:
                dlg = c
                print("新窗:", repr(t[:40]))
        except Exception:
            continue
    if dlg is None:
        print("!! 通讯设置对话框没出现")
        return 2

    print("=== 对话框控件 ===")
    for c in dlg.descendants():
        try:
            ei = c.element_info
            aid = ei.automation_id or ""
            t = (c.window_text() or "").strip()
            en = ""
            try:
                en = " en=%s" % c.is_enabled()
            except Exception:
                pass
            if aid or t:
                print("  %-9s aid=%-30r text=%-22r%s" % (ei.control_type,
                                                         aid[:30], t[:22], en))
        except Exception:
            continue
    try:
        img = dlg.capture_as_image()
        img.save(SHOT)
        print("截图:", SHOT)
    except Exception as e:
        print("截图失败:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
