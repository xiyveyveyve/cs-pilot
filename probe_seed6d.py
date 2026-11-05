# -*- coding: utf-8 -*-
"""probe_seed6d.py —— A1 种子+dump 第四轮：抄 p107 的成熟机制。

关键认知（p107 实测 + 三轮探针教训）：
  * 下拉浮层是顶层 WindowsForms10.Window.20808 窗，EnumWindows 可见即开着
  * 滚动浮层到底后行位置固定（「扩展测量」组在底部：行0=线性极化，行1=频率扫描）
  * 点中条目后浮层可能仍开着——此时点对话框角落（浮层矩形之外的点）收起，
    绝不能点标题栏/combo（上拉浮层会盖住它们，点了就选中别的项）
  * EIS/Step 需要滚到底才看得到；OCP/Tafel 不滚也在（seed6b: OCP@row1）

流程每 kind：添加→浮层→（不滚扫描→滚底扫描→滚顶扫描）→点中→收浮层→
值校验→确定→参数窗→dump+默认值→取消
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
KINDS = [D6.EXP_OCP, D6.EXP_TAFEL, D6.EXP_EIS, D6.EXP_STEP]

TITLE_KEY = {
    D6.EXP_OCP: "开路电位",
    D6.EXP_TAFEL: "动电位",
    D6.EXP_EIS: "频率扫描",
    D6.EXP_STEP: "任意恒电位阶梯波",
}

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "run_d.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def kill_cs():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                   capture_output=True)
    time.sleep(1.5)


def close_settings(ui):
    n = 0
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
            n += 1
        except Exception:
            break
        time.sleep(0.5)
    if n:
        log("关掉 %d 个挡路窗" % n)
    ui.clear_modals(3)
    return n


def click(x, y):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def popup():
    """枚举可见的自绘浮层（p107 原版机制），返回 (hwnd, rect) 或 None。"""
    found = []

    def cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and "20808" in win32gui.GetClassName(h):
                r = win32gui.GetWindowRect(h)
                if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 100:
                    found.append((h, r))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return found[-1] if found else None


def scroll_popup(pr, direction):
    """在浮层上滚轮。direction=-1 到底，+1 到顶。"""
    win32api.SetCursorPos((pr[0] + 40, (pr[1] + pr[3]) // 2))
    time.sleep(0.2)
    for _ in range(30):
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, direction * 120, 0)
        time.sleep(0.06)
    time.sleep(0.6)


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
    n_aid = sum(1 for r in rows if r["aid"])
    log("  dump：%d 控件 / %d 带 aid" % (len(rows), n_aid))
    return rows


def save_defaults(rows, kind):
    keys = {}
    for r in rows:
        aid = r["aid"]
        if not aid:
            continue
        low = aid.lower()
        if (r["type"] in ("Edit", "ComboBox", "CheckBox")
                and any(k in low for k in ("timeunit", "cycles", "vs_", "initial", "final",
                                           "scanrate", "freq", "amp", "sampleinterval",
                                           "testtime", "usestop", "chkstop"))):
            keys[aid] = "%s|%s" % (r["name"][:20], r["value"])
    with open(os.path.join(OUTDIR, "defaults_%s.json" % kind), "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=1)
    for k, v in keys.items():
        log("    %s = %s" % (k, v))


def pick_kind(base, dlg, kind):
    """在「添加」对话框里把 cboExp 切到 kind。返回是否成功。"""
    combo = None
    for c in dlg.descendants():
        try:
            if c.element_info.automation_id == "cboExp":
                combo = c
                break
        except Exception:
            continue
    if combo is None:
        log("  找不到 cboExp")
        return False
    key = D6.EXP_COMBO_TEXT[kind]

    def read_val():
        try:
            return combo.legacy_properties().get("Value", "") or combo.window_text() or ""
        except Exception:
            return ""

    rc = combo.rectangle()
    # 展开（先给对话框焦点；点右缘箭头，必要时两次）
    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    pu = None
    for _ in range(2):
        click(rc.right - 12, (rc.top + rc.bottom) // 2)
        time.sleep(0.9)
        pu = popup()
        if pu:
            break
    if not pu:
        log("  浮层没展开")
        return False

    def try_click(x, y):
        click(x, y)
        time.sleep(0.7)
        return read_val()

    hit = ""
    hit_from = ""
    # 阶段1：不滚，从 combo 下方扫（seed6b：OCP@row1）
    for i in range(15):
        v = try_click(rc.left + 60, rc.bottom + 8 + i * 32)
        if key in v:
            hit, hit_from = v, "down@%d" % i
            break
    # 阶段2：滚到底，从浮层顶部往下扫（p107：行1=频率扫描@+33）
    if not hit:
        pu = popup()
        if pu:
            pr = pu[1]
            log("  不滚没找到，滚到底再扫…")
            scroll_popup(pr, -1)
            for j in range(14):
                v = try_click(pr[0] + 40, pr[1] + 20 + j * 32)
                if key in v:
                    hit, hit_from = v, "bottom@%d" % j
                    break
    # 阶段3：滚回顶再扫
    if not hit:
        pu = popup()
        if pu:
            pr = pu[1]
            log("  滚回顶再扫…")
            scroll_popup(pr, +1)
            for j in range(14):
                v = try_click(pr[0] + 40, pr[1] + 20 + j * 32)
                if key in v:
                    hit, hit_from = v, "top@%d" % j
                    break
    if not hit:
        log("  三个阶段都没找到 %s" % key)
        try:
            win32api.SetCursorPos((rc.left - 200, rc.top - 100))
            click(rc.left - 200, rc.top - 100)
        except Exception:
            pass
        return False
    log("  命中 %r（%s）" % (hit, hit_from))

    # 收浮层：点对话框内、浮层外的角落
    time.sleep(0.4)
    if popup() is not None:
        dr = dlg.rectangle()
        cands = [(dr.right - 10, dr.top + 10), (dr.left + 10, dr.top + 10),
                 (dr.right - 10, dr.bottom - 10), (dr.left + 10, dr.bottom - 10)]
        p_rect = popup()[1] if popup() else None
        done = False
        for x, y in cands:
            if p_rect and p_rect[0] - 4 <= x <= p_rect[2] + 4 and p_rect[1] - 4 <= y <= p_rect[3] + 4:
                continue
            click(x, y)
            time.sleep(0.6)
            done = True
            break
        log("  收浮层点击：%s" % done)
    v = read_val()
    if key not in v:
        log("  收浮层后值=%r，选择丢失 → 失败" % v)
        return False
    log("  已选中：%r" % v)
    return True


def add_and_dump(ui, base, kind):
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
        ok = False
        for attempt in (1, 2):
            if pick_kind(base, dlg, kind):
                ok = True
                break
            time.sleep(0.6)
            # 重选前把可能还开着的浮层关掉
            if popup() is not None:
                click(dlg.rectangle().right - 10, dlg.rectangle().bottom - 10)
                time.sleep(0.4)
        if not ok:
            ui.press_cancel(dlg)
            return False, 0
        okbtn = ui.by_id("buttonOK", dlg) or ui.button("确定", dlg)
        if okbtn is None:
            log("  没有确定键")
            return False, 0
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
    save_defaults(rows, kind)
    try:
        ui.press_cancel(pnl)
    except Exception:
        pass
    time.sleep(1.0)
    ui.clear_modals(2)
    return True, len(rows)


def main():
    summary = []
    kill_cs()
    log("启动 6 版")
    subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            log("!! 40s 没等到主窗")
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        close_settings(ui)
        if not ui.is_demo:
            ok = ui.click_menu("%s", "进入演示模式")
            log("进入演示模式 -> %s" % ok)
            time.sleep(2.0)
            close_settings(ui)
        log("主窗=%r 演示=%s" % (ui.title, ui.is_demo))
        base = D6.ParasiteDriver(ui, log)
        if not base.ensure_channel():
            log("!! ensure_channel 失败")
            return 2
        base.activate()
        log("通道=%r 序列行数=%d" % (base.channel_title, len(base.read_sequence())))

        for kind in KINDS:
            log("")
            log("=== %s ===" % kind)
            try:
                ok, n = add_and_dump(ui, base, kind)
                summary.append((kind, "OK" if ok else "FAIL", "%d 控件" % n))
            except Exception as e:
                import traceback
                log("  总异常：%s\n%s" % (e, traceback.format_exc()[-500:]))
                summary.append((kind, "FAIL", str(e)[:80]))
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
        try:
            kill_cs()
        except Exception:
            pass
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
