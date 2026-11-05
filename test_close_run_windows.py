# -*- coding: utf-8 -*-
"""test_close_run_windows.py —— 回归：close_run_windows 绝不能关掉通道窗。

probe_rehearsal6 实测踩坑：旧版"MDI Window 标题非空就关"把
「通道1【型号：DEMOSN in Demo】」也关了，通道窗一关点「开始」就没有序列。
运行：python test_close_run_windows.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class FakeWin:
    def __init__(self, title):
        self._t = title
        self.closed = False

    def window_text(self):
        return self._t

    def close(self):
        self.closed = True


class FakeMain:
    def __init__(self, wins):
        self._wins = wins

    def descendants(self, control_type=None):
        return list(self._wins)


class FakeUI:
    def __init__(self, wins):
        self.main = FakeMain(wins)


def make_dd(ui):
    import driver_direct as DD
    return DD.DirectDriver(ui, base=None, log=lambda m: None)


def main():
    wins = [
        FakeWin("[通道1]-开路电位测量(OCP) <D:\\x\\a.txt> [2mA] "),  # 该关
        FakeWin("通道1【型号：DEMOSN in Demo】"),                     # 绝不能关
        FakeWin("[通道1]-动电位扫描(Tafel,LPR) <D:\\x\\b.txt> "),     # 该关
        FakeWin("CS Studio6  演示模式"),                              # 主窗不碰（不在树里也会被过滤）
    ]
    dd = make_dd(FakeUI(wins))
    n = dd.close_run_windows()
    ok1 = wins[0].closed and wins[2].closed
    ok2 = not wins[1].closed
    ok3 = n == 2
    print("PASS 关掉运行窗" if ok1 else "FAIL 运行窗没关")
    print("PASS 通道窗保留" if ok2 else "FAIL 通道窗被误关（rehearsal6 踩的坑）")
    print("PASS 返回计数=2" if ok3 else "FAIL 计数=%d" % n)
    # 波形图独立窗
    wins2 = [FakeWin("波形图"), FakeWin("通道1【型号：X】")]
    dd2 = make_dd(FakeUI(wins2))
    dd2.close_run_windows()
    print("PASS 波形图被关" if wins2[0].closed else "FAIL 波形图没关")
    print("PASS 通道窗保留(2)" if not wins2[1].closed else "FAIL 通道窗被误关(2)")
    allok = ok1 and ok2 and ok3 and wins2[0].closed and not wins2[1].closed
    print()
    print("全部 PASS" if allok else "FAIL")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
