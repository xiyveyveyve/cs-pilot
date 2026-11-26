# -*- coding: utf-8 -*-
"""real_r_gui2.py —— 逐级展开 5 版三级菜单，打开恒电流阶跃参数窗并 dump 控件。

5 版菜单项预注册，子项 rect 只有父级展开后才有效；open_experiment 的一次循环
点不到三级（实测 2026-11-18）。本脚本显式逐级点 + 每级 dump 可见项。
"""
import sys, os, time, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")

import driver5
from pywinauto.keyboard import send_keys as _sk
import win32gui, win32con

OUT = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\real_r_gui2.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(OUT, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass

def dump_visible(st, tag):
    items = st.menu_items()
    vis = [(t, r, c) for t, r, c in items if (r.right - r.left) > 10 and (r.bottom - r.top) > 6 and r.top > 0]
    log("  [%s] 可见菜单项 %d:" % (tag, len(vis)))
    for t, r, c in vis[:30]:
        log("     %-28s top=%d" % (t, r.top))

def click_visible(st, name):
    cands = [(r, c) for t, r, c in st.menu_items()
             if t == name and (r.right - r.left) > 10 and (r.bottom - r.top) > 6 and r.top > 0]
    cands.sort(key=lambda x: x[0].top)
    for r, c in cands:
        try:
            driver5.msg_click(c)
            log("  点 '%s' (top=%d) OK" % (name, r.top))
            return True
        except Exception as e:
            log("  点 '%s' 失败 %s" % (name, e))
    log("  找不到可见的 '%s'" % name)
    return False

def main():
    st = driver5.Studio5(log=log)
    if not st.find_main(): log("FATAL 主窗"); return 2
    log("主窗: " + st.title())
    st.close_user_settings()
    try: st.main.set_focus()
    except Exception: pass
    time.sleep(0.5)

    # 一级：测试方法(E)
    st.click_main_menu("测试方法(E)")
    time.sleep(0.8)
    dump_visible(st, "一级展开")
    # 二级：稳态极化(S)（点它展开三级）
    click_visible(st, "稳态极化(S)")
    time.sleep(0.8)
    dump_visible(st, "二级展开")
    # 三级：恒电流阶跃(G)
    click_visible(st, "恒电流阶跃(G)")
    time.sleep(1.5)

    # 找参数窗（列出所有顶层 CS5 窗口）
    def cb(h, _):
        try:
            t = win32gui.GetWindowText(h)
            if t.strip() and "CS Studio5" in win32gui.GetClassName(h):
                log("  WIN: %r" % t[:70])
        except Exception: pass
        return True
    win32gui.EnumWindows(cb, None)
    return 0

if __name__ == "__main__":
    sys.exit(main())
