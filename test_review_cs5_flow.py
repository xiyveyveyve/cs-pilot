# -*- coding: utf-8 -*-
"""test_review_cs5_flow.py —— 2026-11-14 代码审查修复 6-10 的离线回归。

6 wait_endexp 默认 quiet 3→8 s；阻抗收尾 quiet=120/轮超时 135/强制轮 150（低频点慢，
  短 quiet 会把测量间隙误判成已收尾）；OCP/动电位保持 8 s/12 s/30 s
7 _do_mon_test 文件心跳兜底取 files["test"]（旧取 "tafel" 恒 None = 死代码）
8 _safe_finish 拿不到 UI 锁 → 不做界面注入（多机互打架）
9 OCP 单位切不到「秒」/ EIS 电位基准切换失败 → fill_* 返回 False（不带错参数启动）
10 gui.py CS5 分支补 tafel_stop_ma（对齐 runner5_live，防残留阈值截断扫描）

纯离线：studio/运行窗/锁全部打桩。
"""
import inspect
import os
import sys
import tempfile
import time as _time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import driver5
import runner5 as R5
import ui_lock

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  | " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


class FakeTime:
    time = staticmethod(_time.time)
    sleep = staticmethod(lambda s: None)


class FakeStudio:
    def __init__(self):
        self.calls = []

    def stop_run(self, runwin=None):
        self.calls.append("stop")
        return True

    def close_run(self, runwin=None):
        self.calls.append("close")
        return True

    def cleanup_run_windows(self):
        self.calls.append("cleanup")
        return 0

    def _pid(self):
        return 4242


class FakeRunWin:
    def exists(self):
        return True

    def descendants(self, control_type=None):
        return []

    def window_text(self):
        return "开路电位 <2mA>  D:\\x\\1.cor"


def make_runner(studio, runwin=None, files=None):
    r = R5.Runner5.__new__(R5.Runner5)
    r.studio = studio
    r.runwin = runwin
    r.files = files or {}
    r.error = ""
    r.log = lambda *a: None
    r._states = []
    r.set_state = lambda s, e="": r._states.append(s)
    return r


# ---------------- 修复 6：quiet/超时按项目区分 ----------------
def test_finish_quiet():
    check("6a wait_endexp 默认 quiet=8 s",
          inspect.signature(R5.wait_endexp).parameters["quiet"].default == 8.0)

    orig_wait = R5.wait_endexp
    orig_modal = driver5.clear_modals
    seen = []

    def run_case(label, seq):
        seen.clear()

        def cap(log, method="", runwin=None, path=None, timeout=0,
                fallback=0, quiet=None, **kw):
            seen.append({"timeout": timeout, "quiet": quiet})
            return seq.pop(0) if seq else False

        R5.wait_endexp = cap
        driver5.clear_modals = lambda limit=4, prefer=None, pid=None: 0
        st = FakeStudio()
        r = make_runner(st, FakeRunWin(), {})
        ok = r._finish_run(label, idle_wait=0)
        return ok, st, r

    try:
        ok, st, r = run_case("动电位", [True])
        check("6b 动电位正常轮 quiet=8/超时12",
              ok is True and seen == [{"timeout": 12.0, "quiet": 8.0}], seen)
        ok, st, r = run_case("阻抗扫描", [True])
        check("6c 阻抗正常轮 quiet=120/超时135（低频点慢）",
              ok is True and seen == [{"timeout": 135.0, "quiet": 120.0}], seen)
        ok, st, r = run_case("交流阻抗", [False, False, False, True])
        check("6d 阻抗强制轮 超时150/quiet120",
              ok is True and len(seen) == 4
              and seen[3] == {"timeout": 150.0, "quiet": 120.0}
              and "close" in st.calls, (seen, st.calls))
        ok, st, r = run_case("动电位", [False] * 6 + [True])
        check("6e 动电位强制轮 超时30/quiet8",
              ok is True and len(seen) == 7
              and seen[6] == {"timeout": 30.0, "quiet": 8.0}, seen)
        ok, st, r = run_case("阻抗扫描", [])
        check("6f 阻抗最多 3 轮重点停止后报错（1+3 次 stop）",
              ok is False and st.calls.count("stop") == 4
              and R5.S_ERROR in r._states, (ok, st.calls, r._states))
        ok, st, r = run_case("动电位", [])
        check("6g 动电位最多 6 轮重点停止后报错（1+6 次 stop）",
              ok is False and st.calls.count("stop") == 7
              and R5.S_ERROR in r._states, (ok, st.calls, r._states))
    finally:
        R5.wait_endexp = orig_wait
        driver5.clear_modals = orig_modal


# ---------------- 修复 7：监视兜底用真实数据文件 ----------------
class FakeSampler:
    def alive(self):
        return True

    def read(self):
        return None


def test_mon_test_heartbeat():
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "2026-11-14 样品 动电位")
        with open(base + ".cor", "wb") as f:
            f.write(b"x" * 100)
        sig = (os.path.getsize(base + ".cor"), os.path.getmtime(base + ".cor"))

        def mk(files):
            r = make_runner(FakeStudio(), FakeRunWin(), files)
            r.cfg = R5.RunConfig5(sample="样品")
            r.sampler = FakeSampler()
            r.test_first_data_at = None
            r.t0 = _time.time()
            r._test_phase_t0 = _time.time()
            r._f_last = sig
            r._f_still = 59
            r._fin = []
            r._safe_finish = lambda label, idle_wait=0: r._fin.append(label) or True
            return r

        r = mk({"test": base})
        r._do_mon_test()
        check("7a files['test'] 冻结 24 s → 触发收尾判结束",
              r._fin == ["动电位"] and R5.S_DONE in r._states, (r._fin, r._states))

        r2 = mk({"tafel": base})   # 旧死键：不应再被使用
        r2._do_mon_test()
        check("7b 只有旧键 tafel 时不误触发（键已改 test）",
              r2._fin == [] and R5.S_DONE not in r2._states, (r2._fin, r2._states))


# ---------------- 修复 8：无 UI 锁不做界面收尾 ----------------
def test_lock_gate():
    orig_acq, orig_rel = ui_lock.ui_acquire, ui_lock.ui_release
    rel = []
    try:
        ui_lock.ui_release = lambda: rel.append(1)

        ui_lock.ui_acquire = lambda timeout=0: False
        r = make_runner(FakeStudio())
        r._fin = []
        r._finish_run = lambda label, idle_wait=0: r._fin.append(label) or True
        ok = r._safe_finish("动电位")
        check("8a 拿不到锁 → False 且不注入界面、不释放锁",
              ok is False and r._fin == [] and rel == [], (ok, r._fin, rel))

        ui_lock.ui_acquire = lambda timeout=0: True
        r2 = make_runner(FakeStudio())
        r2._fin = []
        r2._finish_run = lambda label, idle_wait=0: r2._fin.append(label) or True
        ok2 = r2._safe_finish("动电位")
        check("8b 拿到锁 → 正常收尾并释放锁",
              ok2 is True and r2._fin == ["动电位"] and rel == [1], (ok2, r2._fin, rel))
    finally:
        ui_lock.ui_acquire, ui_lock.ui_release = orig_acq, orig_rel


# ---------------- 修复 9：单位/基准切换失败 → 参数写入失败 ----------------
class FakeEdit:
    def __init__(self, aid, val=""):
        self.aid = aid
        self.val = val

    def automation_id(self):
        return self.aid

    def get_value(self):
        return self.val


class FakeCombo:
    def __init__(self, val):
        self.val = val

    def legacy_properties(self):
        return {"Value": self.val}


def make_studio(ids):
    s = driver5.Studio5.__new__(driver5.Studio5)
    s._logs = []
    s.log = lambda m: s._logs.append(str(m))
    s.by_ids = lambda panel: ids
    s.set_edit = lambda c, v: True
    return s


def test_fill_failures():
    real_time = driver5.time
    real_click = driver5.msg_click
    real_keys = driver5.send_keys
    driver5.time = FakeTime
    driver5.msg_click = lambda c: True
    driver5.send_keys = lambda *a, **k: None
    try:
        # OCP 单位卡在「分」→ False
        ids = {"Control_FileName_Text": FakeEdit("Control_FileName_Text"),
               "Ocp_Param_Combo": FakeCombo("分"),
               "Ocp_Param_Text": FakeEdit("Ocp_Param_Text")}
        s = make_studio(ids)
        ok = s.fill_ocp(None, r"C:\x.cor", 1800)
        check("9a OCP 单位切不到「秒」→ False",
              ok is False and any("参数写入失败" in m for m in s._logs), (ok, s._logs))
        # 单位本来就是「秒」→ True
        ids2 = dict(ids, Ocp_Param_Combo=FakeCombo("秒"))
        s2 = make_studio(ids2)
        check("9b OCP 单位已是「秒」→ True", s2.fill_ocp(None, r"C:\x.cor", 1800) is True)

        # EIS 基准切换失败 → False
        eis_ids = {k: FakeEdit(k) for k in (
            "Control_FileName_Text", "EISVSfrq_SineBias_Text", "EISVSfrq_SineAmp_Text",
            "EISVSfrq_InitFre_Text", "EISVSfrq_FinalFre_Text", "EISVSfrq_TenTwice_Text")}
        eis_ids["Vs_Combo"] = FakeCombo("相对参比")
        s3 = make_studio(eis_ids)
        s3._select_combo_containing = lambda c, want: False
        ok3 = s3.fill_eis(None, r"C:\x.z60")
        check("9c EIS 电位基准切换失败 → False",
              ok3 is False and any("电位基准" in m for m in s3._logs), (ok3, s3._logs))
        s4 = make_studio(eis_ids)
        s4._select_combo_containing = lambda c, want: True
        check("9d EIS 基准切换成功 → True", s4.fill_eis(None, r"C:\x.z60") is True)
    finally:
        driver5.time = real_time
        driver5.msg_click = real_click
        driver5.send_keys = real_keys


# ---------------- 修复 10：gui.py CS5 分支停止电流接线 ----------------
def test_gui_wiring():
    root = os.path.dirname(os.path.abspath(__file__))
    expr = "cfg.tafel_stop_ma = float(cfg.test_stop_i_density or 1e-3) * 1000.0"
    gui_src = open(os.path.join(root, "gui.py"), encoding="utf-8").read()
    live_src = open(os.path.join(root, "runner5_live.py"), encoding="utf-8").read()
    i = gui_src.find("cfg = R5.RunConfig5(")
    check("10a gui.py CS5 分支紧随停止电流接线",
          i >= 0 and expr in gui_src[i:i + 400], i)
    check("10b 与 runner5_live 口径一致", expr in live_src)
    cfg = R5.RunConfig5(sample="样品", area_cm2=1.2)
    cfg.tafel_stop_ma = float(cfg.test_stop_i_density or 1e-3) * 1000.0
    check("10c 绝对电流口径：1e-3 A → 1 mA（不乘面积）", abs(cfg.tafel_stop_ma - 1.0) < 1e-9,
          cfg.tafel_stop_ma)


if __name__ == "__main__":
    test_finish_quiet()
    test_mon_test_heartbeat()
    test_lock_gate()
    test_fill_failures()
    test_gui_wiring()
    print("-" * 50)
    if FAIL:
        print("FAIL %d 项：%s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("test_review_cs5_flow 全部通过")