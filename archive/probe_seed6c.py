# -*- coding: utf-8 -*-
"""probe_seed6c.py —— A1 种子 + 全参数窗 dump 一体化（seed6b 的修正版）。

修正点：pick 命中后，用「再点一下 combo」收浮层（点标题栏会点在浮层项上，
把选择弄丢——seed6b 实测选中值变成了『使用数据文件重测』）。

流程：
    演示模式 → 工作通道(C)→通道1 → 对每个 kind：
        seq工具栏「添加」→ 「添加」对话框 → 测量方法 → 选类型 → 收浮层 → 确定
        → 参数窗自动弹出 → dump 控件表 + 截图 + 记录关键默认值 → 取消
    最后队列里留下 4 个条目（顺带解决空队列种子问题，且都是软件自己写的）。

产出：D:\\deepseek\\_probe\\dump6_all\\{kind}.json/.png + defaults_{kind}.json
"""

import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    with open(os.path.join(OUTDIR, "run_c.log"), "w", encoding="utf-8") as f:
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
    """把关键控件的默认值抽出来存档（TimeUnit=ms 这类陷阱要记录）。"""
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


def dropdown_open(rc=None):
    """浮层是否开着（位置感知：必须在 combo 正下方，排除同类误报）。"""
    import win32gui
    found = []

    def cb(h, acc):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            cls = win32gui.GetClassName(h)
            if "WindowsForms10.Window.20808" not in cls:
                return True
            r = win32gui.GetWindowRect(h)
            if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 100:
                if rc is None or (r[1] >= rc.top - 8 and r[0] >= rc.left - 300):
                    acc.append(h)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, found)
    return bool(found)


def pick_and_keep(base, dlg, kind):
    """选类型 + 用「再点 combo」收浮层，保证选择不丢。"""
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
    from pywinauto import mouse as _m
    from pywinauto.keyboard import send_keys as _sk
    key = D6.EXP_COMBO_TEXT[kind]
    rc = combo.rectangle()

    def read_val():
        try:
            return combo.legacy_properties().get("Value", "") or combo.window_text() or ""
        except Exception:
            return ""

    def try_row(i):
        try:
            _sk("{ESC}")
            time.sleep(0.3)
            combo.click_input()
            time.sleep(0.8)
            if not dropdown_open():
                return ""
            _m.click(coords=(rc.left + 60, rc.bottom + 8 + i * 32))
            time.sleep(0.7)
            return read_val()
        except Exception as e:
            log("  点击行异常：%s" % e)
            return ""

    got = ""
    quick = D6.EXP_PICK_ROW.get(kind, ())
    for i in quick:
        v = try_row(i)
        if key in v:
            got = v
            break
    if not got:
        log("  快路径未命中，全扫描…")
        for i in range(20):
            if i in quick:
                continue
            v = try_row(i)
            if not v:
                continue
            if key in v:
                got = v
                break
    if not got:
        log("  没找到 %s" % key)
        return False
    # 命中后浮层通常已自动收起；只有真开着才收（点 combo 一次）
    if dropdown_open(rc):
        log("  浮层仍开，点 combo 收起")
        try:
            combo.click_input()
        except Exception:
            pass
        time.sleep(0.6)
    v = read_val()
    if key not in v:
        log("  选择未保持（%r）——外层重试" % v)
        return False
    log("  已选中：%r" % v)
    return True


def add_and_dump(ui, base, kind):
    """添加一个 kind 条目并 dump 它的参数窗。返回 (ok, dump行数)。"""
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
            if pick_and_keep(base, dlg, kind):
                ok = True
                break
            time.sleep(0.5)
        if not ok:
            ui.press_cancel(dlg)
            return False, 0
        if dropdown_open():
            log("  确定前浮层仍开，点 combo 收起")
            try:
                for c in dlg.descendants():
                    try:
                        if c.element_info.automation_id == "cboExp":
                            c.click_input()
                            break
                    except Exception:
                        continue
                time.sleep(0.5)
            except Exception:
                pass
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

    # 参数窗
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
            # 收场：关掉可能残留的参数窗
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
