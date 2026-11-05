# -*- coding: utf-8 -*-
"""probe_seed6g.py —— 浮层双实验：① UIA 能否直读树条目 ② 23px 步进扫描选 OCP。

浮层实测（seed6f 截图）：树形列表，每组/项 23px 均匀行距，
第一项（使用数据文件重测）在浮层顶 +35px，文本在浮层左 +200px 以后。
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32api
import win32con
import win32gui

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
SHOTDIR = r"D:\deepseek\_probe\seed6g"
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
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)


def main():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
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

    def read_val():
        try:
            return combo.legacy_properties().get("Value", "")
        except Exception:
            return "?"

    log("初始值=%r" % read_val())
    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    combo.click_input()
    time.sleep(1.0)
    ps = popups()
    if not ps:
        log("!! 浮层没开")
        return 2
    h, pr = ps[0]
    log("浮层 hwnd=%d rect=%s" % (h, tuple(pr)))

    # ---- 实验①：UIA 直读浮层 ----
    log("")
    log("=== 实验①：UIA 读浮层树 ===")
    try:
        import pywinauto
        from pywinauto import Desktop
        pop_win = Desktop(backend="uia").window(handle=h)
        n = 0
        for c in pop_win.descendants():
            try:
                t = (c.window_text() or "").strip()
                r = c.rectangle()
                if t or c.element_info.control_type in ("TreeItem", "ListItem", "Item"):
                    log("  UIA: %s %r y=%d" % (c.element_info.control_type, t[:30], r.top))
                    n += 1
            except Exception:
                continue
        log("  UIA 可读条目数：%d" % n)
        if n == 0:
            log("  → 自绘树对 UIA 不可见，走扫描")
    except Exception as e:
        log("  UIA 异常：%s" % e)

    # ---- 实验②：23px 步进扫描选 OCP ----
    log("")
    log("=== 实验②：23px 扫描 ===")
    key = D6.EXP_COMBO_TEXT[D6.EXP_OCP]
    hit = False
    for k in range(18):
        y = pr[1] + 35 + k * 23
        if y > pr[3] - 6:
            break
        # 浮层如果被关了（选中过别的项）就重开
        if not popups():
            log("  浮层已关（k=%d 前选中了 %r），重开" % (k, read_val()))
            if key in read_val():
                hit = True
                break
            combo.click_input()
            time.sleep(0.9)
            ps2 = popups()
            if not ps2:
                log("  重开失败")
                break
            pr = ps2[0][1]
        click(pr[0] + 200, y)
        time.sleep(0.5)
        v = read_val()
        still = bool(popups())
        log("  k=%02d y=%d → 值=%r 浮层开=%s" % (k, y, v, still))
        if key in v:
            hit = True
            break
    log("命中=%s" % hit)
    if hit:
        time.sleep(0.5)
        if popups():
            click(pr[0] - 30, pr[1] - 30)   # 浮层外一点（对话框标题栏上方，无控件）
            time.sleep(0.5)
        v = read_val()
        log("收浮层后值=%r" % v)
        if key in v:
            okbtn = None
            for c in dlg.descendants():
                try:
                    if c.element_info.automation_id == "buttonOK":
                        okbtn = c
                        break
                except Exception:
                    continue
            log("点确定…")
            okbtn.click_input()
            time.sleep(2.0)
            ui.clear_modals(2)
            pnl = ui.window_titled("开路电位")
            log("参数窗=%r" % (pnl.window_text() if pnl else None,))
            log("序列行数=%d %r" % (len(base.read_sequence()), base.rows_desc()))
            if pnl is not None:
                ui.press_cancel(pnl)
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
