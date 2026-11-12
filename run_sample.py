# -*- coding: utf-8 -*-
"""run_sample.py —— 一条命令跑一个试样：认领窗口 → 起 runner。

前提（用户 2026-11-11 指示）：CS Studio 自己连工作站，脚本不管连接。
本工具只做三件事：
  1. 读 machines_real.json 找机位（按名字或序列号）；
  2. 用 who_is_who 的实时窗口表，按**标题里的序列号**认领该机位的窗口
     （自动连接后工作在哪个口、哪个实例，以标题为准，不信配置）；
  3. 用认领到的 hwnd/sn 起 runnerX_live.py，不传 --com（绝不点通讯设置）。

用法：
    python run_sample.py CS350M 1.2                  # 机位名 + 面积
    python run_sample.py CS350M 1.2 Tafel no-eis     # 不测阻抗
    python run_sample.py CS1201312168 1.0 --sample 7号
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import who_is_who as W

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCKS = {}          # 进程内记录已起的锁，防同一秒重复起同一台


def load_machines(path: str = None) -> list:
    path = path or os.path.join(ROOT, "machines_real.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("machines", [])


def pick_machine(machines: list, key: str):
    for m in machines:
        if key in (m.get("name"), m.get("sn")):
            return m
    return None


def resolve_window(machine: dict, windows: list):
    """按配置里的序列号认领窗口。返回 (window, error)。"""
    sn = (machine.get("sn") or "").strip()
    if not sn:
        return None, "配置项 %r 没写序列号，无法认领窗口" % machine.get("name")
    hits = [w for w in windows if w["sn"] == sn]
    if not hits:
        return None, "没有任何实例连着序列号 %s（先让软件连上工作站）" % sn
    if len(hits) > 1:
        return None, ("序列号 %s 同时出现在 %d 个实例上（pid %s）——"
                      "先把多余实例关掉，否则会两个 runner 抢同一台仪器"
                      % (sn, len(hits), "/".join(str(w["pid"]) for w in hits)))
    w = hits[0]
    if w["state"] != "connected":
        return None, "序列号 %s 的实例状态=%s（标题：%s）" % (sn, w["state"], w["title"][:60])
    return w, ""


def main() -> int:
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 2:
        print(__doc__.strip())
        return 2
    key, area_s = pos[0], pos[1]
    item = pos[2] if len(pos) > 2 else "Tafel"
    try:
        area = float(area_s)
    except ValueError:
        print("面积不是数字：%r" % area_s)
        return 2

    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    machines = load_machines(opt("--cfg"))
    m = pick_machine(machines, key)
    if m is None:
        print("配置里没有机位 %r，可选：%s"
              % (key, ", ".join("%s(%s)" % (x.get("name"), x.get("sn")) for x in machines)))
        return 2

    windows = W.collect()
    w, err = resolve_window(m, windows)
    if err:
        print("✗ " + err)
        if windows:
            print("\n当前实例：")
            for x in windows:
                print("  pid=%-6d hwnd=%-8s 型号=%-8s 串口=%-6s SN=%-18s 状态=%s"
                      % (x["pid"], hex(x["hwnd"]), x["model"] or "-",
                         x["com"] or "-", x["sn"] or "-", x["state"]))
        return 1

    ver = int(m.get("version", 6))
    script = m.get("script") or ("runner6_live.py" if ver == 6 else "runner5_live.py")
    sample = opt("--sample") or m.get("name")
    lock = m.get("lock") or ""
    no_eis = ("no-eis" in argv) or bool(m.get("no_eis", False))

    args = [sys.executable, script, sample, str(area), item]
    if no_eis:
        args.append("no-eis")
    args += ["--sn", m["sn"], "--cs-hwnd", str(w["hwnd"])]
    for k, dest in (("max_ocp", "--max-ocp"), ("ocp_time", "--ocp-time"),
                    ("ocp_rounds", "--ocp-rounds")):
        if m.get(k) is not None:
            args += [dest, str(m[k])]
    if m.get("init") is not None:
        args += ["--init", str(m["init"])]
    if m.get("final") is not None:
        args += ["--final", str(m["final"])]
    if m.get("rate") is not None:
        args += ["--rate", str(m["rate"])]
    if lock:
        args += ["--lock", lock]
    if "resume" in argv or m.get("resume"):
        args.append("--resume")

    print("机位 %s  →  窗口 pid=%d hwnd=%s  %s in %s  SN=%s"
          % (m.get("name"), w["pid"], hex(w["hwnd"]), w["model"], w["com"], w["sn"]))
    print("样品 %s / %g cm² / %s / 阻抗=%s" % (sample, area, item, "否" if no_eis else "测"))
    print("命令 %s\n" % " ".join(args))

    if lock and lock in LOCKS and LOCKS[lock].poll() is None:
        print("✗ 同一把锁 %s 已有 runner 在跑（pid=%d）" % (lock, LOCKS[lock].pid))
        return 1
    if lock:
        # 复用 runner 自己的命名互斥锁做最终裁决（它持锁到进程退出）
        pass
    proc = subprocess.Popen(args, cwd=ROOT)
    if lock:
        LOCKS[lock] = proc
    rc = proc.wait()
    print("\nrunner 退出码 %s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
