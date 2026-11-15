# -*- coding: utf-8 -*-
"""回归：CS5 stop_run 必须区分「已结束」与「停不下来」（11-14 真机事故）。

背景：实验自然结束后「停止」键禁用，旧 stop_run 静默跳过 → 返回 False →
runner 空转 6 轮"停止未生效"（~90 s）再走关窗兜底；兜底图标键只认英文
"stop"，中文名「停止」永远匹配不上。本测试锁定：
  ① 停止键禁用 → 返回 True（交文件心跳裁决），不点击、不进兜底
  ② 点击未生效（msg_click False）→ 如实返回 False，不谎报成功
  ③ 图标兜底只点 enabled 的键
运行：python test_stop_run_cs5.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import driver5
from driver5 import Studio5

FAIL = []
TOTAL = [0]


def check(cond, label):
    TOTAL[0] += 1
    if cond:
        print("PASS %s" % label)
    else:
        FAIL.append(label)
        print("FAIL %s" % label)


class FakeInfo:
    def __init__(self, aid=""):
        self.automation_id = aid


class FakeButton:
    def __init__(self, text="", enabled=True, visible=True, aid=""):
        self._text = text
        self._enabled = enabled
        self._visible = visible
        self.element_info = FakeInfo(aid)

    def window_text(self):
        return self._text

    def is_enabled(self):
        return self._enabled

    def is_visible(self):
        return self._visible


class FakeRunWin:
    def __init__(self, btns):
        self._btns = btns

    def descendants(self, control_type=None):
        return list(self._btns)


def make_studio(logs):
    s = Studio5.__new__(Studio5)
    s.log = lambda m: logs.append(m)
    s._pid = lambda: 1234
    return s


def run_case(btns, click_ok=True):
    """返回 (结果, 被点的按钮列表, 日志)。"""
    clicked = []
    logs = []
    orig = (driver5.msg_click, driver5.modal_dialogs, driver5.modal_text,
            driver5.clear_modals, driver5.answer_confirm_uia)
    try:
        driver5.msg_click = lambda b: (clicked.append(b), click_ok)[1]
        driver5.modal_dialogs = lambda pid=None: []
        driver5.modal_text = lambda h: ""
        driver5.clear_modals = lambda limit=6, prefer=None, pid=None: 0
        driver5.answer_confirm_uia = lambda pid, prefer=None: ""
        s = make_studio(logs)
        ok = s.stop_run(FakeRunWin(btns), tries=1)
    finally:
        (driver5.msg_click, driver5.modal_dialogs, driver5.modal_text,
         driver5.clear_modals, driver5.answer_confirm_uia) = orig
    return ok, clicked, logs


b_ok = FakeButton("停止", enabled=True)
ok, clicked, logs = run_case([FakeButton("打开"), b_ok, FakeButton("暂停")])
check(ok is True and clicked == [b_ok], "1 停止键可用 → 点它并返回 True")

b_dis = FakeButton("停止", enabled=False)
ok, clicked, logs = run_case([FakeButton("打开"), b_dis, FakeButton("暂停")])
check(ok is True and not clicked and any("禁用" in m for m in logs),
      "2 停止键禁用 → 不点击、返回 True、日志说明原因")

b_icon = FakeButton("", enabled=True, aid="toolStripButtonStop")
ok, clicked, logs = run_case([FakeButton("打开"), b_icon])
check(ok is True and clicked == [b_icon], "3 无文本停止键 → 图标兜底点 enabled 键")

b_icon_dis = FakeButton("", enabled=False, aid="toolStripButtonStop")
ok, clicked, logs = run_case([FakeButton("打开"), b_icon_dis])
check(ok is False and not clicked, "4 图标键禁用 → 不盲点，返回 False")

ok, clicked, logs = run_case([FakeButton("打开"), FakeButton("重新测试")])
check(ok is False and not clicked, "5 无停止相关键 → 返回 False，绝不点「重新测试」")

b_ok2 = FakeButton("停止", enabled=True)
ok, clicked, logs = run_case([b_ok2], click_ok=False)
check(ok is False and clicked == [b_ok2],
      "6 msg_click 未生效 → 如实返回 False（不谎报成功）")

ok, clicked, logs = run_case([b_dis, b_icon])
check(ok is True and not clicked,
      "7 文本停止键禁用时直接判已结束，不再进图标兜底")

print()
if FAIL:
    for f in FAIL:
        print("FAIL " + f)
    sys.exit(1)
print("全部 %d 项 PASS" % TOTAL[0])