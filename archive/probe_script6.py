# -*- coding: utf-8 -*-
"""probe_script6.py —— 「组合方法(B)」下四个入口逐个点，用 win32 枚举顶层窗口，
看点击到底有没有反应（上一支探针 panels() 抓到空列表，可能弹的是独立顶层窗）。

四个入口：组合测试 / 脚本化定制测试 / 脚本化双恒测试 / 定时测量(T)
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
OUT = r"D:\deepseek\_probe\script6.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def top_windows(pid=None):
    res = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            t = win32gui.GetWindowText(h)
            if not t:
                return True
            if pid is not None:
                _tid, p = win32process.GetWindowThreadProcessId(h)
                if int(p) != pid:
                    return True
            res.append((h, t))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return res


def main():
    kill6()
    time.sleep(1.0)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=4)

    pid = None
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(ui.main.handle)
        log("pid=%s" % pid)
    except Exception as e:
        log("取 pid 失败：%s" % e)

    base = set(t for _h, t in top_windows(pid))
    log("起始顶层窗：%r" % (sorted(base),))

    for name in ("组合测试", "脚本化定制测试", "脚本化双恒测试", "定时测量(T)"):
        log("")
        log("########## %s ##########" % name)
        ui.force_foreground()
        ui.open_menu("%b")
        time.sleep(1.0)
        tgt = None
        for t, _c, r in ui.menu_items(only_visible=False):
            if r.width() > 0 and name in t.strip():
                tgt = (t.strip(), r)
                break
        if tgt is None:
            log("   !! 菜单里没有")
            continue
        t, r = tgt
        log("   点 %r" % t)
        pt = (r.left + 15, r.top + r.height() // 2)
        mouse.move(coords=pt)
        time.sleep(0.3)
        mouse.click(coords=pt)

        neww = None
        for i in range(10):
            time.sleep(0.6)
            cur = set(x for _h, x in top_windows(pid))
            add = cur - base
            if add:
                neww = sorted(add)
                log("   +%.1fs 新窗：%r" % (0.6 * (i + 1), neww))
                break
        if neww is None:
            log("   6 s 内没有任何新顶层窗")
        # 也看看 panels
        try:
            log("   panels=%r" % ([x for x, _ in ui.panels()],))
        except Exception as e:
            log("   panels 出错：%s" % e)
        # dump 新窗内容
        if neww:
            for t2, c2 in ui.panels():
                if t2 in neww:
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
                                if n > 60:
                                    break
                        except Exception:
                            continue
        # 关掉新窗
        for t2, c2 in ui.panels():
            if neww and t2 in neww:
                for d in c2.descendants():
                    try:
                        if getattr(d.element_info, "control_type", "") != "Button":
                            continue
                        tx = (d.window_text() or "").strip()
                        if tx in ("取消", "退出", "关闭"):
                            d.click_input()
                            log("   关 %r 用「%s」" % (t2, tx))
                            time.sleep(1.2)
                            break
                    except Exception:
                        continue
                break
        base = set(t for _h, t in top_windows(pid))

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
