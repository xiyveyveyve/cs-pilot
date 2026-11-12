# -*- coding: utf-8 -*-
"""probe_step6_combo2.py —— 全局窗口枚举版。

上一版教训：ui.panels() 从**主窗 descendants** 里找 Window，
而「添加」这类 owned 弹窗可能不是主窗的 UIA 后代 → 永远找不到。
本版改用 Desktop(backend="uia").windows() 全局枚举所有顶层窗。

流程：
  1. 演示模式 → 组合测试 → 通道窗
  2. 停掉可能在跑的测量（工具栏 index 3）
  3. 试点「编辑」(index 4) —— 验证 编辑→参数窗 路径（顺带拿 frmOCP 表）
  4. 点「+」(index 2) → 全局快照找「添加」→ 下拉选阶梯波 → 确认
     → 「提示」点「扩展(Y)」→ 等阶梯波参数窗 → dump
"""

import json
import os
import subprocess
import sys
import time

from pywinauto import Desktop, mouse
from pywinauto.keyboard import send_keys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUTDIR = r"D:\deepseek\_probe\step6_combo"
os.makedirs(OUTDIR, exist_ok=True)

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def global_wins():
    """全部可见顶层窗 [(title, wrapper)]，UIA 全局桌面枚举。"""
    out = []
    try:
        for w in Desktop(backend="uia").windows():
            try:
                t = (w.window_text() or "").strip()
                if t:
                    out.append((t, w))
            except Exception:
                continue
    except Exception as e:
        log("  全局枚举失败：%s" % e)
    return out


def gfind(substr, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for t, w in global_wins():
            if substr in t:
                return t, w
        time.sleep(0.3)
    return None, None


UI = [None]  # main wrapper 引用，供 find_in_main 用


def find_in_main(substr, timeout=3.0, types=("Window", "Pane", "Custom", "Dialog")):
    """在**主窗子树**里找名字含 substr 的窗式控件。

    关键教训：「用户设置」「添加」「提示」「通讯配置向导」全都不是
    顶层窗口（EnumWindows 看不见），而是主窗内部的 child 窗，
    control_type 多为 Pane/Custom —— 必须在主窗 descendants 里找。
    """
    ui = UI[0]
    if ui is None:
        return None, None
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for c in ui.main.descendants():
                ei = c.element_info
                t = (ei.name or "").strip()
                if substr in t and (ei.control_type in types):
                    return t, c
        except Exception:
            pass
        time.sleep(0.3)
    return None, None


def dump_panel(root, tag):
    rows = []
    try:
        ctrls = root.descendants()
    except Exception as e:
        log("  dump 失败：%s" % e)
        return rows
    for c in ctrls:
        try:
            info = c.element_info
            try:
                r = c.rectangle()
                rc = [r.left, r.top, r.right, r.bottom]
            except Exception:
                rc = None
            val = ""
            try:
                v = c.get_value()
                if v:
                    val = str(v)
            except Exception:
                if not val:
                    try:
                        val = c.window_text() or ""
                    except Exception:
                        val = ""
            rows.append({"aid": info.automation_id or "",
                         "name": (info.name or "").strip(),
                         "type": info.control_type or "",
                         "rect": rc, "value": val[:120]})
        except Exception:
            continue
    with open(os.path.join(OUTDIR, "dump_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    log("  控件 %d 个（有 aid 的 %d 个）→ dump_%s.json"
        % (len(rows), len([r for r in rows if r["aid"]]), tag))
    return rows


def shot(root, tag):
    try:
        p = os.path.join(OUTDIR, "shot_%s.png" % tag)
        root.capture_as_image().save(p)
        log("  截图 → %s" % p)
    except Exception as e:
        log("  截图失败：%s" % e)


def titles_now():
    return [t for t, _w in global_wins()]


def click_tb_button(tb, idx, tag):
    try:
        btns = list(tb.descendants(control_type="Button"))
    except Exception as e:
        log("  枚举工具栏按钮失败：%s" % e)
        return None
    if idx >= len(btns):
        log("  工具栏只有 %d 个按钮，没有 [%d]" % (len(btns), idx))
        return None
    b = btns[idx]
    try:
        b.click_input()
        log("  已点工具栏[%d]（%s）" % (idx, tag))
        return b
    except Exception as e:
        log("  click_input 失败：%s" % e)
        return None


def click_button(root, text):
    try:
        for c in root.descendants(control_type="Button"):
            if (c.window_text() or "").strip() == text:
                c.click_input()
                log("    已点「%s」" % text)
                return True
    except Exception as e:
        log("    点「%s」失败：%s" % (text, e))
    return False


def toggle_check(root, text):
    try:
        for c in root.descendants(control_type="CheckBox"):
            if text in (c.window_text() or ""):
                try:
                    if c.is_checked():
                        c.click_input()
                        log("    已取消勾选「%s」" % text)
                except Exception:
                    pass
                return
    except Exception:
        pass


def main():
    kill6()
    time.sleep(1.2)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(45):
        log("!! 没能连上主窗")
        return 2
    UI[0] = ui
    log("主窗：%r" % (ui.title,))
    time.sleep(1.5)
    ui.force_foreground()
    ui.clear_modals()

    def find_any(substr, timeout=3.0):
        t, w = find_in_main(substr, timeout=timeout * 0.7)
        if w is not None:
            return t, w
        return gfind(substr, timeout=timeout * 0.5)

    # 用户设置：它是主窗 child 窗，延迟弹出，必须反复关
    def dismiss_settings():
        n = 0
        for _ in range(3):
            t, usr = find_in_main("用户设置", timeout=0.8)
            if usr is None:
                break
            n += 1
            log("「用户设置」挡路，取消自动弹出并保存")
            toggle_check(usr, "在启动时显示窗口")
            if not click_button(usr, "保存"):
                click_button(usr, "退出")
            time.sleep(0.8)
        return n

    dismiss_settings()

    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进入演示模式 -> %s" % ok)
        time.sleep(2.0)
        ui.clear_modals()
    log("现在：%r  演示=%s" % (ui.title, ui.is_demo))

    ok = ui.click_menu("%b", "组合测试")
    log("打开「组合测试」 -> %s" % ok)
    time.sleep(2.5)

    chan = None
    for t, w in global_wins():
        if "通道" in t and "DEMOSN" in t:
            chan = w
            log("通道窗：%r" % (t,))
            break
    if chan is None:
        # MDI 子窗不在全局顶层列表里，从主窗 descendants 找
        try:
            for c in ui.main.descendants(control_type="Window"):
                t = (c.window_text() or "").strip()
                if "通道" in t:
                    chan = c
                    log("通道窗（MDI）：%r" % (t,))
                    break
        except Exception:
            pass
    if chan is None:
        log("!! 没找到通道窗")
        shot(ui.main, "no_chan")
        return 3

    tb = None
    for c in chan.descendants(control_type="ToolBar"):
        if (c.element_info.automation_id or "") == "toolStrip1":
            tb = c
            break
    if tb is None:
        log("!! 没拿到工具栏")
        return 4

    # ---- 2. 停掉可能在跑的测量 ----
    click_tb_button(tb, 3, "停止")
    time.sleep(1.0)
    dismiss_settings()
    t, tip = find_any("提示", timeout=1.0)
    if tip is not None:
        log("  「提示」弹出，点「确定」/「取消(Esc)」")
        if not click_button(tip, "取消(Esc)"):
            click_button(tip, "确定")
        time.sleep(0.8)
    dismiss_settings()

    # ---- 3. 试点「编辑」(index 4) ----
    log("=== 试「编辑」路径 ===")
    click_tb_button(tb, 4, "编辑")
    time.sleep(2.0)
    got = None
    for key in ("参数", "开路电位", "OCP"):
        t, w = find_any(key, timeout=1.2)
        if w is not None:
            got = (t, w)
            break
    if got is not None:
        t, w = got
        log("  「编辑」打开了：%r" % (t,))
        rows = dump_panel(w, "edit_ocp")
        shot(w, "edit_ocp")
        for r in rows:
            if r["aid"] and r["type"] in ("Edit", "ComboBox", "Button", "CheckBox"):
                log("    %-34s %-10s %-16s %s" % (r["aid"], r["type"],
                                                  (r["value"] or "")[:16], r["name"][:20]))
        click_button(w, "取消") or click_button(w, "退出") or click_button(w, "Cancel")
        time.sleep(1.0)
    else:
        log("  「编辑」没打开参数窗。")
        shot(ui.main, "edit_none")
    dismiss_settings()

    # ---- 4. 点「+」→ 找「添加」 ----
    log("=== 点「+」抓「添加」 ===")
    click_tb_button(tb, 2, "添加")
    time.sleep(1.5)
    t, dlg = find_any("添加", timeout=2.5)
    if dlg is None:
        # 主窗子树里列全部 Pane/Window/Custom 供辨认
        log("  没匹配到「添加」，主窗里的窗式控件：")
        try:
            for c in ui.main.descendants():
                ei = c.element_info
                if ei.control_type in ("Window", "Pane", "Custom") and (ei.name or "").strip():
                    t2 = ei.name.strip()
                    if t2 == ui.title:
                        continue
                    try:
                        r = c.rectangle()
                        log("    %-14s %r rect=(%d,%d,%d,%d)"
                            % (ei.control_type, t2, r.left, r.top, r.right, r.bottom))
                    except Exception:
                        log("    %-14s %r" % (ei.control_type, t2))
        except Exception:
            pass
        # 试常见别名
        for key in ("选择", "测量方法", "控制指令", "方法"):
            t, dlg = find_any(key, timeout=1.0)
            if dlg is not None:
                log("  用别名 %r 命中：%r" % (key, t))
                break
    if dlg is None:
        log("!! 找不到「添加」类对话框")
        shot(ui.main, "no_add")
        return 5
    log("「添加」对话框：%r" % (t,))
    dlg_rows = dump_panel(dlg, "add_dlg")
    for r in dlg_rows:
        if r["aid"] or r["name"]:
            log("    %-34s %-12s %-18s %s" % (r["aid"], r["type"],
                                              (r["value"] or "")[:18], r["name"][:24]))
    shot(dlg, "add_dlg")

    # 选「任意恒电位阶梯波(多电位阶跃)」
    WANT = "任意恒电位阶梯波(多电位阶跃)"
    combo = None
    try:
        for c in dlg.descendants(control_type="ComboBox"):
            combo = c
            break
    except Exception:
        pass
    if combo is not None:
        log("选方法：%r" % (WANT,))
        done = False
        try:
            combo.select(WANT)
            done = True
            log("  select() 成功")
        except Exception as e:
            log("  select() 失败：%s" % e)
        if not done:
            try:
                combo.click()
                time.sleep(0.8)
                li = None
                for c in Desktop(backend="uia").windows():
                    pass
                for c in dlg.descendants(control_type="ListItem"):
                    if WANT in (c.window_text() or ""):
                        li = c
                        break
                if li is None:
                    # 下拉列表可能是全局弹出窗
                    for t2, w2 in global_wins():
                        try:
                            for c in w2.descendants(control_type="ListItem"):
                                if WANT in (c.window_text() or ""):
                                    li = c
                                    break
                            if li:
                                break
                        except Exception:
                            continue
                if li is not None:
                    r = li.rectangle()
                    mouse.click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
                    done = True
                    log("  下拉点选成功")
                else:
                    send_keys("{ESC}")
                    log("  下拉里没找到目标项")
            except Exception as e:
                log("  下拉点选失败：%s" % e)
                try:
                    send_keys("{ESC}")
                except Exception:
                    pass
        if not done:
            try:
                combo.set_edit_text(WANT)
                log("  set_edit_text 成功")
            except Exception as e:
                log("  set_edit_text 失败：%s" % e)
        try:
            log("  当前值：%r" % (combo.selected_text(),))
        except Exception:
            pass
    else:
        log("!! 没找到 ComboBox，先只点确认试试")

    # 确认：优先具名按钮，否则回车
    okb = None
    for r in dlg_rows:
        if r["type"] == "Button" and (r["aid"] in ("btnOK", "buttonOk", "btnOk")
                                      or r["name"] in ("确定", "添加", "OK")):
            okb = r
            break
    if okb is not None:
        r = okb["rect"]
        mouse.click(coords=((r[0] + r[2]) // 2, (r[1] + r[3]) // 2))
        log("  点确认按钮 %s" % (okb["aid"] or okb["name"],))
    else:
        send_keys("{ENTER}")
        log("  没有具名确认按钮，发回车")

    # 打地鼠：提示→扩展(Y)；等参数窗
    panel = None
    for i in range(6):
        t, tip = find_any("提示", timeout=1.0)
        if tip is not None:
            log("  [第 %d 轮]「提示」，点「扩展(Y)」" % (i + 1))
            click_button(tip, "扩展(Y)")
            time.sleep(1.2)
        for key in ("阶梯波", "恒电位"):
            t, w = find_any(key, timeout=0.8)
            if w is not None:
                panel = (t, w)
                break
        if panel:
            break
        time.sleep(0.8)
    if panel is None:
        log("!! 没等到参数窗。顶层窗：%r" % (titles_now(),))
        shot(ui.main, "no_panel")
        return 8
    t, panel = panel
    log("参数窗出现：%r" % (t,))
    rows = dump_panel(panel, "pot_square")
    shot(panel, "pot_square")

    aids = {r["aid"] for r in rows if r["aid"]}
    log("")
    log("=== 对照 runner6.py（5 版抄来的）控件表 ===")
    expect = ["Control_FileName_Text", "PotSquare_TimeUnit_cbo", "Vs_Combo",
              "PotSquare_InitialE_txt", "PotSquare_InitTime_txt",
              "PotSquare_FinalE_txt", "PotSquare_FinalTime_txt",
              "PotSquare_Cycles_txt", "FrqControl_Frq_Radio", "FrqControl_Frq_Text"]
    for e in expect:
        log("  %-28s %s" % (e, "命中" if e in aids else "** 未命中 **"))
    hits = [a for a in sorted(aids) if a.startswith("PotSquare_Step") and a.endswith("_chb")]
    log("  中间电位开关：%s" % (", ".join(hits) if hits else "** 无 **"))
    log("")
    log("=== 参数窗全部带 aid 的控件 ===")
    for r in rows:
        if r["aid"]:
            log("    %-38s %-12s %-16s %s" % (r["aid"], r["type"],
                                              (r["value"] or "")[:16], r["name"][:24]))
    return 0


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
    finally:
        log("清理 taskkill")
        try:
            kill6()
        except Exception:
            pass
        with open(os.path.join(OUTDIR, "run.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        log("EXIT=%s" % rc)
