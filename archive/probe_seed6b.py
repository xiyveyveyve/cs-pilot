# -*- coding: utf-8 -*-
"""probe_seed6b.py —— A1-seed 第三轮：验证「两个通道窗」假设并种子队列。

假设（由 p107_addeis 成功史 + 输入错误正文推导）：
    演示模式里有两个同题名 MDI 窗：
      A. 组合方法(B)→组合测试 的窗：工具栏 [新建,打开,+,停止,编辑,-,删除,…]
         空队列点 “+” → 「输入错误：请至少选择一种测试方法!」
      B. 工作通道(C)→通道1 的序列窗（frmMultiExp）：工具栏 [加载方案,保存方案,
         开始,停止,添加,修改,移除,清空,…]（SEQ_BTN 映射），添加@4 从空队列也能加。
本探针：
    0) dump 两个窗的 toolStrip1 按钮全套属性（help_text/Name/legacy）钉死映射
    1) 在 B 窗 add_experiment('ocp') → 看 listViewTest 行数
    2) 回 A 窗（组合测试）看队列行数是否同步
    3) 若 B 也报「输入错误」：dump 「快速实验定制」（主工具栏 index 9）找方法选择处
    4) 兜底：空列表右键上下文菜单 dump
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
OUTDIR = r"D:\deepseek\_probe\seed6"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "run_b.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def kill_cs():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                   capture_output=True)
    time.sleep(1.5)


def close_settings(ui):
    n = 0
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
            n += 1
        except Exception:
            break
        time.sleep(0.5)
    if n:
        log("关掉 %d 个挡路窗" % n)
    ui.clear_modals(3)
    return n


def find_chan(ui, exclude=None):
    """找标题形如 通道N【型号…】 的 MDI 窗，可排除一个已知的。"""
    hits = []
    try:
        for c in ui.main.descendants(control_type="Window"):
            t = c.window_text() or ""
            if t.startswith("通道") and "型号" in t:
                if exclude is not None and t == exclude:
                    continue
                hits.append((t, c))
    except Exception:
        pass
    return hits


def dump_toolbar_buttons(ui, root, tag):
    """把 root 里的每个 toolStrip1 的按钮属性全 dump 出来。"""
    out = []
    try:
        for tb in root.descendants(control_type="ToolBar"):
            aid = tb.element_info.automation_id or ""
            r = tb.rectangle()
            btns = [c for c in tb.descendants(control_type="Button")]
            log("[%s] toolStrip=%s top=%d 按钮数=%d" % (tag, aid, r.top, len(btns)))
            for i, b in enumerate(btns):
                ei = b.element_info
                help_t = ""
                try:
                    help_t = ei.help_text or ""
                except Exception:
                    pass
                legacy = ""
                try:
                    legacy = str((b.legacy_properties() or {}).get("Value", ""))[:20]
                except Exception:
                    pass
                rec = {"i": i, "aid": ei.automation_id or "", "name": b.window_text() or "",
                       "help": help_t, "legacy": legacy}
                out.append(rec)
                log("   [%2d] name=%r help=%r legacy=%r" % (i, rec["name"], help_t, legacy))
    except Exception as e:
        log("dump 工具栏异常：%s" % e)
    with open(os.path.join(OUTDIR, "toolbar_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def main():
    verdict = "failed"
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
        close_settings(ui)
        if not ui.is_demo:
            ok = ui.click_menu("%s", "进入演示模式")
            log("进入演示模式 -> %s" % ok)
            time.sleep(2.0)
            close_settings(ui)
        log("主窗=%r 演示=%s" % (ui.title, ui.is_demo))
        base = D6.ParasiteDriver(ui, log)

        # ---- B 窗：工作通道(C) → 通道1 ----
        log("")
        log("=== B 窗：工作通道(C) → 通道 1 ===")
        if ui.open_menu("%c"):
            time.sleep(0.5)
            items = [(t, r.top) for t, _c, r in ui.menu_items()]
            log("工作通道菜单项：%r" % [t for t, _ in items])
            try:
                from pywinauto.keyboard import send_keys as _sk
                _sk("{ESC}")
            except Exception:
                pass
        got = base.ensure_channel()
        log("ensure_channel -> %s 通道=%r" % (got, base.channel_title))
        if not got:
            verdict = "no-channel-window"
            return 1
        time.sleep(1.0)
        chanB = None
        for t, c in find_chan(ui):
            if t == base.channel_title:
                chanB = c
                break
        if chanB is not None:
            dump_toolbar_buttons(ui, chanB, "chanB_seq")
            base.activate()
            rows_b = base.read_sequence()
            log("B 窗序列行数：%d %r" % (len(rows_b), base.rows_desc()))

            log("add_experiment('OCP') …")
            panel = base.add_experiment(D6.EXP_OCP)
            log("  -> %r" % (panel.window_text() if panel else None,))
            if panel is not None:
                ui.press_cancel(panel)
                time.sleep(0.8)
            rows_b2 = base.read_sequence()
            log("B 窗添加后行数：%d %r" % (len(rows_b2), base.rows_desc()))

        # ---- A 窗：组合方法(B) → 组合测试 ----
        log("")
        log("=== A 窗：组合测试 ===")
        if not ui.click_menu("%b", "组合测试"):
            log("组合测试点不开")
        time.sleep(2.5)
        chanA = None
        for t, c in find_chan(ui):
            chanA = c
            if chanB is None or (c.element_info.runtime_id != chanB.element_info.runtime_id
                                 if chanB is not None else True):
                pass
        log("组合测试后可见通道窗：%r" % [t for t, _c in find_chan(ui)])
        # 数每个窗的行
        for t, c in find_chan(ui):
            n = 0
            try:
                for cc in c.descendants(control_type="ListItem"):
                    if (cc.window_text() or "").strip().isdigit():
                        n += 1
            except Exception:
                pass
            lv = None
            try:
                for cc in c.descendants():
                    if (cc.element_info.automation_id or "") == "listViewTest":
                        lv = cc
                        break
            except Exception:
                pass
            log("窗 %r：数字行=%d listViewTest=%s" % (t, n, "有" if lv is not None else "无"))
            if c.element_info.runtime_id != (chanB.element_info.runtime_id if chanB else None):
                dump_toolbar_buttons(ui, c, "chanA_combo")

        # ---- 兜底：空列表右键菜单 ----
        if base.read_sequence() == 0:
            log("")
            log("=== 兜底：空列表右键 ===")
            try:
                base.activate()
                lv = None
                for cc in ui.descendants():
                    if (cc.element_info.automation_id or "") == "listViewTest":
                        lv = cc
                        break
                if lv is not None:
                    r = lv.rectangle()
                    from pywinauto import mouse as _m
                    _m.right_click(coords=(r.left + 120, r.top + 40))
                    time.sleep(1.2)
                    items = [(t) for t, _c, _r in ui.menu_items()]
                    log("右键菜单：%r" % items)
                    from pywinauto.keyboard import send_keys as _sk
                    _sk("{ESC}")
            except Exception as e:
                log("右键异常：%s" % e)
        if base.read_sequence():
            verdict = "seeded-via-sequence-channel"
        elif any("输入错误" in ln for ln in _lines):
            verdict = "input-error-both-windows"
        else:
            verdict = "unclear"
    finally:
        try:
            kill_cs()
        except Exception:
            pass
        flush_log()

    log("")
    log("VERDICT: %s" % verdict)
    print("VERDICT: %s" % verdict)
    return 0


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
