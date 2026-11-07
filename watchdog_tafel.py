# -*- coding: utf-8 -*-
"""watchdog_tafel.py —— JK-O 动电位扫描完成自动停止看门狗。

背景：跑扫描的 runner 进程已死，扫描完成（E 到 +1.5V）后没人点停止，
电极会一直被极化。本看门狗每 5s 检查数据文件：
  * 最后一点 E ≥ +1.48V（扫描到终点）或文件 ≥90s 没增长（扫描结束）
  → 找运行窗 → 点数据工具栏「停止」→ 应答弹窗 → 验证数据停写。
全部日志落盘，完成后写 DONE 标记退出。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

DATA = r"C:\Users\xiyve\Desktop\CS-Pilot数据\2026-11-07-JK-O-动电位.txt"
LOG = r"D:\deepseek\_probe\live_jkf\watchdog.log"
DONE = LOG + ".done"


def log(m):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_last():
    try:
        rows = [l.split() for l in open(DATA, encoding="utf-8", errors="replace")
                if l.strip()][2:]
        size = os.path.getsize(DATA)
        mtime = os.path.getmtime(DATA)
        return rows, size, mtime
    except Exception as e:
        log("读数据失败: %r" % (e,))
        return [], 0, 0.0


def click_stop():
    """找运行窗 → 点数据工具栏「停止」。返回是否点到了。"""
    import studio_ui as S2
    ui = S2.Studio(log=None)
    run = None
    for c in ui.descendants():
        try:
            if c.element_info.control_type == "Window" and "[通道" in (c.window_text() or ""):
                run = c
                break
        except Exception:
            continue
    if run is None:
        log("  运行窗不在（可能已自行结束）")
        return False
    for c in run.descendants():
        try:
            if (c.element_info.control_type == "ToolBar"
                    and (c.element_info.automation_id or "") == "toolStrip1"):
                btns = [b for b in c.descendants()
                        if b.element_info.control_type == "Button"]
                log("  工具栏按钮数=%d" % len(btns))
                if btns:
                    btns[0].click_input()      # 停止 = 首键（与 6 版数据栏一致）
                    log("  已点停止键")
                    return True
        except Exception:
            continue
    log("  运行窗里没找到工具栏")
    return False


def main():
    if os.path.exists(DONE):
        os.remove(DONE)
    log("看门狗启动：盯 %s" % os.path.basename(DATA))
    quiet_t0 = None
    last_size = -1
    while True:
        rows, size, mtime = read_last()
        # 终点判定 1：最后一点 E ≥ +1.48V（扫到 +1.5V 终点）
        at_end = False
        if rows:
            try:
                at_end = float(rows[-1][0]) >= 1.48
            except (ValueError, IndexError):
                pass
        # 终点判定 2：文件 90s 没增长（扫描自然结束）
        if size != last_size:
            last_size = size
            quiet_t0 = time.time()
        quiet = (time.time() - quiet_t0) >= 90.0 if quiet_t0 else False

        if rows and (at_end or quiet):
            log("触发：at_end=%s quiet=%s（末点 E=%s t=%s）"
                % (at_end, quiet, rows[-1][0] if rows else "?",
                   rows[-1][2] if rows else "?"))
            clicked = click_stop()
            time.sleep(3)
            # 应答可能的「是否立即停止?」弹窗
            ui = S.Studio(log=None)
            if ui.acquire(5):
                for _ in range(3):
                    r = ui.close_win32_modal(prefer=("是(Y)", "是", "确定"))
                    if r is None:
                        break
                    log("  应答弹窗: %r" % (r,))
                    time.sleep(1)
            # 验证数据停写
            s1 = os.path.getsize(DATA) if os.path.exists(DATA) else 0
            time.sleep(8)
            s2 = os.path.getsize(DATA) if os.path.exists(DATA) else s1
            stopped = (s2 <= s1 + 32)
            log("停止后 8s 增长 %d B → %s" % (s2 - s1, "已停 ✓" if stopped else "仍在写!"))
            if stopped or not clicked:
                open(DONE, "w").write("done")
                log("DONE")
                return 0
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
