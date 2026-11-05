# -*- coding: utf-8 -*-
"""probe_seed6e.py —— A1 种子第五轮：每步自诊断的「添加」流程。

seed6d 教训：raw click 点右缘箭头 + 不打逐行读值 = 盲跑。本版：
  ① 展开用 combo.click_input()（seed6b 已证能开浮层）
  ② 每次点击后立即读值并打日志
  ③ 浮层 hwnd/rect 全程跟踪 + 关键时刻截图
先只跑 OCP 一个类型把机制钉死，成功即续跑其余三个。
"""

import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32gui

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUTDIR = r"D:\deepseek\_probe\dump6_all"
SHOTDIR = r"D:\deepseek\_probe\seed6e"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(SHOTDIR, exist_ok=True)
    with open(os.path.join(SHOTDIR, "run.log"), "w", encoding="utf-8") as f:
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


def popups():
    """当前所有可见的自绘浮层窗 [(hwnd, rect)]。"""
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


def log_popups(tag):
    ps = popups()
    log("  [%s] 浮层 %d 个：%s" % (tag, len(ps),
                                  [(h, tuple(r)) for h, r in ps[:3]]))
    return ps


def shot(ui, tag):
    try:
        ui.main.set_focus()
        time.sleep(0.2)
        ui.main.capture_as_image().save(os.path.join(SHOTDIR, "shot_%s.png" % tag))
    except Exception as e:
        log("  截图失败(%s)：%s" % (tag, e))


def pick_kind_diag(ui, base, dlg, kind):
    """带自诊断的选类型。"""
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
    log("  combo rect=%s 初始值=%r" % ((rc.left, rc.top, rc.right, rc.bottom), read_val()))
    log_popups("展开前")

    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.4)

    # 展开：click_input 点 combo 中心（seed6b 已证）
    opened = False
    for attempt in range(3):
        try:
            combo.click_input()
        except Exception as e:
            log("  combo.click_input 异常：%s" % e)
        time.sleep(0.9)
        ps = log_popups("展开后%d" % attempt)
        if ps:
            opened = True
            break
    if not opened:
        log("  浮层始终没开")
        return False

    pr = ps[0][1]
    hit = ""
    # 扫描：combo 下方（浮层若上拉，点击读不到值，靠 read_val 判断）
    for i in range(14):
        try:
            from pywinauto import mouse as _m
            _m.click(coords=(rc.left + 60, rc.bottom + 8 + i * 32))
        except Exception as e:
            log("  点击异常：%s" % e)
            break
        time.sleep(0.7)
        v = read_val()
        log("    down row%02d → %r" % (i, v))
        if key in v:
            hit = v
            break
    if not hit:
        # 浮层可能上拉：往 combo 上方扫
        log("  下方没命中，试上方（上拉浮层）…")
        for i in range(14):
            try:
                from pywinauto import mouse as _m
                _m.click(coords=(rc.left + 60, rc.top - 8 - i * 32))
            except Exception:
                break
            time.sleep(0.7)
            v = read_val()
            log("    up row%02d → %r" % (i, v))
            if key in v:
                hit = v
                break
    log_popups("选中后")
    shot(ui, "picked_%s" % kind)
    if not hit:
        log("  未命中 %s" % key)
        try:
            from pywinauto.keyboard import send_keys as _sk
            _sk("{ESC}")
        except Exception:
            pass
        return False

    # 收浮层：点对话框内且浮层外的点
    dr = dlg.rectangle()
    cur_ps = popups()
    cands = [(dr.right - 12, dr.top + 12), (dr.right - 12, dr.bottom - 12),
             (dr.left + 12, dr.top + 12), (dr.left + 12, dr.bottom - 12)]
    clicked = "(浮层已自闭)"
    if cur_ps:
        for x, y in cands:
            inside = any(pr2[0] - 6 <= x <= pr2[2] + 6 and pr2[1] - 6 <= y <= pr2[3] + 6
                         for _h, pr2 in cur_ps)
            if not inside:
                from pywinauto import mouse as _m
                _m.click(coords=(x, y))
                clicked = "(%d,%d)" % (x, y)
                break
    time.sleep(0.7)
    log("  收浮层点击%s" % clicked)
    log_popups("收起后")
    v = read_val()
    log("  收起后值=%r" % v)
    if key not in v:
        shot(ui, "lost_%s" % kind)
        return False
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
            if pick_kind_diag(ui, base, dlg, kind):
                ok = True
                break
            log("  第 %d 次选择失败，重试" % attempt)
            time.sleep(0.6)
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

    TITLE_KEY = {
        D6.EXP_OCP: "开路电位", D6.EXP_TAFEL: "动电位",
        D6.EXP_EIS: "频率扫描", D6.EXP_STEP: "任意恒电位阶梯波",
    }
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
    rows = []
    for c in pnl.descendants():
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
    with open(os.path.join(OUTDIR, "%s.json" % kind), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    try:
        pnl.set_focus()
        time.sleep(0.3)
        pnl.capture_as_image().save(os.path.join(OUTDIR, "%s.png" % kind))
    except Exception as e:
        log("  截图失败：%s" % e)
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
    log("  dump：%d 控件 / %d 带 aid / %d 关键默认值"
        % (len(rows), sum(1 for r in rows if r["aid"]), len(keys)))
    try:
        ui.press_cancel(pnl)
    except Exception:
        pass
    time.sleep(1.0)
    ui.clear_modals(2)
    return True, len(rows)


def main(only=None):
    kinds = [D6.EXP_OCP] if only == "ocp" else [
        D6.EXP_OCP, D6.EXP_TAFEL, D6.EXP_EIS, D6.EXP_STEP]
    summary = []
    kill_cs()
    log("启动 6 版（kinds=%r）" % kinds)
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

        for kind in kinds:
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
        verdict = "seeded+dumped" if len(rows) >= len(kinds) else ("partial" if rows else "failed")
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
    rc = main(*sys.argv[1:2])
    flush_log()
    sys.exit(rc)
