# -*- coding: utf-8 -*-
"""who_is_who.py —— 只读：查「哪个工作站连在哪个 CS Studio 实例上」。

软件自己会连工作站（用户 2026-11-11 指示：连接不归脚本管，脚本只负责认领窗口）。
本工具不点任何控件，只读窗口标题 + 进程信息，把标题里的
【型号：XXX in COMn】、序列号、以及 pid/hwnd 列出来，并和 machines_real.json 对账。

用法：
    python who_is_who.py                 # 人类可读表格
    python who_is_who.py --json          # 机器可读
    python who_is_who.py 配置.json       # 指定配置（默认 machines_real.json）
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

import win32gui
import win32process

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))

RE_MODEL = re.compile(r"【型号：(.+?)\s+in\s+(COM\d+)】")
RE_SN = re.compile(r"序列号[:：]\s*([A-Za-z0-9]+)")


def _exe_path(pid: int) -> str:
    """按 pid 取可执行文件全路径（QueryFullProcessImageNameW，无需第三方库）。"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        k32.CloseHandle(h)


def collect() -> list:
    """枚举所有 CS Studio 主窗。返回 [{hwnd,pid,ver,title,model,com,sn,exe,state}]。"""
    found = {}

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            t = win32gui.GetWindowText(hwnd) or ""
            if "CS Studio" not in t:
                return
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            exe = _exe_path(pid)
            if "CorrTest.CSStudio" not in os.path.basename(exe):
                return
            found[hwnd] = {
                "hwnd": hwnd,
                "pid": pid,
                "ver": 6 if "CS Studio6" in t else 5,
                "title": t,
                "model": "",
                "com": "",
                "sn": "",
                "exe": exe,
                "state": "connected",
            }
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)

    out = []
    for hwnd, info in found.items():
        t = info["title"]
        m = RE_MODEL.search(t)
        s = RE_SN.search(t)
        if m:
            info["model"], info["com"] = m.group(1).strip(), m.group(2)
        if s:
            info["sn"] = s.group(1)
        if "演示模式" in t:
            info["state"] = "demo"
        elif "未找到设备" in t:
            info["state"] = "no_device"
        elif not info["sn"]:
            info["state"] = "no_sn"
        out.append(info)
    out.sort(key=lambda x: (x["pid"]))
    return out


def load_machines(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("machines", [])


def reconcile(windows: list, machines: list) -> list:
    """窗口 ↔ 配置 对账，返回告警列表（空=一切正常）。"""
    warns = []
    by_sn = {}
    for w in windows:
        if w["sn"]:
            by_sn.setdefault(w["sn"], []).append(w)
    cfg_sn = {m.get("sn"): m for m in machines if m.get("sn")}

    for sn, ws in by_sn.items():
        if len(ws) > 1:
            warns.append("❗ 序列号 %s 同时出现在 %d 个实例上（pid %s）——"
                         "两个 runner 会驱动同一台仪器，必须先关掉多余实例"
                         % (sn, len(ws), "/".join(str(x["pid"]) for x in ws)))
    for sn, m in cfg_sn.items():
        if sn not in by_sn:
            warns.append("⚠ 配置项 %s 的序列号 %s 没有对应实例（软件没连上/没启动）"
                         % (m.get("name"), sn))
        else:
            w = by_sn[sn][0]
            if w["state"] != "connected":
                warns.append("⚠ %s 的实例状态=%s（标题：%s）"
                             % (m.get("name"), w["state"], w["title"][:60]))
            cm = (m.get("com") or "").strip()
            if cm and w["com"] and cm != w["com"]:
                warns.append("ℹ %s：配置写 %s，软件实际连在 %s（自动连接后以实际为准）"
                             % (m.get("name"), cm, w["com"]))
    for sn in by_sn:
        if sn not in cfg_sn:
            warns.append("ℹ 发现配置里没有的序列号 %s（pid %d）——多出来的实例"
                         % (sn, by_sn[sn][0]["pid"]))
    return warns


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg_path = args[0] if args else os.path.join(ROOT, "machines_real.json")
    windows = collect()
    machines = load_machines(cfg_path) if os.path.exists(cfg_path) else []
    warns = reconcile(windows, machines)

    if "--json" in sys.argv:
        print(json.dumps({"windows": windows, "warnings": warns},
                         ensure_ascii=False, indent=2))
        return 0

    print("时间 %s   配置 %s" % (time.strftime("%H:%M:%S"), os.path.basename(cfg_path)))
    if not windows:
        print("\n没有在运行的 CS Studio 窗口（或窗口标题里没有 'CS Studio'）。")
        return 1
    hdr = "%-10s %-7s %-3s %-10s %-8s %-18s %-6s %s" % (
        "hwnd", "pid", "版", "型号", "串口", "序列号", "状态", "配置项")
    print("\n" + hdr)
    print("-" * len(hdr))
    cfg_by_sn = {m.get("sn"): m.get("name") for m in machines}
    for w in windows:
        print("%-10s %-7d %-3d %-10s %-8s %-18s %-6s %s" % (
            hex(w["hwnd"]), w["pid"], w["ver"], w["model"] or "-",
            w["com"] or "-", w["sn"] or "-", w["state"],
            cfg_by_sn.get(w["sn"], "?")))
    print()
    if warns:
        for x in warns:
            print(x)
        return 1
    print("✅ 窗口与配置一一对应，没有重复序列号。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
