# -*- coding: utf-8 -*-
"""test_review_cs6.py —— 2026-11-14 代码审查修复 11-18 的离线回归。

11 _data_paths 枚举真实存在的 .txt/.cor/.z60（阻抗 .z60 心跳不再盲）
12 close_run_windows 顶层 owned 运行窗先点停止，停不下来保留（关窗≠实验停）
13 _finish 拿不到 UI 锁不做界面收尾；判停分支不再锁外裸 stop
14 is_running 键数守卫（抓错工具栏不瞎判）；_toolbar 双候选键数不符 → None
15 _do_stop_eis 无条件 settle（is_running 启发式有假阴性）
16 _settle_after_stop 60s 文件仍在长 → False（不再「按已停止处理」）
17 force_stop is_running 抛异常不再谎报已停
18 ocp_fixed 固定时长模式不重试 OCP

纯离线：UI/锁/时钟全部打桩。
"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import driver_direct as DD
import runner6 as R6
import studio_ui as S
import ui_lock

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  | " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_r6(files=None):
    r = R6.Runner6.__new__(R6.Runner6)
    r.files = files or {}
    r._logs = []
    r.log = lambda m: r._logs.append(str(m))
    r.ui = None
    return r


# ---------------- 修复 11：数据文件后缀枚举 ----------------
def test_data_paths():
    with tempfile.TemporaryDirectory() as td:
        b_ocp = os.path.join(td, "2026-11-14 样品 开路电位")
        b_test = os.path.join(td, "2026-11-14 样品 动电位")
        b_eis = os.path.join(td, "2026-11-14 样品 交流阻抗")
        open(b_ocp + ".txt", "w").close()
        open(b_test + ".txt", "w").close()
        open(b_eis + ".z60", "w").close()
        r = make_r6({"ocp_real": b_ocp + ".txt", "test": b_test, "eis": b_eis})
        paths = r._data_paths()
        check("11a 阻抗 .z60 被监视（不再只补 .txt）",
              b_eis + ".z60" in paths and b_eis + ".txt" not in paths, paths)
        check("11b OCP/动电位 .txt 正常收录",
              b_ocp + ".txt" in paths and b_test + ".txt" in paths, paths)

        r2 = make_r6({"eis": os.path.join(td, "不存在")})
        check("11c 文件未落盘 → 不收幽灵路径", r2._data_paths() == [], r2._data_paths())

        b_cor = os.path.join(td, "2026-11-14 样品 动电位2")
        open(b_cor + ".cor", "w").close()
        r3 = make_r6({"test": b_cor})
        check("11d .cor 变体同样收录", r3._data_paths() == [b_cor + ".cor"], r3._data_paths())


# ---------------- 修复 16/15：settle 超时与无条件收尾 ----------------
class FakeDD:
    def __init__(self):
        self.calls = []

    def stop(self, tries=5):
        self.calls.append("stop")
        return True

    def force_stop(self, timeout=30.0):
        self.calls.append("force_stop")
        return True

    def close_run_windows(self):
        self.calls.append("close_windows")
        return 0

    def close_analysis(self):
        self.calls.append("close_analysis")
        return 0

    def is_running(self):
        return False


def test_settle_timeout():
    clock = FakeClock()
    real_time = R6.time
    R6.time = clock
    try:
        # 文件一直在长 → 60s 后必须 False，且不关窗、不进下一步
        r = make_r6()
        r.dd = FakeDD()
        r._data_paths = lambda: ["fake.cor"]
        r._file_growing = lambda p, window=0: True
        r._wait_idle_menu = lambda timeout=0: True
        ok = r._settle_after_stop("交流阻抗", idle=0)
        check("16a 60s 仍在长 → False（不再按已停止处理）",
              ok is False and "force_stop" in r.dd.calls
              and "close_windows" not in r.dd.calls
              and any("停止未生效" in m for m in r._logs), (ok, r.dd.calls))

        # 文件冻结 → 正常走完收尾
        r2 = make_r6()
        r2.dd = FakeDD()
        r2._data_paths = lambda: ["fake.cor"]
        r2._file_growing = lambda p, window=0: False
        r2._wait_idle_menu = lambda timeout=0: True
        ok2 = r2._settle_after_stop("交流阻抗", idle=0)
        check("16b 文件冻结 → 收尾成功",
              ok2 is True and "close_windows" in r2.dd.calls, (ok2, r2.dd.calls))

        # 菜单没恢复 → False（原有红线保持）
        r3 = make_r6()
        r3.dd = FakeDD()
        r3._data_paths = lambda: []
        r3._file_growing = lambda p, window=0: False
        r3._wait_idle_menu = lambda timeout=0: False
        check("16c 菜单栏未恢复 → False", r3._settle_after_stop("测试项", idle=0) is False)
    finally:
        R6.time = real_time


def test_stop_eis_unconditional():
    r = make_r6()
    r.dd = FakeDD()                     # is_running() 恒 False（假阴性场景）
    r.cfg = R6.RunConfig6(sample="样品", eis_enabled=True, tafel_enabled=False)
    r.stage_elapsed = lambda: 10.0
    r._settled = []
    r._settle_after_stop = lambda label, idle=0: r._settled.append(label) or True
    r._done = []
    r._done_no_test = lambda: r._done.append(1)
    r._fail = lambda msg: r._logs.append("FAIL:" + msg)
    r.stage_t0 = 0.0
    r._do_stop_eis()
    check("15a is_running=False 也走 settle（文件心跳裁决）",
          r._settled == ["交流阻抗"] and r._done == [1], (r._settled, r._done))

    r2 = make_r6()
    r2.dd = FakeDD()
    r2.cfg = r.cfg
    r2.stage_elapsed = lambda: 10.0
    r2._settle_after_stop = lambda label, idle=0: False
    r2._done = []
    r2._done_no_test = lambda: r2._done.append(1)
    r2._failed = []
    r2._fail = lambda msg: r2._failed.append(msg)
    r2.stage_t0 = 0.0
    r2._do_stop_eis()
    check("15b settle 失败 → 报错且不进下一步",
          r2._failed and r2._done == [], (r2._failed, r2._done))


# ---------------- 修复 13：_finish 锁门 + 判停分支无裸 stop ----------------
def test_finish_lock():
    orig_acq, orig_rel = ui_lock.ui_acquire, ui_lock.ui_release
    rel = []
    try:
        ui_lock.ui_release = lambda: rel.append(1)

        ui_lock.ui_acquire = lambda timeout=0: False
        r = make_r6()
        r.dd = FakeDD()
        r.running = True
        r._settled = []
        r._settle_after_stop = lambda label, idle=0: r._settled.append(label) or True
        r._failed = []
        r._fail = lambda msg: r._failed.append(msg)
        r._states = []
        r.set_state = lambda s, d="": r._states.append(s)
        r._finish()
        check("13a 拿不到锁 → 不收尾、报失败、不释放锁",
              r._settled == [] and r._failed and r.running is False
              and rel == [] and R6.S_DONE not in r._states,
              (r._settled, r._failed, rel))

        ui_lock.ui_acquire = lambda timeout=0: True
        r2 = make_r6()
        r2.dd = FakeDD()
        r2.running = True
        r2._settled = []
        r2._settle_after_stop = lambda label, idle=0: r2._settled.append(label) or True
        r2._failed = []
        r2._fail = lambda msg: r2._failed.append(msg)
        r2._states = []
        r2.set_state = lambda s, d="": r2._states.append(s)
        r2._finish()
        check("13b 拿到锁 → 正常收尾并释放",
              r2._settled == ["测试项"] and rel == [1]
              and R6.S_DONE in r2._states and not r2._failed,
              (r2._settled, rel, r2._states))
    finally:
        ui_lock.ui_acquire, ui_lock.ui_release = orig_acq, orig_rel

    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner6.py"),
               encoding="utf-8").read()
    i = src.find("if self._i_hit >= 2:")
    block = src[i:i + 300]
    check("13c 判停分支不再锁外裸 stop（settle 在锁内点停止）",
          i >= 0 and "self.dd.stop()" not in block.split("self._finish()")[0], block)


# ---------------- 修复 14：键数守卫 + 工具栏宁缺毋滥 ----------------
class FakeBtn:
    def __init__(self, enabled=True):
        self._e = enabled

    def is_enabled(self):
        return self._e


class FakeUI:
    def __init__(self, btns):
        self._btns = btns

    def _toolbar(self, kind):
        return object()

    def _tb_buttons(self, tb):
        return self._btns


def test_is_running_guard():
    dd = DD.DirectDriver.__new__(DD.DirectDriver)
    dd._is_running_heuristic = lambda: True
    dd.ui = FakeUI([FakeBtn(False)] * 17)
    check("14a 数据栏 17 键且停止禁用 → 判已停", dd.is_running() is False)
    dd.ui = FakeUI([FakeBtn(False)] * 3)
    check("14b 抓错工具栏（3 键）→ 保守判在跑", dd.is_running() is True)
    dd._is_running_heuristic = lambda: False
    dd.ui = FakeUI([FakeBtn(True)] * 17)
    check("14c 启发式判没跑 → False", dd.is_running() is False)


def test_toolbar_none():
    ui = S.Studio.__new__(S.Studio)
    tb_hi, tb_lo = object(), object()
    nseq = len(S.SEQ_BTN)
    ui.toolbars = lambda: [(400, None, tb_hi), (100, None, tb_lo)]
    ui._tb_buttons = lambda tb: [FakeBtn()] * nseq     # 两个都是序列栏键数
    check("14d 双候选键数都不符 → None（不瞎认数据栏）",
          ui._toolbar("data") is None)
    ui._tb_buttons = lambda tb: [FakeBtn()] * (17 if tb is tb_hi else nseq)
    check("14e 下方候选 17 键 → 认它", ui._toolbar("data") is tb_hi)


# ---------------- 修复 12：顶层运行窗先停再关 ----------------
class FakeApp:
    def __init__(self, backend=None):
        pass

    def connect(self, handle=None, timeout=None):
        return self

    def window(self, handle=None):
        return object()


class FakeMain:
    def descendants(self, control_type=None):
        return []


class FakeUI2:
    main = FakeMain()


def test_owned_stop_first():
    fake_w32 = types.SimpleNamespace(
        GetWindowText=lambda h: "波形图 <2mA> D:\\x.cor",
        PostMessage=lambda h, msg, a, b: posted.append((h, msg)))
    fake_pywinauto = types.SimpleNamespace(Application=FakeApp)
    old_w32 = sys.modules.get("win32gui")
    old_pw = sys.modules.get("pywinauto")
    sys.modules["win32gui"] = fake_w32
    sys.modules["pywinauto"] = fake_pywinauto
    real_time = DD.time
    DD.time = FakeClock()
    posted = []
    try:
        def mk(stop_ret):
            dd = DD.DirectDriver.__new__(DD.DirectDriver)
            dd.ui = FakeUI2()
            dd.run_windows = lambda: [555]
            dd._stop_via_runwin = lambda w: stop_ret
            dd._logs = []
            dd.log = lambda m: dd._logs.append(str(m))
            return dd

        posted.clear()
        dd = mk((False, True))          # 有停止键但停不下来
        n = dd.close_run_windows()
        check("12a 停不下来 → 保留窗口（不 WM_CLOSE）",
              n == 0 and posted == [] and any("保留" in m for m in dd._logs),
              (n, posted))

        posted.clear()
        dd = mk((True, True))           # 停下来了
        n = dd.close_run_windows()
        check("12b 已停 → 关窗", n == 1 and posted == [(555, 0x0010)], (n, posted))

        posted.clear()
        dd = mk((False, False))         # 窗里没有停止键（纯波形图）
        n = dd.close_run_windows()
        check("12c 无停止键 → 按旧行为关窗", n == 1 and posted == [(555, 0x0010)],
              (n, posted))
    finally:
        DD.time = real_time
        if old_w32 is None:
            sys.modules.pop("win32gui", None)
        else:
            sys.modules["win32gui"] = old_w32
        if old_pw is None:
            sys.modules.pop("pywinauto", None)
        else:
            sys.modules["pywinauto"] = old_pw


# ---------------- 修复 17：force_stop 异常不谎报 ----------------
def test_force_stop():
    real_time = DD.time
    DD.time = FakeClock()
    try:
        dd = DD.DirectDriver.__new__(DD.DirectDriver)
        dd.mdi_run_windows = lambda: []
        dd.run_windows = lambda: []
        dd.ui = None
        dd._logs = []
        dd.log = lambda m: dd._logs.append(str(m))

        def boom():
            raise RuntimeError("UIA 抖动")

        dd.is_running = boom
        check("17a is_running 一直抛异常 → 超时返回 False（不谎报已停）",
              dd.force_stop(timeout=5.0) is False)
        dd.is_running = lambda: False
        check("17b 确认已停 → True", dd.force_stop(timeout=5.0) is True)
    finally:
        DD.time = real_time


# ---------------- 修复 18：固定时长不重试 ----------------
def test_ocp_fixed():
    r = make_r6()
    r._ocp_round = 0
    r.cfg = R6.RunConfig6(sample="样品", ocp_fixed=True, ocp_max_rounds=0)
    check("18a ocp_fixed=True 不限轮数也不重试", r._ocp_can_retry() is False)
    r.cfg = R6.RunConfig6(sample="样品", ocp_fixed=False, ocp_max_rounds=0)
    check("18b 非 fixed 不限轮数 → 可重试", r._ocp_can_retry() is True)
    r.cfg = R6.RunConfig6(sample="样品", ocp_fixed=False, ocp_max_rounds=2)
    check("18c 非 fixed 第 1/2 轮 → 可重试", r._ocp_can_retry() is True)
    r._ocp_round = 1
    check("18d 非 fixed 第 2/2 轮 → 不再重试", r._ocp_can_retry() is False)


if __name__ == "__main__":
    test_data_paths()
    test_settle_timeout()
    test_stop_eis_unconditional()
    test_finish_lock()
    test_is_running_guard()
    test_toolbar_none()
    test_owned_stop_first()
    test_force_stop()
    test_ocp_fixed()
    print("-" * 50)
    if FAIL:
        print("FAIL %d 项：%s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("test_review_cs6 全部通过")