# -*- coding: utf-8 -*-
"""probe_seed6f.py —— 最小诊断：开浮层→截屏→点 row1→截屏→读值，用人眼裁决。

只做 OCP 一个类型、一次展开、两次点击，所有关键步骤截图。
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32api
import win32con
import win32gui
from PIL import ImageGrab

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
SHOTDIR = r"D:\deepseek\_probe\seed6f"
os.makedirs(SHOTDIR, exist_ok=True)

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    with open(os.path.join(SHOTDIR, "run.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def popups():
    found = []

    def cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and "20808" in win32gui.GetClassName(h):
                r = win32gui.GetWindowRect(h)
                if (r[2] - r[0]) > 150 and (r[3] - r[1]) > 60:
                    found.append((h, r))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return found


def click(x, y):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.25)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)


def grab(tag, box=None):
    p = os.path.join(SHOTDIR, "%s.png" % tag)
    ImageGrab.grab(bbox=box).save(p)
    log("  截图 %s → %s box=%s" % (tag, p, box))


def main():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没等到主窗")
        return 2
    time.sleep(1.5)
    ui.force_foreground()
    ui.clear_modals(4)
    for _ in range(4):
        w = None
        try:
            for t, c in ui.panels():
                if "用户设置" in t:
                    w = c
                    break
        except Exception:
            pass
        if w is None:
            break
        try:
            ui.press_cancel(w)
        except Exception:
            break
        time.sleep(0.5)
    if not ui.is_demo:
        ui.click_menu("%s", "进入演示模式")
        time.sleep(2.0)
        ui.clear_modals(3)
    base = D6.ParasiteDriver(ui, log)
    base.ensure_channel()
    base.activate()
    log("通道=%r 行数=%d" % (base.channel_title, len(base.read_sequence())))

    ui.click_toolbar("seq", "添加", wait=1.6)
    time.sleep(0.6)
    dlg = ui.window_titled("添加")
    if dlg is None:
        log("!! 添加对话框没出现")
        return 2
    combo = None
    for c in dlg.descendants():
        try:
            if c.element_info.automation_id == "cboExp":
                combo = c
                break
        except Exception:
            continue
    rc = combo.rectangle()
    log("combo rect=%s" % ((rc.left, rc.top, rc.right, rc.bottom),))

    def read_val():
        try:
            return combo.legacy_properties().get("Value", "")
        except Exception:
            return "?"

    log("初始值=%r" % read_val())
    log("浮层(开前)=%s" % popups())
    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    combo.click_input()
    time.sleep(1.0)
    ps = popups()
    log("浮层(开后)=%s 值=%r" % (ps, read_val()))
    if ps:
        pr = ps[0][1]
        grab("01_popup_open", (pr[0] - 8, pr[1] - 8, pr[2] + 8, pr[3] + 8))
        grab("02_full_screen", None)

        # 点 row1（seed6b 命中 OCP 的位置）：combo 下方 8+32
        x = rc.left + 60
        y = rc.bottom + 8 + 32
        log("点 row1 (%d,%d)…" % (x, y))
        click(x, y)
        time.sleep(0.9)
        log("值=%r 浮层(点后)=%s" % (read_val(), popups()))
        grab("03_after_row1", (pr[0] - 8, pr[1] - 8, pr[2] + 8, pr[3] + 8))

        # 若浮层还开，再点 row2
        if popups():
            y2 = rc.bottom + 8 + 64
            log("点 row2 (%d,%d)…" % (x, y2))
            click(x, y2)
            time.sleep(0.9)
            log("值=%r 浮层(点后)=%s" % (read_val(), popups()))
            grab("04_after_row2", (pr[0] - 8, pr[1] - 8, pr[2] + 8, pr[3] + 8))
    # 收尾
    try:
        ui.press_cancel(dlg)
    except Exception:
        pass
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    print("DONE")
    return 0


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
