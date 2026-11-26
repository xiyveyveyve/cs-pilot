# -*- coding: utf-8 -*-
"""code/pilot.py —— 单机/多机作业编排（纯代码，零 GUI，不碰真机）。

与 tests/run_case.py 的分工：
  * run_case.py：**一次实验作业**的执行器（清场→起 sim→跑宿主→校验），带失败重试。
  * pilot.py   ：**多机编排**——每台机器分配独立端口 + 独立模拟器 + 独立宿主进程，
                 并行跑，汇总成一份 report.json。

机器配置（machines.json）：
{
  "machines": [
    {"name": "M1", "port": 31011,
     "replay_ocp": "...", "replay_pot": "...",
     "experiments": [ ... 与 run_case job 里的 experiments 同结构 ... ]}
  ]
}

用法：
    python -I code/pilot.py machines.json            # 跑全部
    python -I code/pilot.py machines.json --only M1  # 只跑一台
    python -I code/pilot.py machines.json --jobs 2   # 最多 2 台并行
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
LOGS = os.path.join(ROOT, "logs")
DATA = os.path.join(ROOT, "data")
RUN_CASE = os.path.join(TESTS, "run_case.py")

# 红线端口：真机串口不对应 TCP，这里只是防手滑把端口配到 CS Studio 的固定口
FORBIDDEN_PORTS = {1024}     # CS6/CS5 的 UDP 发现端口


class Machine:
    def __init__(self, spec, idx):
        self.name = spec.get("name") or ("M%d" % (idx + 1))
        self.port = int(spec.get("port") or (31011 + idx))
        self.replay_ocp = spec.get("replay_ocp")
        self.replay_pot = spec.get("replay_pot")
        self.experiments = spec.get("experiments") or []
        self.probe = bool(spec.get("probe", False))
        self.native_writer = bool(spec.get("native_writer", True))
        self.retries = int(spec.get("retries", 3))
        self.timeout = int(spec.get("timeout", 420))

    @property
    def out_dir(self):
        return os.path.join(DATA, self.name)

    def job(self):
        for e in self.experiments:
            params = e.setdefault("params", {})
            stem = "%s_%s" % (self.name, e.get("kind", "exp"))
            params.setdefault("FileName", stem)
            params.setdefault("FilePath", os.path.join(self.out_dir, stem + ".cor"))
        return {
            "mode": "tcp",
            "endpoint": "127.0.0.1:%d" % self.port,
            "out_dir": self.out_dir,
            "native_writer": self.native_writer,
            "probe": self.probe,
            "open_retry": 10,
            "assembly_dir": r"D:\sci\MDI Jade 9",
            "experiments": self.experiments,
        }

    def write_job(self):
        os.makedirs(self.out_dir, exist_ok=True)
        p = os.path.join(TESTS, "jobs", "auto_%s.json" % self.name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.job(), f, ensure_ascii=False, indent=2)
        return p

    def sim_args(self):
        a = []
        if self.replay_ocp:
            a += ["--sim-arg=--replay-ocp", "--sim-arg=" + self.replay_ocp]
        if self.replay_pot:
            a += ["--sim-arg=--replay-pot", "--sim-arg=" + self.replay_pot]
        return a


def kill_sims():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*simdevice.py*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def run_machine(m: Machine, results, lock):
    """跑一台机器：调用 run_case.py（它内部自带 sim 管理与重试）。"""
    job = m.write_job()
    cmd = [sys.executable, "-I", RUN_CASE, job,
           "--port", "%d" % m.port,
           "--timeout", str(m.timeout),
           "--retries", str(m.retries)] + m.sim_args()
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=m.timeout * m.retries + 180)
        out, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        rc = 124
    dur = time.time() - t0
    res_path = os.path.join(LOGS, "auto_%s_result.json" % m.name)
    summary = {}
    if os.path.exists(res_path):
        try:
            summary = json.load(open(res_path, encoding="utf-8"))
        except Exception:
            pass
    with lock:
        results[m.name] = {
            "machine": m.name,
            "port": m.port,
            "rc": rc,
            "dur_sec": round(dur, 1),
            "verdict": summary.get("verdict", "FAIL"),
            "rows": summary.get("rows", []),
            "tail": "\n".join([l for l in out.strip().splitlines()[-6:]]),
        }
    print("[pilot] %-6s rc=%-4s %-8s %5.1fs  %s"
          % (m.name, rc, summary.get("verdict", "?"), dur,
             " ".join("%s:%s" % (r["kind"], r["points"]) for r in summary.get("rows", []))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("machines", help="machines.json 路径")
    ap.add_argument("--only", default=None, help="只跑指定机器名（逗号分隔）")
    ap.add_argument("--jobs", type=int, default=0, help="并行台数（0=全部并行）")
    ap.add_argument("--keep-going", action="store_true", default=True)
    a = ap.parse_args()

    cfg = json.load(open(a.machines, encoding="utf-8"))
    specs = cfg.get("machines") or []
    ms = [Machine(s, i) for i, s in enumerate(specs)]

    for m in ms:
        if m.port in FORBIDDEN_PORTS:
            print("[pilot] 红线：端口 %d 是设备发现端口，拒绝使用" % m.port)
            return 2

    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        ms = [m for m in ms if m.name in want]
    if not ms:
        print("[pilot] 没有要跑的机器")
        return 2

    for m in ms:
        print("[pilot] %-6s port=%d exp=%s replay=%s"
              % (m.name, m.port,
                 [e.get("kind") for e in m.experiments],
                 "yes" if (m.replay_ocp or m.replay_pot) else "no"))

    kill_sims()
    os.makedirs(LOGS, exist_ok=True)

    results, lock = {}, threading.Lock()
    limit = a.jobs if a.jobs > 0 else len(ms)
    sem = threading.Semaphore(limit)

    def worker(m):
        with sem:
            run_machine(m, results, lock)

    threads = [threading.Thread(target=worker, args=(m,), daemon=False) for m in ms]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.time() - t0

    ordered = [results.get(m.name) or {"machine": m.name, "verdict": "FAIL", "rows": []} for m in ms]
    allok = bool(ordered) and all(r.get("verdict") == "ALL-OK" for r in ordered)
    print("\n[pilot] ==== 汇总（并行 %d 台，总耗时 %.1fs）====" % (limit, total))
    for r in ordered:
        print("  %-6s %-8s %s" % (r["machine"], r["verdict"],
                                  " ".join("%s=%s" % (x["kind"], x["points"]) for x in r.get("rows", []))))
    print("[pilot] VERDICT: %s" % ("ALL-OK" if allok else "FAIL"))

    report = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": os.path.abspath(a.machines),
        "parallel": limit,
        "total_sec": round(total, 1),
        "verdict": "ALL-OK" if allok else "FAIL",
        "machines": ordered,
    }
    rp = os.path.join(LOGS, "pilot_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("[pilot] 报告：%s" % rp)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
