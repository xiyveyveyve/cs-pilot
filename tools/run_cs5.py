# -*- coding: utf-8 -*-
"""tools/run_cs5.py -- 单进程驱动 CS5 全链路（**一次命令完成，不需要外部清场**）

为什么有这个脚本（2026-11-10）
--------------------------------
之前每轮巡检要做几十次独立操作：powershell 清场 → 起 sim → 跑探针 → grep 日志 → 再清场。
每一次都要一次系统授权确认，用户跟不上。

本脚本把全部步骤收进**一个 Python 进程**：
  * 自己 Popen 起模拟器并**保留句柄** → finally 里 terminate，不需要 powershell 杀进程
  * 用 socket connect 探测端口就绪，不依赖 netstat / tasklist
  * subprocess 跑 C# 探针，直接解析结论
  * 端口自动挑选（从 --base-port 起找空闲口），不会被残留连接卡住
  * 结果写 JSON 摘要，一次输出全部结论

所以外部只需要一条命令。

用法
----
    # 跑单个 ack53 变体
    python -I tools/run_cs5.py --variant 53le

    # 扫全部 ack53 变体（11 个，约 3 分钟）
    python -I tools/run_cs5.py --scan53

    # 用逐步探针（定位失败点），配合任意变体
    python -I tools/run_cs5.py --variant 53le --probe steps
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = os.path.join(ROOT, "code", "cs5", "sim_cs5.py")
LOGS = os.path.join(ROOT, "logs")
PROBES = {
    "probe": os.path.join(ROOT, "tests", "probe", "t_cs5probe.exe"),
    "steps": os.path.join(ROOT, "tests", "probe", "t_cs5steps.exe"),
}

sys.path.insert(0, os.path.join(ROOT, "code", "cs5"))


# ---------------------------------------------------------------- 端口工具
def pick_port(start=32200, tries=80):
    """从 start 起找一个能 bind 的空闲端口（bind 后立刻释放，交给 sim 用）。"""
    for p in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            s.close()
    raise RuntimeError("找不到空闲端口（%d~%d）" % (start, start + tries))


def wait_port(port, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.25)
    return False


# ---------------------------------------------------------------- 单次运行
def run_one(variant, probe_name="probe", timeout=120, extra_sim=None, ack85sub=None, ack74="echo"):
    """起 sim -> 等端口 -> 跑探针 -> 收尾。返回 dict。"""
    probe = PROBES[probe_name]
    if not os.path.exists(probe):
        return {"variant": variant, "error": "探针不存在: " + probe}
    if not os.path.exists(SIM):
        return {"variant": variant, "error": "sim_cs5.py 不存在"}

    port = pick_port()
    tag = "auto53_%s_%d" % (variant, port)
    logf = os.path.join(LOGS, tag + ".jsonl")
    outf = os.path.join(LOGS, tag + ".out")

    sim_args = [sys.executable, "-I", SIM,
                "--port", "0.0.0.0:%d" % port,
                "--ack85", "silent", "--ack74", ack74,
                "--ack53", variant, "--log", logf]
    if ack85sub:
        sim_args += ["--ack85sub", ack85sub]
    if extra_sim:
        sim_args += extra_sim

    fh = open(outf, "w", encoding="utf-8", errors="replace")
    sim = subprocess.Popen(sim_args, stdout=fh, stderr=subprocess.STDOUT)
    try:
        if not wait_port(port):
            return {"variant": variant, "port": port, "error": "模拟器端口未就绪"}
        t0 = time.time()
        try:
            r = subprocess.run([probe, "--port", str(port)],
                               capture_output=True, timeout=timeout)
            raw = (r.stdout or b"") + (r.stderr or b"")
            txt = raw.decode("utf-8", "replace")
            if "\ufffd" in txt:                       # 编码兜底
                try:
                    txt = raw.decode("gbk", "replace")
                except Exception:
                    pass
            rc = r.returncode
        except subprocess.TimeoutExpired as e:
            raw = e.stdout or b""
            txt = (raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
            rc = 124
        return {
            "variant": variant,
            "port": port,
            "rc": rc,
            "dur": round(time.time() - t0, 1),
            "out": txt,
            "log": logf,
        }
    finally:
        try:
            sim.terminate()
            sim.wait(timeout=5)
        except Exception:
            try:
                sim.kill()
            except Exception:
                pass
        try:
            fh.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 摘要
def summarize(res):
    """从探针输出里抽关键行。"""
    txt = res.get("out", "") or ""
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    keys = [l for l in lines
            if l.startswith(("StartMethod", "Data", "[S", "[4]", "[5]", "[6]", "[7]"))
            or "diag" in l or "ExtAmp" in l or "VotCoef" in l or "inject" in l]
    res["summary"] = keys
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="53le", help="ack53 变体名")
    ap.add_argument("--scan53", action="store_true", help="扫全部 ack53 变体")
    ap.add_argument("--probe", default="probe", choices=sorted(PROBES))
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--json", default=None, help="结果 JSON 输出路径")
    ap.add_argument("--ack85sub", default=None,
                    help="按 0x85 子命令区分应答（如 0a_echo / 0a_cf00）")
    ap.add_argument("--ack74", default="echo", choices=["echo", "bare74", "cf00", "silent"],
                    help="0x74 方法帧应答（2026-11-10 修：默认 echo，旧版强制 silent 致 S4 帧1 无 ACK）")
    ap.add_argument("--no-stream", dest="no_stream", action="store_true",
                    help="关 sim 推流（2026-11-10：StartMethod 内 Sleep(800) 期间推流塞满 m_DataBuffer 卡死判定层）")
    ap.add_argument("--scan85sub", action="store_true",
                    help="扫全部 ack85sub 变体（0x85 子命令应答）")
    a = ap.parse_args()

    os.makedirs(LOGS, exist_ok=True)

    if a.scan85sub:
        try:
            from sim_cs5 import VARIANTS_85_SUB
        except Exception as e:
            print("无法读取变体表: %r" % (e,))
            return 2
        names = list(VARIANTS_85_SUB)
        print("扫 %d 个 ack85sub 变体：%s" % (len(names), ", ".join(names)))
        results = []
        for i, v in enumerate(names, 1):
            print("[%d/%d] ack85sub=%s ..." % (i, len(names), v), flush=True)
            r = summarize(run_one(a.variant, a.probe, a.timeout, ack85sub=v, ack74=a.ack74))
            r["ack85sub"] = v
            results.append(r)
            if r.get("error"):
                print("  ERROR: " + r["error"])
            else:
                print("  rc=%s dur=%ss" % (r["rc"], r["dur"]))
                for l in r["summary"]:
                    print("    " + l)
        print("=" * 78)
        print("SUMMARY (ack85sub)")
        print("=" * 78)
        print("%-12s %-4s %s" % ("ack85sub", "rc", "key result"))
        for r in results:
            key = ""
            for l in r.get("summary", []):
                if l.startswith("StartMethod"):
                    key = l
                    break
            if not key and r.get("summary"):
                key = r["summary"][0]
            print("%-12s %-4s %s" % (r.get("ack85sub"), r.get("rc"), key[:66]))
        if a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump([{k: v for k, v in r.items() if k != "out"} for r in results],
                          f, ensure_ascii=False, indent=2)
        return 0

    if a.scan53:
        try:
            from sim_cs5 import VARIANTS_READOCP
        except Exception as e:
            print("无法读取变体表: %r" % (e,))
            return 2
        names = [n for n in VARIANTS_READOCP]
        print("扫 %d 个 ack53 变体：%s" % (len(names), ", ".join(names)))
    else:
        names = [a.variant]

    results = []
    extra = ["--no-stream"] if a.no_stream else None
    for i, v in enumerate(names, 1):
        print("\n[%d/%d] variant=%s ..." % (i, len(names), v), flush=True)
        r = summarize(run_one(v, a.probe, a.timeout, extra_sim=extra, ack85sub=a.ack85sub, ack74=a.ack74))
        results.append(r)
        if r.get("error"):
            print("  ERROR: " + r["error"])
        else:
            print("  rc=%s dur=%ss port=%s" % (r["rc"], r["dur"], r["port"]))
            for l in r["summary"]:
                print("    " + l)

    # ---- 汇总 ----
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    hdr = "%-10s %-4s %-6s %s" % ("variant", "rc", "dur", "key result")
    print(hdr)
    for r in results:
        if r.get("error"):
            print("%-10s %-4s %-6s %s" % (r["variant"], "-", "-", r["error"]))
            continue
        key = ""
        for l in r["summary"]:
            if l.startswith("StartMethod"):
                key = l
                break
        if not key and r["summary"]:
            key = r["summary"][0]
        print("%-10s %-4s %-6s %s" % (r["variant"], r["rc"], r["dur"], key[:70]))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([{k: v for k, v in r.items() if k != "out"} for r in results],
                      f, ensure_ascii=False, indent=2)
        print("\n结果已写入 " + a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
