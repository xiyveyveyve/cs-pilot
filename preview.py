# -*- coding: utf-8 -*-
"""preview.py —— 每桌面截图预览（方案 A 配套）。

runner 进程与它的 CS Studio 在同一命名桌面 → 同桌面截图百分百可靠。
每 interval 秒截主窗（含 MDI 曲线图）存 PNG，fleet_gui 四格拼屏定时重载。
"""
from __future__ import annotations

import os
import threading

PREVIEW_DIR = os.path.join(r"D:\deepseek\_probe\live", "preview")


def preview_path(name: str) -> str:
    return os.path.join(PREVIEW_DIR, "%s.png" % name)


def start_preview(name: str, stop_evt: threading.Event,
                  interval: float = 2.0, log=None) -> threading.Thread:
    """启动截图线程（daemon）。截本桌面 CS Studio 主窗 → preview/<name>.png。"""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    png = preview_path(name)

    def capture_hwnd(hwnd):
        """PrintWindow 截单窗（PW_RENDERFULLCONTENT）——非激活桌面也可靠。

        PIL ImageGrab 走 GDI 抓屏，在非激活虚拟桌面报 'screen grab failed'
        （2026-11-08 实证）；PrintWindow 由窗口自身线程渲染，无此限制。
        """
        import ctypes
        import win32gui
        import win32ui
        from PIL import Image
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return None
        hwindc = win32gui.GetWindowDC(hwnd)
        srcdc = win32ui.CreateDCFromHandle(hwindc)
        memdc = srcdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(srcdc, w, h)
        memdc.SelectObject(bmp)
        try:
            ok = ctypes.windll.user32.PrintWindow(hwnd, memdc.GetSafeHdc(), 2)
            if not ok:                          # 旧系统回退 0（客户区）
                ok = ctypes.windll.user32.PrintWindow(hwnd, memdc.GetSafeHdc(), 0)
            info = bmp.GetInfo()
            img = Image.frombuffer("RGB",
                                   (info["bmWidth"], info["bmHeight"]),
                                   bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
            return img if ok else None
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            memdc.DeleteDC()
            srcdc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwindc)

    def _loop():
        import win32gui
        while not stop_evt.is_set():
            try:
                hwnds = []

                def _cb(h, acc):
                    try:
                        t = win32gui.GetWindowText(h)
                        # 本桌面枚举自动只回调用进程所在桌面的顶层窗口
                        if "CS Studio" in t and win32gui.IsWindowVisible(h):
                            acc.append(h)
                    except Exception:
                        pass

                win32gui.EnumWindows(_cb, hwnds)
                if hwnds:
                    img = capture_hwnd(hwnds[0])
                    if img is not None:
                        tmp = png + ".tmp.png"
                        img.save(tmp)
                        os.replace(tmp, png)        # 原子替换，防 GUI 读到半张
            except Exception as e:
                if log:
                    log("preview: %r" % (e,))
            stop_evt.wait(interval)

    t = threading.Thread(target=_loop, daemon=True, name="preview-" + name)
    t.start()
    return t
