# -*- coding: utf-8 -*-
"""probe_step6_combo.py —— 用户指的路（m00722/m00725 截图）：

    6 版【演示模式】→ 组合方法(B) → 组合测试
    → 出现「通道1 [型号： DEMOSN in Demo]」MDI 窗
    → 点通道窗工具栏的“+”号 → 「添加」对话框
    → 下拉框选「任意恒电位阶梯波(多电位阶跃)」→ 确定
    → 弹出和真实测试**一模一样**的参数窗

这样无设备也能拿到 6 版阶梯波参数窗的真实控件表，
用来核实 runner6.py 里从 5 版抄来的那套 id。
"""

import json
import os
import subprocess
import sys
import time

from pywinauto.keyboard import send_keys
from pywinauto import mouse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUTDIR = r"D:\deepseek\_probe\step6_combo"
os.makedirs(OUTDIR, exist_ok=True)

_lines = []
STEP_EVIDENCE = {}


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_panel(root, tag):
    """把一个窗口/控件子树的所有控件导成 JSON + 摘要日志。返回行列表。"""
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
            for attr in ("get_value", "window_text"):
                try:
                    v = getattr(c, attr)()
                    if v:
                        val = str(v)
                        break
                except Exception:
                    pass
            rows.append({"aid": info.automation_id or "",
                         "name": (info.name or "").strip(),
                         "type": info.control_type or "",
                         "rect": rc, "value": val[:120]})
        except Exception:
            continue
    with open(os.path.join(OUTDIR, "dump_%s.json" % tag), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    withaid = [r for r in rows if r["aid"]]
    log("  控件 %d 个（有 aid 的 %d 个）→ dump_%s.json" % (len(rows), len(withaid), tag))
    return rows


def show_rows(rows, only_types=("Edit", "ComboBox", "Button", "CheckBox", "RadioButton")):
    """打印关键控件，优先看 aid。"""
    for r in rows:
        if not r["aid"] and not r["name"]:
            continue
        if only_types and r["type"] not in only_types:
            continue
        log("    %-34s %-11s %-12s val=%-14s name=%s"
            % (r["aid"], r["type"], (r["value"] or "")[:12], "", r["name"][:20]))


def shot(root, tag):
    try:
        p = os.path.join(OUTDIR, "shot_%s.png" % tag)
        root.capture_as_image().save(p)
        log("  截图 → %s" % p)
    except Exception as e:
        log("  截图失败：%s" % e)


def find_win(ui, substr, timeout=8.0, include_mdi=True):
    """在顶层窗与 MDI 子窗里找标题含 substr 的窗口。返回 (title, wrapper)。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for t, c in ui.panels():
                if substr in t:
                    return t, c
        except Exception:
            pass
        if include_mdi:
            try:
                for c in ui.main.descendants(control_type="Window"):
                    t = (c.window_text() or "").strip()
                    if substr in t:
                        return t, c
            except Exception:
                pass
        time.sleep(0.4)
    return None, None


def click_center(wrapper_or_rect):
    try:
        r = wrapper_or_rect.rectangle()
        mouse.click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
        return True
    except Exception as e:
        log("  点击失败：%s" % e)
        return False


def main():
    kill6()
    time.sleep(1.2)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(45):
        log("!! 没能连上主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    time.sleep(1.5)
    ui.force_foreground()
    ui.clear_modals()

    # ---------- 1. 演示模式 ----------
    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进入演示模式 -> %s" % ok)
        time.sleep(2.0)
        ui.clear_modals()
    log("现在：%r  演示=%s" % (ui.title, ui.is_demo))

    # ---------- 2. 组合方法(B) → 组合测试 ----------
    ok = ui.click_menu("%b", "组合测试")
    log("打开「组合测试」 -> %s" % ok)
    time.sleep(2.5)

    t, chan = find_win(ui, "通道")
    if chan is None:
        log("!! 没找到通道窗")
        shot(ui.main, "no_chan")
        return 3
    log("通道窗：%r" % (t,))
    chan_rows = dump_panel(chan, "channel")
    # 只打工具栏/按钮类，找“+”号
    log("  通道窗的 Button/分栏：")
    for r in chan_rows:
        if r["type"] in ("Button", "ToolBar", "SplitButton") and (r["aid"] or r["name"]):
            log("    %-30s %-10s name=%s" % (r["aid"], r["type"], r["name"][:24]))
    shot(chan, "channel")

    # ---------- 3. 点通道窗工具栏“+”号 ----------
    # 截图证据（m00722）：通道窗自己的工具栏从左到右是
    # 新建/打开/**+**/停止/编辑/-/删除/...，"+" 是第 3 个（0 起 index=2）。
    # 该工具栏 aid='toolStrip1'、name='bar'，子按钮 Name 全空，只能按 index。
    log("找工具栏 toolStrip1 ...")
    tb = None
    try:
        for c in chan.descendants(control_type="ToolBar"):
            if (c.element_info.automation_id or "") == "toolStrip1":
                tb = c
                break
    except Exception as e:
        log("  枚举 ToolBar 失败：%s" % e)
    if tb is None:
        log("!! 没拿到工具栏")
        return 4
    btn_wrappers = []
    try:
        btn_wrappers = list(tb.descendants(control_type="Button"))
    except Exception as e:
        log("  枚举工具栏按钮失败：%s" % e)
    log("  工具栏按钮 %d 个：" % len(btn_wrappers))
    for i, b in enumerate(btn_wrappers):
        try:
            r = b.rectangle()
            log("    [%d] rect=(%d,%d,%d,%d) name=%r"
                % (i, r.left, r.top, r.right, r.bottom, (b.window_text() or "")))
        except Exception:
            pass
    if len(btn_wrappers) < 3:
        log("!! 工具栏按钮不足 3 个")
        return 4
    target = btn_wrappers[2]
    log("点第 3 个按钮（应为“+”号）...")
    try:
        target.click_input()
    except Exception as e:
        log("  click_input 失败，退回坐标点击：%s" % e)
        click_center(target)
    time.sleep(1.6)

    # 点“+”可能先弹「通讯配置向导」（设备未连接 + 自动启动勾选）。
    # 策略：打地鼠——向导就取消勾选并退出，用户设置就退出，
    # 直到「添加」出现或次数用完。
    def toggle_check(root, text):
        """取消 root 里文字含 text 的勾选框。返回是否动过。"""
        try:
            for c in root.descendants(control_type="CheckBox"):
                if text in (c.window_text() or ""):
                    try:
                        if c.is_checked():
                            c.click_input()
                            log("    已取消勾选「%s」" % text)
                            return True
                        return False
                    except Exception:
                        c.click_input()
                        log("    盲点勾选框「%s」" % text)
                        return True
        except Exception as e:
            log("    勾选框处理失败：%s" % e)
        return False

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

    def find_top(substr, timeout=1.2):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                for t, c in ui.panels():
                    if substr in t:
                        return c
            except Exception:
                pass
            time.sleep(0.3)
        return None

    def list_titles():
        try:
            return [t for t, _c in ui.panels()]
        except Exception:
            return []

    def hunt_add(max_tries=6, verbose=True):
        """循环清挡路窗，直到「添加」出现。"""
        for i in range(max_tries):
            dlg = find_top("添加")
            if dlg is not None:
                log("  「添加」对话框出现了（第 %d 轮）" % (i + 1))
                return dlg
            wiz = find_top("通讯配置向导", timeout=0.7)
            if wiz is not None:
                log("  [第 %d 轮] 向导弹了，处理" % (i + 1))
                toggle_check(wiz, "自动启动")
                click_button(wiz, "退出")
                time.sleep(0.8)
                continue
            usr = find_top("用户设置", timeout=0.7)
            if usr is not None:
                log("  [第 %d 轮] 「用户设置」挡路，退出它" % (i + 1))
                click_button(usr, "退出")
                time.sleep(0.8)
                continue
            tip = find_top("提示", timeout=0.7)
            if tip is not None:
                # 文件重名对话框：点「扩展(Y)」保住旧数据
                log("  [第 %d 轮] 「提示」（数据文件重复），点「扩展(Y)」" % (i + 1))
                click_button(tip, "扩展(Y)")
                time.sleep(1.2)
                continue
            time.sleep(0.7)
        if verbose:
            log("  hunt_add 放弃，当前顶层窗：%r" % (list_titles(),))
        return find_top("添加", timeout=1.0)

    def click_plus():
        log("点工具栏第 3 个按钮（“+”号）...")
        try:
            target.click_input()
        except Exception as e:
            log("  click_input 失败，退回坐标点击：%s" % e)
            click_center(target)

    click_plus()
    time.sleep(2.0)
    log("  点后顶层窗：%r" % (list_titles(),))
    shot(ui.main, "after_plus1")
    dlg = hunt_add()
    if dlg is None:
        click_plus()
        dlg = hunt_add()
    if dlg is None:
        log("!! 「添加」对话框没出现")
        shot(ui.main, "no_add")
        return 5
    log("「添加」对话框拿到了")
    dlg_rows = dump_panel(dlg, "add_dlg")
    show_rows(dlg_rows)
    shot(dlg, "add_dlg")

    # ---------- 5. 选「任意恒电位阶梯波(多电位阶跃)」----------
    WANT = "任意恒电位阶梯波(多电位阶跃)"
    combo = None
    combo_row = None
    for c in dlg.descendants(control_type="ComboBox"):
        combo = c
        break
    if combo is None:
        log("!! 没找到 ComboBox")
        return 6
    log("选中方法：%r" % (WANT,))
    done = False
    # 5a. 标准 select
    try:
        combo.select(WANT)
        done = True
        log("  select() 成功")
    except Exception as e:
        log("  select() 失败：%s" % e)
    # 5b. 展开下拉找 ListItem
    if not done:
        try:
            combo.click()
            time.sleep(0.8)
            li = None
            for c in ui.main.descendants(control_type="ListItem"):
                if WANT in (c.window_text() or ""):
                    li = c
                    break
            if li is not None:
                click_center(li)
                done = True
                log("  下拉列表点选成功")
            else:
                log("  下拉列表里没找到目标项")
                send_keys("{ESC}")
        except Exception as e:
            log("  下拉点选失败：%s" % e)
            try:
                send_keys("{ESC}")
            except Exception:
                pass
    # 5c. 可编辑就直接写
    if not done:
        try:
            combo.set_edit_text(WANT)
            done = True
            log("  set_edit_text 成功")
        except Exception as e:
            log("  set_edit_text 失败：%s" % e)
    try:
        cur = combo.selected_text()
    except Exception:
        cur = "<unreadable>"
    log("  下拉当前值：%r" % (cur,))
    STEP_EVIDENCE["combo"] = str(cur)

    # ---------- 6. 确认按钮 ----------
    okbtn = None
    for r in dlg_rows:
        if r["type"] != "Button":
            continue
        blob = (r["aid"] + " " + r["name"])
        if r["aid"] in ("btnOK", "buttonOk", "btnOk") or r["name"] in ("确定", "添加", "OK"):
            okbtn = r
            break
    if okbtn is None:
        # 下拉框右侧那个小按钮（截图中带图标）可能是“确认添加”
        for r in dlg_rows:
            if r["type"] == "Button" and r["rect"] and not r["name"]:
                okbtn = r
                break
    if okbtn is None:
        log("!! 没找到确认按钮，先停在这里")
        shot(dlg, "no_ok")
        return 7
    log("点确认：aid=%r name=%r rect=%s" % (okbtn["aid"], okbtn["name"], okbtn["rect"]))
    click_center_rect(okbtn["rect"])
    time.sleep(2.2)

    # ---------- 7. 期望弹出参数窗 ----------
    got = None
    for key in ("任意恒电位阶梯波", "恒电位阶梯波", "PotSquare"):
        t, w = find_win(ui, key, timeout=5.0)
        if w is not None:
            got = (t, w)
            break
    if got is None:
        # 也可能是 MDI 子窗
        try:
            for c in ui.main.descendants():
                ei = c.element_info
                if ei.control_type == "Window" and "阶梯波" in (ei.name or ""):
                    got = (ei.name, c)
                    break
        except Exception:
            pass
    if got is None:
        log("!! 没等到参数窗")
        shot(ui.main, "no_panel")
        return 8
    t, panel = got
    log("参数窗出现：%r" % (t,))
    rows = dump_panel(panel, "pot_square")
    shot(panel, "pot_square")

    # ---------- 8. 对照 runner6 的 5 版控件表 ----------
    aids = {r["aid"] for r in rows if r["aid"]}
    log("")
    log("=== 对照 runner6.py（5 版抄来的）控件表 ===")
    expect = ["Control_FileName_Text", "PotSquare_TimeUnit_cbo", "Vs_Combo",
              "PotSquare_InitialE_txt", "PotSquare_InitTime_txt",
              "PotSquare_FinalE_txt", "PotSquare_FinalTime_txt",
              "PotSquare_Cycles_txt", "FrqControl_Frq_Radio", "FrqControl_Frq_Text"]
    for e in expect:
        log("  %-28s %s" % (e, "命中" if e in aids else "** 未命中 **"))
    log("  中间电位开关 PotSquare_StepN_chb：")
    hits = [a for a in sorted(aids) if a.startswith("PotSquare_Step") and a.endswith("_chb")]
    log("    %s" % (", ".join(hits) if hits else "** 一个都没有 **"))
    log("")
    log("=== 参数窗里所有带 aid 的控件 ===")
    for r in rows:
        if r["aid"]:
            log("    %-38s %-12s %-16s %s" % (r["aid"], r["type"],
                                              (r["value"] or "")[:16], r["name"][:24]))
    return 0


def click_center_rect(rc):
    mouse.click(coords=((rc[0] + rc[2]) // 2, (rc[1] + rc[3]) // 2))


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
