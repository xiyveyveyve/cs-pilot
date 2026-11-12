# -*- coding: utf-8 -*-
"""position_windows.py —— 把 CS Studio5 / CS Studio6 主窗摆到左右两半。

两套 runner 并行时 UIA 点击按屏幕坐标落点：窗口重叠会把点击送到
别的窗口上。左右分屏后互不遮挡，这是双机并行的唯一硬要求。
"""
import sys
import win32gui

# 950x1000：完整落在 1080p 屏内（任务栏上方），左右分屏互不遮挡
TARGETS = {"CS Studio5": (0, 0, 950, 1000),
           "CS Studio6": (960, 0, 950, 1000)}


def main():
    moved = []
    hits = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            t = win32gui.GetWindowText(h)
            for key, rect in TARGETS.items():
                if t.startswith(key) and h not in hits:
                    x, y, w, hgt = rect
                    win32gui.MoveWindow(h, x, y, w, hgt, True)
                    hits.append((key, h, t[:50]))
                    moved.append(h)
                    break
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    for key, h, t in hits:
        print("已摆放: %s hwnd=%s %r" % (key, h, t))
    if len(hits) < 2:
        print("警告：只找到 %d 个主窗（两台都要在运行才能摆）" % len(hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
