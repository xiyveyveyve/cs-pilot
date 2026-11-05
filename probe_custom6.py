# -*- coding: utf-8 -*-
"""probe_custom6.py —— 6 版无设备下唯一能打开的定制入口：
  A. 主工具栏 toolbar[9] → 「快速实验定制」
  B. 菜单 组合方法(B) → 「脚本化定制测试」

菜单 测试方法(E) 的实验在无设备时会被通讯配置向导拦掉，但这两个入口
在 probe_step6c 里是能打开的。把它们的控件树完整 dump 出来，
判断哪条是"用代码下参数/跑实验"的正路。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pywinauto import mouse
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\custom6.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dump_tree(c, tag, maxn=200):
    log("=== %s ===" % tag)
    rows = []

    def walk(node, depth):
        if len(rows) >= maxn:
            return
        try:
            for ch in node.children():
                try:
                    ei = ch.element_info
                    ct = getattr(ei, "control_type", "") or ""
                    aid = getattr(ei, "automation_id", "") or ""
                    try:
                        txt = (ch.window_text() or "").strip()
                    except Exception:
                        txt = ""
                    if txt or aid or ct in ("List", "Tree", "Table", "DataGrid"):
                        rows.append((depth, ct, aid, txt))
                except Exception:
                    pass
                walk(ch, depth + 1)
        except Exception:
            pass

    walk(c, 0)
    for d, ct, aid, txt in rows:
        log("%s%-14s aid=%-26r %r" % ("  " * min(d, 8), ct, aid, txt[:80]))
    log("   （%d 条）" % len(rows))
    return rows


def close_all(ui, keep_kw=("CS Studio",)):
    for t, c in ui.panels():
        if not t:
            continue
        for d in c.descendants():
            try:
                if getattr(d.element_info, "control_type", "") != "Button":
                    continue
                txt = (d.window_text() or "").strip()
                if txt in ("取消", "退出", "关闭"):
                    d.click_input()
                    log("   关 [%s] 用「%s」" % (t, txt))
                    time.sleep(1.0)
                    return True
            except Exception:
                continue
    return False


def main():
    kill6()
    time.sleep(1.0)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=4)
    for _ in range(4):
        if not close_all(ui):
            break

    # ---------- A. toolbar[9] ----------
    log("")
    log("########## A. 主工具栏 toolbar[9] ##########")
    tb = None
    for c in ui.descendants():
        try:
            if c.element_info.automation_id == "toolStrip":
                tb = c
                break
        except Exception:
            continue
    if tb is None:
        log("!! 没工具栏")
    else:
        try:
            n = len(tb.buttons())
            log("工具栏按钮数 = %d" % n)
        except Exception as e:
            log("数按钮失败：%s" % e)
        try:
            tb.button(9).click_input()
            time.sleep(2.5)
        except Exception as e:
            log("点 toolbar[9] 失败：%s" % e)
        cur = ui.panels()
        log("点后可见窗：%r" % ([t for t, _ in cur],))
        hit = [c for t, c in cur if "快速实验" in t]
        if hit:
            dump_tree(hit[0], "快速实验定制")
            ui.snapshot(r"D:\deepseek\_probe\custom_quick.png")
            close_all(ui)
        else:
            log("!! 没出现「快速实验定制」")

    # ---------- B. 组合方法(B) → 脚本化定制测试 ----------
    log("")
    log("########## B. 组合方法(B) → 脚本化定制测试 ##########")
    ui.force_foreground()
    ui.open_menu("%b")
    time.sleep(1.0)
    bars = [(t.strip(), r) for t, _c, r in ui.menu_items(only_visible=False) if r.width() > 0]
    log("展开项：%r" % ([t for t, _r in bars],))
    tgt = None
    for t, r in bars:
        if "脚本化定制测试" in t:
            tgt = (t, r)
            break
    if tgt is None:
        log("!! 「组合方法(B)」里没脚本化定制测试")
    else:
        t, r = tgt
        log("点 %r rect=(%d,%d %dx%d)" % (t, r.left, r.top, r.width(), r.height()))
        pt = (r.left + 15, r.top + r.height() // 2)
        mouse.move(coords=pt)
        time.sleep(0.3)
        mouse.click(coords=pt)
        time.sleep(3.0)
        cur = ui.panels()
        log("点后可见窗：%r" % ([t for t, _ in cur],))
        for t2, c2 in cur:
            if t2:
                dump_tree(c2, "窗：" + t2)
        ui.snapshot(r"D:\deepseek\_probe\custom_script.png")

    return 0


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
    finally:
        log("清理：taskkill /T")
        try:
            kill6()
        except Exception:
            pass
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        log("EXIT=%s" % rc)
