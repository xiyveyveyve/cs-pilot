# -*- coding: utf-8 -*-
"""probe_net2.py —— 网口全链探针：simdevice(--tcp) ↔ 软件(网口手动 IP:PORT)。

反编译依据：SockectConnect.Open("IP:PORT") 纯 TCP 连接，无串口式 VID 门禁。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
SIMLOG = r"D:\deepseek\_probe\live\net2_simlog.jsonl"
ADDR = "127.0.0.1:58001"


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
    os.system('taskkill /F /IM CorrTest.CSStudio.exe >nul 2>&1')
    time.sleep(2)

    # 1) 模拟器 TCP 服务端
    try:
        os.makedirs(os.path.dirname(SIMLOG), exist_ok=True)
        if os.path.exists(SIMLOG):
            os.remove(SIMLOG)
    except Exception:
        pass
    sim = subprocess.Popen([sys.executable,
                            os.path.join(ROOT, "testbed", "simdevice.py"),
                            "--port", ADDR, "--tcp", "--log", SIMLOG],
                           cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("simdevice --tcp %s 已启动" % ADDR)
    time.sleep(3)

    # 2) 软件 → 通讯设置 → 网口 → 手动
    subprocess.Popen([EXE6])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        print("!! 没等到主窗")
        sim.terminate()
        return 2
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

    by_aid(dlg, "chkEthernet").click_input()
    time.sleep(0.5)
    by_aid(dlg, "rbtUser").click_input()
    time.sleep(0.5)
    print("已选 网口→手动")

    # 3) IP combo 键入 127.0.0.1:58001
    pc = by_aid(dlg, "Com_Com_Com_Combox")
    print("IP 下拉 enabled =", pc.is_enabled())
    if not pc.is_enabled():
        print("!! 仍禁用")
        sim.terminate()
        return 2
    pc.set_focus()
    time.sleep(0.3)
    pc.type_keys("^a", pause=0.1)   # 全选清空
    time.sleep(0.2)
    pc.type_keys(ADDR, pause=0.03)
    time.sleep(0.4)
    try:
        rb = str(pc.legacy_properties().get("Value") or "")
    except Exception:
        rb = "?"
    print("IP 回读:", repr(rb))
    if "58001" not in rb:
        print("!! IP 键入未生效，终止")
        sim.terminate()
        return 2

    # 4) 确定 → 等标题翻转
    by_aid(dlg, "btnOK").click_input()
    print("已点确定 → 等 TCP 连接与握手 …")

    t_end = time.time() + 30
    result = "未连上"
    while time.time() < t_end:
        time.sleep(2)
        try:
            title = ui.title
        except Exception:
            continue
        print("  [%4.1fs] %s" % (30 - (t_end - time.time()), title[:60]))
        if "CS350M" in title:
            result = "已连接"
            break
    print("结果:", result, "| 标题:", ui.title[:80])

    # 5) 收尾 + sim 日志
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
        print("!! 模拟器帧日志不存在——TCP 层无帧")
    return 0 if result == "已连接" else 1


if __name__ == "__main__":
    sys.exit(main())
