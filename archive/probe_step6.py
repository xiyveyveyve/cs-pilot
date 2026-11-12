# -*- coding: utf-8 -*-
"""probe_step6.py —— 非演示模式下打开 6 版「任意恒电位阶梯波」参数窗，抓真实控件表。

关键前提（probe_menu6b.py 实测）：**演示模式下「测试方法(E)」整个菜单会消失**，
换成「工作通道(C)」，也就是说演示模式根本开不了实验参数窗。
所以必须保持非演示模式（无设备也能开参数窗，参数窗是纯 UI）。

顺带核实 MENU_PATH 里那几条菜单文字是否与 6 版实际一致。
"""

import json
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pywinauto import mouse
from pywinauto.keyboard import send_keys
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\step6.log"
OUTJ = r"D:\deepseek\_probe\step6_controls.json"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def vis_items(ui):
    """只返回屏幕上真有位置的 MenuItem（展开后的可点项）。"""
    out = []
    for t, c, r in ui.menu_items(only_visible=False):
        if r.width() > 0 and r.height() > 0:
            out.append((t, c, r))
    return out


def show(ui, tag):
    items = vis_items(ui)
    log("--- %s：%d 项有位置 ---" % (tag, len(items)))
    for t, _c, r in items:
        log("   %-46r rect=(%d,%d %dx%d)" % (t, r.left, r.top, r.width(), r.height()))
    return items


def hover(ui, text, exact_endswith=True):
    """在菜单里找文字匹配的项并悬停，返回该项 rect。"""
    for t, _c, r in vis_items(ui):
        tt = t.strip()
        if (tt == text) or (exact_endswith and tt.endswith(text)) or (text in tt):
            pt = (r.left + 15, r.top + r.height() // 2)
            mouse.move(coords=pt)
            time.sleep(1.5)
            return tt, r
    return None, None


def main():
    kill6()
    time.sleep(1.0)
    log("启动 6 版（保持非演示模式）")
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=4)
    if ui.is_demo:
        log("!! 意外处于演示模式，退出它")
        ui.click_menu("%s", "退出演示模式")
        time.sleep(1.5)
        ui.clear_modals(limit=3)
        ui.force_foreground()

    # ① 展开「测试方法(E)」
    ui.force_foreground()
    ui.open_menu("%e")
    time.sleep(1.0)
    bars = show(ui, "① Alt+E 展开后")
    names = [t for t, _c, _r in bars]
    for want in ("测试方法(E)", "稳态极化", "暂态极化", "交流阻抗"):
        log("   含 %-10r → %s" % (want, want in names))

    # ② hover 暂态极化
    got, rect = hover(ui, "暂态极化")
    if got is None:
        log("!! 找不到「暂态极化」")
        return 3
    log("② 悬停二级：%r rect=(%d,%d)" % (got, rect.left, rect.top))
    bars2 = show(ui, "② 悬停后")

    # ③ 点三级「任意恒电位阶梯波」
    target = None
    for t, _c, r in bars2:
        if "任意恒电位阶梯波" in t:
            target = (t, r)
            break
    if target is None:
        log("!! 找不到「任意恒电位阶梯波」；现有=%r" % ([t for t, _c, _r in bars2],))
        return 4
    tt, rr = target
    log("③ 点三级：%r rect=(%d,%d %dx%d)" % (tt, rr.left, rr.top, rr.width(), rr.height()))
    pt = (rr.left + 15, rr.top + rr.height() // 2)
    mouse.move(coords=pt)
    time.sleep(0.3)
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
        log("!! 没出现参数窗")
        ui.snapshot(r"D:\deepseek\_probe\step6_fail.png")
        mdi = []
        try:
            mdi = [w.window_text() for w in ui.main.descendants(control_type="Window")]
        except Exception:
            pass
        log("MDI 窗：%r" % (mdi,))
        return 5

    title, pc = pnl
    log("参数窗：%r" % (title,))

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
            try:
                en = d.is_enabled()
            except Exception:
                en = None
            rows.append({"aid": aid, "type": ct, "text": txt, "rect": box, "enabled": en})
        except Exception:
            continue

    with open(OUTJ, "w", encoding="utf-8") as f:
        json.dump({"title": title, "controls": rows}, f, ensure_ascii=False, indent=1)

    aids = sorted({r["aid"] for r in rows if r["aid"]})
    log("控件总数=%d，有 aid 的=%d，唯一 aid=%d"
        % (len(rows), len([r for r in rows if r["aid"]]), len(aids)))
    log("=== aid 清单（含文字）===")
    for r in rows:
        if not r["aid"]:
            continue
        log("   %-30s %-14s %r%s"
            % (r["aid"], r["type"], r["text"][:40],
               "" if r["enabled"] is None else ("  启用" if r["enabled"] else "  禁用")))

    ui.snapshot(r"D:\deepseek\_probe\step6_panel.png")
    try:
        ui.press_cancel(pc)
        log("已取消参数窗")
    except Exception as e:
        log("取消失败：%s" % e)
    return 0


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
        try:
            send_keys("{ESC}")
        except Exception:
            pass
    finally:
        log("清理：taskkill /T")
        try:
            kill6()
        except Exception:
            pass
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        log("EXIT=%s" % rc)
