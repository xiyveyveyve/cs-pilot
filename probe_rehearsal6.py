# -*- coding: utf-8 -*-
"""probe_rehearsal6.py —— A2：演示模式全流程预演（用项目自己的机制）。

队列已有 4 行（OCP→动电位→频率扫描→阶梯波，A1 种下）。本探针：
    点「开始」→ 抓运行窗真实标题（喂给 A3 的 is_run_title 求证）
    → CorFileTail 盯 OCP 数据文件（验证演示模式是否写盘）
    → 判稳器实时吃数据（验证联动接线，数值无意义）
    → 判稳/超时后 dd.stop()（验证"停当前+自动接续"行为）
    → 观察下一项是否自动开始 → 全部停掉 → 文件心跳验证收尾
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6
import driver_direct as DD
import stabilizer as ST
import watch as W

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
ROWDIR = r"D:\deepseek\_probe\seed6row"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(r"D:\deepseek\_probe\rehearsal6", exist_ok=True)
    with open(r"D:\deepseek\_probe\rehearsal6\run.log", "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def kill_cs():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                   capture_output=True)
    time.sleep(1.5)


def close_settings(ui):
    for _ in range(5):
        w = None
        try:
            for t, c in ui.panels():
                if "用户设置" in t or "通讯配置向导" in t:
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
    ui.clear_modals(3)


def main():
    kill_cs()
    log("启动 6 版")
    subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            log("!! 没等到主窗")
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        close_settings(ui)
        if not ui.is_demo:
            ui.click_menu("%s", "进入演示模式")
            log("进入演示模式 -> %s" % ui.is_demo)
            time.sleep(2.0)
            close_settings(ui)
        base = D6.ParasiteDriver(ui, log)
        base.ensure_channel()
        base.activate()
        rows = base.read_sequence()
        log("序列 %d 行：%r" % (len(rows), [r["name"] for r in rows]))
        if not rows:
            log("!! 队列空了，先跑种子")
            return 2

        dd = DD.DirectDriver(ui, base, log)
        dd.prepare()

        # ---- 开始 ----
        log("点「开始」（seq 工具栏 index 2）")
        ui.click_toolbar("seq", "开始", wait=2.0)
        time.sleep(2.0)

        # 运行窗标题（A3 实证素材）
        rw = dd.mdi_run_windows()
        log("MDI 运行窗：%r" % [t for _w, t in rw])
        from driver_direct import is_run_title
        for _w, t in rw:
            log("  is_run_title(%r) = %s" % (t, is_run_title(t)))
        log("主窗标题：%r" % ui.title)

        # ---- 盯文件 ----
        ocp_txt = os.path.join(ROWDIR, "2026-11-06-DEMO-开路电位.txt")
        tail = W.CorFileTail(ocp_txt)
        stab = ST.OcpStabilizer(ST.StabConfig())
        log("盯数据文件：%s（存在=%s）" % (ocp_txt, os.path.exists(ocp_txt)))

        t0 = time.time()
        stable_at = None
        last_log = 0.0
        while time.time() - t0 < 150:
            new = tail.poll()
            series = tail.series_ev()
            if series:
                st = stab.feed(series)
                if time.time() - last_log >= 10:
                    last_log = time.time()
                    log("  t=%5.1fs 文件=%dB 点=%d E=%.4f 斜率=%+.2f mV/min 峰峰=%.2f (%s)"
                        % (time.time() - t0, tail.size(), len(series),
                           series[-1][1], st.slope_mv_per_min, st.ppt_mv, st.phase))
                if st.stable and stable_at is None:
                    stable_at = time.time() - t0
                    log("  ★ 判稳 @%.1fs E=%.6f（演示数据，仅验证接线）" % (stable_at, st.mean_v))
                    break
            if not dd.is_running():
                log("  dd.is_running()=False @%.1fs（实验自己结束了？）" % (time.time() - t0))
                break
            time.sleep(0.4)

        ran_files = os.path.exists(ocp_txt)
        log("演示模式写盘=%s 文件=%dB" % (ran_files, tail.size()))

        # ---- 停止当前（看是否自动接续）----
        log("判稳/超时 → dd.stop()")
        ok = dd.stop()
        log("dd.stop() -> %s" % ok)
        time.sleep(3.0)
        rw2 = dd.mdi_run_windows()
        log("停止后 MDI 运行窗：%r" % [t for _w, t in rw2])
        if rw2:
            log("  → 停止当前后序列接续了下一项（行为确认）")
            log("  再次停止，结束整个序列")
            dd.stop()
            time.sleep(2.0)
            log("  最终运行窗：%r" % [t for _w, t in dd.mdi_run_windows()])

        # ---- 文件心跳验证 ----
        time.sleep(2.0)
        quiet = None
        for p in (ocp_txt,):
            if os.path.exists(p):
                age = time.time() - os.path.getmtime(p)
                quiet = age
                log("文件心跳：%s 最后写入距今 %.1fs（>10s 即判定收尾成功）" % (os.path.basename(p), age))
        log("VERDICT: %s" % ("rehearsal-ok" if ran_files else "no-data-file"))
        return 0
    finally:
        try:
            kill_cs()
        except Exception:
            pass
        flush_log()


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
