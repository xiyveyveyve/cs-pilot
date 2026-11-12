# -*- coding: utf-8 -*-
"""probe_cs5net.py —— CS Studio5 网口连接探针（阶段 1：菜单+对话框侦察）。

前置：simdevice 第二实例 --tcp --lan :30005 --sn CS1201312168（真机 SN）。
流程：启动 CS5 → 抓主窗（标题预过滤 CS Studio5）→ dump 菜单 →
  找通讯设置 → 打开 → dump 对话框控件+截图。不点确定。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE5 = r"D:\sci\CS Studio5\CS Studio5\CorrTest.CSStudio.exe"
SHOT = r"D:\deepseek\_probe\cs5_commset.png"


def find_main5(timeout=30):
    """抓 CS Studio5 主窗（标题预过滤，防误抓 CS6）。"""
    from pywinauto import Desktop
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in Desktop(backend="uia").windows():
            try:
                t = w.window_text() or ""
                if "CS Studio5" in t:
                    return w
            except Exception:
                continue
        time.sleep(1)
    return None


def main():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'simdevice.*30005' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)
    # 1) sim 第二实例（CS120 SN）
    sim = subprocess.Popen([sys.executable,
                            os.path.join(ROOT, "testbed", "simdevice.py"),
                            "--port", "0.0.0.0:30005", "--tcp", "--lan",
                            "--sn", "CS1201312168",
                            "--log", r"D:\deepseek\_probe\live\cs5_simlog.jsonl"],
                           cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("sim CS120 实例已启动 (TCP:30005)")
    time.sleep(3)

    # 2) 启动 CS5
    subprocess.Popen([EXE5])
    w = find_main5(40)
    if w is None:
        print("!! 没等到 CS Studio5 主窗")
        sim.terminate()
        return 2
    print("主窗:", repr((w.window_text() or "")[:60]))

    # 3) dump 菜单结构（找通讯设置）
    ui5 = None
    try:
        import studio_ui as S
        ui5 = S.Studio(log=print)
        # 强制把 main 指到 CS5 窗（Studio 可能抓到 CS6——用标题区分）
        if ui5.main is not None and "CS Studio5" not in (ui5.title or ""):
            print("Studio 抓到的是 CS6，改用直连 wrapper")
            ui5 = None
    except Exception as e:
        print("Studio 异常:", e)
        ui5 = None

    if ui5 is not None and ui5.main is not None:
        try:
            ui5.open_menu("%s")
            time.sleep(0.5)
            print("=== 菜单项 ===")
            for t, c, r in ui5.menu_items():
                if r.top > 0:
                    print("  %r @(%d,%d)" % (t[:30], r.left, r.top))
        except Exception as e:
            print("菜单打开失败:", e)
    else:
        # 直接枚举 CS5 主窗的菜单栏
        print("=== CS5 菜单栏（wrapper 直查）===")
        try:
            for mb in w.descendants():
                try:
                    if mb.element_info.control_type == "MenuItem":
                        print("  MenuItem:", repr((mb.window_text() or "")[:24]))
                except Exception:
                    continue
        except Exception as e:
            print("枚举失败:", e)
    try:
        w.set_focus()
        img = w.capture_as_image()
        img.save(SHOT)
        print("截图:", SHOT)
    except Exception as e:
        print("截图失败:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
