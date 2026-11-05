# -*- coding: utf-8 -*-
"""probe_step6c.py —— 非演示模式下，把主工具栏 1..13 个按钮逐个点一遍，
记录每个按钮到底能开出什么窗口，找出能打开「任意恒电位阶梯波」参数窗的那个。

背景：菜单路径 测试方法(E) → 暂态极化 → 任意恒电位阶梯波 是通的，
但无设备时点下去会被「通讯配置向导」拦掉，参数窗不出现。
所以改试工具栏按钮（可能不走设备检查）。

每次点完都清理：关向导 / 关用户设置 / 关冒出来的参数窗。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pywinauto.keyboard import send_keys
import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\step6c.log"

PANEL_KW = ("阶梯", "阶跃", "恒电位", "开路电位", "动电位", "频率扫描",
            "循环伏安", "线性扫描", "恒电流", "计时", "电池", "极化")

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def close_nonparam(ui, keep=()):
    """关掉挡路的窗（向导/用户设置/提示），返回关掉了什么。"""
    done = []
    for t, c in ui.panels():
        if not t or t in keep:
            continue
        if any(k in t for k in PANEL_KW):
            continue
        for d in c.descendants():
            try:
                ei = d.element_info
                if getattr(ei, "control_type", "") != "Button":
                    continue
                txt = (d.window_text() or "").strip()
                if txt in ("退出", "取消", "关闭", "否(N)", "确定"):
                    d.click_input()
                    done.append((t, txt))
                    time.sleep(0.9)
                    break
            except Exception:
                continue
    try:
        ui.clear_modals(limit=3)
    except Exception:
        pass
    return done


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
    log("清场：%r" % (close_nonparam(ui),))

    # 先建一个通道，看看工具栏会不会解锁
    log("")
    log("=== 试「工作通道(C)」→ 建通道 ===")
    ui.force_foreground()
    ui.open_menu("%c")
    time.sleep(1.0)
    bars = [(t, r) for t, _c, r in ui.menu_items(only_visible=False) if r.width() > 0]
    log("菜单栏/展开项：%r" % ([t for t, _r in bars],))
    ch = None
    for t, r in bars:
        if t.strip() in ("通道 1", "通道1"):
            ch = (t, r)
            break
    if ch:
        from pywinauto import mouse
        log("点 %r" % (ch[0],))
        mouse.click(coords=(ch[1].left + 15, ch[1].top + ch[1].height() // 2))
        time.sleep(2.5)
        log("点后可见窗：%r" % ([t for t, _ in ui.panels()],))
        log("清场：%r" % (close_nonparam(ui),))
        mdi = []
        try:
            mdi = [w.window_text() for w in ui.main.descendants(control_type="Window")]
        except Exception:
            pass
        log("MDI 窗：%r" % (mdi,))
    else:
        log("!! 没找到「通道 1」")
        send_keys("{ESC}")

    # 再逐个点工具栏
    log("")
    log("=== 逐个点主工具栏 ===")
    tb = None
    for c in ui.descendants():
        try:
            if c.element_info.automation_id == "toolStrip":
                tb = c
                break
        except Exception:
            continue
    if tb is None:
        log("!! 没找到主工具栏 toolStrip")
        return 3

    for idx in range(1, 14):
        log("")
        log("--- toolbar[%d] ---" % idx)
        try:
            tb2 = None
            for c in ui.descendants():
                try:
                    if c.element_info.automation_id == "toolStrip":
                        tb2 = c
                        break
                except Exception:
                    continue
            if tb2 is None:
                log("   工具栏丢了，重取失败")
                break
            tb2.button(idx).click_input()
        except Exception as e:
            log("   点不动：%s" % e)
            continue
        time.sleep(2.0)
        cur = [t for t, _ in ui.panels()]
        log("   可见窗：%r" % (cur,))
        hit = [t for t in cur if any(k in t for k in PANEL_KW)]
        if hit:
            log("   *** 疑似参数窗：%r" % (hit,))
        closed = close_nonparam(ui)
        if closed:
            log("   清场：%r" % (closed,))
        time.sleep(0.4)

    ui.snapshot(r"D:\deepseek\_probe\step6c_state.png")
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
