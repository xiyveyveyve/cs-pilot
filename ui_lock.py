# -*- coding: utf-8 -*-
"""ui_lock.py —— 跨进程全局 UI 操作锁。

主桌面下 4 个 CS Studio 实例并存时，鼠标/键盘注入是**全局**的
（SendInput 发给前台窗口）。必须保证「同一时刻只有一个 runner 在做
UI 交互」（点菜单、填参数、点确定、收尾点停止），否则 4 个实例
互相抢焦点：A 的 keystroke 打到 B 的窗口。

实验监视段（读数、判停）不注入输入，不持锁——4 台并行推进。

命名桌面（CreateDesktop）已证伪：那边 SendInput/keybd_event/PostMessage
全部被系统拒绝，GetForegroundWindow()=0，本锁只用于主桌面方案。
"""
import ctypes
import time

_MUTEX_NAME = "Global\\cspilot_ui_lock"
_k32 = ctypes.windll.kernel32
_handle = None
_held = False
_depth = 0


def ui_acquire(timeout: float = 0.0) -> bool:
    """尝试拿全局 UI 锁。timeout=0 为非阻塞（拿不到立即返回 False）。

    可重入：同进程嵌套 acquire 只加计数，配对 release 减到 0 才真释放
    （旧版内层 release 会把外层的锁提前放掉，别台趁虚而入，审查 #24）。
    """
    global _handle, _held, _depth
    if _held:
        _depth += 1
        return True
    h = _k32.CreateMutexW(None, False, _MUTEX_NAME)
    if not h:
        return False
    ms = int(max(0.0, timeout) * 1000)
    r = _k32.WaitForSingleObject(h, ms)
    # WAIT_OBJECT_0=0, WAIT_ABANDONED=0x80（前一个持有者异常退出）
    if r in (0, 0x80):
        _handle = h
        _held = True
        _depth = 1
        return True
    _k32.CloseHandle(h)
    return False


def ui_release():
    """释放全局 UI 锁（幂等；重入计数减到 0 才真释放）。"""
    global _handle, _held, _depth
    if not _held:
        return
    _depth -= 1
    if _depth > 0:
        return
    try:
        if _handle:
            _k32.ReleaseMutex(_handle)
            _k32.CloseHandle(_handle)
    except Exception:
        pass
    _handle = None
    _held = False
    _depth = 0


def ui_held() -> bool:
    return _held


class ui_guard:
    """with 语法糖：拿不到锁则抛 TimeoutError。"""

    def __init__(self, timeout: float = 600.0):
        self.timeout = timeout

    def __enter__(self):
        if not ui_acquire(self.timeout):
            raise TimeoutError("等待 UI 锁超时 %.0fs" % self.timeout)
        return self

    def __exit__(self, *exc):
        ui_release()
        return False
