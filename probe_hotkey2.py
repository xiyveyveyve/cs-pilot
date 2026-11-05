# -*- coding: utf-8 -*-
"""probe_hotkey2.py —— 用 pywinauto 重新读 6 版「自定义快捷键」对话框。

上一次用 uiautomation 的 GetChildren 读到 0 个控件，这次换 pywinauto，
并保证无论如何都把对话框和软件关干净（上次留下 3 个窗口，很烦人）。
"""

import json
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import win32gui
import win32process

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT_LOG = r"D:\deepseek\_probe\hotkey2.log"
OUT_JSON = r"D:\deepseek\_probe\hotkey2.json"

_lines = []
_records = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill_all():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                       capture_output=True, timeout=20)
    except Exception:
        pass


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


def dump(win, tag, limit=300):
    log("")
    log("=== %s ===" % tag)
    n = 0
    try:
        kids = win.descendants()
    except Exception as e:
        log("  !! descendants 失败：%s" % e)
        return
    for c in kids:
        try:
            ei = c.element_info
            ct = (ei.control_type or "")
            name = (c.window_text() or "").strip()
            aid = getattr(ei, "automation_id", "") or ""
            cls = getattr(ei, "class_name", "") or ""
            r = c.rectangle()
            rec = {"tag": tag, "type": ct, "name": name, "aid": aid,
                   "cls": cls, "l": r.left, "t": r.top, "r": r.right, "b": r.bottom}
            _records.append(rec)
            log("  %-14s %-34r aid=%-24r cls=%-16r (%d,%d)"
                % (ct, name[:34], aid, cls[:16], r.left, r.top))
            n += 1
            if n >= limit:
                log("  …截断")
                break
        except Exception:
            continue
    log("  共 %d 个" % n)


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
    log("pid=%s" % pid)
    for h, t in wins_of(pid or -1):
        if "用户设置" in t or "找寻设备" in t:
            log("  关闭启动窗 %r" % t)
            win32gui.PostMessage(h, 0x0010, 0, 0)
    time.sleep(1.0)
    ui.force_foreground()
    ui.clear_modals(limit=3)

    log("")
    log("打开 系统设置 → 自定义快捷键 …")
    ok = ui.click_menu("%s", "自定义快捷键")
    log("  点击 → %s" % ok)
    time.sleep(2.0)

    from pywinauto import Desktop
    dlg = None
    try:
        d = Desktop(backend="uia")
        for w in d.windows():
            try:
                if (w.window_text() or "").strip() == "自定义快捷键":
                    dlg = w
                    break
            except Exception:
                continue
    except Exception as e:
        log("枚举桌面窗口失败：%s" % e)

    if dlg is None:
        log("!! 没拿到「自定义快捷键」窗口，硬找 pid 下的窗")
        for h, t in wins_of(pid or -1):
            log("   %#010x %r" % (h, t))
        return 3

    log("拿到对话框：%r" % (dlg.window_text(),))
    dump(dlg, "自定义快捷键")

    # 关掉对话框（点 取消/关闭），再关软件
    closed = False
    for label in ("取消", "关闭", "确定"):
        try:
            b = dlg.child_window(title=label, control_type="Button")
            if b.exists(timeout=0.5):
                b.click_input()
                log("点了「%s」关闭对话框" % label)
                closed = True
                break
        except Exception:
            continue
    if not closed:
        log("找不到关闭按钮")
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    finally:
        kill_all()
    try:
        with open(OUT_LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(_records, f, ensure_ascii=False, indent=1)
        print("已写 %s" % OUT_LOG)
    except Exception:
        pass
    sys.exit(rc)
