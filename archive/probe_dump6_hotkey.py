# -*- coding: utf-8 -*-
"""probe_dump6_hotkey.py v2 —— 定位 6 版「自定义快捷键」对话框。

策略：点之前先记录该进程的窗口集合，点之后再看新增了什么，
避免被启动时就存在的「用户设置」窗干扰。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psutil
import win32gui
import win32process
from pywinauto.keyboard import send_keys

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\dump6_hotkey.log"
_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def wins_of(pid):
    out = []

    def cb(h, _):
        try:
            _t, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h):
                out.append((h, win32gui.GetWindowText(h)))
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)
    return out


def snapshot(label, pid):
    ws = wins_of(pid)
    log("  [%s] %d 个可见窗口" % (label, len(ws)))
    for h, t in ws:
        log("     %#010x %r" % (h, t))
    return {h for h, _ in ws}


def dump_win(h, limit=400):
    import uiautomation as auto

    try:
        root = auto.ControlFromHandle(h)
    except Exception as e:
        log("   !! 取控件树失败：%s" % e)
        return

    n = [0]

    def walk(c, depth):
        if n[0] >= limit:
            return
        try:
            ei = c.element_info
            name = (c.window_text() or "").strip()
            aid = getattr(ei, "automation_id", "") or ""
            r = c.rectangle()
            log("     %s%-14s %-38r aid=%-20r (%d,%d)"
                % ("  " * depth, ei.control_type or "", name[:38], aid, r.left, r.top))
            n[0] += 1
        except Exception:
            pass
        try:
            kids = c.GetChildren()
        except Exception:
            kids = []
        for k in kids:
            walk(k, depth + 1)

    walk(root, 0)
    log("     共 %d 个控件" % n[0])


def pid_of(ui, p):
    """CS Studio6 会由启动器再起一个进程，必须从主窗句柄反查真实 pid。"""
    try:
        h = ui.main.handle
        _t, pid = win32process.GetWindowThreadProcessId(h)
        return pid
    except Exception:
        try:
            return p.pid
        except Exception:
            return 0


def main():
    p = subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(30):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    time.sleep(1.5)
    ui.force_foreground()
    ui.clear_modals(limit=4)
    # 6 版启动会留『用户设置』和『正在找寻设备...』两个窗口，会抢焦点
    for h, t in wins_of(pid_of(ui, p)):
        if t.strip() in ("用户设置", "正在找寻设备...") or "找寻设备" in t:
            log("  关闭启动窗口 %r" % t)
            try:
                win32gui.PostMessage(h, 0x0010, 0, 0)   # WM_CLOSE
            except Exception:
                pass
    time.sleep(1.0)
    ui.force_foreground()
    time.sleep(0.5)

    mpid = pid_of(ui, p)
    log("主窗 pid=%s（启动器 pid=%s）" % (mpid, getattr(p, "pid", "?")))
    before = snapshot("点击前", mpid)

    ui.open_menu("%s")
    time.sleep(0.4)
    log("")
    log("--- 系统设置菜单项 ---")
    target = None
    for t, c, r in ui.menu_items():
        if r.top <= 60:            # 主菜单栏那一行
            continue
        log("   %r  (%d,%d)" % (t, r.left, r.top))
        if t == "自定义快捷键":
            target = c
    if target is None:
        log("!! 菜单里没找到「自定义快捷键」")
        send_keys("{ESC}")
        return 3

    log("")
    log("点击「自定义快捷键」…")
    try:
        target.click_input()
    except Exception as e:
        log("   click_input 失败：%s，改用坐标点击" % e)
        try:
            target.click()
        except Exception as e2:
            log("   还是失败：%s" % e2)
            return 4
    time.sleep(2.5)

    after = snapshot("点击后", mpid)
    new = after - before
    log("")
    log("新增窗口 %d 个" % len(new))
    for h in new:
        t = win32gui.GetWindowText(h)
        log("")
        log("=== 新窗口 %#010x %r ===" % (h, t))
        dump_win(h)

    send_keys("{ESC}")
    time.sleep(0.5)
    send_keys("{ESC}")
    time.sleep(0.5)
    try:
        p.terminate()
        p.wait(timeout=10)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    rc = main()
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
    except Exception:
        pass
    sys.exit(rc)
