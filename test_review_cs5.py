# -*- coding: utf-8 -*-
"""test_review_cs5.py —— 2026-11-14 代码审查修复 1-5 的离线回归。

1 fill_tafel 停止电流强制写入+回读核验（缺控件→False；回读不符→重写；重写仍不符→False）
2 modal_dialogs/clear_modals 按 pid 过滤（多实例不点别台的确认框）
3 click_modal「另存为」只点「取消」，绝不 id 兜底误点「保存(S)」(id=1)
4 build_filenames5 查重覆盖 .cor/.z60/.txt（阻抗 .z60 同名不再被覆盖）
5 _stop_via_runwin_w：msg_click 结果检查 / 禁用态=已结束 / 确认框应答 / 无停止键保留窗口

纯离线：win32gui/win32process 全部打桩，不碰真窗口。
"""
import os
import shutil
import sys
import tempfile
import time as _time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import driver5
import runner5 as R5

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  | " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


class FakeTime:
    time = staticmethod(_time.time)
    sleep = staticmethod(lambda s: None)


# ---------------- 假 win32 ----------------
class FakeGui:
    """windows: [{h, cls, title, visible, pid, children:[{h, cls, id, text}]}]"""

    def __init__(self, windows):
        self.windows = windows
        self.clicked = []
        self._map = {}
        for w in windows:
            self._map[w["h"]] = w
            for c in w.get("children", []):
                self._map[c["h"]] = c

    def _get(self, h):
        return self._map.get(h, {})

    def IsWindowVisible(self, h):
        return self._get(h).get("visible", True)

    def GetClassName(self, h):
        return self._get(h).get("cls", "")

    def GetWindowText(self, h):
        return self._get(h).get("title", "") or self._get(h).get("text", "")

    def GetDlgCtrlID(self, h):
        return self._get(h).get("id", 0)

    def EnumWindows(self, cb, _):
        for w in self.windows:
            cb(w["h"], None)

    def EnumChildWindows(self, h, cb, _):
        for c in self._get(h).get("children", []):
            cb(c["h"], None)

    def SendMessage(self, h, msg, a, b):
        self.clicked.append((h, msg))


class FakeProc:
    def __init__(self, gui):
        self.gui = gui

    def GetWindowThreadProcessId(self, h):
        return (0, self.gui._get(h).get("pid", 0))


def install_fake_win32(windows):
    gui = FakeGui(windows)
    sys.modules["win32gui"] = gui
    sys.modules["win32process"] = FakeProc(gui)
    return gui


def uninstall_fake_win32():
    sys.modules.pop("win32gui", None)
    sys.modules.pop("win32process", None)


def btn(h, bid, text):
    return {"h": h, "cls": "Button", "id": bid, "text": text}


def static(h, text):
    return {"h": h, "cls": "Static", "id": 0, "text": text}


# ---------------- 修复 2：pid 过滤 ----------------
def test_pid_filter():
    windows = [
        {"h": 101, "cls": "#32770", "title": "提示", "pid": 111,
         "children": [static(1010, "是否覆盖当前文件?"), btn(1011, 6, "是(&Y)")]},
        {"h": 202, "cls": "#32770", "title": "提示", "pid": 222,
         "children": [static(2020, "别台的确认框"), btn(2021, 6, "是(&Y)")]},
        {"h": 303, "cls": "NotDialog", "title": "x", "pid": 111, "children": []},
    ]
    gui = install_fake_win32(windows)
    real_time = driver5.time
    driver5.time = FakeTime
    try:
        check("2a modal_dialogs 无 pid = 全部对话框",
              driver5.modal_dialogs() == [101, 202], driver5.modal_dialogs())
        check("2b modal_dialogs(pid=111) 只留本进程",
              driver5.modal_dialogs(pid=111) == [101], driver5.modal_dialogs(pid=111))
        gui.clicked.clear()
        n = driver5.clear_modals(limit=1, pid=111)
        check("2c clear_modals(pid=111) 只点本台的框",
              n == 1 and gui.clicked == [(1011, 0x00F5)], (n, gui.clicked))
        gui.clicked.clear()
        n = driver5.clear_modals(limit=1)
        check("2d clear_modals 无 pid 保持旧行为（两台都点）",
              n == 2 and set(h for h, _ in gui.clicked) == {1011, 2021}, (n, gui.clicked))
    finally:
        driver5.time = real_time
        uninstall_fake_win32()


# ---------------- 修复 3：另存为防护 ----------------
def test_saveas_guard():
    windows = [
        {"h": 404, "cls": "#32770", "title": "另存为", "pid": 1,
         "children": [btn(4041, 1, "保存(S)"), btn(4042, 2, "取消")]},
        {"h": 505, "cls": "#32770", "title": "另存为", "pid": 1,
         "children": [btn(5051, 1, "保存(S)")]},
        {"h": 606, "cls": "#32770", "title": "提示", "pid": 1,
         "children": [btn(6061, 6, "是(&Y)")]},
        {"h": 707, "cls": "#32770", "title": "", "pid": 1,
         "children": [static(7070, "另存为：请确认文件名"), btn(7071, 1, "保存(S)"), btn(7072, 2, "取消")]},
    ]
    gui = install_fake_win32(windows)
    try:
        got = driver5.click_modal(404)
        check("3a 另存为 → 点「取消」而非 id=1 的「保存」",
              got == "取消" and gui.clicked == [(4042, 0x00F5)], (got, gui.clicked))
        gui.clicked.clear()
        got = driver5.click_modal(505)
        check("3b 另存为无「取消」→ 不点任何按钮",
              got == "" and gui.clicked == [], (got, gui.clicked))
        gui.clicked.clear()
        got = driver5.click_modal(606)
        check("3c 普通确认框不受影响（点「是」）",
              got == "是(Y)" and gui.clicked == [(6061, 0x00F5)], (got, gui.clicked))
        gui.clicked.clear()
        got = driver5.click_modal(707)
        check("3d 标题为空但正文含「另存为」→ 同样只点「取消」",
              got == "取消" and gui.clicked == [(7072, 0x00F5)], (got, gui.clicked))
    finally:
        uninstall_fake_win32()


# ---------------- 修复 1：停止电流写入+回读 ----------------
class FakeEdit:
    def __init__(self, aid, val=""):
        self.aid = aid
        self.val = val
        self.writes = []

    def automation_id(self):
        return self.aid

    def get_value(self):
        return self.val

    def get_toggle_state(self):
        return 1


def make_studio(ids):
    s = driver5.Studio5.__new__(driver5.Studio5)
    s._logs = []
    s.log = lambda m: s._logs.append(str(m))
    s.by_ids = lambda panel: ids
    return s


def test_stop_current():
    real_time = driver5.time
    driver5.time = FakeTime
    try:
        # A 正常写入：阳极 5 mA + 下限固定 -2.00 mA，回读一致
        ids = {k: FakeEdit(k) for k in (
            "Control_FileName_Text", "PotDynamic_ScanStop_chk",
            "PotDynamic_MaxCurrent_txt", "PotDynamic_MinCurrent_txt")}
        s = make_studio(ids)
        s.set_edit = lambda c, v: (c.writes.append(v), setattr(c, "val", v), True)[-1]
        ok = s.fill_tafel(None, r"C:\x.cor", -0.5, 1.5, stop_ma=5.0)
        check("1a 停止电流写入成功 → True",
              ok and ids["PotDynamic_MaxCurrent_txt"].val == "5.00"
              and ids["PotDynamic_MinCurrent_txt"].val == "-2.00",
              (ok, ids["PotDynamic_MaxCurrent_txt"].val, ids["PotDynamic_MinCurrent_txt"].val))
        check("1b 日志记录软件侧实际停止电流",
              any("软件侧停止电流" in m for m in s._logs), s._logs)

        # B 缺 MaxCurrent 控件 → 中止（防残留阈值截断扫描）
        ids2 = {k: FakeEdit(k) for k in (
            "Control_FileName_Text", "PotDynamic_ScanStop_chk",
            "PotDynamic_MinCurrent_txt")}
        s2 = make_studio(ids2)
        s2.set_edit = lambda c, v: (c.writes.append(v), setattr(c, "val", v), True)[-1]
        ok2 = s2.fill_tafel(None, r"C:\x.cor", -0.5, 1.5, stop_ma=5.0)
        check("1c 缺 MaxCurrent 控件 → False 并告警",
              ok2 is False and any("缺 PotDynamic_MaxCurrent_txt" in m for m in s2._logs),
              (ok2, s2._logs))

        # C 写入“成功”但值残留（软件没吃进去）→ 重写仍不符 → False
        ids3 = {k: FakeEdit(k, "0.10" if "Current" in k else "") for k in (
            "Control_FileName_Text", "PotDynamic_ScanStop_chk",
            "PotDynamic_MaxCurrent_txt", "PotDynamic_MinCurrent_txt")}
        s3 = make_studio(ids3)

        def sticky_set(c, v):
            c.writes.append(v)
            if "Current" in c.aid:
                return True  # 假成功：值不变（真机残留阈值场景）
            c.val = v
            return True

        s3.set_edit = sticky_set
        ok3 = s3.fill_tafel(None, r"C:\x.cor", -0.5, 1.5, stop_ma=5.0)
        check("1d 回读不符且重写无效 → False（不带残留阈值启动）",
              ok3 is False and any("回读" in m for m in s3._logs), (ok3, s3._logs))

        # D 首次回读不符，重写后生效 → True
        ids4 = {k: FakeEdit(k, "0.10" if "Current" in k else "") for k in (
            "Control_FileName_Text", "PotDynamic_ScanStop_chk",
            "PotDynamic_MaxCurrent_txt", "PotDynamic_MinCurrent_txt")}
        s4 = make_studio(ids4)

        def flaky_set(c, v):
            c.writes.append(v)
            if c.aid == "PotDynamic_MaxCurrent_txt" and len(c.writes) == 1:
                return True  # 第一遍没吃进去
            c.val = v
            return True

        s4.set_edit = flaky_set
        ok4 = s4.fill_tafel(None, r"C:\x.cor", -0.5, 1.5, stop_ma=5.0)
        check("1e 回读不符 → 重写生效 → True",
              ok4 is True and ids4["PotDynamic_MaxCurrent_txt"].val == "5.00"
              and len(ids4["PotDynamic_MaxCurrent_txt"].writes) == 2,
              (ok4, ids4["PotDynamic_MaxCurrent_txt"].val))

        # F stop_ma=None → 不动停止电流框
        ids5 = {k: FakeEdit(k) for k in (
            "Control_FileName_Text", "PotDynamic_ScanStop_chk",
            "PotDynamic_MaxCurrent_txt", "PotDynamic_MinCurrent_txt")}
        s5 = make_studio(ids5)
        s5.set_edit = lambda c, v: (c.writes.append(v), setattr(c, "val", v), True)[-1]
        ok5 = s5.fill_tafel(None, r"C:\x.cor", -0.5, 1.5)
        check("1f stop_ma=None 不触碰停止电流框",
              ok5 and not ids5["PotDynamic_MaxCurrent_txt"].writes
              and not ids5["PotDynamic_MinCurrent_txt"].writes, ok5)
    finally:
        driver5.time = real_time


# ---------------- 修复 4：查重覆盖三种后缀 ----------------
def test_pick_extensions():
    from datetime import datetime
    tmp = tempfile.mkdtemp(prefix="cspilot_pick_")
    try:
        cfg = R5.RunConfig5(sample="JK-F", out_dir=tmp, item="Tafel", eis_enabled=True)
        d = datetime.now().strftime("%Y-%m-%d")
        base_eis = os.path.join(tmp, "%s JK-F 交流阻抗" % d)
        base_ocp = os.path.join(tmp, "%s JK-F 开路电位" % d)
        base_test = os.path.join(tmp, "%s JK-F 动电位" % d)

        open(base_eis + ".z60", "w").close()
        f = R5.build_filenames5(cfg)
        check("4a 已存在 .z60 → 阻抗名加 _2（不再覆盖）",
              f["eis"] == base_eis + "_2", f["eis"])

        open(base_eis + "_2.txt", "w").close()
        f = R5.build_filenames5(cfg)
        check("4b _2 被 .txt 占用 → 继续 _3", f["eis"] == base_eis + "_3", f["eis"])

        open(base_ocp + ".cor", "w").close()
        open(base_test + ".txt", "w").close()
        f = R5.build_filenames5(cfg)
        check("4c OCP .cor / 动电位 .txt 同样查重",
              f["ocp"] == base_ocp + "_2" and f["test"] == base_test + "_2", f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 修复 5：_stop_via_runwin_w ----------------
class FakeBtn:
    def __init__(self, text, enabled=True):
        self.text = text
        self.enabled = enabled

    def window_text(self):
        return self.text

    def is_enabled(self):
        return self.enabled


class FakeTB:
    def __init__(self, btns):
        self.btns = btns

    def descendants(self, control_type=None):
        return self.btns


class FakeW:
    def __init__(self, tbs):
        self.tbs = tbs

    def descendants(self, control_type=None):
        return self.tbs


def test_stop_via_runwin():
    real_time = driver5.time
    real_msg_click = driver5.msg_click
    real_clear = driver5.clear_modals
    real_answer = driver5.answer_confirm_uia
    driver5.time = FakeTime
    calls = {"click": [], "clear": [], "answer": []}
    click_ret = [True]
    clear_ret = [1]

    def fake_msg_click(b):
        calls["click"].append(b.text)
        return click_ret[0]

    def fake_clear(**kw):
        calls["clear"].append(kw)
        return clear_ret[0]

    def fake_answer(pid, **kw):
        calls["answer"].append(pid)
        return "是"

    driver5.msg_click = fake_msg_click
    driver5.clear_modals = fake_clear
    driver5.answer_confirm_uia = fake_answer
    gui = install_fake_win32([{"h": 999, "cls": "RunWin", "title": "动电位", "pid": 4242}])
    try:
        def run(btns):
            for k in calls:
                calls[k].clear()
            return driver5._stop_via_runwin_w(FakeW([FakeTB(btns)]), 999)

        # A 点到停止 + 应答确认框
        click_ret[0] = True
        clear_ret[0] = 1
        r = run([FakeBtn("停止")])
        check("5a 点击生效 → True，并按 pid 应答确认框",
              r is True and calls["click"] == ["停止"]
              and calls["clear"] and calls["clear"][0].get("pid") == 4242
              and not calls["answer"], (r, calls))

        # B 点击未生效 → False（保留窗口，不关）
        click_ret[0] = False
        r = run([FakeBtn("停止")])
        check("5b msg_click False → False（不再谎报已停）",
              r is False and not calls["clear"], (r, calls))

        # C 停止键禁用 = 实验已自行结束
        click_ret[0] = True
        r = run([FakeBtn("停止", enabled=False)])
        check("5c 停止键禁用 → True 且不点击",
              r is True and not calls["click"], (r, calls))

        # D 没有停止键 → False
        r = run([FakeBtn("开始"), FakeBtn("关闭")])
        check("5d 无停止键 → False（保留窗口）", r is False, r)

        # E 确认框不是 #32770 → UIA 兜底
        click_ret[0] = True
        clear_ret[0] = 0
        r = run([FakeBtn("停止")])
        check("5e clear_modals 无获 → answer_confirm_uia(pid) 兜底",
              r is True and calls["answer"] == [4242], (r, calls))

        # F 禁用键在前、可用键在后 → 点可用的那个
        clear_ret[0] = 1
        r = run([FakeBtn("停止", enabled=False), FakeBtn("停止")])
        check("5f 禁用+可用并存 → 点可用键",
              r is True and calls["click"] == ["停止"], (r, calls))
    finally:
        driver5.time = real_time
        driver5.msg_click = real_msg_click
        driver5.clear_modals = real_clear
        driver5.answer_confirm_uia = real_answer
        uninstall_fake_win32()


if __name__ == "__main__":
    test_pid_filter()
    test_saveas_guard()
    test_stop_current()
    test_pick_extensions()
    test_stop_via_runwin()
    print("-" * 50)
    if FAIL:
        print("FAIL %d 项：%s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("test_review_cs5 全部通过")