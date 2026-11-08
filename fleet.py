# -*- coding: utf-8 -*-
"""fleet.py —— 多通道编排器（N 台机器的受监督 runner 编排）。

职责
----
1. 按 machines.json 逐台 spawn runner 子进程（runner6_live/runner5_live，
   错峰 15s 避免启动期 UIA 竞争）
2. 监督：每 2s 检查各子进程存活 + 心跳文件年龄
3. 死亡自动复活：带 --resume 断点续跑（连死 3 次熔断该机器并告警）
4. 全局急停：先 CTRL_BREAK（子进程优雅退出：中止实验→收尾），再 taskkill /F 兜底
5. 状态表：每 2s 打印各机一行（名称/阶段/心跳年龄/重启次数）

用法
----
  python fleet.py machines.json
  机器清单格式见 machines.example.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
HB_DIR = os.path.join(ROOT, "_auto", "hb")
MAX_RESTARTS = 3
STALE_SEC = 30.0


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    machines = cfg.get("machines")
    if not machines:
        raise ValueError("配置里没有 machines")
    return machines


def build_args(m):
    """机器配置 → runner 命令行参数列表。script 可注入（离线测试用假 runner）。"""
    ver = int(m.get("version", 6))
    script = m.get("script") or ("runner6_live.py" if ver == 6 else "runner5_live.py")
    args = [sys.executable, script, m["name"], str(m.get("area", 1.0)),
            m.get("item", "Tafel")]
    if m.get("no_eis", True):
        args.append("no-eis")
    for k in ("max_ocp", "ocp_time", "init", "final", "rate"):
        if k in m:
            # ★ 连字符：runner 的 _argval 解析 --max-ocp（下划线不匹配=参数落空，
            #   2026-11-08 冒烟实证 JK-O 监视 269s 没停）
            args += ["--" + k.replace("_", "-"), str(m[k])]
    if m.get("sn"):
        args += ["--sn", m["sn"]]      # ★ runner 按序列号锁定本机窗口
    if m.get("sim") and m["sim"].get("port"):
        args += ["--port", m["sim"]["port"]]   # ★ runner 手动连自己的端口
    if m.get("lock"):
        args += ["--lock", m["lock"]]          # ★ 每机独立单实例锁
    args += list(m.get("args_extra", []))   # 透传额外参数（离线测试用）
    if m.get("resume"):
        args.append("--resume")
    return args


def create_desktop(name: str):
    """创建（或取已有）命名虚拟桌面句柄。方案 A：每机一个隔离桌面。"""
    import ctypes
    GENERIC_ALL = 0x10000000
    h = ctypes.windll.user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    return h


def spawn_on_desktop(desktop: str, cmdline: str, cwd: str = None,
                     flags: int = 0):
    """在命名桌面上启动进程（pywin32 CreateProcess 支持 lpDesktop）。

    返回 pid。runner/CS Studio 用它——子进程的 UIA/鼠标只作用于本桌面。
    """
    import win32api
    import win32con
    import win32process
    si = win32process.STARTUPINFO()
    si.lpDesktop = desktop
    hProc, hThread, pid, tid = win32process.CreateProcess(
        None, cmdline, None, None, 0,
        win32con.CREATE_NEW_PROCESS_GROUP | flags, None, cwd, si)
    return pid


def build_sim_args(sim):
    """sim 配置 → simdevice 命令行。sim: {"port","sn","lan5","hz"}。"""
    args = [sys.executable, os.path.join("testbed", "simdevice.py"),
            "--port", sim.get("port", "0.0.0.0:30001"), "--tcp", "--lan",
            "--sn", sim.get("sn", "CS350M24030650")]
    if sim.get("lan5"):
        args.append("--lan5")
    if sim.get("hz"):
        args += ["--hz", str(sim["hz"])]
    if sim.get("replay"):
        args += ["--replay", sim["replay"]]
    return args


def wait_sn_title(sn, timeout=75):
    """等 CS Studio 标题出现 SN（自动发现+连接完成的标志）。"""
    if not sn:
        return True
    from pywinauto import Desktop
    end = time.time() + timeout
    while time.time() < end:
        try:
            for w in Desktop(backend="uia").windows():
                t = w.window_text() or ""
                if "CS Studio" in t and sn in t:
                    return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def spawn(m, resume=True):
    """拉起一台机器的 runner 子进程（新进程组，便于 CTRL_BREAK 精准打击）。"""
    args = build_args(dict(m, resume=resume))
    logf = os.path.join(r"D:\deepseek\_probe\live",
                        "run_%s_%s.log" % (m["name"], time.strftime("%m%d_%H%M%S")))
    os.makedirs(os.path.dirname(logf), exist_ok=True)
    lf = open(logf, "a", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(args, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT,
                            creationflags=flags)
    return proc, logf


def stop_machine(proc):
    """优雅停止：CTRL_BREAK（runner 的 SIGBREAK 处理器→中止实验收尾），
    超时再 kill 兜底。"""
    import signal
    if proc.poll() is None:
        try:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        try:
            proc.wait(timeout=90)       # 收尾可能要 1~2 分钟（UIA 停止）
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass


class _PopenShell:
    """桌面模式进程的监控壳：无 Popen 句柄，用 pid 判活 + taskkill 兜底。"""

    def __init__(self, pid):
        self.pid = pid
        self._killed = False

    def poll(self):
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, self.pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return 1                   # 已退出
        ctypes.windll.kernel32.CloseHandle(h)
        return None

    @property
    def returncode(self):
        rc = self.poll()
        return rc

    def wait(self, timeout=None):
        import time as _t
        end = _t.time() + (timeout or 0)
        while True:
            if self.poll() is not None:
                return 0
            if timeout is not None and _t.time() >= end:
                raise subprocess.TimeoutExpired("desktop-pid", timeout)
            _t.sleep(0.5)

    def kill(self):
        import subprocess as _sp
        if not self._killed:
            self._killed = True
            _sp.run(["taskkill", "/F", "/PID", str(self.pid)],
                    capture_output=True)


class Fleet:
    def __init__(self, machines):
        self.machines = machines
        self.state = {}                 # name -> {proc, logf, restarts, hb_ts, failed}
        self.sims = {}                  # name -> sim proc（有 sim 配置的机器）
        self.stopping = False

    # ------------------------------------------------------------
    def ensure_sim(self, m):
        """确保该机器的虚拟设备在线（死了自动重启）。"""
        sim = m.get("sim")
        if not sim:
            return True
        name = m["name"]
        proc = self.sims.get(name)
        if proc is not None and proc.poll() is None:
            return True
        args = build_sim_args(sim)
        logf = os.path.join(r"D:\deepseek\_probe\live", "sim_%s.log" % name)
        os.makedirs(os.path.dirname(logf), exist_ok=True)
        lf = open(logf, "a", encoding="utf-8")
        proc = subprocess.Popen(args, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.sims[name] = proc
        print("[fleet] sim %s (pid=%d) %s" % (name, proc.pid, sim.get("port")))
        time.sleep(3)                   # 应答器上线要几秒
        return proc.poll() is None

    def launch_desktop(self, m, resume=True):
        """桌面模式：建桌面 → 桌面内拉 CS Studio 与 runner。"""
        import time as _t
        name = m["name"]
        dname = "CSP-%s" % name
        create_desktop(dname)
        cmdline = '"%s"' % m["exe"] if m.get("exe") else None
        if cmdline:
            spawn_on_desktop(dname, cmdline)
            self._exes_launched = getattr(self, "_exes_launched", set())
            self._exes_launched.add(name)
            print("[fleet] %s CS Studio 已拉起于桌面 %s" % (name, dname))
            _t.sleep(8)                 # 让它先起来再连
        args = build_args(dict(m, resume=resume))
        argstr = subprocess.list2cmdline(args)
        logf = os.path.join(r"D:\deepseek\_probe\live",
                            "run_%s_%s.log" % (name, _t.strftime("%m%d_%H%M%S")))
        os.makedirs(os.path.dirname(logf), exist_ok=True)
        # ★ argstr 已含引号包裹的 python 路径——不能再拼一次
        #   （拼两次 → python 把自己当脚本执行，SyntaxError Non-UTF-8 实证）
        pid = spawn_on_desktop(dname, 'cmd /c "%s > "%s" 2>&1"' % (
            argstr, logf), cwd=ROOT)
        # 占位 proc：桌面模式没有 Popen 句柄，用 poll-safe 壳
        self.state[name] = {"proc": _PopenShell(pid), "logf": logf,
                            "restarts": 0, "failed": False, "hb_ts": _t.time()}
        print("[fleet] 启动 %s (pid=%d, 桌面=%s) %s" % (name, pid, dname, logf))

    def launch_exe(self, m):
        """拉起该机器的 CS Studio 实例（有 sim 时会自动发现并连接）。

        ★ 每台只拉起一次（respawn 复活时 CS Studio 通常还活着——
          再 spawn 会实例堆积，2026-11-08 冒烟实证 4 个 CS5 并存）。
        """
        exe = m.get("exe")
        if not exe:
            return True
        if getattr(self, "_exes_launched", None) and m["name"] in self._exes_launched:
            return True
        self._exes_launched = getattr(self, "_exes_launched", set())
        self._exes_launched.add(m["name"])
        subprocess.Popen([exe])
        ok = wait_sn_title(m.get("sn"), timeout=75)
        print("[fleet] %s CS Studio %s" % (m["name"], "已连接(SN 在标题)" if ok else "SN 等待超时"))
        return ok

    def launch(self, m, resume):
        # ★ 编排顺序：sim → CS Studio（自动连接）→ 确认 SN 标题 → runner
        if m.get("sim") and not self.ensure_sim(m):
            print("[fleet] ⚠ %s sim 启动失败" % m["name"])
        if m.get("desktop"):
            # 方案 A：CS Studio 与 runner 都拉到命名虚拟桌面（UIA/焦点隔离），
            # SN 等待由 runner 在本桌面内自行轮询（主桌面看不到那边的标题）
            self.launch_desktop(m, resume=resume)
            return
        if m.get("exe"):
            self.launch_exe(m)
        # 保留该机器的 restarts 计数：respawn 会重建 state 条目，
        # 计数丢失会让熔断永不触发（2026-11-07 离线测试 T2/T3 抓到）
        prev = self.state.get(m["name"], {})
        restarts = prev.get("restarts", 0)
        failed = prev.get("failed", False)
        proc, logf = spawn(m, resume=resume)
        self.state[m["name"]] = {"proc": proc, "logf": logf, "restarts": restarts,
                                 "failed": failed, "hb_ts": time.time()}
        print("[fleet] 启动 %s (pid=%d, 重启#%d) %s" % (m["name"], proc.pid,
                                                        restarts, logf))

    def launch_all(self, resume=False):
        for i, m in enumerate(self.machines):
            if i:
                time.sleep(15)          # 错峰：避免启动期 UIA 竞争
            self.launch(m, resume=resume)

    def stop_all(self):
        self.stopping = True
        for name, st in self.state.items():
            if st["proc"].poll() is None:
                print("[fleet] 停止 %s …" % name)
                stop_machine(st["proc"])
        print("[fleet] 全部停止")

    # ------------------------------------------------------------
    def supervise_round(self):
        alive = 0
        for m in self.machines:
            name = m["name"]
            if m.get("sim"):
                self.ensure_sim(m)      # sim 死亡自动重启（幂等）
            st = self.state.get(name)
            if st is None or st["failed"]:
                continue
            proc = st["proc"]
            if proc.poll() is None:
                alive += 1
                continue
            # 子进程死了：自动复活（带 --resume 断点续跑）
            st["restarts"] += 1
            if st["restarts"] > MAX_RESTARTS:
                st["failed"] = True
                print("[fleet] ⚠ %s 连死 %d 次，熔断（需要人工排查）"
                      % (name, MAX_RESTARTS))
                continue
            print("[fleet] %s 进程退出 (rc=%s) → 自动复活 #%d（--resume）"
                  % (name, proc.returncode, st["restarts"]))
            self.launch(dict(m, resume=True), resume=True)

    def status_line(self):
        cells = []
        for m in self.machines:
            name = m["name"]
            st = self.state.get(name)
            if st is None:
                cells.append("%s:未启动" % name)
                continue
            if st["proc"].poll() is None:
                hb = os.path.join(HB_DIR, name + ".json")
                age = time.time() - os.path.getmtime(hb) if os.path.exists(hb) else -1
                stage = ""
                try:
                    stage = json.load(open(hb, encoding="utf-8")).get("stage", "")[:12]
                except Exception:
                    pass
                cells.append("%s:%s(%ds)" % (name, stage[:12] or "运行中", max(0, age)))
            elif st["failed"]:
                cells.append("%s:熔断" % name)
            else:
                cells.append("%s:退出" % name)
        return "  ".join(cells)


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "machines.json")
    machines = load_config(cfg_path)
    print("fleet 编排器：%d 台机器" % len(machines))
    fleet = Fleet(machines)
    fleet.launch_all(resume=False)
    t0 = time.time()
    try:
        while True:
            time.sleep(2)
            fleet.supervise_round()
            print("[fleet %6.0fs] %s" % (time.time() - t0, fleet.status_line()),
                  flush=True)
    except KeyboardInterrupt:
        print("\n[fleet] Ctrl+C → 全局急停")
        fleet.stop_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
