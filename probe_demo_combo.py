# -*- coding: utf-8 -*-
"""probe_demo_combo.py —— 在 6 版【演示模式】下走「组合方法(B)」，
看能不能打开各实验的参数窗，并把窗口内容完整 dump 出来。

用户提示：演示模式的「组合方法」里能打开每种测试的窗口，内容和真实测试一样，
只是「测试方法(E)」菜单在演示模式下被「工作通道(C)」替换了。
"""

import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
from pywinauto.keyboard import send_keys

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUTDIR = r"D:\deepseek\_probe\demo_combo"
os.makedirs(OUTDIR, exist_ok=True)

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_panel(ui, panel, tag):
    """把一个窗口的所有控件导成结构化 JSON。"""
    rows = []
    try:
        ctrls = panel.descendants()
    except Exception as e:
        log("  dump 失败：%s" % e)
        return []
    for c in ctrls:
        try:
            info = c.element_info
            aid = info.automation_id or ""
            name = (info.name or "").strip()
            ctype = info.control_type or ""
            try:
                rect = c.rectangle()
                rc = (rect.left, rect.top, rect.right, rect.bottom)
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
            rows.append({"aid": aid, "name": name, "type": ctype,
                         "rect": rc, "value": val[:120]})
        except Exception:
            continue
    path = os.path.join(OUTDIR, "dump_%s.json" % tag)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    log("  控件 %d 个 → %s" % (len(rows), path))
    # 只打有 aid 的，方便快速看关键控件
    withaid = [r for r in rows if r["aid"]]
    log("  其中有 automation_id 的 %d 个：" % len(withaid))
    for r in withaid[:80]:
        log("    %-34s %-22s %-18s %s" % (r["aid"], r["type"], r["value"][:18], r["name"][:28]))
    return rows


def new_titles(ui, before):
    now = {}
    try:
        for t, c in ui.panels():
            now[t] = c
    except Exception:
        pass
    return [(t, c) for t, c in now.items() if t not in before]


def snapshot_titles(ui):
    d = {}
    try:
        for t, c in ui.panels():
            d[t] = c
    except Exception:
        pass
    return d


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

    # ---- 进演示模式 ----
    if not ui.is_demo:
        ok = ui.click_menu("%s", "进入演示模式")
        log("进入演示模式 -> %s" % ok)
        time.sleep(2.0)
        ui.clear_modals()
    log("现在：%r  演示=%s" % (ui.title, ui.is_demo))

    # ---- 菜单栏现状 ----
    log("")
    log("=== 菜单栏（顶级） ===")
    try:
        for t, c, r in ui.menu_items():
            if r.top < 60:
                log("  %-14s x=%d w=%d" % (t, r.left, r.width()))
    except Exception as e:
        log("枚举菜单栏失败：%s" % e)

    # ---- 展开「组合方法(B)」 ----
    log("")
    log("=== 组合方法(B) ===")
    before = snapshot_titles(ui)
    ok = ui.open_menu("%b")
    log("open_menu('%%b') -> %s" % ok)
    time.sleep(0.8)
    items = []
    try:
        for t, c, r in ui.menu_items():
            if r.top > 55:
                items.append((t, r.left, r.top, r.width(), r.height()))
    except Exception:
        pass
    log("展开后可见菜单项 %d 个：" % len(items))
    for t, x, y, w, h in sorted(items, key=lambda z: (z[1], z[2])):
        log("  (%-4d,%4d %3dx%-3d) %s" % (x, y, w, h, t))

    # 截图留档
    try:
        shot = os.path.join(OUTDIR, "menu_b.png")
        ui.main.capture_as_image().save(shot)
        log("截图 → %s" % shot)
    except Exception as e:
        log("截图失败：%s" % e)

    # ---- 逐个点「组合方法」下的二级项，看能不能开出参数窗 ----
    log("")
    log("=== 逐个点击组合方法下的项（每次点击前重新展开菜单）===")
    from pywinauto import mouse
    names = [it[0] for it in sorted(items, key=lambda z: z[2]) if it[0]]
    seq = 0
    for want in names:
        log("")
        log("--- 处理「%s」 ---" % want)
        ui.clear_modals()
        time.sleep(0.3)
        before = snapshot_titles(ui)
        if not ui.open_menu("%b"):
            log("  菜单打不开")
            continue
        time.sleep(0.5)
        target = None
        for t, c, r in ui.menu_items():
            if t == want and r.top > 55 and 200 < r.left < 320:
                target = (t, c, r)
                break
        if target is None:
            log("  菜单里找不到这一项")
            try:
                send_keys("{ESC}")
            except Exception:
                pass
            continue
        t, c, r = target
        # 先悬停，看有没有三级子菜单
        try:
            mouse.move(coords=(r.left + r.width() // 2, r.top + r.height() // 2))
        except Exception:
            pass
        time.sleep(1.0)
        sub = [(st, sr) for st, _sc, sr in ui.menu_items()
               if sr.top > r.top + 10 and sr.left > r.left + 100]
        if sub:
            log("  三级子菜单 %d 项：" % len(sub))
            for st, sr in sub:
                log("    (%-4d,%4d) %s" % (sr.left, sr.top, st))
            # 逐个点三级
            for st, sr in sub:
                log("    -- 点三级「%s」 --" % st)
                try:
                    mouse.click(coords=(sr.left + sr.width() // 2, sr.top + sr.height() // 2))
                except Exception as e:
                    log("      点击失败 %s" % e)
                    continue
                time.sleep(2.2)
                news = new_titles(ui, before)
                if not news:
                    log("      没有新窗口")
                for nt, nc in news:
                    log("      新窗口：%r" % (nt,))
                    seq += 1
                    dump_panel(ui, nc, "win%02d" % seq)
                    try:
                        shot = os.path.join(OUTDIR, "win%02d.png" % seq)
                        nc.capture_as_image().save(shot)
                        log("      截图 → %s" % shot)
                    except Exception:
                        pass
                ui.clear_modals()
                time.sleep(0.6)
                if not ui.open_menu("%b"):
                    break
                time.sleep(0.4)
                try:
                    mouse.move(coords=(r.left + r.width() // 2, r.top + r.height() // 2))
                except Exception:
                    pass
                time.sleep(0.6)
            continue
        # 叶子项：直接点击
        try:
            mouse.click(coords=(r.left + r.width() // 2, r.top + r.height() // 2))
        except Exception as e:
            log("  点击失败：%s" % e)
            continue
        time.sleep(2.2)
        news = new_titles(ui, before)
        if not news:
            log("  没有新窗口")
            continue
        for nt, nc in news:
            log("  新窗口：%r" % (nt,))
            seq += 1
            dump_panel(ui, nc, "win%02d" % seq)
            try:
                shot = os.path.join(OUTDIR, "win%02d.png" % seq)
                nc.capture_as_image().save(shot)
                log("  截图 → %s" % shot)
            except Exception:
                pass

    log("")
    log("=== 当前所有顶层窗 ===")
    for t in snapshot_titles(ui):
        log("  %r" % (t,))
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
