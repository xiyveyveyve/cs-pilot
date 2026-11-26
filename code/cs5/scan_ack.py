# -*- coding: utf-8 -*-
"""code/cs5/scan_ack.py -- auto-scan CS5 ACK variants.

Modes:
  default    : scan 0x85 param-frame ACKs (conclusion: device must stay silent)
  --scan53   : scan 0x53 ReadOcpBytes ACKs (the real blocker of StartMethod)

For each variant:
  1. start a Cs5Sim on its own port
  2. run the C# probe (t_cs5probe.exe): Open->StartThread->assemble->InitExp->StartMethod
  3. read back probe verdict + simulator log for connection resets
  4. print a summary table

Usage:
    python -I code/cs5/scan_ack.py --scan53 --base-port 31100
    python -I code/cs5/scan_ack.py            --base-port 31060
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, "code", "cs5")
LOGS = os.path.join(ROOT, "logs")
PROBE = os.path.join(ROOT, "tests", "probe", "t_cs5probe.exe")

sys.path.insert(0, HERE)


def sim_start(port, ack85, ack74, log_path, ack53=None):
    args = [sys.executable, "-I", os.path.join(HERE, "sim_cs5.py"),
            "--port", "0.0.0.0:%d" % port,
            "--ack85", ack85, "--ack74", ack74, "--log", log_path]
    if ack53:
        args += ["--ack53", ack53]
    outf = open(os.path.join(LOGS, "scan_%d.out" % port), "w",
                encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdout=outf, stderr=subprocess.STDOUT)
    time.sleep(2.5)
    if p.poll() is not None:
        raise RuntimeError("sim failed to start rc=%s" % p.returncode)
    return p, outf


def sim_stop(p, outf):
    try:
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    try:
        outf.close()
    except Exception:
        pass


def kill_stray():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*sim_cs5.py*' -or $_.CommandLine -like '*simdevice.py*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def read_text(path):
    if not os.path.exists(path):
        return ""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return open(path, encoding=enc, errors="strict").read()
        except Exception:
            continue
    return open(path, encoding="utf-8", errors="replace").read()


def run_probe(port, timeout=90):
    if not os.path.exists(PROBE):
        return None, "probe missing: " + PROBE
    try:
        r = subprocess.run([PROBE, "--port", str(port)], capture_output=True, timeout=timeout)
        return r.returncode, ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        out = e.stdout or b""
        return 124, (out if isinstance(out, str) else out.decode("utf-8", "replace"))


def grab(out, label):
    m = re.search(label + r"\s*(?:\u2192|->)\s*(.+)", out or "")
    return m.group(1).strip() if m else "?"


def scan53(base_port):
    from sim_cs5 import VARIANTS_READOCP

    names = [n for n in VARIANTS_READOCP if n != "legacy"]
    names.append("legacy")

    rows = []
    kill_stray()
    port = base_port
    for name in names:
        log = os.path.join(LOGS, "scan53_%s_%d.jsonl" % (name, port))
        print("")
        print("=" * 62)
        print("ack53=%-12s port=%d" % (name, port))
        print("=" * 62)
        p, outf = sim_start(port, "silent", "silent", log, ack53=name)
        rc, out = run_probe(port)
        sim_stop(p, outf)
        kill_stray()
        time.sleep(0.5)

        simtxt = read_text(os.path.join(LOGS, "scan_%d.out" % port))
        reset = ("ConnectionResetError" in simtxt) or ("\u5f3a\u5236\u5173\u95ed" in simtxt)
        sm = grab(out, "StartMethod")
        dt = grab(out, "Data")
        rows.append({"variant": name, "rc": rc, "startmethod": sm,
                     "data": dt, "reset": reset})
        print("  rc=%s  StartMethod=%s  Data=%s  reset=%s" % (rc, sm, dt, reset))
        port += 1

    print("")
    print("=" * 84)
    print("SUMMARY (ack53 = ReadOcpBytes reply variants)")
    print("=" * 84)
    print("%-12s %-4s %-6s %-30s %s" % ("variant", "rc", "reset", "StartMethod", "Data"))
    best = []
    for r in rows:
        print("%-12s %-4s %-6s %-30s %s" % (
            r["variant"], r["rc"], "Y" if r["reset"] else "n",
            r["startmethod"][:30], r["data"]))
        if r["rc"] == 0 and not r["reset"] and "ret=True" in r["startmethod"]:
            best.append(r["variant"])
    print("")
    print("PASS (StartMethod ret=True, no reset): %s" % (", ".join(best) or "none"))
    return 0 if best else 1


def scan85(base_port):
    from sim_cs5 import VARIANTS_85

    names = [n for n in VARIANTS_85 if n != "echo"]
    names.append("echo")

    rows = []
    kill_stray()
    port = base_port
    for name in names:
        log = os.path.join(LOGS, "scan_%s_%d.jsonl" % (name, port))
        print("")
        print("=" * 62)
        print("ack85=%-16s port=%d" % (name, port))
        print("=" * 62)
        p, outf = sim_start(port, name, "echo", log)
        rc, out = run_probe(port)
        sim_stop(p, outf)
        kill_stray()
        time.sleep(0.6)

        simtxt = read_text(os.path.join(LOGS, "scan_%d.out" % port))
        reset = ("ConnectionResetError" in simtxt) or ("\u5f3a\u5236\u5173\u95ed" in simtxt)
        got85 = ("cmd=0x85" in simtxt) or ("AA 85 63" in simtxt)
        sm = grab(out, "StartMethod")
        rows.append({"variant": name, "rc": rc, "startmethod": sm,
                     "reset": reset, "got85": got85})
        print("  rc=%s  StartMethod=%s  reset=%s" % (rc, sm, reset))
        port += 1

    print("")
    print("=" * 80)
    print("SUMMARY (ack85 variants)")
    print("=" * 80)
    print("%-16s %-4s %-6s %-8s %s" % ("variant", "rc", "reset", "got85", "StartMethod"))
    for r in rows:
        print("%-16s %-4s %-6s %-8s %s" % (
            r["variant"], r["rc"], "Y" if r["reset"] else "n",
            "Y" if r["got85"] else "n", r["startmethod"][:40]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-port", type=int, default=31060)
    ap.add_argument("--scan53", action="store_true",
                    help="scan 0x53 ReadOcpBytes reply variants")
    a = ap.parse_args()

    if not os.path.exists(PROBE):
        print("compile the probe first: csc -out:tests\\probe\\t_cs5probe.exe tests\\probe\\t_cs5probe.cs")
        return 2

    return scan53(a.base_port) if a.scan53 else scan85(a.base_port)


if __name__ == "__main__":
    sys.exit(main())
