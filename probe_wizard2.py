# -*- coding: utf-8 -*-
"""probe_wizard2.py —— press_ok 触发连接向导，持续 20s 抓其出现与结构。"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver_direct as DD
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"


def dump_win(c, tag):
    try:
        ei = c.element_info
        print("  [%s] %r aid=%r class=%r" % (ei.control_type, (c.window_text() or "")[:30],
                                             ei.automation_id, ei.class_name))
    except Exception as e:
        print("  [%s] 枚举失败 %r" % (tag, e))


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
    dd = DD.DirectDriver(ui, base, print)
    panel = dd.open("ocp")
    print("OCP 参数窗:", panel.window_text() if panel else None)
    if panel is None:
        return 2
    print("press_ok（无设备 → 应触发连接向导）…")
    ok = dd.press_ok(panel)
    print("press_ok:", ok)
    # 20s 内每 2s 枚举一次顶层窗口与主窗子窗
    t0 = time.time()
    seen = set()
    while time.time() - t0 < 20:
        time.sleep(2)
        now = set()
        try:
            for c in ui.descendants():
                try:
                    if c.element_info.control_type == "Window":
                        t = (c.window_text() or "").strip()
                        r = c.rectangle()
                        if t:
                            now.add((t[:50], r.left, r.top))
                except Exception:
                    continue
        except Exception:
            pass
        new = now - seen
        seen = now
        if new:
            print("  +%.1fs 新窗: %r" % (time.time() - t0, sorted(new)[:6]))
    # 全量 dump 最后状态
    print("=== 最终全部 Window ===")
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window":
                t = (c.window_text() or "").strip()
                if t:
                    print("  %r" % t[:60])
        except Exception:
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
