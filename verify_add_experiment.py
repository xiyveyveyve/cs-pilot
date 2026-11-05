# -*- coding: utf-8 -*-
"""verify_add_experiment.py —— 验证重写后的 driver.ParasiteDriver.add_experiment。

seed6 系列用的是探针内联实现；本探针直接调项目代码，确认固化成功。
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def main():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        ui.clear_modals(4)
        for _ in range(4):
            w = None
            try:
                for t, c in ui.panels():
                    if "用户设置" in t:
                        w = c
                        break
            except Exception:
                pass
            if w is None:
                break
            try:
                ui.press_cancel(w)
            except Exception:
                break
            time.sleep(0.5)
        if not ui.is_demo:
            ui.click_menu("%s", "进入演示模式")
            time.sleep(2.0)
            ui.clear_modals(3)
        base = D6.ParasiteDriver(ui, log)
        base.ensure_channel()
        base.activate()
        before = len(base.read_sequence())
        log("添加前行数=%d" % before)

        panel = base.add_experiment(D6.EXP_OCP)
        log("add_experiment(OCP) -> %r" % (panel.window_text() if panel else None,))
        ok = False
        if panel is not None:
            fname = r"D:\deepseek\_probe\seed6row\2026-11-06-DEMO-验证固化"
            got = ui.set_edit("Control_FileName_Text", fname, panel)
            log("填文件名 -> %s" % got)
            ui.press_ok(panel)
            time.sleep(1.5)
            for _ in range(4):
                r = ui.close_win32_modal(prefer=("是(Y)", "是", "确定"))
                if r is None:
                    break
            time.sleep(1.0)
            after = len(base.read_sequence())
            log("添加后行数=%d" % after)
            ok = after > before
        # 收尾：把刚加的行删掉（选中最后一行→垃圾桶 btns[6]），保持队列 4 行
        base.activate()
        rows = base.read_sequence()
        if len(rows) > 4:
            chan = None
            for c in ui.main.descendants(control_type="Window"):
                if "通道" in (c.window_text() or ""):
                    chan = c
                    break
            tb = None
            for c in chan.descendants(control_type="ToolBar"):
                if (c.element_info.automation_id or "") == "toolStrip1":
                    tb = c
                    break
            items = [c for c in chan.descendants(control_type="ListItem")
                     if (c.window_text() or "").strip().isdigit()]
            if items and tb:
                items[-1].click_input()
                time.sleep(0.4)
                btns = list(tb.descendants(control_type="Button"))
                btns[6].click_input()
                time.sleep(0.6)
                log("已清理验证行，队列 %d 行" % len(base.read_sequence()))
        log("VERDICT: %s" % ("driver-add-ok" if ok else "driver-add-fail"))
        return 0 if ok else 1
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"], capture_output=True)
        os.makedirs(r"D:\deepseek\_probe\rehearsal6", exist_ok=True)
        with open(r"D:\deepseek\_probe\rehearsal6\verify_add.log", "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
