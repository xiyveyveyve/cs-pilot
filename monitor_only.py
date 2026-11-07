# -*- coding: utf-8 -*-
"""monitor_only.py —— 人工启动实验 + 脚本自动判流/停机（最稳妥协作模式）。

监视 CS-Pilot数据 目录下最新出现的 JK-O 动电位数据文件：
  * 实时判流：|电流密度| 连续 2 个新点 ≥ 1e-3 A/cm² → 点数据工具栏「停止」
  * 文件 90s 静默 → 视为实验自然结束
  * 停止后验证数据停写，输出 VERDICT
用法：python monitor_only.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver_direct as DD
import driver as D6
from watch import Sample

D_DIR = r"C:\Users\xiyve\Desktop\CS-Pilot数据"
PREFIX = "2026-11-07-JK-O-动电位"
THR = 1e-3
LOG = r"D:\deepseek\_probe\live_jkf\monitor_only.log"
_lines = []


def log(m):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    _lines.append(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_for_file(timeout: float = 600.0):
    """等用户在软件里启动动电位（新文件出现并开始增长）。"""
    log("等待动电位数据文件出现（请在软件里启动动电位）…")
    t_end = time.time() + timeout
    while time.time() < t_end:
        cands = [f for f in os.listdir(D_DIR)
                 if f.startswith(PREFIX) and f.endswith(".txt")]
        for f in cands:
            p = os.path.join(D_DIR, f)
            try:
                if os.path.getsize(p) > 300 and time.time() - os.path.getmtime(p) < 30:
                    return p
            except OSError:
                continue
        time.sleep(2)
    return None


def main():
    log("=" * 60)
    log("监视模式上线：JK-O 动电位（人工启动，脚本判流+停机）")
    log("=" * 60)
    data = wait_for_file()
    if data is None:
        log("!! 10 分钟内没等到数据文件，退出")
        return 1
    log("数据文件锁定: %s" % data)

    tail_rows = []
    i_hit = 0
    i_last_t = None
    quiet_t0 = time.time()
    last_size = -1
    stopped = False
    t_end = time.time() + 90 * 60          # 90 分钟硬上限
    ui = None

    while time.time() < t_end:
        time.sleep(0.5)
        try:
            rows = [l.split() for l in open(data, encoding="utf-8",
                                            errors="replace") if l.strip()][2:]
        except OSError:
            continue
        if len(rows) == len(tail_rows):     # 没有新点
            if (time.time() - quiet_t0) > 90.0 and len(rows) > 5:
                log("数据 90s 静默 → 实验自然结束")
                break
            continue
        quiet_t0 = time.time()
        new = rows[len(tail_rows):]
        tail_rows = rows
        last = rows[-1]
        try:
            e_now, i_now, t_now = float(last[0]), abs(float(last[1])), float(last[2])
        except (ValueError, IndexError):
            continue
        if t_now != i_last_t:               # 只计新点
            i_last_t = t_now
            if i_now >= THR:
                i_hit += 1
            else:
                i_hit = 0
        if len(tail_rows) % 100 == 0 or i_hit >= 1:
            log("  %d 点 E=%+.4f |i|=%.3e (hit=%d)" % (len(rows), e_now, i_now, i_hit))
        if i_hit >= 2:
            log("★ 电流密度 %.3e A/cm² 连续 2 点达标 → 停止" % i_now)
            stopped = True
            break

    if stopped:
        # 点数据工具栏停止键（用户指认路径，真机已验证）
        log("执行停止：置前 CS Studio6 → 点数据工具栏「停止」键")
        ui = S.Studio(log=log)
        if ui.acquire(10):
            try:
                ui.force_foreground()
                time.sleep(0.5)
                if ui.click_toolbar("data", "停止", wait=1.2):
                    log("  已点「停止」")
            except Exception as e:
                log("  点停止异常：%s" % e)
            time.sleep(2)
            for _ in range(3):
                r = ui.close_win32_modal(prefer=("是(Y)", "是", "确定"))
                if r is None:
                    break
                log("  应答弹窗: %r" % (r,))
                time.sleep(1)

    # 验证数据停写
    s1 = os.path.getsize(data)
    time.sleep(8)
    s2 = os.path.getsize(data)
    stopped_ok = s2 <= s1 + 32
    log("数据 8s 增长 %d B → %s" % (s2 - s1, "已停 ✓" if stopped_ok else "仍在写!"))
    if not stopped_ok and stopped:
        # 再补一轮停止（含运行窗置前）
        ui2 = S.Studio(log=log)
        if ui2.acquire(5):
            dd = DD.DirectDriver(ui2, D6.ParasiteDriver(ui2, log), log)
            dd.stop()
        s3 = os.path.getsize(data)
        time.sleep(6)
        log("补停后 6s 增长 %d B" % (os.path.getsize(data) - s3))
    log("VERDICT: %s" % ("完成" if stopped_ok else "需人工确认"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
