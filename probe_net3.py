# -*- coding: utf-8 -*-
"""probe_net3.py —— dump「网络配置」对话框（btnESet）——LAN 设备管理入口。

先看 IP 下拉现有条目（navigate 逐项走一遍），再点网络配置 dump 结构+截图。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
SHOT = r"D:\deepseek\_probe\commset_eset.png"


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
    subprocess.Popen([EXE6])
    ui = S.Studio(log=print)
    if not ui.acquire(30):
        return 2
    if not ui.open_menu("%s"):
        return 2
    time.sleep(0.4)
    for t, c, r in ui.menu_items():
        if t == "通讯设置":
            c.click_input()
            break
    time.sleep(1.5)
    dlg = None
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "通讯设置" in (c.window_text() or ""):
                dlg = c
                break
        except Exception:
            continue
    if dlg is None:
        print("!! 对话框没出现")
        return 2

    by_aid(dlg, "chkEthernet").click_input()
    time.sleep(0.4)
    by_aid(dlg, "rbtUser").click_input()
    time.sleep(0.4)

    # IP 下拉现有条目：键盘走一遍收集
    pc = by_aid(dlg, "Com_Com_Com_Combox")
    print("=== IP 下拉条目收集 ===")
    try:
        pc.set_focus()
        pc.type_keys("{HOME}", pause=0.1)
        vals = []
        for i in range(12):
            v = ""
            try:
                v = str(pc.legacy_properties().get("Value") or "")
            except Exception:
                pass
            print("  [%d] %r" % (i, v))
            if v and v not in [x for x in vals]:
                vals.append(v)
            pc.type_keys("{DOWN}", pause=0.1)
        print("条目集合:", vals)
    except Exception as e:
        print("导航失败:", e)

    # 网络配置按钮
    eset = by_aid(dlg, "btnESet")
    if eset is None:
        print("!! btnESet 没找到")
        return 2
    eset.click_input()
    time.sleep(1.5)

    print("=== 网络配置对话框控件 ===")
    for c in ui.descendants():
        try:
            ei = c.element_info
            if ei.control_type == "Window" and ei.automation_id:
                pass
        except Exception:
            continue
    # 找新弹的窗
    eset_dlg = None
    for c in ui.descendants():
        try:
            ei = c.element_info
            t = (c.window_text() or "").strip()
            if ei.control_type == "Window" and t and "通讯设置" not in t:
                eset_dlg = c
                print("新窗:", repr(t[:40]))
        except Exception:
            continue
    if eset_dlg is None:
        print("!! 网络配置对话框没出现")
        return 2
    for c in eset_dlg.descendants():
        try:
            ei = c.element_info
            aid = ei.automation_id or ""
            t = (c.window_text() or "").strip()
            en = ""
            try:
                en = " en=%s" % c.is_enabled()
            except Exception:
                pass
            if aid or t:
                print("  %-9s aid=%-30r text=%-22r%s" % (ei.control_type,
                                                         aid[:30], t[:22], en))
        except Exception:
            continue
    try:
        img = eset_dlg.capture_as_image()
        img.save(SHOT)
        print("截图:", SHOT)
    except Exception as e:
        print("截图失败:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
