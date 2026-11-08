# -*- coding: utf-8 -*-
"""probe_input.py —— 命名桌面输入 API 诊断（在目标桌面上运行）。

用法：fleet.spawn_on_desktop("CSP-X", 'python probe_input.py CSP-X 结果文件路径')
依次测 SetCursorPos / mouse_event / keybd_event / SendInput / GetCursorPos，
结果写文本文件。
"""
import sys


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "?"
    out = sys.argv[2] if len(sys.argv) > 2 else r"D:\deepseek\_probe\live\input_diag.txt"
    lines = ["== desktop %s ==" % name]
    # ★ 全程 pywin32（不经 _ctypes——它在命名桌面初始化失败）
    import win32api
    import win32gui
    import win32con
    h = win32api.GetCurrentThread()      # 伪句柄——GetUserObjectInformation 取线程桌面名
    buf = win32gui.PyMakeBuffer(256)
    win32gui.GetUserObjectInformation(h, 2, buf, 256)
    lines.append("thread desktop: %r" % buf[:].decode("utf-16-le", errors="replace").split(chr(0))[0])

    # 1) SetCursorPos
    try:
        win32api.SetCursorPos((200, 200))
        lines.append("SetCursorPos: OK")
    except Exception as e:
        lines.append("SetCursorPos ERR: %r" % (e,))

    # 2) GetCursorPos 读回
    try:
        x, y = win32api.GetCursorPos()
        lines.append("GetCursorPos: (%d,%d)" % (x, y))
    except Exception as e:
        lines.append("GetCursorPos ERR: %r" % (e,))

    # 3) keybd_event（pywin32）
    try:
        win32api.keybd_event(0x14, 0, 0, 0)   # SCROLL LOCK 无害
        win32api.keybd_event(0x14, 0, 2, 0)   # keyup
        lines.append("keybd_event: OK")
    except Exception as e:
        lines.append("keybd_event ERR: %r" % (e,))

    # 1) SetCursorPos
    try:
        ok = u32.SetCursorPos(200, 200)
        err = k32.GetLastError()
        lines.append("SetCursorPos: ok=%s err=%d" % (bool(ok), err if not ok else 0))
    except Exception as e:
        lines.append("SetCursorPos EX: %r" % (e,))

    # 2) GetCursorPos（读回验证）
    try:
        pt = ctypes.wintypes.POINT() if hasattr(ctypes, "wintypes") else None
        import ctypes.wintypes as wt
        pt = wt.POINT()
        ok = u32.GetCursorPos(ctypes.byref(pt))
        lines.append("GetCursorPos: ok=%s pos=(%d,%d)" % (bool(ok), pt.x, pt.y))
    except Exception as e:
        lines.append("GetCursorPos EX: %r" % (e,))

    # 3) mouse_event（旧 API，移动+点击）
    try:
        u32.mouse_event(0x0001, 50, 0, 0, 0)      # MOUSEEVENTF_MOVE
        lines.append("mouse_event MOVE: no exception")
    except Exception as e:
        lines.append("mouse_event EX: %r" % (e,))

    # 4) SendInput（结构体）
    try:
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_uint), ("time", ctypes.c_uint),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        class INPUT(ctypes.Structure):
            class _I(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("i",)
            _fields_ = [("type", ctypes.c_uint), ("i", _I)]
        inp = INPUT()
        inp.type = 1                              # INPUT_KEYBOARD
        inp.i.ki.wVk = 0x14                       # SCROLL LOCK 无害键
        r = u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        lines.append("SendInput: sent=%d" % r)
    except Exception as e:
        lines.append("SendInput EX: %r" % (e,))

    with open(out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
