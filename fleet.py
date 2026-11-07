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
            args += ["--" + k, str(m[k])]
    args += list(m.get("args_extra", []))   # 透传额外参数（离线测试用）
    if m.get("resume"):
        args.append("--resume")
    return args


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


class Fleet:
    def __init__(self, machines):
        self.machines = machines
        self.state = {}                 # name -> {proc, logf, restarts, hb_ts, failed}
        self.stopping = False

    # ------------------------------------------------------------
    def launch(self, m, resume):
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
