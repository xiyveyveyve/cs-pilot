# -*- coding: utf-8 -*-
"""probe_dump6_all.py —— A1-dump：演示模式下把 4 种实验参数窗的控件表全部抓下来。

前提：组合测试通道队列非空（A1-seed 已解决）。
路径（每个实验类型重复）：组合测试 → “+” → 「添加」→ 选类型 → 确定
    → （提示：文件重复 → 扩展）→ 参数窗 → dump 全控件 → 取消。

产出：D:\\deepseek\\_probe\\dump6_all\\{kind}.json + {kind}.png + summary.md
"""

import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUTDIR = r"D:\deepseek\_probe\dump6_all"
KINDS = [D6.EXP_OCP, D6.EXP_TAFEL, D6.EXP_EIS, D6.EXP_STEP]

TITLE_KEY = {
    D6.EXP_OCP: "开路电位",
    D6.EXP_TAFEL: "动电位",
    D6.EXP_EIS: "频率扫描",
    D6.EXP_STEP: "任意恒电位阶梯波",
}

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "run.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def kill_cs():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                   capture_output=True)
    time.sleep(1.5)


def dump_panel(panel, path_base):
    rows = []
    for c in panel.descendants():
        try:
            ei = c.element_info
            val = ""
            try:
                val = c.get_value() or ""
            except Exception:
                val = c.window_text() or ""
            rect = None
            try:
                r = c.rectangle()
                rect = [r.left, r.top, r.right, r.bottom]
            except Exception:
                pass
            rows.append({"aid": ei.automation_id or "", "type": ei.control_type,
                         "name": (c.window_text() or "")[:40], "value": str(val)[:80],
                         "rect": rect})
        except Exception:
            continue
    with open(path_base + ".json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    try:
        panel.set_focus()
        time.sleep(0.3)
        img = panel.capture_as_image()
        img.save(path_base + ".png")
    except Exception as e:
        log("  截图失败：%s" % e)
    n_aid = sum(1 for r in rows if r["aid"])
    log("  dump %s：%d 控件 / %d 带 aid" % (os.path.basename(path_base), len(rows), n_aid))
    return rows


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    summary = []
    kill_cs()
    log("启动 6 版")
    subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            log("!! 40s 没等到主窗")
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        ui.clear_modals(4)
        if not ui.is_demo:
            ok = ui.click_menu("%s", "进入演示模式")
            log("进入演示模式 -> %s" % ok)
            time.sleep(2.0)
            ui.clear_modals(4)
        log("主窗=%r 演示=%s" % (ui.title, ui.is_demo))

        base = D6.ParasiteDriver(ui, log)

        if not ui.click_menu("%b", "组合测试"):
            log("组合测试点不开")
            return 2
        time.sleep(2.5)
        chan = None
        for c in ui.main.descendants(control_type="Window"):
            if "通道" in (c.window_text() or ""):
                chan = c
                break
        if chan is None:
            log("没找到通道窗")
            return 2
        rows = sum(1 for c in chan.descendants(control_type="ListItem")
                   if (c.window_text() or "").strip().isdigit())
        log("队列行数：%d" % rows)
        if rows == 0:
            log("!! 队列还是空的，先跑 probe_seed6.py")
            return 3

        tb = None
        for c in chan.descendants(control_type="ToolBar"):
            if (c.element_info.automation_id or "") == "toolStrip1":
                tb = c
                break
        if tb is None:
            log("没有 toolStrip1")
            return 2

        for kind in KINDS:
            log("")
            log("=== %s ===" % kind)
            added = add_via_plus(ui, base, tb, chan, kind)
            if added is None:
                summary.append((kind, "FAIL", "加不上/窗没开"))
                ui.clear_modals(3)
                continue
            key = TITLE_KEY[kind]
            pnl = None
            for _ in range(10):
                pnl = ui.window_titled(key)
                if pnl is not None:
                    break
                time.sleep(0.5)
            if pnl is None:
                log("  参数窗（%s）没出现" % key)
                summary.append((kind, "FAIL", "参数窗没出现"))
                ui.clear_modals(3)
                continue
            log("  参数窗：%r" % (pnl.window_text(),))
            rows_ = dump_panel(pnl, os.path.join(OUTDIR, kind))
            n_edit = sum(1 for r in rows_ if r["type"] == "Edit")
            n_combo = sum(1 for r in rows_ if r["type"] == "ComboBox")
            n_chk = sum(1 for r in rows_ if r["type"] == "CheckBox")
            summary.append((kind, "OK",
                            "%s | %d 控件(%d带aid) %d Edit %d Combo %d Chk"
                            % (pnl.window_text(), len(rows_), n_aid := sum(1 for r in rows_ if r["aid"]),
                               n_edit, n_combo, n_chk)))
            # 收尾：取消参数窗（不写任何数据）
            try:
                ui.press_cancel(pnl)
            except Exception:
                pass
            time.sleep(1.0)
            ui.clear_modals(3)

        # 额外：开一次 OCP 参数窗，把「电解池」子窗也 dump 了
        log("")
        log("=== 电解池子窗（借 OCP 参数窗） ===")
        try:
            pnl = None
            for c in ui.main.descendants(control_type="Window"):
                if "开路电位" in (c.window_text() or ""):
                    pnl = c
                    break
            if pnl is None:
                added = add_via_plus(ui, base, tb, chan, D6.EXP_OCP)
                for _ in range(10):
                    pnl = ui.window_titled("开路电位")
                    if pnl is not None:
                        break
                    time.sleep(0.5)
            if pnl is not None:
                btn = ui.by_id("Btn_Cell", pnl)
                if btn is not None:
                    btn.click_input()
                    time.sleep(1.5)
                    cell = None
                    for t, c in ui.panels():
                        if "电极" in t or "电解池" in t:
                            cell = c
                            break
                    if cell is not None:
                        dump_panel(cell, os.path.join(OUTDIR, "cell"))
                        summary.append(("cell", "OK", cell.window_text()))
                        ui.press_cancel(cell)
                        time.sleep(0.8)
                    else:
                        summary.append(("cell", "FAIL", "电解池窗没出现"))
                else:
                    summary.append(("cell", "FAIL", "OCP 窗里没有 Btn_Cell"))
                ui.press_cancel(pnl)
        except Exception as e:
            log("电解池 dump 异常：%s" % e)
    finally:
        try:
            kill_cs()
        except Exception:
            pass
        flush_log()

    log("")
    log("=== 汇总 ===")
    with open(os.path.join(OUTDIR, "summary.md"), "w", encoding="utf-8") as f:
        f.write("# 6 版参数窗控件表普查 · 2026-11-06\n\n| 类型 | 结果 | 说明 |\n|---|---|---|\n")
        for k, st, msg in summary:
            f.write("| %s | %s | %s |\n" % (k, st, msg))
            log("%-6s %s  %s" % (k, st, msg))
    ok_n = sum(1 for _k, st, _m in summary if st == "OK")
    print("DONE %d/%d" % (ok_n, len(summary)))
    return 0 if ok_n >= 4 else 1


def add_via_plus(ui, base, tb, chan, kind):
    """点 “+” → 「添加」→ 选 kind → 确定。返回是否看到参数窗标题出现。"""
    def row_count():
        try:
            return sum(1 for c in chan.descendants(control_type="ListItem")
                       if (c.window_text() or "").strip().isdigit())
        except Exception:
            return -1

    before_rows = row_count()
    try:
        btns = list(tb.descendants(control_type="Button"))
        btns[2].click_input()
    except Exception as e:
        log("  点“+”失败：%s" % e)
        return None
    time.sleep(1.5)

    dlg = None
    for _ in range(8):
        # 打地鼠：文件重复提示 / 输入错误 / 添加
        tip = ui.window_titled("提示")
        if tip is not None:
            try:
                b = ui.button_prefix("扩展", tip) or ui.button_prefix("覆盖", tip)
                if b is not None:
                    b.click_input()
                    log("  提示框：点了扩展/覆盖")
                    time.sleep(0.8)
                    continue
            except Exception:
                pass
            ui.clear_modals(2)
        err = ui.window_titled("输入错误")
        if err is not None:
            log("  「输入错误」弹出（正文见日志）")
            for _h, t, _r in S.Studio.win32_modal_dialogs():
                log("    win32: [%s] %r" % (t, S.Studio.dialog_text(_h)[:100]))
            ui.clear_modals(2)
            return None
        dlg = ui.window_titled("添加")
        if dlg is not None:
            break
        time.sleep(0.6)
    if dlg is None:
        log("  「添加」没出现")
        return None

    # 选类型
    try:
        for c in dlg.descendants():
            try:
                ei = c.element_info
                if ei.control_type == "RadioButton" and "测量方法" in (c.window_text() or ""):
                    c.click_input()
                    break
            except Exception:
                continue
        if not base.pick_experiment(dlg, kind):
            log("  选类型失败：%s" % D6.EXP_COMBO_TEXT[kind])
            ui.press_cancel(dlg)
            return None
    except Exception as e:
        log("  选类型异常：%s" % e)
        ui.press_cancel(dlg)
        return None

    # 收浮层 + 确定
    try:
        from pywinauto import mouse as _m
        rc = dlg.rectangle()
        _m.click(coords=((rc.left + rc.right) // 2, rc.top + 12))
        time.sleep(0.5)
    except Exception:
        pass
    okbtn = ui.by_id("buttonOK", dlg) or ui.button("确定", dlg)
    if okbtn is None:
        log("  「添加」没有确定键")
        return None
    try:
        okbtn.click_input()
    except Exception as e:
        log("  点确定异常：%s" % e)
    time.sleep(2.2)
    ui.clear_modals(2)
    log("  行数 %d → %d" % (before_rows, row_count()))
    return True


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
