# -*- coding: utf-8 -*-
"""real_r_gui.py —— 用 CS Studio5 软件本体（已连真机 COM10）跑恒电流阶跃测电阻。

流程（软件本体负责串口握手/连接/采样，UIA 只做开窗口+填参+读数）：
  1. open_experiment(("测试方法(E)","稳态极化(S)","恒电流阶跃(G)")) 打开参数窗
  2. dump 控件 id，找电流/时间/文件名输入框
  3. 填 PorCurr=0.1mA、短时间、文件名
  4. 点确定启动，读运行窗界面 E（UiSampler）
  5. R = E / I

这是 2026-11-18 真机验证的快路；纯代码链缺握手帧的补法另记。
"""
import sys, os, time, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")

import driver5
import studio_ui as SU
from uiprobe import UiSampler

OUT = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\real_r_gui.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(OUT, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass

def main():
    curr_ma = 0.1
    st = driver5.Studio5(log=log)
    if not st.find_main():
        log("FATAL 找不到 CS Studio5 主窗"); return 2
    log("主窗: " + st.title())
    if "CS350" not in st.title():
        log("FATAL 主窗标题未见 CS350 真机连接"); return 2

    # 1) 打开恒电流阶跃参数窗
    path = ("测试方法(E)", "稳态极化(S)", "恒电流阶跃(G)")
    panel = st.open_experiment(path, "frmGalStatic")
    if panel is None:
        # 退而求其次：按标题找
        panel = st.find_panel_by_title("恒电流", timeout=2.0)
    log("参数窗: " + (panel.window_text() if panel else "NOT FOUND"))
    if panel is None: return 3

    # 2) dump 控件 id（只列可编辑类，找电流字段）
    ids = st.by_ids(panel)
    log("控件 %d 个；TextBox/Edit 类:" % len(ids))
    for k, c in sorted(ids.items()):
        try:
            ct = c.element_info.control_type
            if ct in ("Edit", "Text", "ComboBox"):
                v = ""
                try: v = str(c.legacy_properties().get("Value") or "")
                except Exception: pass
                log("  %-34s %-10s = %s" % (k, ct, v[:40]))
        except Exception: pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
