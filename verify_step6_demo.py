# -*- coding: utf-8 -*-
"""verify_step6_demo.py —— 验证 driver_direct.open_by_combo_demo() 可复用路径：

    演示模式 → 组合测试 → 通道窗“+” → 「添加」→ 确认 → 阶梯波参数窗
    → 试写 5 个关键参数（不点确定）→ 取消 → 关软件。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver_direct as DD

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
PROBE_DIR = r"D:\deepseek\_probe\step6_combo"
_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    kill6()
    time.sleep(1.5)
    subprocess.Popen([EXE6])
    ui = S.Studio(timeout=45, log=log)
    if not ui.acquire(45):
        log("!! 没连上 CS Studio6")
        return 2
    time.sleep(1.5)
    dd = DD.DirectDriver(ui, None, log)
    ui.force_foreground()
    ui.clear_modals()
    # 关「用户设置」（主窗 child 窗，可能延迟弹）
    for _ in range(3):
        s = dd._main_child("用户设置")
        if s is None:
            break
        try:
            for c in s.descendants(control_type="Button"):
                if (c.window_text() or "").strip() in ("退出", "保存"):
                    c.click_input()
                    break
        except Exception:
            pass
        time.sleep(0.8)
    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进演示模式 -> %s" % ok)
        time.sleep(2.0)
        ui.clear_modals()
    log("演示=%s" % ui.is_demo)

    # 前置检查：空队列时 open_by_combo_demo 必失败（软件“+”依赖非空队列）
    chan_probe = dd._main_child("通道1")
    n_rows = dd._combo_channel_rows(chan_probe) if chan_probe is not None else -1
    if n_rows == 0:
        log("!! 通道队列为空：本软件“+”添加在空队列下必报「输入错误」，"
            "无法自动建队（软件约束，见 driver_direct.open_by_combo_demo 注释）。"
            "真实测量时 runner 会先建条目，不受影响。本次验证到此为止。")
        return 5
    log("通道队列 %d 条" % n_rows)

    pnl = dd.open_by_combo_demo("step")
    if pnl is None:
        log("!! open_by_combo_demo 失败，现场排查：")
        try:
            names = []
            for c in ui.descendants():
                ei = c.element_info
                if (ei.name or "").strip() and ei.control_type in (
                        "Window", "Pane", "Custom", "Dialog"):
                    names.append("%s|%s" % (ei.control_type, ei.name.strip()))
            log("主窗内窗式控件：%s" % "; ".join(names[:40] or ["（无）"]))
        except Exception as e:
            log("排查失败：%s" % e)
        return 3
    try:
        ei = pnl.element_info
        log("参数窗：%r  顶层 aid=%r  control_type=%s"
            % (ei.name, ei.automation_id, ei.control_type))
    except Exception:
        pass

    # 试写关键参数（不点确定）：写 → 读回核对
    checks = [
        ("PotSquare_InitialE_txt", "-0.2"),
        ("PotSquare_InitTime_txt", "2"),
        ("PotSquare_FinalE_txt", "0.5"),
        ("PotSquare_FinalTime_txt", "2"),
        ("PotSquare_Cycles_txt", "20"),
    ]
    good = 0
    for aid, want in checks:
        try:
            ui.set_edit(aid, want, pnl)
            got = str(ui.by_id(aid, pnl).get_value() or "")
            okflag = want in got
        except Exception as e:
            got, okflag = "ERR:%s" % e, False
        log("  %s -> want=%s got=%r %s" % (aid, want, got, "OK" if okflag else "FAIL"))
        good += 1 if okflag else 0
    log("写入核对：%d/%d 通过" % (good, len(checks)))

    # 取消关窗
    try:
        for c in pnl.descendants(control_type="Button"):
            if (c.element_info.automation_id or "") == "PotSquare_Cancel_Btn":
                c.click_input()
                log("已点取消")
                break
    except Exception as e:
        log("点取消失败：%s" % e)
    time.sleep(1.0)
    return 0 if good == len(checks) else 4


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
    finally:
        kill6()
        with open(PROBE_DIR + r"\verify.log", "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        print("EXIT=%s" % rc)
