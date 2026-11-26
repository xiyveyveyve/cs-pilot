# -*- coding: utf-8 -*-
"""tests/run_all.py —— 一键回归（纯代码链路，全程只用模拟器）。

分两层：
  L0 离线（不占端口，秒级）
     - 纯策略单元测试 test_policies.py
     - 模拟器自测 simdevice.py --selftest
  L1 端到端（占 TCP 高位端口）
     - 单机四实验 t2_all4
     - 策略端到端 t3_policy（真机回放 + stabilize/current_density）
  L2 多机
     - machines_demo（2 台并行）

用法：
    python -I tests/run_all.py            # 跑 L0+L1+L2
    python -I tests/run_all.py --quick    # 只跑 L0
    python -I tests/run_all.py --skip-multi
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
DATA = r"C:\Users\xiyve\Desktop\10.31与11.3数据"

PASS = FAIL = 0
FAILS = []


def banner(t):
    print("\n" + "=" * 68)
    print("  " + t)
    print("=" * 68)


def record(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [PASS] %s %s" % (name, detail))
    else:
        FAIL += 1
        FAILS.append(name + " " + detail)
        print("  [FAIL] %s %s" % (name, detail))


def _dec(b):
    """子进程输出解码兜底：优先 UTF-8，失败退 GBK（Windows 中文控制台常见）。"""
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", "replace")


def run(cmd, timeout=900, must_contain=None):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)   # 收 bytes，自己解码
        out = _dec(r.stdout) + _dec(r.stderr)
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
        out = _dec(e.stdout) + _dec(e.stderr)
        rc = 124
    dur = time.time() - t0
    ok = rc == 0 and (must_contain is None or must_contain in out)
    return ok, rc, out, dur


def L0():
    banner("L0 离线：策略单元测试")
    ok, rc, out, dur = run([sys.executable, "-I", os.path.join(ROOT, "tests", "test_policies.py")], 180,
                           must_contain="0 FAIL")
    tail = [l for l in out.strip().splitlines() if "汇总" in l]
    record("test_policies.py", ok, (tail[0] if tail else "rc=%s" % rc) + " %.1fs" % dur)

    banner("L0 离线：模拟器自测")
    sim = os.path.join(ROOT, "code", "sim", "simdevice.py")
    ok, rc, out, dur = run([sys.executable, "-I", sim, "--selftest"], 300)
    # 以「M/M 通过」这一行为准（stdout 在某些编码下会丢 PASS 字样）
    import re
    mres = re.search(r"自测结果:\s*(\d+)/(\d+)\s*通过", out)
    if mres:
        got, tot = int(mres.group(1)), int(mres.group(2))
        record("simdevice --selftest", ok and got == tot, "%d/%d 通过 %.1fs" % (got, tot, dur))
    else:
        record("simdevice --selftest", ok, "rc=%s（未找到自测结果行）%.1fs" % (rc, dur))


def L1():
    banner("L1 端到端：单机四实验（模拟信号）")
    ok, rc, out, dur = run([sys.executable, "-I", os.path.join(ROOT, "tests", "run_case.py"),
                            os.path.join("tests", "jobs", "t2_all4.json"),
                            "--timeout", "200", "--retries", "3"], 900,
                           must_contain="VERDICT: ALL-OK")
    record("t2_all4 四实验", ok, "%.1fs" % dur)

    banner("L1 端到端：策略（真机回放 + stabilize / current_density）")
    if not os.path.isdir(DATA):
        record("t3_policy 策略端到端", False, "真机数据目录不存在：%s" % DATA)
        return
    cmd = [sys.executable, "-I", os.path.join(ROOT, "tests", "run_case.py"),
           os.path.join("tests", "jobs", "t3_policy.json"),
           "--timeout", "150", "--retries", "3",
           "--sim-arg=--replay-ocp", "--sim-arg=" + os.path.join(DATA, "26.11.3 GC-C OCP.txt"),
           "--sim-arg=--replay-pot", "--sim-arg=" + os.path.join(DATA, "26.11.3 GC-C DDW.txt")]
    ok, rc, out, dur = run(cmd, 900, must_contain="VERDICT: ALL-OK")
    record("t3_policy 策略端到端", ok, "%.1fs" % dur)


def L2():
    banner("L2 多机并行：2 台")
    ok, rc, out, dur = run([sys.executable, "-I", os.path.join(ROOT, "code", "pilot.py"),
                            os.path.join("tests", "jobs", "machines_demo.json")], 1200,
                           must_contain="VERDICT: ALL-OK")
    record("pilot 双机并行", ok, "%.1fs" % dur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="只跑 L0 离线")
    ap.add_argument("--skip-multi", action="store_true", help="跳过 L2 多机")
    a = ap.parse_args()

    print("CS-Pilot 纯代码路线 · 一键回归")
    print("工作目录：%s" % ROOT)
    print("时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    L0()
    if not a.quick:
        L1()
        if not a.skip_multi:
            L2()

    banner("汇总")
    total = PASS + FAIL
    print("  %d / %d 通过" % (PASS, total))
    if FAILS:
        print("  失败项：")
        for f in FAILS:
            print("    ! " + f)
    print("\n  VERDICT: %s" % ("ALL-OK" if FAIL == 0 else "FAIL"))

    # 落一份报告
    import json
    os.makedirs(LOGS, exist_ok=True)
    with open(os.path.join(LOGS, "run_all_report.json"), "w", encoding="utf-8") as f:
        json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "pass": PASS, "fail": FAIL, "fails": FAILS,
                   "verdict": "ALL-OK" if FAIL == 0 else "FAIL"},
                  f, ensure_ascii=False, indent=2)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
