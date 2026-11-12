# -*- coding: utf-8 -*-
"""probe_step6b.py —— 点「任意恒电位阶梯波」后被「通讯配置向导」挡住，摸清向导怎么过。

probe_step6.py 已经证明菜单路径是通的：
    测试方法(E) → 暂态极化 → 任意恒电位阶梯波(多电位阶跃)   ← 注意菜单文字带后缀
点下去之后因为**没有设备**，弹的是「通讯配置向导-第一步」+「用户设置」，
参数窗没出现。本支探针把这两个窗的控件与文字 dump 出来，试各种关法，
看能不能逼出参数窗。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pywinauto import mouse
from pywinauto.keyboard import send_keys
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\step6b.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_panel(tag, c):
    log("=== %s ===" % tag)
    n = 0
    for d in c.descendants():
        try:
            ei = d.element_info
            ct = getattr(ei, "control_type", "") or ""
            aid = getattr(ei, "automation_id", "") or ""
            try:
                txt = (d.window_text() or "").strip()
            except Exception:
                txt = ""
            if ct in ("Text", "Button", "ComboBox", "Edit", "RadioButton",
                      "CheckBox", "ListItem", "Window", "Pane", "DataItem"):
                if txt or aid:
                    log("   %-14s aid=%-24r %r" % (ct, aid, txt[:70]))
                    n += 1
        except Exception:
            continue
    log("   （%d 条）" % n)


def main():
    kill6()
    time.sleep(1.0)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=4)

    ui.force_foreground()
    ui.open_menu("%e")
    time.sleep(1.0)

    def find(text):
        for t, _c, r in ui.menu_items(only_visible=False):
            if r.width() > 0 and text in t.strip():
                return t, r
        return None, None

    t1, r1 = find("暂态极化")
    if t1 is None:
        log("!! 没「暂态极化」")
        return 3
    log("悬停 %r" % t1)
    mouse.move(coords=(r1.left + 15, r1.top + r1.height() // 2))
    time.sleep(1.5)

    t2, r2 = find("任意恒电位阶梯波")
    if t2 is None:
        log("!! 没「任意恒电位阶梯波」")
        return 4
    log("点 %r" % t2)
    pt = (r2.left + 15, r2.top + r2.height() // 2)
    mouse.move(coords=pt)
    mouse.click(coords=pt)
    time.sleep(3.0)

    panels = ui.panels()
    log("点后可见窗：%r" % ([t for t, _ in panels],))
    for t, c in panels:
        if t:
            dump_panel(t, c)

    # 试各种关法，看参数窗会不会浮出来
    trials = [
        ("ESC", lambda: send_keys("{ESC}")),
        ("关「通讯配置向导」按钮", lambda: _click_any(ui, ("取消", "关闭", "退出", "下一步", "完成"))),
        ("关模态框", lambda: ui.clear_modals(limit=4)),
    ]
    for name, fn in trials:
        log(">>> 尝试：%s" % name)
        try:
            fn()
        except Exception as e:
            log("   出错：%s" % e)
        time.sleep(1.8)
        cur = [t for t, _ in ui.panels()]
        log("   现在可见窗：%r" % (cur,))
        hit = [t for t in cur if ("阶梯" in t or "阶跃" in t or "恒电位" in t)]
        if hit:
            log("   !! 出现参数窗：%r" % (hit,))
            for t, c in ui.panels():
                if t in hit:
                    dump_panel("参数窗：" + t, c)
            break

    ui.snapshot(r"D:\deepseek\_probe\step6b_state.png")
    return 0


def _click_any(ui, texts):
    for t, c in ui.panels():
        if not t:
            continue
        for d in c.descendants():
            try:
                ei = d.element_info
                if getattr(ei, "control_type", "") != "Button":
                    continue
                txt = (d.window_text() or "").strip()
                for w in texts:
                    if txt == w or txt.startswith(w):
                        d.click_input()
                        log("   点了 [%s] 里的「%s」" % (t, txt))
                        return True
            except Exception:
                continue
    return False


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
