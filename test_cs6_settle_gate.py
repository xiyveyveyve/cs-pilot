# -*- coding: utf-8 -*-
"""回归：CS6 收尾红线（11-14 真机两次 COMError 崩溃事故）。

事故链：OCP 数据停滞 7.5 s 被误判"自行结束" → 收尾陷「另存为」循环
（点保存(S) 4 次不消失）→ 菜单栏 60 s 不恢复 → 旧代码"先按空闲处理"
硬开下一轮 → UIA COMError 崩溃。本测试锁定四件事：
  ① 「另存为」模态框点「取消」，绝不点「保存」（数据已在盘上）
  ② _menu_idle 三态：明确禁用=False，判不了=True（保持原行为）
  ③ 数据停滞但菜单禁用 → 不判"自行结束"，继续监视
  ④ _settle_after_stop 返回 False 时，OCP/阻抗/测试项三个收尾闸门
     都必须 _fail 停止自动接续，绝不硬开下一项
运行：python test_cs6_settle_gate.py
"""
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win32gui
import win32con

import runner6
import studio_ui
from runner6 import Runner6, S_STOP_OCP, S_DONE
from studio_ui import Studio

FAIL = []
TOTAL = [0]


def check(cond, label):
    TOTAL[0] += 1
    if cond:
        print("PASS %s" % label)
    else:
        FAIL.append(label)
        print("FAIL %s" % label)


# ---- A. 另存为模态框应答 ----

def run_modal(title, buttons):
    """buttons: [(hwnd, 文本, 控件ID)]；返回 (结果, SendMessage记录, PostMessage记录)。"""
    s = Studio.__new__(Studio)
    s.win32_modal_dialogs = lambda pid=None: [(100, title, None)]
    s.dialog_text = lambda h: "保存在(&I): / 文件名(&N):"
    s._main_pid = lambda: 1
    sent, posted = [], []
    names = ("EnumChildWindows", "GetClassName", "GetWindowText",
             "GetDlgCtrlID", "SendMessage", "PostMessage")
    orig = {n: getattr(win32gui, n) for n in names}
    try:
        win32gui.EnumChildWindows = lambda h, cb, acc: [cb(c, acc) for c, _, _ in buttons]
        win32gui.GetClassName = lambda ch: "BUTTON"
        win32gui.GetWindowText = lambda ch: next(t for c, t, _ in buttons if c == ch)
        win32gui.GetDlgCtrlID = lambda ch: next(i for c, _, i in buttons if c == ch)
        win32gui.SendMessage = lambda ch, msg, *a: sent.append((ch, msg))
        win32gui.PostMessage = lambda h, msg, *a: posted.append((h, msg))
        r = s.close_win32_modal()
    finally:
        for n, v in orig.items():
            setattr(win32gui, n, v)
    return r, sent, posted


r, sent, posted = run_modal("另存为", [(1, "保存(S)", 1), (2, "取消", 2)])
check(r[2] == "取消" and sent == [(2, win32con.BM_CLICK)] and not posted,
      "A1 另存为 → 点取消，不点保存")

r, sent, posted = run_modal("提示", [(1, "是(Y)", 6), (2, "否(N)", 7)])
check(r[2] == "是(Y)" and sent == [(1, win32con.BM_CLICK)],
      "A2 普通确认框应答行为不变（是(Y)）")

r, sent, posted = run_modal("另存为", [(1, "保存(S)", 1)])
check(r[2] == "<WM_CLOSE>" and not sent and posted == [(100, win32con.WM_CLOSE)],
      "A3 另存为无取消键 → WM_CLOSE 关掉，仍不点保存")


# ---- B. _menu_idle 三态 ----

class FakeItem:
    def __init__(self, text, enabled):
        self._t, self._e = text, enabled

    def window_text(self):
        return self._t

    def is_enabled(self):
        return self._e


class FakeMain:
    def __init__(self, items, raise_=False):
        self._items, self._raise = items, raise_

    def descendants(self, control_type=None):
        if self._raise:
            raise RuntimeError("UIA 抖动")
        return list(self._items)


class FakeUI:
    def __init__(self, items, raise_=False):
        self.main = FakeMain(items, raise_)


def menu_idle(ui):
    r = Runner6.__new__(Runner6)
    r.ui = ui
    return r._menu_idle()


check(menu_idle(FakeUI([FakeItem("测试方法(E)", True)])) is True,
      "B1 菜单可用 → True")
check(menu_idle(FakeUI([FakeItem("测试方法(E)", False)])) is False,
      "B2 菜单禁用 → False")
check(menu_idle(FakeUI([FakeItem("文件(F)", True)])) is True,
      "B3 找不到测试方法项 → True（判不了保持原行为）")
check(menu_idle(None) is True, "B4 无 ui → True")
check(menu_idle(FakeUI([], raise_=True)) is True, "B5 读取出错 → True")


# ---- C. 停滞交叉验证 ----

class FakeTail:
    def __init__(self, series):
        self._s = series

    def poll(self):
        pass

    def series_ev(self):
        return list(self._s)


class FakeStab:
    def feed(self, series):
        return types.SimpleNamespace(stable=False, t_now=series[-1][0],
                                     mean_v=series[-1][1], reason="")


def make_mon(menu_idle_val):
    r = Runner6.__new__(Runner6)
    r.cfg = types.SimpleNamespace(
        stab=types.SimpleNamespace(min_points=2),
        ocp_fixed=False, ocp_time_sec=1800, max_ocp_sec=1800)
    r.tail_ocp = FakeTail([(1.0, -0.1), (1117.0, -0.18)])
    r.stab = FakeStab()
    r.on_sample = None
    r._ocp_last_t = 1117.0
    r._ocp_stall = 29
    r._ocp_round = 0
    r._ocp_can_retry = lambda: False
    r._menu_idle = lambda: menu_idle_val
    r.stage_t0 = time.time()
    r.states = []
    r.logs = []
    r.set_state = lambda s, d="": r.states.append((s, d))
    r.log = lambda m: r.logs.append(m)
    return r


r = make_mon(False)
r._do_mon_ocp()
check(not r.states and r._ocp_stall == 30
      and any("菜单仍禁用" in m for m in r.logs),
      "C1 停滞+菜单禁用 → 不判自行结束，继续监视")
r._do_mon_ocp()
check(sum("菜单仍禁用" in m for m in r.logs) == 1,
      "C2 持续停滞不刷屏（只提示一次）")

r = make_mon(True)
r._do_mon_ocp()
check(any(s == S_STOP_OCP and "自行结束" in d for s, d in r.states),
      "C3 停滞+菜单可用 → 照旧判自行结束")


# ---- D. 收尾闸门 ----

class FakeDD:
    def __init__(self, running=True):
        self._running = running
        self.analysis_closed = 0

    def is_running(self):
        return self._running

    def stop(self, tries=1):
        return True

    def force_stop(self, timeout=30.0):
        pass

    def close_run_windows(self):
        return 0

    def close_analysis(self):
        self.analysis_closed += 1
        return 0


def make_settler(idle_menu):
    r = Runner6.__new__(Runner6)
    r.files = {}
    r.dd = FakeDD()
    r.ui = None
    r.logs = []
    r.log = lambda m: r.logs.append(m)
    r._wait_idle_menu = lambda timeout=60.0: idle_menu
    return r


r = make_settler(False)
check(r._settle_after_stop("开路电位", idle=0) is False,
      "D1 菜单未恢复 → _settle_after_stop 返回 False")
r = make_settler(True)
check(r._settle_after_stop("开路电位", idle=0) is True
      and r.dd.analysis_closed == 1,
      "D2 菜单恢复 → 返回 True 且照旧关 CSAnalysis")

r = Runner6.__new__(Runner6)
r.stage_elapsed = lambda: 10.0
r._settle_after_stop = lambda *a, **k: False
r.fails, r.enters = [], []
r._fail = lambda m: r.fails.append(m)
r._enter_after_stop = lambda s: r.enters.append(s)
r._ocp_retry = False
r.cfg = types.SimpleNamespace(eis_enabled=True)
r.log = lambda m: None
r._do_stop_ocp()
check(len(r.fails) == 1 and not r.enters,
      "D3 OCP 收尾失败 → _fail 且不进下一项")

r = Runner6.__new__(Runner6)
r.dd = FakeDD(running=True)
r.stage_elapsed = lambda: 10.0
r._settle_after_stop = lambda *a, **k: False
r.fails, r.enters, r.dones = [], [], []
r._fail = lambda m: r.fails.append(m)
r._enter_after_stop = lambda s: r.enters.append(s)
r._done_no_test = lambda: r.dones.append(1)
r._next_test_state = lambda: "S_TEST"
r.cfg = types.SimpleNamespace(tafel_enabled=True)
r.log = lambda m: None
r._do_stop_eis()
check(len(r.fails) == 1 and not r.enters and not r.dones,
      "D4 阻抗收尾失败 → _fail 且不进下一项")

fake_lock = types.ModuleType("ui_lock")
fake_lock.ui_acquire = lambda t=60.0: True
fake_lock.ui_release = lambda: None
fake_lock.ui_held = lambda: False
_orig_lock = sys.modules.get("ui_lock")
sys.modules["ui_lock"] = fake_lock
try:
    for settled, want_done in ((False, False), (True, True)):
        r = Runner6.__new__(Runner6)
        r.dd = FakeDD()
        r._settle_after_stop = lambda *a, **k: settled
        r.running = True
        r.states, r.fails = [], []
        r.set_state = lambda s, d="": r.states.append(s)
        r._fail = lambda m: r.fails.append(m)
        r.log = lambda m: None
        r._finish()
        if want_done:
            check(S_DONE in r.states and not r.fails and r.running is False,
                  "D5 测试项收尾成功 → 照旧 S_DONE")
        else:
            check(S_DONE not in r.states and len(r.fails) == 1
                  and r.running is False,
                  "D6 测试项收尾失败 → _fail，绝不谎报完成")
finally:
    if _orig_lock is not None:
        sys.modules["ui_lock"] = _orig_lock
    else:
        del sys.modules["ui_lock"]

print()
if FAIL:
    for f in FAIL:
        print("FAIL " + f)
    sys.exit(1)
print("全部 %d 项 PASS" % TOTAL[0])