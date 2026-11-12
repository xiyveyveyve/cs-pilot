# -*- coding: utf-8 -*-
"""test_run_window_visible.py —— 运行窗跑到屏幕外时的归位逻辑（离线，不需要 CS Studio）。

2026-11-12 真机 2 号：多实例并发时 CS5 把运行窗排到主窗左边
rect=(-31,97,640,571)，用户看不到页面、msg_click 的坐标点击全部落空。
driver5.ensure_run_window_visible 负责把它拉回屏幕内（只挪位置、不改可见性）。
"""
import sys

try:
    import win32api
    import win32con
    import win32gui
except ImportError:      # pragma: no cover
    print("SKIP 需要 pywin32")
    sys.exit(0)

from driver5 import Studio5

TOTAL = 0
FAIL = 0
_CLS = "JKPVisibleTest"


def check(name, ok, detail=""):
    global TOTAL, FAIL
    TOTAL += 1
    print(("PASS " if ok else "FAIL ") + name + (("  " + detail) if detail else ""))
    if not ok:
        FAIL += 1


class FakeRW:
    def __init__(self, hwnd):
        self.handle = hwnd


def _wndproc(h, m, wp, lp):
    return win32gui.DefWindowProc(h, m, wp, lp)


def _ensure_class():
    try:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = _wndproc
        wc.lpszClassName = _CLS
        wc.hInstance = win32gui.GetModuleHandle(None)
        win32gui.RegisterClass(wc)
    except Exception:
        pass


def make_win(x, y, w=400, hh=300):
    _ensure_class()
    h = win32gui.CreateWindowEx(
        0, _CLS, "JKP 运行窗测试", win32con.WS_OVERLAPPEDWINDOW,
        x, y, w, hh, 0, 0, win32gui.GetModuleHandle(None), None)
    win32gui.ShowWindow(h, win32con.SW_SHOW)
    return h


def destroy(h):
    try:
        win32gui.DestroyWindow(h)
    except Exception:
        pass


def main():
    studio = object.__new__(Studio5)
    logs = []
    studio.log = lambda m: logs.append(m)

    # 1) 正常可见窗口 → 不动
    h1 = make_win(100, 100)
    ok = studio.ensure_run_window_visible(FakeRW(h1))
    check("正常窗口不动", ok is False)
    destroy(h1)

    # 2) 跑到屏幕外（负坐标，复现 2 号 (-31,97,640,571)）→ 拉回
    h2 = make_win(-500, -400)
    ok = studio.ensure_run_window_visible(FakeRW(h2))
    l, t, r, b = win32gui.GetWindowRect(h2)
    check("屏幕外窗口被拉回", ok is True and l >= 0 and t >= 0,
          "rect=(%d,%d,%d,%d)" % (l, t, r, b))
    destroy(h2)

    # 3) 右下越界 → 拉回
    sw = win32api.GetSystemMetrics(0)
    sh = win32api.GetSystemMetrics(1)
    h3 = make_win(sw + 100, sh + 100)
    ok = studio.ensure_run_window_visible(FakeRW(h3))
    l, t, r, b = win32gui.GetWindowRect(h3)
    check("右下越界被拉回", ok is True and r <= sw and b <= sh,
          "rect=(%d,%d,%d,%d)" % (l, t, r, b))
    destroy(h3)

    print("\n全部 %d 项 %s" % (TOTAL, "PASS" if not FAIL else "%d FAIL" % FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
