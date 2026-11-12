# -*- coding: utf-8 -*-
"""probe_cs5net3.py —— CS5 网口全链连接：sim(CS120)→网口→手动→30005→确定。

CS5 与 CS6 同构（btnEthernet→rbtUser→Com_Com_Com_Combox→btn_Ok）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as SU

ROOT = os.path.dirname(os.path.abspath(__file__))
SIMLOG = r"D:\deepseek\_probe\live\cs5_simlog.jsonl"


def find_main5(timeout=10):
    from pywinauto import Desktop
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in Desktop(backend="uia").windows():
            try:
                if "CS Studio5" in (w.window_text() or ""):
                    return w
            except Exception:
                continue
        time.sleep(1)
    return None


def main():
    # 0) 清残留 sim——但 30006 已监听则复用外部 sim（runner 阶段需 sim 存活；
    #    此前探针自杀 sim 导致 CS5 连接断裂、"发送OCP失败"——实证教训）
    try:
        import socket as _s
        _c = _s.create_connection(("127.0.0.1", 30006), timeout=1)
        _c.close()
        ns = "LISTENING"
    except Exception:
        ns = ""
    reuse = "LISTENING" in ns
    sim = None
    if not reuse:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                        "Where-Object { $_.CommandLine -match 'simdevice.*30006' } | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True)
        time.sleep(1)
        try:
            if os.path.exists(SIMLOG):
                os.remove(SIMLOG)
        except Exception:
            pass
        sim = subprocess.Popen([sys.executable,
                                os.path.join(ROOT, "testbed", "simdevice.py"),
                                "--port", "0.0.0.0:30006", "--tcp", "--lan",
                                "--sn", "CS1201312168", "--lan5", "--log", SIMLOG],
                               cwd=ROOT,
                               stdout=open(r"D:\deepseek\_probe\live\cs5_sim_console.log", "w"),
                               stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        print("sim CS120 (TCP:30006) 已启动")
        time.sleep(3)
    else:
        print("复用外部 sim（30006 已监听）")

    w = find_main5()
    if w is None:
        print("!! CS Studio5 主窗不在")
        if sim:
            sim.terminate()
        return 2
    print("主窗:", (w.window_text() or "")[:50])

    # 对话框已在（上次探针开的）；不在就点菜单
    dlg = None
    for c in w.descendants():
        try:
            if (c.element_info.automation_id or "") == "frmcomProperty":
                dlg = c
                break
        except Exception:
            continue
    if dlg is None:
        print("对话框不在 → 点菜单打开")
        try:
            w.set_focus()
        except Exception:
            pass
        time.sleep(0.4)
        bar = None
        for attempt in range(3):
            from pywinauto.keyboard import send_keys as _sk
            try:
                _sk("{ESC}")
            except Exception:
                pass
            time.sleep(0.3)
            for mb in w.descendants():
                try:
                    t = (mb.window_text() or "").strip()
                    r = mb.rectangle()
                    if t == "系统设置(S)" and r.width() > 0 and r.height() > 0 and r.top > 0:
                        bar = mb
                        break
                except Exception:
                    continue
            if bar is None:
                time.sleep(0.5)
                continue
            bar.click_input()
            time.sleep(1.2)
            item = None
            for mb in w.descendants():
                try:
                    t = (mb.window_text() or "").strip()
                    r = mb.rectangle()
                    if t == "通讯设置" and r.width() > 0 and r.height() > 0 and r.top > 0:
                        item = mb
                        break
                except Exception:
                    continue
            if item is not None:
                item.click_input()
                time.sleep(1.5)
                break
            bar = None
        if bar is None:
            print("!! 3 次尝试都没能点到「通讯设置」")
            if sim:
                sim.terminate()
            return 2
        for c in w.descendants():
            try:
                if (c.element_info.automation_id or "") == "frmcomProperty":
                    dlg = c
                    break
            except Exception:
                continue
        if dlg is None:
            print("!! 对话框仍未出现")
            if sim:
                sim.terminate()
            return 2
        print("对话框已打开")

    def by_aid(aid):
        for c in dlg.descendants():
            try:
                if c.element_info.automation_id == aid:
                    return c
            except Exception:
                continue
        return None

    # 网口 → 手动
    btn_eth = by_aid("btnEthernet")
    btn_eth.click_input()
    time.sleep(0.6)
    rbt_user = by_aid("rbtUser")
    rbt_user.click_input()
    time.sleep(0.6)
    print("已选 网口→手动")

    pc = by_aid("Com_Com_Com_Combox")
    print("IP 下拉 enabled =", pc.is_enabled())
    if not pc.is_enabled():
        print("!! 仍禁用")
        if sim:
            sim.terminate()
        return 2
    ok_sel = SU.navigate_combo(pc, "30006", max_try=20)
    try:
        rb = str(pc.legacy_properties().get("Value") or "")
    except Exception:
        rb = "?"
    print("选择:", ok_sel, "| 回读:", repr(rb))
    if not ok_sel:
        if sim:
            sim.terminate()
        return 2

    by_aid("btn_Ok").click_input()
    print("已点确定 → 等连接 …")

    t_end = time.time() + 50
    result = "未连上"
    while time.time() < t_end:
        time.sleep(2)
        try:
            title = w.window_text() or ""
        except Exception:
            continue
        print("  [%4.1fs] %s" % (50 - (t_end - time.time()), title[:60]))
        if "CS120" in title:
            result = "已连接"
            break
    print("结果:", result, "| 标题:", (w.window_text() or "")[:70])

    time.sleep(1)
    if os.path.exists(SIMLOG):
        with open(SIMLOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        print("=== 模拟器帧日志 %d 条 ===" % len(lines))
        for ln in lines[:40]:
            print("  ", ln.strip()[:150])
    else:
        print("!! 帧日志不存在")
    return 0 if result == "已连接" else 1


if __name__ == "__main__":
    sys.exit(main())
