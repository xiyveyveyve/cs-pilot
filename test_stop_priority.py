# -*- coding: utf-8 -*-
"""test_stop_priority.py —— 回归：停止必须先点「停止」键，不能直接关窗。

2026-11-12 真机 2/4 号实测：无通道窗直开模式下 _toolbar("data") 强制要求
两个工具栏 → 返回 None → stop() 永远点不到停止键；且 CS6 按钮无文本，
_stop_via_runwin 文本匹配必空 → close_run_windows 把正在跑的实验窗直接
WM_CLOSE（关窗≠实验停）。本测试用假工具栏/假窗锁定三处修复：
  ① _toolbar("data") 认单个数据栏（15~20 键），不误认序列栏/主工具栏
  ② stop() 键数校验用区间而非 16 键全等
  ③ _stop_via_runwin 对无文本按钮按 toolStrip1 + 键数点第 0 键
运行：python test_stop_priority.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import driver_direct as DD
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


class FakeElementInfo:
    def __init__(self, control_type, automation_id=""):
        self.control_type = control_type
        self.automation_id = automation_id


class FakeButton:
    def __init__(self, events, name, text="", enabled=True):
        self.element_info = FakeElementInfo("Button")
        self.name = name
        self._text = text
        self._enabled = enabled
        self._events = events

    def window_text(self):
        return self._text

    def is_enabled(self):
        return self._enabled

    def click_input(self):
        self._events.append(("click", self.name))


class FakeToolbar:
    def __init__(self, events, n, text="", aid="toolStrip1", enabled=True):
        self.element_info = FakeElementInfo("ToolBar", aid)
        self.btns = [FakeButton(events, "b%d" % i, text=text, enabled=enabled)
                     for i in range(n)]

    def descendants(self, control_type=None):
        return list(self.btns)


class FakeStudioUI:
    """只提供 _toolbar 的输入：toolbars() 与 _tb_buttons()。"""

    def __init__(self, tbs):
        self._tbs = tbs            # [(top, toolbar)]

    def toolbars(self):
        return [(top, None, tb) for top, tb in self._tbs]

    def _tb_buttons(self, tb):
        return list(tb.btns)

    _toolbar = Studio._toolbar


class FakeMain:
    def __init__(self, wins):
        self._wins = wins

    def descendants(self, control_type=None):
        return list(self._wins)


class FakeUI:
    def __init__(self, tbs=(), wins=()):
        self._host = FakeStudioUI(tbs)
        self.main = FakeMain(wins)

    def _toolbar(self, kind):
        return self._host._toolbar(kind)

    def _tb_buttons(self, tb):
        return list(tb.btns)

    def clear_modals(self, *a, **k):
        return 0


class DDForStop(DD.DirectDriver):
    """stop() 决策测试：脚本化 is_running，隔离真实窗口枚举与 taskkill。"""

    def __init__(self, ui, runwins, running):
        super().__init__(ui, base=None, log=lambda m: None)
        self._rw = runwins
        self._running = list(running)
        self.fallback_closed = 0

    def mdi_run_windows(self):
        return self._rw

    def run_windows(self):
        return []

    def is_running(self):
        return self._running.pop(0) if self._running else False

    def close_run_windows(self):
        self.fallback_closed += 1
        return 0

    def close_analysis(self):
        return 0


class DDForClose(DD.DirectDriver):
    def run_windows(self):
        return []


class FakeRunWin:
    def __init__(self, title, tbs, events):
        self._t = title
        self._tbs = tbs
        self._events = events
        self.closed = False

    def window_text(self):
        return self._t

    def is_visible(self):
        return True

    def descendants(self, control_type=None):
        return list(self._tbs)

    def close(self):
        self.closed = True
        self._events.append(("close", self._t))


RUN_TITLE = "[通道1]-开路电位测量(OCP) <D:\\x\\a.txt> [2mA]"


def main():
    ev = []

    # ---- A. _toolbar("data") 选择逻辑 ----
    tb17 = FakeToolbar(ev, 17)
    tb16 = FakeToolbar(ev, 16)
    tb14 = FakeToolbar(ev, 14)
    tb13 = FakeToolbar(ev, 13, aid="toolStrip")
    check(FakeStudioUI([(400, tb17)])._toolbar("data") is tb17,
          "A1 单个 17 键数据栏（无通道窗直开模式）能认出")
    check(FakeStudioUI([(400, tb16)])._toolbar("data") is tb16,
          "A2 单个 16 键数据栏能认出")
    check(FakeStudioUI([(100, tb14)])._toolbar("data") is None,
          "A3 单个 14 键序列栏不误认数据栏")
    check(FakeStudioUI([(100, tb13)])._toolbar("data") is None,
          "A4 单个 13 键主工具栏不误认数据栏")
    check(FakeStudioUI([(100, tb14), (400, tb17)])._toolbar("data") is tb17,
          "A5 双工具栏取靠下的数据栏（原行为保持）")
    check(FakeStudioUI([(100, tb17), (400, tb14)])._toolbar("data") is tb17,
          "A6 双工具栏位置颠倒仍按键数认出数据栏（原行为保持）")
    check(FakeStudioUI([])._toolbar("data") is None,
          "A7 无工具栏返回 None")
    check(FakeStudioUI([(400, FakeToolbar(ev, 15))])._toolbar("data") is not None
          and FakeStudioUI([(400, FakeToolbar(ev, 20))])._toolbar("data") is not None
          and FakeStudioUI([(400, FakeToolbar(ev, 21))])._toolbar("data") is None,
          "A8 键数区间边界 15/20 认、21 不认")

    # ---- B. stop() 的点击决策 ----
    rw = [(object(), RUN_TITLE)]
    evB = []
    ui = FakeUI(tbs=[(400, FakeToolbar(evB, 17))])
    dd = DDForStop(ui, rw, running=[True, False])
    ok = dd.stop()
    check(ok and ("click", "b0") in evB and dd.fallback_closed == 0,
          "B1 无通道窗+17 键数据栏：点第 0 键停止，不走关窗兜底")

    evB = []
    ui = FakeUI(tbs=[(400, FakeToolbar(evB, 16))])
    dd = DDForStop(ui, rw, running=[True, False])
    ok = dd.stop()
    check(ok and ("click", "b0") in evB and dd.fallback_closed == 0,
          "B2 16 键数据栏仍点停止（向后兼容）")

    evB = []
    ui = FakeUI(tbs=[(400, FakeToolbar(evB, 18))])
    dd = DDForStop(ui, rw, running=[True, False])
    ok = dd.stop()
    check(ok and ("click", "b0") in evB and dd.fallback_closed == 0,
          "B3 18 键数据栏点停止（旧 16 键全等校验会漏）")

    evB = []
    ui = FakeUI(tbs=[(100, FakeToolbar(evB, 13, aid="toolStrip"))])
    dd = DDForStop(ui, rw, running=[True, False])
    ok = dd.stop(tries=1)
    check(ok and not evB and dd.fallback_closed == 1,
          "B4 只有主工具栏：绝不盲点索引（CS Analysis 旧事故），走兜底")

    evB = []
    ui = FakeUI(tbs=[(100, FakeToolbar(evB, 14))])
    dd = DDForStop(ui, rw, running=[True, False])
    ok = dd.stop(tries=1)
    check(ok and not evB and dd.fallback_closed == 1,
          "B5 只有序列栏：不当数据栏点，走兜底")

    # ---- C. _stop_via_runwin / close_run_windows ----
    dd = DDForClose(FakeUI(), base=None, log=lambda m: None)

    evC = []
    w = FakeRunWin(RUN_TITLE, [FakeToolbar(evC, 17)], evC)
    check(dd._stop_via_runwin(w) == (True, True) and evC == [("click", "b0")],
          "C1 CS6 无文本 17 键 toolStrip1：点第 0 键停止")

    evC = []
    tb = FakeToolbar(evC, 5)
    tb.btns[2]._text = "停止"
    w = FakeRunWin(RUN_TITLE, [tb], evC)
    check(dd._stop_via_runwin(w) == (True, True) and evC == [("click", "b2")],
          "C2 有文本「停止」按钮优先按文本点（CS5 路径保持）")

    evC = []
    w = FakeRunWin(RUN_TITLE, [FakeToolbar(evC, 17, enabled=False)], evC)
    check(dd._stop_via_runwin(w) == (False, False) and not evC,
          "C3 停止键禁用=实验已结束：不点，交调用方直接关")

    evC = []
    w = FakeRunWin("波形图", [FakeToolbar(evC, 5)], evC)
    check(dd._stop_via_runwin(w) == (False, False) and not evC,
          "C4 小工具栏图形窗：不点，可直接关")

    evC = []
    w = FakeRunWin(RUN_TITLE, [FakeToolbar(evC, 17, aid="toolStripOther")], evC)
    check(dd._stop_via_runwin(w) == (False, False) and not evC,
          "C5 非 toolStrip1 的 17 键工具栏不盲点")

    class StaleWin:
        def descendants(self, control_type=None):
            raise RuntimeError("stale")

    check(dd._stop_via_runwin(StaleWin()) == (False, False),
          "C6 stale 窗读不出结构：按无停止钮处理（原行为保持）")

    evC = []
    run = FakeRunWin(RUN_TITLE, [FakeToolbar(evC, 17)], evC)
    chan = FakeRunWin("通道1【型号：X】", [], evC)
    dd = DDForClose(FakeUI(wins=[run, chan]), base=None, log=lambda m: None)
    n = dd.close_run_windows()
    check(evC == [("click", "b0"), ("close", RUN_TITLE)] and n == 1
          and not chan.closed,
          "C7 关运行窗前先点停止（顺序锁定），通道窗不碰")

    print()
    if FAIL:
        print("FAIL %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
        return 1
    print("全部 PASS（%d 项）" % TOTAL[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())