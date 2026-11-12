# -*- coding: utf-8 -*-
"""probe_menu6.py —— 诊断 6 版「测试方法(E)」菜单，并抓阶梯波参数窗的真实控件表。

只为回答两个问题：
1. 为什么 open_by_menu 报「菜单里找不到『暂态极化』」——是文字不匹配，还是根本没展开？
2. 6 版「任意恒电位阶梯波」参数窗的 automation_id 到底叫什么。
"""

import json
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pywinauto import mouse
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\menu6.log"
OUTJ = r"D:\deepseek\_probe\menu6_step.json"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_items(ui, tag):
    items = ui.menu_items(only_visible=False)
    log("--- %s：%d 项 ---" % (tag, len(items)))
    for t, c, r in items:
        try:
            ei = c.element_info
            aid = getattr(ei, "automation_id", "") or ""
            acc = getattr(ei, "accelerator_key", "") or ""
            try:
                vis = "V" if c.is_visible() else "-"
            except Exception:
                vis = "?"
            log("  %s %-44r aid=%-24r key=%-8r rect=(%d,%d,%dx%d)"
                % (vis, t, aid, acc, r.left, r.top, r.width(), r.height()))
        except Exception as e:
            log("  <err %r>" % (e,))
    return items


def main():
    kill6()
    time.sleep(1.0)
    log("启动 6 版：%s" % EXE6)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 40 s 没找到主窗")
        return 2
    log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))
    time.sleep(1.0)
    ui.force_foreground()
    ui.clear_modals(limit=4)

    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进演示模式：%s" % ok)
        time.sleep(1.5)
        ui.clear_modals(limit=3)
    log("当前主窗：%r 演示=%s" % (ui.title, ui.is_demo))

    ui.force_foreground()
    ok = ui.open_menu("%e")
    log("展开「测试方法(E)」：%s" % ok)
    time.sleep(1.0)
    items = dump_items(ui, "展开后")

    sub = None
    for t, c, r in items:
        if "暂态" in t:
            sub = (t, c, r)
            break
    if sub is None:
        names = sorted({t for t, _c, _r in items})
        log("!! 没找到含「暂态」的菜单项；现有文字=%r" % (names,))
        return 3

    tt, _cc, rr = sub
    log("hover 二级：%r rect=(%d,%d,%dx%d)"
        % (tt, rr.left, rr.top, rr.width(), rr.height()))
    mouse.move(coords=(rr.left + 15, rr.top + rr.height() // 2))
    time.sleep(1.8)
    items2 = dump_items(ui, "hover 暂态极化之后")

    item = None
    for t, c, r in items2:
        if ("阶梯" in t) or ("阶跃" in t):
            item = (t, c, r)
            break
    if item is None:
        names = sorted({t for t, _c, _r in items2})
        log("!! 没找到含「阶梯/阶跃」的项；现有文字=%r" % (names,))
        return 4

    it, _ic, ir = item
    log("点三级：%r rect=(%d,%d,%dx%d)" % (it, ir.left, ir.top, ir.width(), ir.height()))
    pt = (ir.left + 15, ir.top + ir.height() // 2)
    mouse.move(coords=pt)
    mouse.click(coords=pt)
    time.sleep(2.5)
    ui.clear_modals(limit=3)

    panels = ui.panels()
    log("点后可见窗：%r" % ([t for t, _ in panels],))
    pnl = None
    for t, c in panels:
        if ("阶梯" in t) or ("阶跃" in t) or ("恒电位" in t):
            pnl = (t, c)
            break
    if pnl is None:
        log("!! 没出现阶梯波参数窗")
        ui.snapshot(r"D:\deepseek\_probe\menu6_fail.png")
        return 5

    pt_, pc = pnl
    log("参数窗：%r" % (pt_,))
    rows = []
    for d in pc.descendants():
        try:
            ei = d.element_info
            aid = getattr(ei, "automation_id", "") or ""
            ct = getattr(ei, "control_type", "") or ""
            try:
                txt = (d.window_text() or "").strip()
            except Exception:
                txt = ""
            try:
                r = d.rectangle()
                box = [r.left, r.top, r.width(), r.height()]
            except Exception:
                box = None
            rows.append({"aid": aid, "type": ct, "text": txt, "rect": box})
        except Exception:
            continue

    aidn = len([r for r in rows if r["aid"]])
    log("控件数：%d，其中有 aid 的：%d" % (len(rows), aidn))
    with open(OUTJ, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    log("aid 清单（去重）：")
    for a in sorted({r["aid"] for r in rows if r["aid"]}):
        log("   %s" % a)
    ui.snapshot(r"D:\deepseek\_probe\menu6_step.png")
    try:
        ui.press_cancel(pc)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
    finally:
        log("清理：taskkill /T")
        try:
            kill6()
        except Exception:
            pass
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        log("EXIT=%s" % rc)
