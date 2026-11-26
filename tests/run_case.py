# -*- coding: utf-8 -*-
"""tests/run_case.py —— 跑一个作业：新起模拟器 → 起宿主 → 收尾 → 校验产物。

为什么要有这层：早期实测出现过「连接 ok 但探测全超时、BeginStartWriteFile 永久阻塞」
的僵尸态，当时误判为「模拟器一个进程只能服务一次连接」。
**2026-11-10 晚间复查纠正**：模拟器连续 14 次重连全通，真因在宿主侧——
上一进程退出留下的半关闭 socket 让 `SockectConnect` 连上但 `auto_wired=false`，
此后所有下发/写盘都无效。已在宿主加 `auto_wired` 校验 + 弃连接重建（见 CsPilotHost.cs
BuildContext），根治后 `--retries 1` 也能 3/3 通过。
本文件保留每作业配新 sim 的做法作为额外隔离，但不再是必需。

用法：
    python tests/run_case.py tests/jobs/t2_all4.json
    python tests/run_case.py tests/jobs/t1_ocp.json --port 31011 --keep-sim
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.path.join(ROOT, "code", "cshost", "CsPilotHost.exe")
SIM = os.path.join(ROOT, "code", "sim", "simdevice.py")
LOGS = os.path.join(ROOT, "logs")


def kill_sims():
    """只杀本目录起的模拟器（命令行含本仓 simdevice.py 的 python）。"""
    # 注意：命令行里路径可能是相对路径（code/sim/simdevice.py），
    # 所以匹配 simdevice.py 而不是带绝对路径的串；本机只有本项目的 simdevice。
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*simdevice.py*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "
          "Write-Output ('killed ' + $_.ProcessId) }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30)
        return [l for l in out.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def port_free(host_port, wait=10.0):
    """等端口真的能监听（上一次的连接 TIME_WAIT 不算）。"""
    import socket
    h, p = host_port.split(":")
    t0 = time.time()
    while time.time() - t0 < wait:
        s = socket.socket()
        try:
            s.bind((("0.0.0.0" if h in ("0.0.0.0", "127.0.0.1") else h), int(p)))
            s.close()
            return True
        except OSError:
            s.close()
            time.sleep(0.5)
    return False


def sim_selfcheck(port, retries=6):
    """起完 sim 后自己先连一次，确认它真的在服务（否则宿主会撞上僵尸连接）。"""
    import socket
    host, p = "127.0.0.1", int(port.split(":")[-1])
    for k in range(retries):
        try:
            s = socket.create_connection((host, p), timeout=3)
            s.sendall(bytes.fromhex("55AA00061015"))   # GetSerialNumber
            s.settimeout(3)
            data = s.recv(256)
            s.close()
            if data:
                return True, data.hex()
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(0.5)
    return False, locals().get("last", "no response")


def start_sim(port, log_path, extra=None, wait=3.0):
    args = [sys.executable, SIM, "--tcp", "--port", port, "--hz", "10",
            "--points", "30", "--log", log_path] + (extra or [])
    outf = open(os.path.join(LOGS, "sim_%s.out" % port.replace(":", "_").replace(".", "")), "w",
                encoding="utf-8", errors="replace")
    proc = subprocess.Popen(args, stdout=outf, stderr=subprocess.STDOUT)
    time.sleep(wait)
    if proc.poll() is not None:
        raise RuntimeError("模拟器启动即退出 rc=%s" % proc.returncode)
    return proc, outf


def stop_sim(proc, outf):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        outf.close()
    except Exception:
        pass


def run_host(job_path, ev_path, timeout):
    args = [HOST, job_path, ev_path]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr, False
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "TIMEOUT", True


def read_events(path):
    evs = []
    if not os.path.exists(path):
        return evs
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                evs.append(json.loads(line))
            except Exception:
                pass
    return evs


def verify(evs, out_dir):
    """验收：每个实验都有 exp_done，且 points>0 或文件非空。"""
    rows = []
    for e in evs:
        if e.get("ev") != "exp_done":
            continue
        kind = e.get("kind")
        pts = e.get("points") or 0
        files = []
        for f in glob.glob(os.path.join(out_dir, "*")):
            if kind in os.path.basename(f):
                files.append((os.path.basename(f), os.path.getsize(f)))
        native = [(n, s) for n, s in files if n.endswith(".cor")]
        own = [(n, s) for n, s in files if n.startswith("own_")]
        rows.append({
            "kind": kind,
            "points": pts,
            "dp": e.get("dp"),
            "reason": e.get("reason"),
            "cor_bytes": max([s for _, s in native], default=0),
            "own_bytes": max([s for _, s in own], default=0),
            "ok": pts > 0 and (max([s for _, s in native], default=0) > 0
                               or max([s for _, s in own], default=0) > 0),
        })
    return rows


def one_attempt(job_path, listen, sim_log, ev_path, out_dir, timeout, sim_extra, keep_sim):
    """一次尝试：清场 -> 起 sim -> 跑宿主 -> 收尾 -> 返回 (rc, timed_out, rows)。"""
    for p in (ev_path, sim_log):
        if os.path.exists(p):
            os.remove(p)
    killed = kill_sims()
    if killed:
        print("[runner] 清掉残留模拟器：" + ", ".join(killed))
    if not port_free("127.0.0.1:" + listen.split(":")[-1]):
        print("[runner] 端口 %s 仍被占用" % listen)
        return None, True, []
    sim, simf = start_sim(listen, sim_log, extra=sim_extra)
    print("[runner] 模拟器 pid=%s listen=%s" % (sim.pid, listen))
    rc, timed_out = 0, False
    try:
        rc, out, err, timed_out = run_host(job_path, ev_path, timeout)
        print("[runner] 宿主 rc=%s timed_out=%s" % (rc, timed_out))
        if err:
            print("[runner] stderr: " + err[:600])
    finally:
        if keep_sim:
            print("[runner] --keep-sim，模拟器保留 pid=%s" % sim.pid)
        else:
            stop_sim(sim, simf)
    return rc, timed_out, verify(read_events(ev_path), out_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--port", default=None, help="覆盖作业里的 endpoint（0.0.0.0:PORT）")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--keep-sim", action="store_true")
    ap.add_argument("--no-restart-sim", action="store_true", help="不杀已有模拟器（排查用）")
    ap.add_argument("--retries", type=int, default=3, help="失败时换新模拟器重试次数（默认 3）")
    ap.add_argument("--view", action="store_true",
                    help="拉起实时波形显示窗口（code/viewer.py 尾随本作业事件流）")
    ap.add_argument("--sim-arg", action="append", default=[], metavar="ARG",
                    help="透传给 simdevice.py 的参数，可多次（如 --sim-arg=--replay-ocp --sim-arg=<file>）")
    a = ap.parse_args()

    job_path = os.path.abspath(a.job)
    job = json.load(open(job_path, encoding="utf-8"))
    endpoint = job.get("endpoint", "127.0.0.1:31001")
    # 模拟器监听用 0.0.0.0:PORT，宿主永远连 127.0.0.1:PORT
    portnum = (a.port or endpoint).split(":")[-1]
    listen = "0.0.0.0:" + portnum
    out_dir = job.get("out_dir") or os.path.join(ROOT, "data", "run")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)

    tag = os.path.splitext(os.path.basename(job_path))[0]
    ev_path = os.path.join(LOGS, "%s_events.jsonl" % tag)
    sim_log = os.path.join(LOGS, "%s_sim.jsonl" % tag)
    for p in (ev_path, sim_log):
        if os.path.exists(p):
            os.remove(p)
    viewer_proc = None
    if a.view:
        viewer_proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "code", "viewer.py"), ev_path], cwd=ROOT)
        print("[runner] 实时波形窗口已拉起（尾随 %s）" % ev_path)

    # 每次尝试配全新 sim（额外隔离，成本很低）。
    # 注：早期「sim 只能服务一次连接」的结论已于 2026-11-10 晚纠正——真因是宿主侧
    # 半死 socket（auto_wired=false），宿主已自愈。此处的重试保留为兜底。
    attempts = 1 if a.no_restart_sim else max(1, a.retries)
    rows, rc, timed_out = [], 0, False
    for k in range(attempts):
        if k:
            print("[runner] ---- 第 %d 次重试（换新模拟器）----" % (k + 1))
        rc, timed_out, rows = one_attempt(job_path, listen, sim_log, ev_path,
                                          out_dir, a.timeout, a.sim_arg, a.keep_sim)
        if rc is None:
            continue
        if rows and all(r["ok"] for r in rows):
            break
    print("\n[runner] ==== 结果 ====")
    if not rows:
        print("  没有任何 exp_done 事件（看 %s）" % ev_path)
    for r in rows:
        print("  %-6s points=%-5s dp=%-5s reason=%-10s cor=%-7s own=%-7s %s"
              % (r["kind"], r["points"], r["dp"], r["reason"],
                 r["cor_bytes"], r["own_bytes"], "OK" if r["ok"] else "FAIL"))
    allok = bool(rows) and all(r["ok"] for r in rows)
    print("[runner] VERDICT: %s" % ("ALL-OK" if allok else "FAIL"))
    summary = {"job": tag, "endpoint": listen, "rc": rc, "timed_out": timed_out,
               "rows": rows, "verdict": "ALL-OK" if allok else "FAIL"}
    with open(os.path.join(LOGS, "%s_result.json" % tag), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
