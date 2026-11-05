# -*- coding: utf-8 -*-
"""probe_seed6i.py —— A1 种子终版：UIA 条目矩形 + 鼠标点中心。

seed6h 实证：TreeItem 的 BoundingRectangle 是真实可点的（OCP=866,596,1004,619，
此前盲点的 x=1014 恰好超出条目宽度 10px）。本版：
    开浮层 → UIA 找目标 TreeItem（rect 有效才算可见）→ 点 rect 中心
    → 值校验 → 确定参数窗 → dump → 取消。
不可见（虚拟化）就滚轮后再找。四种实验一次跑完。
"""

import json
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
OUTDIR = r"D:\deepseek\_probe\dump6_all"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "run_i.log"), "w", encoding="utf-8") as f:
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
    time.sleep(0.6)


def close_settings(ui):
    for _ in range(5):
        w = None
        try:
            for t, c in ui.panels():
                if "用户设置" in t or "通讯配置向导" in t:
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
    ui.clear_modals(3)


def dump_panel(panel, path_base):
    rows = []
    for c in panel.descendants():
        try:
            ei = c.element_info
            try:
                val = c.get_value() or ""
            except Exception:
                val = c.window_text() or ""
            rows.append({"aid": ei.automation_id or "", "type": ei.control_type,
                         "name": (c.window_text() or "")[:40], "value": str(val)[:80]})
        except Exception:
            continue
    with open(path_base + ".json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    try:
        panel.set_focus()
        time.sleep(0.3)
        panel.capture_as_image().save(path_base + ".png")
    except Exception as e:
        log("  截图失败：%s" % e)
    return rows


def pick_by_uia(dlg, kind, combo):
    """开浮层 → UIA 找目标条目 → 点其 rect 中心。返回是否成功。"""
    from pywinauto import Desktop
    target = D6.EXP_COMBO_TEXT[kind]

    def read_val():
        try:
            return combo.legacy_properties().get("Value", "")
        except Exception:
            return "?"

    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    for attempt in range(2):
        try:
            combo.click_input()
        except Exception as e:
            log("  combo.click_input 异常：%s" % e)
        time.sleep(0.9)
        ps = popups()
        if ps:
            break
    if not popups():
        log("  浮层没开")
        return False

    log("  找 TreeItem：%s" % target)
    found_rect = None
    wheels = 0
    while wheels < 10 and found_rect is None:
        h, pr = popups()[0]
        pop_win = Desktop(backend="uia").window(handle=h)
        for c in pop_win.descendants():
            try:
                if c.element_info.control_type != "TreeItem":
                    continue
                if (c.window_text() or "").strip() != target:
                    continue
                r = c.rectangle()
                if r.width() > 20 and r.height() > 5:
                    found_rect = (r.left, r.top, r.right, r.bottom)
                    break
            except Exception:
                continue
        if found_rect is None:
            # 滚一屏再找
            win32api.SetCursorPos((pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2)
            for _ in range(5):
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120, 0)
                time.sleep(0.05)
            time.sleep(0.4)
            wheels += 1
    if found_rect is None:
        log("  滚了 10 屏也没找到目标条目")
        return False
    x = (found_rect[0] + found_rect[2]) // 2
    y = (found_rect[1] + found_rect[3]) // 2
    log("  命中 rect=%s → 点 (%d,%d)" % (found_rect, x, y))
    click(x, y)
    time.sleep(0.8)
    v = read_val()
    log("  点击后值=%r 浮层开=%s" % (v, bool(popups())))
    if target not in v:
        return False
    if popups():
        # 收浮层：点浮层外
        h2, pr2 = popups()[0]
        click(pr2[2] + 30, pr2[1] - 20)
        time.sleep(0.5)
        if target not in read_val():
            log("  收浮层后选择丢失")
            return False
    return True


def add_and_dump(ui, base, kind):
    TITLE_KEY = {
        D6.EXP_OCP: "开路电位", D6.EXP_TAFEL: "动电位",
        D6.EXP_EIS: "频率扫描", D6.EXP_STEP: "任意恒电位阶梯波",
    }
    base.activate()
    ui.click_toolbar("seq", "添加", wait=1.6)
    time.sleep(0.6)
    dlg = ui.window_titled("添加")
    if dlg is None:
        log("  「添加」没出现")
        ui.clear_modals(2)
        return False, 0
    try:
        for c in dlg.descendants():
            try:
                ei = c.element_info
                if ei.control_type == "RadioButton" and "测量方法" in (c.window_text() or ""):
                    c.click_input()
                    break
            except Exception:
                continue
        combo = None
        for c in dlg.descendants():
            try:
                if c.element_info.automation_id == "cboExp":
                    combo = c
                    break
            except Exception:
                continue
        ok = False
        for attempt in (1, 2):
            if pick_by_uia(dlg, kind, combo):
                ok = True
                break
            log("  第 %d 次失败，重试" % attempt)
            if popups():
                click(400, 200)
                time.sleep(0.4)
        if not ok:
            ui.press_cancel(dlg)
            return False, 0
        okbtn = ui.by_id("buttonOK", dlg) or ui.button("确定", dlg)
        okbtn.click_input()
        time.sleep(2.2)
        ui.clear_modals(2)
    except Exception as e:
        import traceback
        log("  添加异常：%s\n%s" % (e, traceback.format_exc()[-400:]))
        ui.clear_modals(2)
        return False, 0

    pnl = None
    for _ in range(10):
        pnl = ui.window_titled(TITLE_KEY[kind])
        if pnl is not None:
            break
        time.sleep(0.5)
    if pnl is None:
        log("  参数窗（%s）没出现" % TITLE_KEY[kind])
        return False, 0
    log("  参数窗：%r" % (pnl.window_text(),))
    rows = dump_panel(pnl, os.path.join(OUTDIR, kind))
    n_aid = sum(1 for r in rows if r["aid"])
    keys = {}
    for r in rows:
        aid = r["aid"]
        low = aid.lower()
        if (aid and r["type"] in ("Edit", "ComboBox", "CheckBox")
                and any(k in low for k in ("timeunit", "cycles", "vs_", "initial", "final",
                                           "scanrate", "freq", "amp", "sampleinterval",
                                           "testtime", "usestop", "chkstop"))):
            keys[aid] = "%s|%s" % (r["name"][:20], r["value"])
    with open(os.path.join(OUTDIR, "defaults_%s.json" % kind), "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=1)
    log("  dump：%d 控件 / %d 带 aid / 默认值 %d 项" % (len(rows), n_aid, len(keys)))
    try:
        ui.press_cancel(pnl)
    except Exception:
        pass
    time.sleep(1.0)
    ui.clear_modals(2)
    return True, len(rows)


def main():
    kinds = [D6.EXP_OCP, D6.EXP_TAFEL, D6.EXP_EIS, D6.EXP_STEP]
    summary = []
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    time.sleep(1.5)
    log("启动 6 版")
    subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            log("!! 没等到主窗")
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        close_settings(ui)
        if not ui.is_demo:
            ui.click_menu("%s", "进入演示模式")
            log("进入演示模式")
            time.sleep(2.0)
            close_settings(ui)
        base = D6.ParasiteDriver(ui, log)
        base.ensure_channel()
        base.activate()
        log("通道=%r 行数=%d" % (base.channel_title, len(base.read_sequence())))

        for kind in kinds:
            log("")
            log("=== %s ===" % kind)
            try:
                ok, n = add_and_dump(ui, base, kind)
                summary.append((kind, "OK" if ok else "FAIL", "%d 控件" % n))
            except Exception as e:
                import traceback
                log("  总异常：%s\n%s" % (e, traceback.format_exc()[-400:]))
                summary.append((kind, "FAIL", str(e)[:70]))
            try:
                for t, c in list(ui.panels()):
                    if any(k in t for k in ("开路电位", "动电位", "频率扫描", "阶梯波", "添加")):
                        ui.press_cancel(c)
                        time.sleep(0.4)
                ui.clear_modals(2)
            except Exception:
                pass

        rows = base.read_sequence()
        log("")
        log("最终序列行数：%d" % len(rows))
        for d in base.rows_desc():
            log("  " + d)
        verdict = "seeded+dumped" if len(rows) >= 4 else ("partial" if rows else "failed")
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
        flush_log()

    log("")
    for k, st, msg in summary:
        log("%-6s %s  %s" % (k, st, msg))
    log("VERDICT: %s" % verdict)
    print("VERDICT: %s" % verdict)
    return 0 if verdict == "seeded+dumped" else 1


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
