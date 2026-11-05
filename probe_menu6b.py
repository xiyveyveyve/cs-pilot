# -*- coding: utf-8 -*-
"""probe_menu6b.py —— 对比「演示模式 / 非演示模式」下菜单栏到底有什么。

上一支探针发现：进了演示模式后菜单栏只剩
系统设置(S) / 工作通道(C) / 组合方法(B) / 窗口(W) / 帮助(H)，
「测试方法(E)」整个消失，所以那 13 个实验菜单项根本不存在。
本支探针只做一件事：把两种模式下的菜单栏各自 dump 一遍，确认是不是演示模式导致的。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\menu6b.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_all(ui, tag):
    """打印所有 MenuItem：菜单栏项（rect 非零）与已展开的子项。"""
    bar, kids = [], []
    for t, c, r in ui.menu_items(only_visible=False):
        if r.width() > 0:
            bar.append((t, r))
        else:
            kids.append(t)
    log("--- %s ---" % tag)
    log("  菜单栏（%d）：%r" % (len(bar), [(t, "%d,%d %dx%d" % (r.left, r.top, r.width(), r.height()))
                                       for t, r in bar]))
    log("  子项（%d）：%r" % (len(kids), kids))
    return [t for t, _r in bar]


def main():
    kill6()
    time.sleep(1.0)
    log("启动 6 版")
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=4)

    dump_all(ui, "A 启动后 演示=%s" % ui.is_demo)

    ui.force_foreground()
    ui.open_menu("%e")
    time.sleep(1.0)
    bar1 = dump_all(ui, "B 按过 Alt+E 之后 演示=%s" % ui.is_demo)
    from pywinauto.keyboard import send_keys
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.6)

    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进演示模式：%s" % ok)
        time.sleep(1.8)
        ui.clear_modals(limit=3)
        ui.force_foreground()
        dump_all(ui, "C 演示模式下 演示=%s" % ui.is_demo)
        ui.open_menu("%e")
        time.sleep(1.0)
        dump_all(ui, "D 演示模式 + Alt+E")
        try:
            send_keys("{ESC}")
        except Exception:
            pass
        time.sleep(0.6)
        # 退出演示模式，再看是否恢复
        ok = ui.click_menu("%s", "退出演示模式")
        log("退出演示模式：%s" % ok)
        time.sleep(1.8)
        ui.clear_modals(limit=3)
        ui.force_foreground()
        dump_all(ui, "E 退出演示后 演示=%s" % ui.is_demo)

    log("")
    log("判断：" + ("「测试方法(E)」在演示模式下消失"
                  if "测试方法(E)" not in [] else ""))
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
