# -*- coding: utf-8 -*-
"""probe_seed6h.py —— 浮层条目用 UIA 模式直接选中（不走鼠标）。

seed6g 实证：浮层树对 UIA 完全可读（84 个 TreeItem，文本齐全）。
本探针：找到目标 TreeItem → 逐个试 SelectionItemPattern/InvokePattern/
ExpandCollapse/LegacyIAccessible.DoDefaultAction → 读 combo 值验证。
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32gui

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(r"D:\deepseek\_probe\seed6h", exist_ok=True)
    with open(r"D:\deepseek\_probe\seed6h\run.log", "w", encoding="utf-8") as f:
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
    log("浮层 hwnd=%d" % h)

    from pywinauto import Desktop
    pop_win = Desktop(backend="uia").window(handle=h)

    target = D6.EXP_COMBO_TEXT[D6.EXP_OCP]     # 开路电位测量(OCP)
    item = None
    items = []
    for c in pop_win.descendants():
        try:
            if c.element_info.control_type == "TreeItem":
                items.append(c)
                t = (c.window_text() or "").strip()
                if t == target and item is None:
                    item = c
        except Exception:
            continue
    log("TreeItem 总数=%d 目标(%s)=%s" % (len(items), target, "找到" if item else "未找到"))
    if item is None:
        return 2

    # 看这个 item 支持什么模式
    import comtypes
    import comtypes.client as cc
    ei = item.element_info
    log("item name=%r class=%r" % (item.window_text(), ei.class_name))
    try:
        raw = item.element_info.element  # IUIA raw
        import UIAutomationClient as UIC
        for pid_name, pid in (("SelectionItem", UIC.UIA_SelectionItemPatternId),
                              ("Invoke", UIC.UIA_InvokePatternId),
                              ("ScrollItem", UIC.UIA_ScrollItemPatternId),
                              ("ExpandCollapse", UIC.UIA_ExpandCollapsePatternId),
                              ("LegacyIAccessible", 10018)):
            try:
                ok = raw.GetCurrentPatternAs(pid) is not None if isinstance(pid, int) else None
                # GetCurrentPatternAvailability 更稳
                avail = raw.GetCurrentPatternAvailability(pid)
                log("  模式 %-16s 可用=%s" % (pid_name, bool(avail)))
            except Exception as e:
                log("  模式 %-16s 查询失败：%s" % (pid_name, e))
    except Exception as e:
        log("  模式查询异常：%s" % e)

    # rect 现状
    try:
        r = item.rectangle()
        log("item rect=%s" % ((r.left, r.top, r.right, r.bottom),))
    except Exception as e:
        log("item rect 失败：%s" % e)

    # 逐个模式试
    def try_pattern(name, fn):
        try:
            fn()
            time.sleep(0.6)
            v = read_val()
            still = bool(popups())
            log("  %-22s → 值=%r 浮层开=%s" % (name, v, still))
            return target in v
        except Exception as e:
            log("  %-22s 异常：%s" % (name, str(e)[:80]))
            return False

    done = False
    try:
        done = try_pattern("SelectionItem.Select", lambda: item.select())
    except Exception:
        pass
    if not done:
        try:
            done = try_pattern("Invoke", lambda: item.invoke())
        except Exception:
            pass
    if not done:
        try:
            def _scroll_select():
                item.scroll_into_view()
                time.sleep(0.3)
                item.select()
            done = try_pattern("ScrollItem+Select", _scroll_select)
        except Exception:
            pass
    if not done:
        try:
            done = try_pattern("DoDefaultAction", lambda: item.iface_accessible.DoDefaultAction())
        except Exception as e:
            log("  DoDefaultAction 不可用：%s" % str(e)[:60])

    log("结果：%s" % ("成功" if done else "全部失败"))
    if done:
        okbtn = None
        for c in dlg.descendants():
            try:
                if c.element_info.automation_id == "buttonOK":
                    okbtn = c
                    break
            except Exception:
                continue
        time.sleep(0.4)
        okbtn.click_input()
        time.sleep(2.0)
        ui.clear_modals(2)
        pnl = ui.window_titled("开路电位")
        log("参数窗=%r" % (pnl.window_text() if pnl else None,))
        log("序列行数=%d" % len(base.read_sequence()))
        if pnl is not None:
            ui.press_cancel(pnl)
    try:
        ui.press_cancel(dlg)
    except Exception:
        pass
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    print("DONE done=%s" % done)
    return 0 if done else 1


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
