# -*- coding: utf-8 -*-
"""probe_net4.py —— LAN 发现全链：simdevice(--tcp --lan) → 软件网口模式连入。

发现链（UdpPort.cs 还原）：软件广播 0x20/0x24 → UDP:1024 应答（41B，
[18:20]=TCP 端口 BE）→ 软件把 IP:PORT 填入 IP 下拉 → TCP 连入 → 帧协议。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import studio_ui as SU

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
SIMLOG = r"D:\deepseek\_probe\live\net4b_simlog.jsonl"


def find_dialog(ui):
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "通讯设置" in (c.window_text() or ""):
                return c
        except Exception:
            continue
    return None


def by_aid(dlg, aid):
    for c in dlg.descendants():
        try:
            if c.element_info.automation_id == aid:
                return c
        except Exception:
            continue
    return None


def main():
    # 0) 预清场：杀残留 sim（SO_REUSEADDR 双绑会让旧进程抢走新连接——实证教训）
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'simdevice' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)
    time.sleep(1)

    os.system('taskkill /F /IM CorrTest.CSStudio.exe >nul 2>&1')
    time.sleep(2)

    sim = subprocess.Popen([sys.executable,
                            os.path.join(ROOT, "testbed", "simdevice.py"),
                            "--port", "0.0.0.0:30001", "--tcp", "--lan",
                            "--log", SIMLOG],
                           cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("simdevice --tcp --lan 0.0.0.0:30001 已启动")
    time.sleep(3)

    subprocess.Popen([EXE6])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        print("!! 没等到主窗")
        sim.terminate()
        return 2
    print("启动标题:", ui.title[:50])
    if not ui.open_menu("%s"):
        print("!! 系统设置打不开")
        sim.terminate()
        return 2
    time.sleep(0.4)
    for t, c, r in ui.menu_items():
        if t == "通讯设置":
            c.click_input()
            break
    time.sleep(1.5)
    dlg = find_dialog(ui)
    if dlg is None:
        print("!! 对话框没出现")
        sim.terminate()
        return 2

    # 网口 → 手动（列表应已含发现的设备）
    by_aid(dlg, "chkEthernet").click_input()
    time.sleep(2.5)      # 给发现协议 2.5s（软件发现窗等待 1.5s+5s）
    by_aid(dlg, "rbtUser").click_input()
    time.sleep(0.5)
    pc = by_aid(dlg, "Com_Com_Com_Combox")
    print("IP 下拉 enabled =", pc.is_enabled())
    ok_sel = SU.navigate_combo(pc, "30001", max_try=20)
    try:
        rb = str(pc.legacy_properties().get("Value") or "")
    except Exception:
        rb = "?"
    print("选择:", ok_sel, "| IP 回读:", repr(rb))
    if not ok_sel:
        # 自动模式也许能直连：切自动试试
        print("手动选择失败 → 改试自动模式")
        by_aid(dlg, "rbtAuto").click_input()
        time.sleep(0.5)
    by_aid(dlg, "btnOK").click_input()
    print("已点确定 → 等连接 …")

    t_end = time.time() + 35
    result = "未连上"
    while time.time() < t_end:
        time.sleep(2)
        try:
            title = ui.title
        except Exception:
            continue
        print("  [%4.1fs] %s" % (35 - (t_end - time.time()), title[:60]))
        if "CS350M" in title:
            result = "已连接"
            break
    print("结果:", result, "| 标题:", ui.title[:80])

    try:
        sim.terminate()
    except Exception:
        pass
    time.sleep(1)
    if os.path.exists(SIMLOG):
        with open(SIMLOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        print("=== 模拟器帧日志 %d 条 ===" % len(lines))
        for ln in lines[:50]:
            print("  ", ln.strip()[:150])
    else:
        print("!! 帧日志不存在——TCP 层无帧")
    return 0 if result == "已连接" else 1


if __name__ == "__main__":
    sys.exit(main())
