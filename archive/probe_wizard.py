# -*- coding: utf-8 -*-
"""probe_wizard.py —— 触发通讯配置向导并完整 dump 其结构。"""
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
    os.system('taskkill /F /IM CorrTest.CSStudio.exe >nul 2>&1')
    time.sleep(2)
    subprocess = __import__("subprocess")
    subprocess.Popen([r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        print("!! 没等到主窗")
        return 2
    print("主窗:", ui.title[:60])
    base = D6.ParasiteDriver(ui, print)
    dd = DD.DirectDriver(ui, base, print)
    panel = dd.open("ocp")
    print("OCP 参数窗:", panel.window_text() if panel else None)
    if panel is None:
        return 2
    # 点确定 → 触发连接（无设备 → 向导）
    ok = dd.press_ok(panel)
    print("press_ok:", ok)
    time.sleep(2)
    # 枚举全部窗口找向导
    found = None
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window":
                t = (c.window_text() or "").strip()
                if "通讯" in t or "向导" in t or "配置" in t:
                    found = c
                    print("向导窗: %r" % t[:50])
        except Exception:
            continue
    if found is None:
        # 泛找：任何新 Window
        for c in ui.descendants():
            try:
                if c.element_info.control_type == "Window":
                    t = (c.window_text() or "").strip()
                    r = c.rectangle()
                    if t and r.width() > 100:
                        print("窗: %r rect=(%d,%d,%d,%d)" % (t[:40], r.left, r.top, r.right, r.bottom))
            except Exception:
                continue
        return 2
    print("=== 向导控件树 ===")
    for c in found.descendants():
        try:
            ei = c.element_info
            t = (c.window_text() or "").strip()
            if ei.control_type in ("Button", "Edit", "ComboBox", "Pane", "Text", "Group") and (t or ei.automation_id):
                r = c.rectangle()
                print("  %s aid=%r name=%r rect=(%d,%d,%d,%d)" % (
                    ei.control_type, ei.automation_id, t[:24], r.left, r.top, r.right, r.bottom))
        except Exception:
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
