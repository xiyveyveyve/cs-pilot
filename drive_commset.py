# -*- coding: utf-8 -*-
"""drive_commset.py —— 驱动「通讯设置」完成连接（选端口→确定→验证）。"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"


def find_dialog(ui):
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "通讯设置" in (c.window_text() or ""):
                return c
        except Exception:
            continue
    return None


def main():
    os.system('taskkill /F /IM CorrTest.CSStudio.exe >nul 2>&1')
    time.sleep(2)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        print("!! 没等到主窗")
        return 2
    print("主窗:", ui.title[:60])
    base = D6.ParasiteDriver(ui, print)

    # 1) 打开通讯设置
    if not ui.open_menu("%s"):
        print("!! 系统设置打不开")
        return 2
    time.sleep(0.4)
    clicked = False
    for t, c, r in ui.menu_items():
        if t == "通讯设置":
            c.click_input()
            clicked = True
            break
    if not clicked:
        print("!! 菜单里没有通讯设置")
        return 2
    time.sleep(1.5)

    dlg = find_dialog(ui)
    if dlg is None:
        print("!! 通讯设置对话框没出现")
        return 2
    print("对话框:", dlg.window_text())

    # 2) 端口下拉选 COM16
    # COM 口选择 = 无 aid 的 Com_Com_Com_Combox（Baute_Combox 是波特率框）
    port_combo = None
    for c in dlg.descendants():
        try:
            ei = c.element_info
            if (ei.control_type == "ComboBox"
                    and "Com_Com_Com_Combox" in (ei.automation_id or "")):
                port_combo = c
                break
        except Exception:
            continue
    if port_combo is None:
        print("!! COM 口下拉没找到")
        return 2

    # 3) 端口选 COM16 + 确定
    # WinForms ComboBox 的文本框接受任意键入：直接键入 COM16
    # （COM16 是 DOS 别名不在 SERIALCOMM，下拉列表里没有它——但按名打开有效）
    print("端口框直接键入 COM16 …")
    try:
        port_combo.set_focus()
        time.sleep(0.3)
        from pywinauto.keyboard import send_keys as _sk
        _sk("^a")
        time.sleep(0.1)
        _sk("COM16")
        time.sleep(0.3)
        _sk("{ENTER}")
        time.sleep(0.5)
        cur = ""
        try:
            cur = str(port_combo.legacy_properties().get("Value") or "")
        except Exception:
            cur = "?"
        try:
            cur2 = port_combo.window_text() or ""
        except Exception:
            cur2 = "?"
        try:
            cur3 = port_combo.get_edit_text()
        except Exception:
            cur3 = "?"
        print("端口框现值: Value=%r Text=%r Edit=%r" % (cur, cur2, cur3))
    except Exception as e:
        print("键入异常: %s" % e)
        return 2
    okbtn = ui.by_id("btnOK", dlg) or ui.button("确定", dlg)
    if okbtn is None:
        print("!! 没有确定键")
        return 2
    okbtn.click_input()
    print("已点确定 → 软件连接 COM16 …")

    # 4) 等连接完成（标题出现 CS350M）
    t_end = time.time() + 30
    while time.time() < t_end:
        time.sleep(2)
        title = ui.title
        if "CS350M" in title:
            print("✓ 已连接：%s" % title[:70])
            break
        print("  等待中: %s" % title[:50])
    else:
        print("!! 30s 未连上")
        return 1

    # 5) 验证设备真连上（标题含序列号）
    print("最终标题:", ui.title[:80])
    print("序列号在:", "CS350M24030650" in ui.title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
