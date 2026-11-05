# -*- coding: utf-8 -*-
"""probe_seed6.py —— A1-seed：解决演示模式组合测试通道「空队列」无法添加条目的问题。

背景（2026-11-05 上一会话结论）：
    组合测试通道队列被清空后，点“+”报「输入错误」，无法从零建队。
    但当时没有区分两种假设：
      H1: “+”按钮本身依赖非空队列（软件约束，无解）
      H2: 「添加」对话框里 cboExp 无默认选中，点确定才报「输入错误」
    本探针用高时间分辨率观察把这个问题钉死，并尝试三条种子路径。

路径：
    P1 演示模式：组合测试 → “+” → （若弹「添加」）选类型 → 确定 → 看行数
    P2 非演示模式：工作通道(C) → 通道1 → 序列工具栏「添加」→ add_experiment("ocp")
       （序列与组合测试队列若是同一份持久化数据，这里加完演示模式就有了）
    P3 兜底观察：右键上下文菜单 / 快速实验定制（只记录，不深入）

安全：全程演示模式或无设备状态，不写数据文件，结束时清干净退出。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver as D6

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\seed6\run.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def flush_log():
    import os
    os.makedirs(r"D:\deepseek\_probe\seed6", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


def kill_cs():
    subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe", "/T"],
                   capture_output=True)
    time.sleep(1.5)


def win_titles(ui):
    """主窗 UIA 树里所有 Window 控件的标题 + 全局 #32770 模态框标题。"""
    uiw = set()
    try:
        for c in ui.main.descendants(control_type="Window"):
            t = (c.window_text() or "").strip()
            if t:
                uiw.add(t)
    except Exception:
        pass
    for _h, t, _r in S.Studio.win32_modal_dialogs():
        uiw.add("[win32] " + t)
    return uiw


def close_settings(ui):
    """关掉「用户设置」挡路窗（UIA 子窗，clear_modals 管不了它）。"""
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
        log("关掉 %d 个挡路窗（用户设置/向导）" % n)
    ui.clear_modals(3)
    return n


def main():
    verdict = "failed"
    detail = {}
    kill_cs()
    log("启动 6 版")
    p = subprocess.Popen([EXE6])
    try:
        ui = S.Studio(log=log)
        if not ui.acquire(40):
            log("!! 40s 没等到主窗")
            return 2
        time.sleep(1.5)
        ui.force_foreground()
        ui.clear_modals(4)
        log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))

        # ---- 进演示模式 ----
        if not ui.is_demo:
            ok = ui.click_menu("%s", "进入演示模式")
            log("进入演示模式 -> %s" % ok)
            time.sleep(2.0)
            ui.clear_modals(4)
            log("现在：主窗=%r 演示=%s" % (ui.title, ui.is_demo))
            if not ui.is_demo:
                log("!! 进不了演示模式，转非演示路径")

        # ---- P1：演示模式组合测试 + “+” ----
        base = D6.ParasiteDriver(ui, log)
        close_settings(ui)
        rows = seed_via_demo_plus(ui, base, detail)
        if rows > 0:
            verdict = "seeded-via-demo-plus" if not detail.get("already") else "already-nonempty"
            log("P1 成功：队列 %d 行" % rows)
        else:
            log("P1 未成功，转 P2（非演示 + 序列添加）")

            # ---- P2：非演示模式，工作通道 → 序列添加 ----
            close_settings(ui)
            try:
                ok = ui.click_menu("%s", "退出演示模式")
                log("退出演示模式 -> %s" % ok)
                time.sleep(2.0)
                ui.clear_modals(4)
                close_settings(ui)
                if base.ensure_channel():
                    log("通道窗：%r" % base.channel_title)
                    base.activate()
                    panel = base.add_experiment("ocp")
                    log("add_experiment('ocp') -> %r" % (panel.window_text() if panel else None,))
                    if panel is not None:
                        base.ui.press_cancel(panel)   # 不填参数，只留条目
                        time.sleep(0.8)
                    rows2 = len(base.read_sequence())
                    log("非演示序列行数：%d 行内容=%r" % (rows2, base.rows_desc()))
                    if rows2 > 0:
                        log("P2 种上了，回演示模式验证队列")
                        ok = ui.click_menu("%s", "进入演示模式")
                        log("再进演示模式 -> %s" % ok)
                        time.sleep(2.0)
                        ui.clear_modals(4)
                        close_settings(ui)
                        rows3 = seed_via_demo_plus(ui, base, detail, observe_only=True)
                        if rows3 > 0:
                            verdict = "seeded-via-sequence"
                            log("P2 验证成功：演示模式队列 %d 行" % rows3)
                        else:
                            verdict = "seeded-sequence-but-demo-empty"
                    else:
                        detail["p2"] = "序列添加后仍 0 行"
                else:
                    detail["p2"] = "ensure_channel 失败（工作通道菜单点不开）"
                    # 留证：工作通道菜单里到底有什么
                    if ui.open_menu("%c"):
                        time.sleep(0.5)
                        items = [t for t, _c, _r in ui.menu_items()]
                        log("工作通道菜单项：%r" % items)
                        try:
                            from pywinauto.keyboard import send_keys as _sk
                            _sk("{ESC}")
                        except Exception:
                            pass
            except Exception:
                import traceback
                log("P2 异常：\n%s" % traceback.format_exc())
    finally:
        try:
            log("清场：taskkill")
            kill_cs()
        except Exception:
            pass
        flush_log()

    log("")
    log("VERDICT: %s  detail=%r" % (verdict, detail))
    flush_log()
    print("VERDICT: %s" % verdict)
    return 0


def seed_via_demo_plus(ui, base, detail, observe_only=False):
    """演示模式：打开组合测试，数行数；空则点“+”并高分辨率观察。

    返回最终行数。detail 收集过程情报。
    """
    if not ui.click_menu("%b", "组合测试"):
        log("组合方法(B)→组合测试 点不开")
        return 0
    time.sleep(2.5)

    chan = None
    for c in ui.main.descendants(control_type="Window"):
        if "通道" in (c.window_text() or ""):
            chan = c
            break
    if chan is None:
        log("没找到通道窗")
        return 0
    log("通道窗：%r" % (chan.window_text(),))

    def row_count():
        n = 0
        try:
            for c in chan.descendants(control_type="ListItem"):
                if (c.window_text() or "").strip().isdigit():
                    n += 1
        except Exception:
            pass
        return n

    rows = row_count()
    log("当前队列行数：%d" % rows)
    if rows > 0:
        detail["already"] = True
        return rows
    if observe_only:
        return 0

    tb = None
    for c in chan.descendants(control_type="ToolBar"):
        if (c.element_info.automation_id or "") == "toolStrip1":
            tb = c
            break
    if tb is None:
        log("通道窗里没有 toolStrip1")
        return 0
    btns = list(tb.descendants(control_type="Button"))
    log("工具栏按钮数：%d" % len(btns))
    if len(btns) < 3:
        return 0

    # 点 “+”，0.5s 分辨率观察 12s
    before = win_titles(ui)
    close_settings(ui)
    before = win_titles(ui)
    log("点“+”前窗口：%r" % sorted(before))
    try:
        btns[2].click_input()
    except Exception as e:
        log("点“+”异常：%s" % e)
        return 0

    add_dlg = None
    seen = set(before)
    for i in range(24):
        time.sleep(0.5)
        now = win_titles(ui)
        new = now - seen
        for t in sorted(new):
            log("  +%.1fs 新窗口：%r" % ((i + 1) * 0.5, t))
        seen |= new
        # 「添加」出现了？
        for t in now:
            if t == "添加" or ("添加" in t and "win32" not in t):
                try:
                    add_dlg = ui.window_titled("添加")
                except Exception:
                    add_dlg = None
        if add_dlg is not None:
            break
    if add_dlg is None:
        # 可能是 win32 模态「输入错误」：读正文留证
        for _h, t, _r in S.Studio.win32_modal_dialogs():
            body = S.Studio.dialog_text(_h)
            log("win32 模态：[%s] 正文=%r" % (t, body[:120]))
            detail["plus_dialog"] = "%s: %s" % (t, body[:80])
        ui.clear_modals(3)
        log("“+”后 12s 没等到「添加」对话框（H1 成立的可能大）")
        return row_count()

    # H2 路线：「添加」开着，cboExp 是空的 → 用 pick_experiment 选开路电位
    log("「添加」出现了！dump 控件并尝试选择类型")
    dump_add(add_dlg)
    rb_ok = False
    try:
        for c in add_dlg.descendants():
            try:
                ei = c.element_info
                if ei.control_type == "RadioButton" and "测量方法" in (c.window_text() or ""):
                    c.click_input()
                    rb_ok = True
                    break
            except Exception:
                continue
    except Exception:
        pass
    log("点「测量方法」radio -> %s" % rb_ok)
    try:
        ok = base.pick_experiment(add_dlg, "ocp")
    except Exception as e:
        ok = False
        log("pick_experiment 异常：%s" % e)
    log("pick_experiment('ocp') -> %s" % ok)
    if not ok:
        ui.press_cancel(add_dlg)
        return row_count()
    # 收浮层 + 确定
    try:
        from pywinauto import mouse as _m
        rc = add_dlg.rectangle()
        _m.click(coords=((rc.left + rc.right) // 2, rc.top + 12))
        time.sleep(0.5)
    except Exception:
        pass
    okbtn = ui.by_id("buttonOK", add_dlg) or ui.button("确定", add_dlg)
    if okbtn is not None:
        try:
            okbtn.click_input()
        except Exception as e:
            log("点确定异常：%s" % e)
    time.sleep(2.0)
    ui.clear_modals(3)
    rows = row_count()
    log("确定后行数：%d" % rows)
    pnl = ui.window_titled("开路电位")
    log("参数窗：%r" % (pnl.window_text() if pnl else None,))
    if pnl is not None:
        ui.press_cancel(pnl)
        time.sleep(0.6)
    return rows


def dump_add(dlg):
    rows = []
    try:
        for c in dlg.descendants():
            try:
                ei = c.element_info
                val = ""
                try:
                    val = c.get_value() or ""
                except Exception:
                    val = (c.window_text() or "")
                rows.append({"aid": ei.automation_id or "", "type": ei.control_type,
                             "name": c.window_text() or "", "value": str(val)[:60]})
            except Exception:
                continue
    except Exception:
        pass
    import json as _json
    import os
    os.makedirs(r"D:\deepseek\_probe\seed6", exist_ok=True)
    with open(r"D:\deepseek\_probe\seed6\dump_add_empty.json", "w", encoding="utf-8") as f:
        _json.dump(rows, f, ensure_ascii=False, indent=1)
    for r in rows:
        log("  %s | %s | %s | val=%r" % (r["aid"], r["type"], r["name"][:20], r["value"][:40]))


if __name__ == "__main__":
    rc = main()
    flush_log()
    sys.exit(rc)
