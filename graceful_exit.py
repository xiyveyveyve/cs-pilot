# -*- coding: utf-8 -*-
"""graceful_exit.py —— CLI 入口的优雅退出防护（2026-11-07 真机首跑事故）。

事故：runner 进程被强杀（taskkill /F 或直接关控制台）时没有任何中止收尾，
实验被丢在软件里继续加电采集，直到有人接手清理。

能防的：
  * Ctrl+C（SIGINT）
  * 控制台窗口关闭 / 任务管理器"结束任务"（SIGBREAK，CTRL_CLOSE_EVENT）
  * 主循环超时截断（配合下面的 drain 习惯用法）
不能防的：
  * taskkill /F /IM —— 系统无条件终结进程，任何语言任何程序都收不到通知。
    这也是 gui 路线加 WM_DELETE_WINDOW 拦截、CLI 路线加本模块的原因。

用法（三个 CLI 入口统一）：
    import graceful_exit
    ...
    r.start()
    graceful_exit.install(lambda: r, log)
    while r.running:
        r.tick()
        time.sleep(0.25)
    # 正常结束
"""
from __future__ import annotations

import signal

_handlers_installed = False


def install(get_runner, log) -> bool:
    """注册 SIGINT/SIGBREAK 处理器。

    get_runner(): 返回当前 runner 实例（或 None）；
    处理器只调 runner.abort()——置位 + 停当前实验 + 置已中止态，
    主循环看到 running=False 后自然退出并打印 summary。
    返回是否成功注册（非主线程/不支持的平台会失败，调用方忽略即可）。
    """
    global _handlers_installed

    def _handler(signum, _frame):
        try:
            r = get_runner()
            if r is not None and getattr(r, "running", False):
                log("[graceful] 收到退出信号 %s → 请求中止实验并收尾…" % signum)
                r.abort()
                log("[graceful] 已请求中止，等待主循环收尾后退出")
        except Exception:
            pass                       # 最后关头的处理器绝不能再抛

    registered = True
    for name in ("SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            registered = False         # 非主线程等场景
    _handlers_installed = registered
    return registered


def drain(r, log, tick, timeout: float = 120.0):
    """abort 后的收尾循环：继续 tick 让 runner 走完收尾状态机。"""
    import time
    end = time.time() + timeout
    while r.running and time.time() < end:
        tick()
        time.sleep(0.25)
    if r.running:
        log("[graceful] 收尾超时（%.0fs），进程退出后实验可能仍在跑" % timeout)
