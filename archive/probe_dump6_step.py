# -*- coding: utf-8 -*-
"""probe_dump6_step.py —— 抓到 6 版「任意恒电位阶梯波」参数窗的真实控件表。

这是当前最关键的事实核查：runner6.py 里那套 PotSquare_* 的 id 全是从 5 版
抄来的、一次都没在 6 版上核实过（循环圈数控件甚至靠逐个试）。

输出：D:\deepseek\_probe\dump6_step.json  + 同名 .log
"""

import json
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psutil
import win32gui
import win32process

import driver as D6
import driver_direct as DD
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT_LOG = r"D:\deepseek\_probe\dump6_step.log"
OUT_JSON = r"D:\deepseek\_probe\dump6_step.json"

_lines = []
_records = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def main_pid(ui):
    try:
        h = ui.main.handle
        _t, pid = win32process.GetWindowThreadProcessId(h)
        return pid
    except Exception:
        return None


def wins_of(pid):
    out = []

    def cb(h, _):
        try:
            _t, p = win32process.GetWindowThreadProcessId(h)
            if p == pid and win32gui.IsWindowVisible(h):
                out.append((h, win32gui.GetWindowText(h)))
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)
    return out


def dump_panel(panel, tag, limit=500):
    """dump 一个 pywinauto 容器下的所有后代控件。"""
    log("")
    log("=== dump %s ===" % tag)
    n = 0
    try:
        kids = panel.descendants()
    except Exception as e:
        log("   !! descendants 失败：%s" % e)
        return
    for c in kids:
        try:
            ei = c.element_info
            ct = (ei.control_type or "").strip() if hasattr(ei, "control_type") else ""
            name = (c.window_text() or "").strip()
            aid = getattr(ei, "automation_id", "") or ""
            cls = getattr(ei, "class_name", "") or ""
            r = c.rectangle()
            rec = {
                "tag": tag,
                "control_type": ct,
                "name": name,
                "automation_id": aid,
                "class_name": cls,
                "left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
            }
            _records.append(rec)
            log("   %-16s %-30r aid=%-32r cls=%-20r (%d,%d)"
                % (ct, name[:30], aid, cls[:20], r.left, r.top))
            n += 1
            if n >= limit:
                log("   …（截断）")
                break
        except Exception:
            continue
    log("   共 %d 个" % n)


def main():
    p = subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(30):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    time.sleep(1.2)
    ui.force_foreground()

    pid = main_pid(ui)
    log("主窗 pid=%s" % pid)

    # 关掉启动时的两个窗口，否则抢焦点
    for h, t in wins_of(pid or -1):
        if "用户设置" in t or "找寻设备" in t:
            log("  关闭启动窗 %r" % t)
            try:
                win32gui.PostMessage(h, 0x0010, 0, 0)
            except Exception:
                pass
    time.sleep(1.0)
    ui.force_foreground()
    ui.clear_modals(limit=3)
    time.sleep(0.5)

    # 进演示模式
    if not ui.is_demo:
        log("进演示模式 …")
        ok = ui.click_menu("%s", "进入演示模式")
        log("  点击 → %s" % ok)
        time.sleep(2.5)
        ui.force_foreground()
        log("  现在标题：%r  演示模式=%s" % (ui.title, ui.is_demo))

    # 打开阶梯波参数窗
    base = D6.ParasiteDriver(ui, log)
    dd = DD.DirectDriver(ui, base, log)
    try:
        dd.prepare()
    except Exception as e:
        log("prepare 出错（继续）：%s" % e)

    before = {h for h, _ in wins_of(pid or -1)}
    log("")
    log("打开「任意恒电位阶梯波」…")
    panel = None
    try:
        panel = dd.open("step")
    except Exception as e:
        log("open(step) 抛异常：%s" % e)
    log("open(step) → %r" % (panel,))
    time.sleep(1.5)

    after = wins_of(pid or -1)
    for h, t in after:
        if h not in before:
            log("  新窗口：%#010x %r" % (h, t))

    # 先 dump 主窗（参数窗若挂在主窗下）
    if panel is not None:
        dump_panel(panel, "panel")
    else:
        # 退一步：主窗里所有名字带 PotSquare 的控件
        log("")
        log("panel 为 None，改从主窗找 PotSquare* 控件")
        dump_panel(ui.main, "main")

    # 额外：所有新窗口也 dump 一遍
    for h, t in after:
        if h in before:
            continue
        try:
            import uiautomation as auto
            w = auto.ControlFromHandle(h)
            dump_panel(w, "win:%s" % t)
        except Exception as e:
            log("  窗口 %r dump 失败：%s" % (t, e))

    # 收尾
    try:
        from pywinauto.keyboard import send_keys
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.5)
    try:
        subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                       capture_output=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    rc = main()
    try:
        with open(OUT_LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(_records, f, ensure_ascii=False, indent=1)
        print("已写 %s / %s" % (OUT_LOG, OUT_JSON))
    except Exception as e:
        print("写文件失败：%s" % e)
    sys.exit(rc)
