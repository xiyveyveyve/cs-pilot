# -*- coding: utf-8 -*-
"""probe_script6b.py —— 修正上一支探针的致命前提错误：
「通讯配置向导-第一步」是**模态**的，一旦挂在那就把主窗禁用，后面所有菜单点击全部无效
（上一支日志里四个入口"6 s 内没有任何新顶层窗"就是这么来的，不是入口不可用）。

本支探针：启动后先把向导/用户设置彻底关干净，确认没有挡路窗，再逐个点
组合方法(B) 下的四个入口。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32gui
import win32process
from pywinauto import mouse
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\script6b.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def top_windows(pid):
    res = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            t = win32gui.GetWindowText(h)
            if not t:
                return True
            _tid, p = win32process.GetWindowThreadProcessId(h)
            if int(p) != pid:
                return True
            res.append(t)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return sorted(set(res))


def clear_blockers(ui, rounds=8):
    """把主窗以外的窗全关掉（只点 取消/退出/关闭）。"""
    for _ in range(rounds):
        closed = False
        for t, c in ui.panels():
            if not t or "CS Studio" in t:
                continue
            for d in c.descendants():
                try:
                    if getattr(d.element_info, "control_type", "") != "Button":
                        continue
                    tx = (d.window_text() or "").strip()
                    if tx in ("取消", "退出", "关闭"):
                        d.click_input()
                        log("   关 [%s] 用「%s」" % (t, tx))
                        time.sleep(1.2)
                        closed = True
                        break
                except Exception:
                    continue
            if closed:
                break
        try:
            r = ui.clear_modals(limit=2)
            if r:
                log("   清模态：%r" % (r,))
                closed = True
        except Exception:
            pass
        if not closed:
            return True
    return False


def click_entry(ui, pid, name):
    log("")
    log("########## %s ##########" % name)
    ui.force_foreground()
    before = set(top_windows(pid))
    ui.open_menu("%b")
    time.sleep(1.0)
    tgt = None
    for t, _c, r in ui.menu_items(only_visible=False):
        if r.width() > 0 and name in t.strip():
            tgt = (t.strip(), r)
            break
    if tgt is None:
        log("   !! 菜单里没有")
        return
    t, r = tgt
    pt = (r.left + 15, r.top + r.height() // 2)
    log("   点 %r rect=(%d,%d)" % (t, r.left, r.top))
    mouse.move(coords=pt)
    time.sleep(0.3)
    mouse.click(coords=pt)

    neww = None
    for i in range(10):
        time.sleep(0.6)
        add = set(top_windows(pid)) - before
        if add:
            neww = sorted(add)
            log("   +%.1fs 新窗：%r" % (0.6 * (i + 1), neww))
            break
    if neww is None:
        log("   6 s 内无新顶层窗")
    cur = [x for x, _ in ui.panels()]
    log("   panels=%r" % (cur,))
    for t2, c2 in ui.panels():
        if not t2 or "CS Studio" in t2:
            continue
        if neww is not None and t2 not in neww:
            continue
        log("   --- 内容 %r ---" % t2)
        n = 0
        for d in c2.descendants():
            try:
                ei = d.element_info
                ct = getattr(ei, "control_type", "") or ""
                aid = getattr(ei, "automation_id", "") or ""
                try:
                    tx = (d.window_text() or "").strip()
                except Exception:
                    tx = ""
                if tx or aid:
                    log("      %-14s aid=%-24r %r" % (ct, aid, tx[:70]))
                    n += 1
                    if n > 50:
                        break
            except Exception:
                continue
    clear_blockers(ui)


def main():
    kill6()
    time.sleep(1.0)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    pid = None
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(ui.main.handle)
    except Exception:
        pass
    log("主窗：%r pid=%s 演示=%s" % (ui.title, pid, ui.is_demo))
    time.sleep(1.2)
    ui.force_foreground()

    log("=== 第一步：清干净挡路窗 ===")
    clear_blockers(ui)
    ui.force_foreground()
    log("清场后可见窗：%r" % ([t for t, _ in ui.panels()],))

    for name in ("组合测试", "脚本化定制测试", "脚本化双恒测试", "定时测量(T)"):
        click_entry(ui, pid, name)

    try:
        ui.snapshot(r"D:\deepseek\_probe\script6b_state.png")
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
