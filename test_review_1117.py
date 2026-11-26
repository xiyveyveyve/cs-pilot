# -*- coding: utf-8 -*-
"""test_review_1117.py —— 2026-11-17 代码审查修复 27-44 的离线回归。

由「审查复现证据_2026-11-17」的 5 个复现脚本翻转而来：复现脚本断言「缺陷存在」，
本套件断言「修复后的正确行为」。纯离线：win32/pywinauto/UIA/锁/时钟全部打桩，
不碰真窗口、真设备、真串口；live main 用 AST 抽出并在 Runner 构造处截停。

编号沿用审查报告（勿重新编号）：
27 序列 GUI 中止后继续跑收尾状态机直到终态（worker 不退而实验未停）
28 收尾/中止失败不许报成功终态（runner5 _finish_and_done / runner6 abort 校验 stop）
29 force_stop / close_run_windows 正确拆包 (wrapper|hwnd, title) 元组
30 fill_tafel 必须勾上「扫描停止电流」开关，勾不上 → False
31 start_experiment 按本进程 pid 过滤模态框（不点别台的确认框）
32 判稳 feed 全量重放不清保持计时；真回退（重建）才 reset
33 runner5_live 透传第三位置参数测试项目（不再写死 Tafel）
34 no-tafel 时阻抗失败 → 直接完成，不硬进动电位
35 runner6_live 断点续跑按具体阶段恢复（阻抗未完成重测阻抗）
36 一键全部启动放后台线程 + 急停可取消（不阻塞 Tk 主循环）
37 UI 锁获取/释放配对（终态释放残留锁；GUI/live 入口接线）
38 动电位判停按绝对电流口径（密度×面积）且只判阳极
39 set_cell 失败 → 拒绝开跑（电极面积/电解池参数）
40 手动启动解除急停冻结/熔断；自动复活保留计数
41 心跳必须属于本进程（pid/ts）才认终态（陈旧心跳不误判）
42 runner6_live 先解析 --lock 再拿单实例锁
43 wait_endexp 采样时间冻结独立计数 static（不再空等超时）
44 排窗脚本用 archive/ 正式路径 + 查退出码
"""
import ast
import os
import sys
import threading
import time as _time
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import driver5 as D5
import driver_direct as DD
import fleet as F
import runner5 as R5
import runner6 as R6
import stabilizer as ST
import ui_lock

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  | " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


def extracted(path, name, cls=None, env=None):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))
    body = tree.body
    if cls:
        body = next(x for x in body if isinstance(x, ast.ClassDef) and x.name == cls).body
    fn = next(x for x in body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name)
    ns = {} if env is None else dict(env)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(ROOT / path), "exec"), ns)
    return ns[name], ns


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


# ---------------- 27 序列 GUI 中止收尾 ----------------
def test_27_gui_abort_drain():
    import queue
    abort, _ = extracted("runner.py", "abort", "Runner")
    tick, _ = extracted("runner.py", "tick", "Runner")
    worker, _ = extracted("gui.py", "_worker_main", "App",
                          {"time": types.SimpleNamespace(sleep=lambda _: None, time=_time.time)})
    app = types.SimpleNamespace(_abort_requested=False, q=queue.Queue())
    r = types.SimpleNamespace(running=False, aborting=False, log=lambda _: None)
    r.start = lambda: setattr(r, "running", True)
    r._step = lambda: setattr(app, "_abort_requested", True)
    stops = []

    def do_abort():
        stops.append("stop")
        r.running = False
        r.aborting = False

    r._do_abort = do_abort
    r.abort = lambda: abort(r)
    r.tick = lambda: tick(r)
    app.runner = r
    worker(app)
    done = app.q.get_nowait()[0]
    check("27a 中止后 worker 继续 tick 直到物理停止并终态",
          done == "done" and not r.running and stops == ["stop"], (done, r.running, stops))


# ---------------- 28 收尾/中止失败不报成功 ----------------
def test_28_finish_failure():
    r = R5.Runner5(R5.RunConfig5())
    r.state = R5.S_MON_TEST
    r.sampler = types.SimpleNamespace(alive=lambda: False)
    r._data_file_for = lambda label: None

    def failed_finish(label, **kw):
        r.set_state(R5.S_ERROR, "stop failed")
        return False

    r._safe_finish = failed_finish
    r._do_mon_test()
    check("28a runner5 收尾失败 → S_ERROR（不被覆盖成 S_DONE）",
          r.state == R5.S_ERROR and "收尾失败" in (r.error or ""), (r.state, r.error))


def test_28_abort_stop_checked():
    for failure in ("false", "exception", "ok"):
        r = R6.Runner6(R6.RunConfig6(), log=lambda *a: None)
        r.running = True
        stop_calls, acq, rel = [], [], []

        def stop():
            stop_calls.append(1)
            if failure == "exception":
                raise RuntimeError("fake UI unavailable")
            return failure == "ok"

        r.dd = types.SimpleNamespace(stop=stop)
        fake_lock = types.SimpleNamespace(
            ui_acquire=lambda *a: (acq.append(1), True)[1],
            ui_release=lambda *a: rel.append(1))
        with patch.dict(sys.modules, {"ui_lock": fake_lock}):
            r.abort()
        want = R6.S_ABORT if failure == "ok" else R6.S_ERROR
        check("28b runner6 abort stop=%s → %s 且持锁配对" % (failure, want),
              r.state == want and not r.running and stop_calls == [1]
              and acq == [1] and rel == [1]
              and (failure == "ok" or "中止失败" in (r.error or "")),
              (r.state, r.running, stop_calls, acq, rel, r.error))


# ---------------- 29 元组拆包 ----------------
def test_29_force_stop_mdi():
    class Win:
        closed = False

        def window_text(self):
            return "[通道1]-开路电位测量(OCP) <D:\\fake.txt> [2mA]"

        def is_visible(self):
            return True

        def close(self):
            self.closed = True

    w = Win()
    dd = DD.DirectDriver.__new__(DD.DirectDriver)
    dd.log = lambda *a: None
    dd.ui = types.SimpleNamespace(
        main=types.SimpleNamespace(descendants=lambda **kw: [w]),
        clear_modals=lambda **kw: None)
    dd.run_windows = lambda: []
    dd.is_running = lambda: not w.closed
    with patch.object(DD, "time", Clock()):
        result = dd.force_stop(timeout=5.0)
    check("29a force_stop 拆包 (wrapper,title) → 真关窗并确认停止",
          result is True and w.closed is True, (result, w.closed))


def test_29_close_run_windows_owned():
    posted = []

    def strict_GetWindowText(hwnd):
        if not isinstance(hwnd, int):
            raise TypeError("HWND must be integer")
        return "波形图 <2mA> D:\\fake.cor"

    fake_win32 = types.SimpleNamespace(
        GetWindowText=strict_GetWindowText,
        PostMessage=lambda *a: posted.append(a))

    class FakeApp:
        def __init__(self, **kw):
            pass

        def connect(self, **kw):
            return self

        def window(self, **kw):
            return object()

    fake_pywinauto = types.SimpleNamespace(Application=FakeApp)
    dd = DD.DirectDriver.__new__(DD.DirectDriver)
    dd.log = lambda *a: None
    dd.ui = types.SimpleNamespace(main=types.SimpleNamespace(descendants=lambda **kw: []))
    dd.run_windows = lambda: [(555, "波形图 <2mA> D:\\fake.cor")]
    dd._stop_via_runwin = lambda w: (True, True)
    with patch.dict(sys.modules, {"win32gui": fake_win32, "pywinauto": fake_pywinauto}):
        with patch.object(DD, "time", Clock()):
            n = dd.close_run_windows()
    check("29b close_run_windows 拆包 (hwnd,title) → WM_CLOSE 关顶层运行窗",
          n == 1 and posted == [(555, 0x0010, 0, 0)], (n, posted))


# ---------------- 30 扫描停止电流开关必须勾上 ----------------
def test_30_checkbox_required():
    class Edit:
        def __init__(self, value=""):
            self.value = value

        def get_value(self):
            return self.value

    class Chk:
        def __init__(self, state=0):
            self.state = state

        def get_toggle_state(self):
            return self.state

    ids = {aid: Edit() for aid in (
        "Control_FileName_Text", "PotDynamic_InitialPot_txt",
        "PotDynamic_FinalPot_txt", "PotDynamic_ScanRate_txt",
        "SampleInterval_txt", "PotDynamic_MaxCurrent_txt",
        "PotDynamic_MinCurrent_txt")}
    chk = Chk(0)
    ids["PotDynamic_ScanStop_chk"] = chk
    s = D5.Studio5.__new__(D5.Studio5)
    s.by_ids = lambda panel: ids
    s.set_edit = lambda c, v: setattr(c, "value", v) or True
    s.log = lambda *a: None
    with patch.multiple(D5, time=Clock(), msg_click=lambda c: False):
        result = s.fill_tafel(object(), "mock", -0.5, 1.5, stop_ma=1.0)
    check("30a 开关勾不上（msg_click False）→ fill_tafel False",
          result is False and chk.get_toggle_state() == 0, (result, chk.state))

    ids2 = {aid: Edit() for aid in ids if aid != "PotDynamic_ScanStop_chk"}
    chk2 = Chk(0)
    ids2["PotDynamic_ScanStop_chk"] = chk2

    def click_on(c):
        c.state = 1
        return True

    s2 = D5.Studio5.__new__(D5.Studio5)
    s2.by_ids = lambda panel: ids2
    s2.set_edit = lambda c, v: setattr(c, "value", v) or True
    s2.log = lambda *a: None
    with patch.multiple(D5, time=Clock(), msg_click=click_on):
        result2 = s2.fill_tafel(object(), "mock", -0.5, 1.5, stop_ma=1.0)
    check("30b 开关勾上 → fill_tafel True",
          result2 is True and chk2.get_toggle_state() == 1, (result2, chk2.state))


# ---------------- 31 模态框按 pid 过滤 ----------------
def test_31_pid_scoped_modals():
    filters, clicked = [], []

    def modals(pid=None):
        filters.append(pid)
        return [111, 222] if pid is None else [111]

    s = D5.Studio5.__new__(D5.Studio5)
    s._pid = lambda: 111
    s.press_ok = lambda *a, **kw: True
    s.log = lambda *a: None
    with patch.multiple(D5, time=Clock(), all_run_hwnds=lambda: [],
                        find_run_hwnd=lambda **kw: 777, modal_dialogs=modals,
                        modal_text=lambda hwnd: "mock dialog",
                        click_modal=lambda hwnd, **kw: clicked.append(hwnd)):
        ok = s.start_experiment(object(), wait=2)
    check("31a start_experiment 按本进程 pid 过滤，只点本台的框",
          ok is True and filters == [111] and clicked == [111], (ok, filters, clicked))


# ---------------- 32 判稳重放 vs 重建 ----------------
def test_32_stabilizer_replay():
    full = ST.OcpStabilizer()
    inc = ST.OcpStabilizer()
    series = []
    a = b = None
    for t in range(901):
        p = (float(t), 0.1)
        series.append(p)
        a = full.feed(series)
        b = inc.feed([p])
    check("32a 全量重放与增量喂点都能判稳（保持计时不被清零）",
          a.stable and b.stable and a.held_sec > 0, (a.stable, a.held_sec, b.stable))

    s = ST.OcpStabilizer(ST.StabConfig(min_points=5, window_sec=60.0))
    s.feed([(0.0, 0.1), (10.0, 0.1), (20.0, 0.1)])
    s.feed([(5.0, 0.2), (15.0, 0.2), (25.0, 0.2)])
    check("32b 真回退（重叠区出现新点）→ 旧序列作废重积累",
          s.ts == [5.0, 15.0, 25.0] and s.vs == [0.2, 0.2, 0.2], (s.ts, s.vs))


# ---------------- 33 / 42 live 入口参数 ----------------
class _Captured(Exception):
    pass


def _live_flags(version, argv):
    got, guard = {}, []

    def config(**kw):
        got["cfg"] = kw
        return types.SimpleNamespace(test_stop_i_density=0.001, **kw)

    def construct(cfg, **kw):
        raise _Captured()

    env = {"sys": types.SimpleNamespace(argv=argv), "os": os, "time": _time,
           "_LOG_DIR": "unused", "log": lambda _: None,
           "_single_instance_guard": lambda lock: guard.append(lock) or True}
    if version == 5:
        env.update(RunConfig5=config, Runner5=construct)
    else:
        env["R6"] = types.SimpleNamespace(RunConfig6=config, Runner6=construct)
    main, _ = extracted("runner%d_live.py" % version, "main", env=env)
    rc = None
    try:
        rc = main()
    except _Captured:
        pass
    return rc, guard, got.get("cfg", {})


def test_33_42_live_flags():
    argv5 = ["runner5_live.py", "SAMPLE", "1.2", "Step", "no-tafel", "--ocp-fixed", "--lock", "custom_lock"]
    rc, guard, cfg = _live_flags(5, argv5)
    check("33a runner5_live 透传第三参 Step（不再写死 Tafel）",
          cfg.get("item") == "Step", cfg.get("item"))
    check("42a runner5_live 先解析 --lock 再拿锁", guard == ["custom_lock"], guard)

    argv6 = ["runner6_live.py", "SAMPLE", "1.2", "Step", "no-tafel", "--ocp-fixed", "--lock", "custom_lock"]
    rc, guard, cfg = _live_flags(6, argv6)
    check("42b runner6_live 先解析 --lock 再拿锁（两台 CS6 不互拒）",
          guard == ["custom_lock"], guard)
    check("33b runner6_live 透传 Step / no-tafel / --ocp-fixed",
          cfg.get("item") == "Step" and cfg.get("tafel_enabled") is False
          and cfg.get("ocp_fixed") is True,
          (cfg.get("item"), cfg.get("tafel_enabled"), cfg.get("ocp_fixed")))

    rc, guard, cfg = _live_flags(5, ["runner5_live.py", "S", "1", "Bogus"])
    check("33c runner5_live 未知测试项目 → 拒绝启动 rc=1", rc == 1, rc)


# ---------------- 34 no-tafel 阻抗失败 ----------------
def test_34_eis_no_tafel():
    for stage in ("open", "start"):
        r = R6.Runner6(R6.RunConfig6(tafel_enabled=False), log=lambda *a: None)
        r.dd = types.SimpleNamespace(open=lambda kind: None, press_ok=lambda *a, **kw: False)
        r._eis_panel = object()
        r.running = True
        getattr(r, "_do_eis_" + stage)()
        check("34a no-tafel 阻抗 %s 失败 → 完成（不硬进动电位）" % stage,
              r.state == R6.S_DONE and not r.running, (r.state, r.running))

    r = R6.Runner6(R6.RunConfig6(tafel_enabled=True, item="Tafel"), log=lambda *a: None)
    r.dd = types.SimpleNamespace(open=lambda kind: None)
    r.running = True
    r._do_eis_open()
    check("34b 有测试项时阻抗失败 → 进测试项参数窗",
          r.state == R6.S_T_OPEN and r.running, (r.state, r.running))


# ---------------- 35 断点续跑按阶段恢复 ----------------
class _ResumeRunner:
    def __init__(self, cfg, **kw):
        self.cfg = cfg
        self.running = False
        self.state = "待机"
        self.detail = ""
        self.ocp_ok_volt = None
        self.captured = {}

    def start(self):
        self.running = True

    def tick(self):
        self.state = R6.S_OCP_OPEN

    def set_state(self, s, *a):
        self.state = s
        self.running = False
        self.captured["jump"] = s
        self.captured["restored_ocp"] = self.ocp_ok_volt

    def summary(self):
        return []

    def _release_ui_lock(self):
        pass


def _resume_main(stage, ocp, argv_extra):
    holder = {}

    def make_runner(cfg, **kw):
        r = _ResumeRunner(cfg)
        holder["r"] = r
        return r

    preview = types.ModuleType("preview")
    preview.start_preview = lambda *a, **k: None
    ge = types.SimpleNamespace(install=lambda *a: None, consume_abort=lambda *a: None,
                               drain=lambda *a: None)
    argv = ["runner6_live.py", "SAMPLE", "1", "Tafel"] + argv_extra + ["--resume"]
    env = {
        "sys": types.SimpleNamespace(argv=argv), "os": os,
        "time": types.SimpleNamespace(time=lambda: 1000.0, strftime=lambda *a: "fixed", sleep=lambda _: None),
        "_LOG_DIR": "unused", "log": lambda _: None,
        "_single_instance_guard": lambda _: True,
        "R6": types.SimpleNamespace(
            RunConfig6=lambda **kw: types.SimpleNamespace(**kw), Runner6=make_runner,
            S_OCP_OPEN=R6.S_OCP_OPEN, S_EIS_OPEN=R6.S_EIS_OPEN,
            S_T_OPEN=R6.S_T_OPEN, S_STEP_OPEN=R6.S_STEP_OPEN),
        "_read_hb": lambda _: {"stage": stage, "ocp": ocp},
        "_write_hb": lambda *a: None,
        "graceful_exit": ge,
    }
    with patch.dict(sys.modules, {"preview": preview}):
        main, _ = extracted("runner6_live.py", "main", env=env)
        rc = main()
    return rc, holder.get("r")


def test_35_resume_target():
    rc, r = _resume_main("监视交流阻抗", 0.432, ["no-tafel"])
    check("35a 阻抗未完成 → 重测阻抗（跳 S_EIS_OPEN）且读回 OCP",
          rc == 0 and r.captured.get("jump") == R6.S_EIS_OPEN
          and r.captured.get("restored_ocp") == 0.432, (rc, r.captured))

    rc, r = _resume_main("监视测试项", 0.2, ["no-tafel"])
    check("35b 测试项阶段但本轮 no-tafel → 无法续跑 rc=1", rc == 1, rc)

    rc, r = _resume_main("监视测试项", 0.2, [])
    check("35c 测试项阶段 + 有测试项 → 跳测试项参数窗并读回 OCP",
          rc == 0 and r.captured.get("jump") == R6.S_T_OPEN
          and r.captured.get("restored_ocp") == 0.2, (rc, r.captured))


# ---------------- 36 全部启动后台 + 急停取消 ----------------
def test_36_start_all_background():
    calls = []

    class FakeFleet:
        def __init__(self, machines):
            self.machines = machines
            self.state = {}

        def launch_all(self, resume=False, cancel=None):
            calls.append(("launch_all", resume, cancel, threading.get_ident()))

        def stop_all(self):
            pass

    app = types.SimpleNamespace(fleet=None, machines=[{"name": str(i)} for i in range(4)],
                                _spawn_supervisor=lambda: None)
    caller = threading.get_ident()
    with patch.object(F, "Fleet", FakeFleet):
        start_all, _ = extracted("fleet_gui.py", "on_start_all", "FleetGUI",
                                 {"F": F, "threading": threading})
        start_all(app)
        for _ in range(200):
            if calls:
                break
            _time.sleep(0.01)
    check("36a 全部启动放后台线程（不阻塞 Tk 主循环）",
          bool(calls) and calls[0][3] != caller, calls)
    check("36b 传入可取消 Event 且 resume=False",
          bool(calls) and isinstance(calls[0][2], threading.Event) and calls[0][1] is False,
          calls)

    app.fleet = FakeFleet(app.machines)
    app._start_cancel = threading.Event()
    stop_all, _ = extracted("fleet_gui.py", "_do_stop_all", "FleetGUI", {"F": F})
    stop_all(app)
    check("36c 急停置 _start_cancel → 停启剩余机器", app._start_cancel.is_set())


# ---------------- 37 UI 锁配对 ----------------
def test_37_lock_pairing():
    class Kernel:
        def __init__(self):
            self.acquires = self.releases = 0

        def CreateMutexW(self, *a):
            return 101

        def WaitForSingleObject(self, *a):
            self.acquires += 1
            return 0

        def ReleaseMutex(self, *a):
            self.releases += 1
            return 1

        def CloseHandle(self, *a):
            return 1

    clock, kernel = Clock(), Kernel()
    with patch.object(R5, "time", clock), patch.multiple(
            ui_lock, _k32=kernel, _handle=None, _held=False, _depth=0):
        r = R5.Runner5(R5.RunConfig5())
        r.studio = types.SimpleNamespace(activate=lambda: None,
                                         ensure_main_visible=lambda: None,
                                         close_temp_curve=lambda: None)
        r.state = R5.S_OCP_OPEN
        r._step = lambda: r.set_state(R5.S_ERROR, "mock")
        clock.now += 1
        r.tick()                      # UI 段：拿一层锁
        d1, rel1, held1 = ui_lock._depth, kernel.releases, ui_lock.ui_held()
        clock.now += 1
        r.tick()                      # 终态：释放
        d2, rel2, held2 = ui_lock._depth, kernel.releases, ui_lock.ui_held()
    check("37a runner5 UI 段只持一层锁（不每 tick +1）",
          d1 == 1 and rel1 == 0 and held1, (d1, rel1, held1))
    check("37b runner5 终态释放残留锁",
          d2 == 0 and rel2 == 1 and not held2 and not r.running, (d2, rel2, held2))

    rel = []
    r6 = R6.Runner6(R6.RunConfig6(), log=lambda *a: None)
    r6._ui_lock_held = True
    r6.state = R6.S_DONE
    with patch.dict(sys.modules, {"ui_lock": types.SimpleNamespace(ui_release=lambda *a: rel.append(1))}):
        r6.tick()
    check("37c runner6 终态释放残留锁（幂等旗标配对）",
          rel == [1] and r6._ui_lock_held is False, (rel, r6._ui_lock_held))

    gui_src = (ROOT / "gui.py").read_text(encoding="utf-8-sig")
    l5 = (ROOT / "runner5_live.py").read_text(encoding="utf-8-sig")
    l6 = (ROOT / "runner6_live.py").read_text(encoding="utf-8-sig")
    check("37d GUI/live 入口终态接线 _release_ui_lock",
          "_release_ui_lock" in gui_src and "r._release_ui_lock()" in l5
          and "r._release_ui_lock()" in l6)


# ---------------- 38 绝对电流口径 + 阳极 ----------------
def _mon_test_runner(area, density):
    r = R6.Runner6(R6.RunConfig6(area_cm2=area, test_stop_i_density=density), log=lambda *a: None)
    r.tail_test = types.SimpleNamespace(poll=lambda: [], samples=[], read_errors=0, bad_lines=0)
    r.stage_elapsed = lambda: 2.0
    finishes = []
    r._finish = lambda: finishes.append("finish")
    return r, finishes


def test_38_current_area_anodic():
    r, fin = _mon_test_runner(0.5, 1e-3)
    for t in (1.0, 2.0):
        r.tail_test.samples.append(types.SimpleNamespace(t=t, e=0.1, i=0.0011))
        r._do_mon_test()
    check("38a 密度×面积=0.55mA < 阈值1mA → 不判停", fin == [], fin)

    r, fin = _mon_test_runner(0.5, 1e-3)
    for t in (1.0, 2.0):
        r.tail_test.samples.append(types.SimpleNamespace(t=t, e=0.1, i=0.003))
        r._do_mon_test()
    check("38b 密度×面积=1.5mA ≥ 阈值1mA 连续2新点 → 判停", fin == ["finish"], fin)

    r, fin = _mon_test_runner(0.5, 1e-3)
    for t in (1.0, 2.0):
        r.tail_test.samples.append(types.SimpleNamespace(t=t, e=0.1, i=-0.003))
        r._do_mon_test()
    check("38c 阴极电流（负）不判停（只判阳极，对齐软件 bound '>'）", fin == [], fin)


# ---------------- 39 set_cell 失败拒绝开跑 ----------------
def test_39_set_cell_refuse():
    r = R6.Runner6(R6.RunConfig6(area_cm2=2.0), log=lambda *a: None)
    r._ocp_panel = object()
    r.ui = types.SimpleNamespace(set_edit=lambda *a: True, by_id=lambda *a: None)
    r.dd = types.SimpleNamespace(set_cell=lambda *a, **kw: False)
    r._select_combo = lambda *a: True
    r.files = {"ocp": str(ROOT / "fake-never-written")}
    r._do_ocp_fill()
    check("39a set_cell 拒绝电极面积 → S_ERROR 拒绝开跑",
          r.state == R6.S_ERROR and not r.running and "电极面积" in (r.error or ""),
          (r.state, r.running, r.error))


# ---------------- 40 手动启动解冻 / 自动复活保留 ----------------
class _Proc:
    pid = 67890
    returncode = None
    alive = True

    def poll(self):
        return None if self.alive else self.returncode

    def wait(self, timeout=None):
        self.alive = False
        self.returncode = 0

    def kill(self):
        self.alive = False
        self.returncode = -9


def test_40_manual_restart():
    orig_spawn = F.spawn
    spawned = []

    def spawn(*a, **k):
        p = _Proc()
        spawned.append(p)
        return p, "unused"

    m = {"name": "REVIEW_FAKE_MACHINE"}
    F.spawn = spawn
    try:
        fl = F.Fleet([m])
        fl.stop_all()
        fl.launch(m, resume=False)        # 自动复活：manual=False
        fl.supervise_round()
        check("40a 急停冻结期间自动复活被跳过（不拉起新进程）",
              fl.stopping and fl.state[m["name"]]["restarts"] == 0 and len(spawned) == 1,
              (fl.stopping, fl.state[m["name"]]["restarts"], len(spawned)))

        fl2 = F.Fleet([m])
        fl2.stopping = True
        fl2.state[m["name"]] = {"failed": True, "restarts": 4, "death_times": [1, 2, 3]}
        fl2.launch(m, resume=False, manual=True)
        st = fl2.state[m["name"]]
        check("40b 手动启动解除急停冻结 + 清熔断/计数",
              fl2.stopping is False and st["failed"] is False and st["restarts"] == 0
              and st["death_times"] == [], (fl2.stopping, st))
    finally:
        F.spawn = orig_spawn


# ---------------- 41 陈旧心跳不误判终态 ----------------
def test_41_stale_heartbeat():
    import json
    import tempfile
    orig_spawn, orig_hb = F.spawn, F.HB_DIR
    spawned = []

    def spawn(*a, **k):
        p = _Proc()
        spawned.append(p)
        return p, "unused"

    m = {"name": "REVIEW_FAKE_MACHINE"}
    F.spawn = spawn
    try:
        with tempfile.TemporaryDirectory(dir=str(ROOT)) as td:
            F.HB_DIR = td
            # 上一轮陈旧心跳：pid 不符、ts 早于本次启动
            Path(td, m["name"] + ".json").write_text(
                json.dumps({"pid": 11111, "ts": 1, "stage": "完成"}), encoding="utf-8")
            p = _Proc()
            p.alive = False
            p.returncode = 1
            fl = F.Fleet([m])
            fl.state[m["name"]] = {"proc": p, "failed": False, "restarts": 0, "hb_ts": _time.time()}
            fl.supervise_round()
            st = fl.state[m["name"]]
            check("41a 陈旧心跳（pid/ts 不符）不认终态 → 仍按死亡复活",
                  not st.get("finished") and st["restarts"] == 1 and len(spawned) == 1,
                  (st.get("finished"), st["restarts"], len(spawned)))

            # 本进程心跳：pid 相符 → 认终态，不复活
            Path(td, m["name"] + ".json").write_text(
                json.dumps({"pid": p.pid, "ts": _time.time(), "stage": "完成"}), encoding="utf-8")
            p2 = _Proc()
            p2.alive = False
            p2.returncode = 0
            fl2 = F.Fleet([m])
            fl2.state[m["name"]] = {"proc": p2, "failed": False, "restarts": 0, "hb_ts": _time.time()}
            fl2.supervise_round()
            st2 = fl2.state[m["name"]]
            check("41b 本进程心跳（pid 相符）认终态 → 不复活",
                  st2.get("finished") == "完成" and st2["restarts"] == 0,
                  (st2.get("finished"), st2["restarts"]))
    finally:
        F.spawn = orig_spawn
        F.HB_DIR = orig_hb


# ---------------- 43 采样时间冻结独立计数 ----------------
def test_43_wait_endexp_static():
    clock = Clock()
    logs = []
    sampler = types.SimpleNamespace(alive=lambda: True,
                                    read=lambda: types.SimpleNamespace(t_sec=12.0))
    with patch.object(R5, "time", clock), patch.object(R5, "UiSampler", lambda *a, **kw: sampler):
        result = R5.wait_endexp(logs.append, runwin=types.SimpleNamespace(window_text=lambda: ""), timeout=8)
    check("43a 采样时间冻结 → static 计数提前判收尾（不空等超时）",
          result is True and clock.now < 108.0
          and any("采样时间停止增长" in m for m in logs), (result, clock.now, logs))


# ---------------- 44 排窗脚本 archive 路径 + 查退出码 ----------------
def test_44_arrange_archive():
    check("44a 排窗脚本在 archive/ 正式路径（根目录旧路径已不存在）",
          (ROOT / "archive" / "position_windows.py").exists()
          and not (ROOT / "position_windows.py").exists())

    seen = {}

    class FakeProc:
        def __init__(self, args, rc):
            seen["args"] = args
            self.rc = rc

        def wait(self, timeout=None):
            seen["timeout"] = timeout
            return self.rc

    fake_sp = types.SimpleNamespace(Popen=lambda args: FakeProc(args, 1))
    env = {"os": os, "sys": sys, "ROOT_DIR": str(ROOT), "subprocess": fake_sp}
    arrange, _ = extracted("fleet_gui.py", "_arrange_async", "FleetGUI", env)
    import contextlib
    import io
    buf = io.StringIO()
    with patch.dict(sys.modules, {"subprocess": fake_sp}):
        with contextlib.redirect_stdout(buf):
            arrange(types.SimpleNamespace())
    want = os.path.join(str(ROOT), "archive", "position_windows.py")
    check("44b 用 archive 路径 + wait(timeout=30) + 查退出码告警",
          seen.get("args") == [sys.executable, want] and seen.get("timeout") == 30
          and "rc=1" in buf.getvalue(), (seen, buf.getvalue()))


if __name__ == "__main__":
    test_27_gui_abort_drain()
    test_28_finish_failure()
    test_28_abort_stop_checked()
    test_29_force_stop_mdi()
    test_29_close_run_windows_owned()
    test_30_checkbox_required()
    test_31_pid_scoped_modals()
    test_32_stabilizer_replay()
    test_33_42_live_flags()
    test_34_eis_no_tafel()
    test_35_resume_target()
    test_36_start_all_background()
    test_37_lock_pairing()
    test_38_current_area_anodic()
    test_39_set_cell_refuse()
    test_40_manual_restart()
    test_41_stale_heartbeat()
    test_43_wait_endexp_static()
    test_44_arrange_archive()
    print("-" * 50)
    if FAIL:
        print("FAIL %d 项：%s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("test_review_1117 全部通过（审查 27-44 正确行为回归）")