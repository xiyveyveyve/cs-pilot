# -*- coding: utf-8 -*-
"""test_review_fleet_data.py —— 2026-11-14 代码审查修复 19-26 的离线回归。

19 stop_all 先广播 CTRL_BREAK 再统一等待；stopping 期间冻结复活
20 stop_machine 收尾等待 90→300 s
21 finished_quiet 自适应写入节奏；静默判停叠加菜单恢复
22 一键清场顺序：先停 runner 再杀软件
23 判稳序列遇 t 回退 → 重置重积累（不再静默丢点）
24 UI 锁可重入计数；信号处理器只置旗标，主循环 consume_abort 执行中止
25 看板 refresh 异常不打断 2s 重排
26 OCP 全程无数据拒绝 0 V 基准（走停止收尾再报错）；读文件异常留痕

纯离线：进程/内核/信号/时钟全部打桩，不碰真机。
"""
import os
import subprocess
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import fleet as F
import fleet_gui as FG
import graceful_exit as GE
import runner6 as R6
import stabilizer as ST
import ui_lock
import watch as W

FAIL = []
ROOT = os.path.dirname(os.path.abspath(__file__))


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  | " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeProc:
    def __init__(self, name, events, alive=True, clock=None, advance=0.0,
                 wait_timeout=False):
        self.name = name
        self.pid = 9000 + sum(ord(c) for c in name)
        self.events = events
        self.alive = alive
        self.clock = clock
        self.advance = advance
        self.wait_timeout = wait_timeout
        self.returncode = 0 if not alive else None

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.events.append(("wait", self.name, timeout))
        if self.clock is not None:
            self.clock.t += self.advance
        if self.wait_timeout:
            raise subprocess.TimeoutExpired(self.name, timeout)
        self.alive = False
        self.returncode = 0
        return 0

    def kill(self):
        self.events.append(("kill", self.name))
        self.alive = False
        self.returncode = -9


def patch_os_kill(events):
    orig = F.os.kill

    def fake(pid, sig):
        events.append(("break", pid))
    F.os.kill = fake
    return orig


# ---------------- 修复 19：急停广播 + 冻结复活 ----------------
def test_stop_all_broadcast():
    ev = []
    orig_kill = patch_os_kill(ev)
    try:
        fl = F.Fleet([{"name": "A"}, {"name": "B"}, {"name": "C"}])
        pa = FakeProc("A", ev)
        pb = FakeProc("B", ev)
        pc = FakeProc("C", ev, alive=False)
        fl.state = {"A": {"proc": pa}, "B": {"proc": pb}, "C": {"proc": pc}}
        fl.stop_all()
        kinds = [e[0] for e in ev]
        check("19a 先给所有活进程广播 CTRL_BREAK，再统一等待",
              kinds == ["break", "break", "wait", "wait"], ev)
        check("19b 已退出的进程不发信号不等待",
              all(e[1] != pc.pid for e in ev if e[0] == "break")
              and all(e[1] != "C" for e in ev if e[0] == "wait"), ev)
        check("19c stopping 旗标置位", fl.stopping is True)
        ta = [e[2] for e in ev if e[0] == "wait" and e[1] == "A"][0]
        check("19d 统一等待上限 300s", 299.0 <= ta <= 300.0, ta)
    finally:
        F.os.kill = orig_kill


def test_stop_all_shared_deadline():
    ev = []
    clock = FakeClock()
    orig_kill = patch_os_kill(ev)
    orig_time = F.time
    F.time = clock
    try:
        fl = F.Fleet([{"name": "A"}, {"name": "B"}])
        pa = FakeProc("A", ev, clock=clock, advance=200.0)
        pb = FakeProc("B", ev, clock=clock)
        fl.state = {"A": {"proc": pa}, "B": {"proc": pb}}
        fl.stop_all()
        waits = {e[1]: e[2] for e in ev if e[0] == "wait"}
        check("19e 共享截止时间：A 耗 200s 后 B 只等剩余 100s",
              abs(waits["A"] - 300.0) < 1e-6 and abs(waits["B"] - 100.0) < 1e-6,
              waits)
    finally:
        F.time = orig_time
        F.os.kill = orig_kill


def test_stop_all_kill_fallback():
    ev = []
    orig_kill = patch_os_kill(ev)
    try:
        fl = F.Fleet([{"name": "A"}])
        pa = FakeProc("A", ev, wait_timeout=True)
        fl.state = {"A": {"proc": pa}}
        fl.stop_all()
        check("19f 收尾超时 → kill 兜底", ("kill", "A") in ev, ev)
    finally:
        F.os.kill = orig_kill


def test_supervise_freeze():
    fl = F.Fleet([{"name": "ZZ_NOHB_FREEZE"}])
    ev = []
    dead = FakeProc("ZZ_NOHB_FREEZE", ev, alive=False)
    fl.state = {"ZZ_NOHB_FREEZE": {"proc": dead, "failed": False, "restarts": 0}}
    fl.launch = lambda *a, **k: ev.append(("launch",))
    fl.stopping = True
    n = fl.supervise_round()
    check("19g 急停期间 supervise 返回 0 且不复活",
          n == 0 and not any(e[0] == "launch" for e in ev)
          and fl.state["ZZ_NOHB_FREEZE"]["restarts"] == 0, ev)
    fl.stopping = False
    fl.supervise_round()
    check("19h 非急停期死亡照常复活（对照）",
          any(e[0] == "launch" for e in ev)
          and fl.state["ZZ_NOHB_FREEZE"]["restarts"] == 1, ev)


# ---------------- 修复 20：单机收尾等待 300s ----------------
def test_stop_machine_timeout():
    ev = []
    orig_kill = patch_os_kill(ev)
    try:
        p = FakeProc("A", ev)
        F.stop_machine(p)
        waits = [e[2] for e in ev if e[0] == "wait"]
        check("20a stop_machine 等待 300s（90s 不够多轮停止+菜单恢复）",
              waits == [300], ev)
        ev2 = []
        p2 = FakeProc("B", ev2, wait_timeout=True)
        F.stop_machine(p2)
        check("20b 超时 kill 兜底仍在", ("kill", "B") in ev2, ev2)
    finally:
        F.os.kill = orig_kill


# ---------------- 修复 21：自适应静默阈值 ----------------
def test_adaptive_quiet():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "data.txt")
        open(p, "w").close()
        tail = W.CorFileTail(p)
        now = time.time()

        def age(sec):
            os.utime(p, (now - sec, now - sec))

        tail.samples = [W.Sample(t=k * 30.0, e=0.1) for k in range(5)]
        age(40)
        check("21a 慢节奏（30s/点）静默 40s 不判结束（需 90s）",
              tail.finished_quiet(10.0) is False)
        age(95)
        check("21b 慢节奏静默 95s 判结束", tail.finished_quiet(10.0) is True)

        tail.samples = [W.Sample(t=float(k), e=0.1) for k in range(5)]
        age(12)
        check("21c 快节奏（1s/点）保底 10s：12s 判结束",
              tail.finished_quiet(10.0) is True)
        age(5)
        check("21d 快节奏 5s 不判结束", tail.finished_quiet(10.0) is False)

        tail.samples = [W.Sample(t=1.0, e=0.1)]
        age(12)
        check("21e 单样本退回固定阈值", tail.finished_quiet(10.0) is True)

        tail.samples = []
        age(100)
        check("21f 无样本不判结束", tail.finished_quiet(10.0) is False)


def make_r6():
    r = R6.Runner6.__new__(R6.Runner6)
    r.files = {}
    r._logs = []
    r.log = lambda m: r._logs.append(str(m))
    r.ui = None
    return r


class FakeTail:
    def __init__(self, samples=None, quiet=True):
        self.samples = samples or []
        self._quiet = quiet
        self.read_errors = 0
        self.bad_lines = 0

    def poll(self):
        return []

    def series_ev(self, last_n=None):
        return [(s.t, s.e) for s in self.samples]

    def finished_quiet(self, q=10.0):
        return self._quiet

    def size(self):
        return 100


def test_menu_gate():
    s = src("runner6.py")
    check("21g 两处静默判停都叠加菜单恢复",
          s.count("finished_quiet(10.0) and self._menu_idle()") == 2)

    r = make_r6()
    r.cfg = types.SimpleNamespace(test_stop_i_density=0, test_timeout_sec=9999.0,
                                  item="Tafel")
    r.tail_test = FakeTail(samples=[types.SimpleNamespace(t=1.0, e=0.1, i=0.0)])
    r.test_first_data_at = time.time() - 100
    r.ocp_ok_volt = None
    r.stage_t0 = time.time()
    r._finish = lambda: r._logs.append("FINISH")
    r._menu_idle = lambda: False
    r._do_mon_test()
    check("21h 文件静默但菜单仍禁用 → 不判结束（动电位）",
          "FINISH" not in r._logs, r._logs)
    r._menu_idle = lambda: True
    r._do_mon_test()
    check("21i 静默且菜单恢复 → 判结束", "FINISH" in r._logs)

    r2 = make_r6()
    r2.cfg = types.SimpleNamespace(test_timeout_sec=9999.0)
    r2.tail_test = FakeTail(samples=[types.SimpleNamespace(t=1.0, e=0.1, i=0.0)])
    r2.test_first_data_at = time.time() - 100
    r2.stage_t0 = time.time()
    r2._finish = lambda: r2._logs.append("FINISH")
    r2._menu_idle = lambda: False
    r2._do_mon_step()
    check("21j 阶梯波同款菜单守卫", "FINISH" not in r2._logs, r2._logs)


# ---------------- 修复 22：清场顺序 ----------------
def test_cleanup_order():
    s = src("fleet_gui.py")
    block = s.split("def on_cleanup", 1)[1].split("\n    def ", 1)[0]
    i_stop = block.find("f.stop_all()")
    i_ps = block.find("Get-CimInstance")
    i_task = block.find("taskkill")
    check("22a 清场先 stop_all（runner 优雅收尾）再杀 runner 进程再杀软件",
          -1 < i_stop < i_ps < i_task, (i_stop, i_ps, i_task))


# ---------------- 修复 23：判稳 t 回退重置 ----------------
def test_stab_t_regress():
    stab = ST.OcpStabilizer(ST.StabConfig(min_points=5, window_sec=60.0))
    stab.feed([(0.0, 0.1), (10.0, 0.1), (20.0, 0.1)])
    check("23a 正常积累", stab.ts == [0.0, 10.0, 20.0], stab.ts)
    stab.feed([(5.0, 0.2), (15.0, 0.2), (25.0, 0.2)])
    check("23b t 回退 → 旧序列作废，从新点重积累（不再静默丢点）",
          stab.ts == [5.0, 15.0, 25.0] and stab.vs == [0.2, 0.2, 0.2],
          (stab.ts, stab.vs))
    stab.feed([(35.0, 0.2)])
    check("23c 重置后继续正常积累", stab.ts == [5.0, 15.0, 25.0, 35.0], stab.ts)
    stab.feed([(35.0, 0.9)])
    check("23d 同时刻去重更新仍生效",
          stab.ts == [5.0, 15.0, 25.0, 35.0] and stab.vs[-1] == 0.9, stab.vs)


# ---------------- 修复 24：锁计数 + 信号旗标 ----------------
class FakeK32:
    def __init__(self):
        self.creates = 0
        self.releases = 0
        self.closes = 0

    def CreateMutexW(self, *a):
        self.creates += 1
        return 100 + self.creates

    def WaitForSingleObject(self, h, ms):
        return 0

    def ReleaseMutex(self, h):
        self.releases += 1

    def CloseHandle(self, h):
        self.closes += 1


def test_ui_lock_refcount():
    orig = ui_lock._k32
    k = FakeK32()
    ui_lock._k32 = k
    ui_lock._handle = None
    ui_lock._held = False
    ui_lock._depth = 0
    try:
        check("24a 首次 acquire 拿锁", ui_lock.ui_acquire() is True and ui_lock._depth == 1)
        check("24b 嵌套 acquire 只加计数不重复建锁",
              ui_lock.ui_acquire() is True and ui_lock._depth == 2 and k.creates == 1)
        ui_lock.ui_release()
        check("24c 内层 release 不放锁（外层还持有）",
              ui_lock._held is True and k.releases == 0)
        ui_lock.ui_release()
        check("24d 计数归零才真释放",
              ui_lock._held is False and k.releases == 1 and k.closes == 1)
        ui_lock.ui_release()
        check("24e 多余 release 幂等", k.releases == 1 and k.closes == 1)
        check("24f 释放后可重新拿锁",
              ui_lock.ui_acquire() is True and k.creates == 2 and ui_lock._depth == 1)
        ui_lock.ui_release()
    finally:
        ui_lock._k32 = orig
        ui_lock._handle = None
        ui_lock._held = False
        ui_lock._depth = 0


def test_graceful_flag():
    orig_sig = GE.signal
    orig_flag = GE._abort_requested
    orig_inst = GE._handlers_installed
    handlers = {}
    fake_sig = types.SimpleNamespace(
        SIGINT=2, SIGBREAK=21,
        signal=lambda sig, fn: handlers.__setitem__(sig, fn))
    GE.signal = fake_sig
    GE._abort_requested = False
    logs = []
    aborts = []
    runner = types.SimpleNamespace(running=True, abort=lambda: aborts.append(1))
    try:
        ok = GE.install(lambda: runner, logs.append)
        check("24g install 注册 SIGINT/SIGBREAK", ok is True and len(handlers) == 2)
        handlers[2](2, None)          # 模拟 Ctrl+C 信号到达
        check("24h 信号处理器只置旗标，不直接 abort（防 UI 重入）",
              aborts == [] and GE._abort_requested is True)
        got = GE.consume_abort(lambda: runner, logs.append)
        check("24i 主循环 consume 时才执行 abort",
              got is True and aborts == [1] and GE._abort_requested is False)
        got2 = GE.consume_abort(lambda: runner, logs.append)
        check("24j 旗标已清 → 不重复 abort", got2 is False and aborts == [1])
        GE._abort_requested = True
        runner.running = False
        got3 = GE.consume_abort(lambda: runner, logs.append)
        check("24k runner 已停 → 消费旗标但不 abort",
              got3 is True and aborts == [1])
    finally:
        GE.signal = orig_sig
        GE._abort_requested = orig_flag
        GE._handlers_installed = orig_inst


def test_consume_wiring():
    expect = {
        "runner5_live.py": 1, "runner6_live.py": 1,
        "runner5_resume_after_ocp.py": 2, "runner5_resume_tafel.py": 2,
        "runner6_resume_eis.py": 2, "runner6_resume_tafel.py": 2,
        "selftest_runner.py": 1, "selftest_runner5.py": 1,
        os.path.join("archive", "resume_tafel.py"): 2,
    }
    total = 0
    bad = []
    for rel, n in expect.items():
        c = src(rel).count("graceful_exit.consume_abort(lambda: r, log)")
        total += c
        if c != n:
            bad.append("%s=%d(期望%d)" % (rel, c, n))
    check("24l 9 个入口 14 处循环全部接线 consume_abort",
          not bad and total == 14, bad or total)


# ---------------- 修复 25：看板刷新防护 ----------------
def test_refresh_guard():
    class Root:
        def __init__(self):
            self.afters = []

        def after(self, ms, fn):
            self.afters.append((ms, fn))

    class Lbl:
        def __init__(self):
            self.texts = []

        def configure(self, text=None, **kw):
            self.texts.append(text)

    fs = types.SimpleNamespace(root=Root(), lbl_summary=Lbl())
    fs.refresh = lambda: None

    def boom():
        raise RuntimeError("模拟看板异常")
    fs._refresh_inner = boom
    FG.FleetGUI.refresh(fs)
    check("25a 刷新异常被捕获且显示在看板",
          any("看板刷新异常" in (t or "") for t in fs.lbl_summary.texts),
          fs.lbl_summary.texts)
    check("25b 异常后仍重排 2s 刷新",
          len(fs.root.afters) == 1 and fs.root.afters[0][0] == 2000)

    fs2 = types.SimpleNamespace(root=Root(), lbl_summary=Lbl())
    fs2.refresh = lambda: None
    fs2._refresh_inner = lambda: None
    FG.FleetGUI.refresh(fs2)
    check("25c 正常路径照常重排", len(fs2.root.afters) == 1)

    fs3 = types.SimpleNamespace(root=Root(), lbl_summary=Lbl())
    fs3.refresh = lambda: None
    fs3._refresh_inner = lambda: None

    def bad_after(ms, fn):
        raise RuntimeError("after 也炸")
    fs3.root.after = bad_after
    try:
        FG.FleetGUI.refresh(fs3)
        ok = True
    except Exception:
        ok = False
    check("25d after 自身异常也不外抛", ok)

    s = src("fleet_gui.py")
    inner = s.split("def _refresh_inner", 1)[1].split("\n    def ", 1)[0]
    check("25e 重排只留在 wrapper（inner 不再自带 after）",
          "self.root.after" not in inner)


# ---------------- 修复 26：拒绝 0V 基准 + 读异常留痕 ----------------
def test_ocp_no_data():
    r = make_r6()
    r.cfg = types.SimpleNamespace(max_ocp_sec=60.0, ocp_fixed=False,
                                  stab=types.SimpleNamespace(min_points=30))
    r.tail_ocp = FakeTail(samples=[])
    r.stage_t0 = time.time() - 100
    r.ocp_ok_volt = None
    states = []
    r.set_state = lambda s, d="": (states.append((s, d)),
                                   setattr(r, "state", s))
    r._do_mon_ocp()
    check("26a 无数据到点 → 走 S_STOP_OCP（先停止收尾），不直接 _fail",
          r.state == R6.S_STOP_OCP and getattr(r, "_ocp_no_data", False) is True,
          states)
    check("26b 无数据不写 0 V 基准", r.ocp_ok_volt is None, r.ocp_ok_volt)

    settles = []
    fails = []
    r._settle_after_stop = lambda label, idle=8.0: settles.append(label) or True
    r._fail = lambda msg: fails.append(msg)
    r.stage_t0 = time.time() - 10
    r._do_stop_ocp()
    check("26c 停止收尾完成后才报错拒绝接续",
          settles == ["开路电位"] and len(fails) == 1 and "无数据" in fails[0],
          (settles, fails))

    r2 = make_r6()
    r2.cfg = types.SimpleNamespace(max_ocp_sec=60.0, ocp_fixed=True,
                                   stab=types.SimpleNamespace(min_points=30))
    r2.tail_ocp = FakeTail(samples=[types.SimpleNamespace(t=10.0, e=0.2)])
    r2.stage_t0 = time.time() - 100
    r2.ocp_ok_volt = None
    r2._ocp_round = 0
    r2.set_state = lambda s, d="": setattr(r2, "state", s)
    r2._do_mon_ocp()
    check("26d 有数据到点 → 正常取末点电位（对照）",
          abs(r2.ocp_ok_volt - 0.2) < 1e-9
          and not getattr(r2, "_ocp_no_data", False), r2.ocp_ok_volt)


def test_tail_health():
    r = make_r6()
    tail = types.SimpleNamespace(read_errors=2, bad_lines=1)
    r._warn_tail_health(tail, "动电位")
    check("26e 读失败+坏行累计告警一次",
          len(r._logs) == 1 and "累计 3 次" in r._logs[0], r._logs)
    r._warn_tail_health(tail, "动电位")
    check("26f 计数未变不重复刷屏", len(r._logs) == 1)
    tail.read_errors = 3
    r._warn_tail_health(tail, "动电位")
    check("26g 计数增长再告警", len(r._logs) == 2 and "累计 4 次" in r._logs[1])
    r2 = make_r6()
    r2._warn_tail_health(types.SimpleNamespace(read_errors=0, bad_lines=0), "x")
    check("26h 无异常不告警", r2._logs == [])

    s = src("runner6.py")
    check("26i 三个监视点都接了健康检查",
          s.count("_warn_tail_health(self.tail_") == 3)


def test_watch_counters():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "data.txt")
        with open(p, "wb") as f:
            f.write(b"CSStudioFile,OCP,xxx\r\nE(V)\ti(A/cm2)\tT(s)\r\n"
                    b"0.1\t0.001\t1.0\r\ngarbage\r\n0.2\t0.001\t2.0\r\n")
        tail = W.CorFileTail(p)
        new = tail.poll()
        check("26j 坏行计数且好行照常读", len(new) == 2 and tail.bad_lines == 1,
              (len(new), tail.bad_lines))

        def raiser(*a, **k):
            raise OSError("模拟占用")
        W.open = raiser
        try:
            out = tail.poll()
        finally:
            del W.open
        check("26k 读失败计数且不再静默", out == [] and tail.read_errors == 1)
        tail.reset()
        check("26l reset 清零计数", tail.read_errors == 0 and tail.bad_lines == 0)


def main():
    test_stop_all_broadcast()
    test_stop_all_shared_deadline()
    test_stop_all_kill_fallback()
    test_supervise_freeze()
    test_stop_machine_timeout()
    test_adaptive_quiet()
    test_menu_gate()
    test_cleanup_order()
    test_stab_t_regress()
    test_ui_lock_refcount()
    test_graceful_flag()
    test_consume_wiring()
    test_refresh_guard()
    test_ocp_no_data()
    test_tail_health()
    test_watch_counters()
    print()
    if FAIL:
        print("共 %d 项失败：%s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("test_review_fleet_data 全部通过")


if __name__ == "__main__":
    main()