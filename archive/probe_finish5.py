# -*- coding: utf-8 -*-
"""probe_finish5.py —— 专测 5 版「停止后会不会留后台」这一个问题。

流程（全在演示模式下，不碰设备）：
    开 1 轮开路电位 → 跑 20 s → 完整收尾 → 检查有没有残留
    → 立刻再开 1 轮开路电位（能开起来 = 软件真的回到空闲）
    → 再收尾 → 检查残留 → 关软件

结束后打印 PASS/FAIL，不依赖人手看界面。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psutil
import win32gui
import win32process

import driver5
from driver5 import Studio5, all_run_hwnds
from uiprobe import UiSampler
from runner5 import wait_endexp

OUT = r"D:\deepseek\_probe\finish5"
T0 = time.time()
FAIL = []


def log(m):
    print("%7.1fs  %s" % (time.time() - T0, m), flush=True)


def wins_of_pid(pid):
    out = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return
            _t, p = win32process.GetWindowThreadProcessId(h)
            if p == pid:
                out.append((h, win32gui.GetWindowText(h)))
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)
    return out


def run_windows(pid):
    """标题像运行窗的窗口：带 <…> 和文件路径。"""
    return [(h, t) for h, t in wins_of_pid(pid) if "<" in t and "\\" in t]


def one_round(st, tag, run_sec=20.0):
    """开一轮开路电位，跑 run_sec 秒，然后完整收尾。返回运行窗 hwnd。"""
    log("── 第 %s 轮：打开参数窗" % tag)
    panel = st.open_ocp()
    if panel is None:
        FAIL.append("%s 打不开开路电位参数窗" % tag)
        return None
    path = r"%s\probe-%s" % (OUT, tag)
    st.fill_ocp(panel, path, 600.0, 10.0)
    st.set_cell_area(panel, 1.0)

    old = set(all_run_hwnds())
    if not st.start_experiment(panel, kind="ocp", wait=8.0):
        FAIL.append("%s 点确定失败" % tag)
        return None
    rw = st.find_run_window(timeout=20, exclude=old, expect="probe-%s" % tag)
    if rw is None:
        FAIL.append("%s 没有出现运行窗口" % tag)
        return None
    log("   运行窗：%r" % (rw.window_text(),))

    sm = UiSampler(rw, log=None)
    t_end = time.time() + run_sec
    n = 0
    while time.time() < t_end:
        try:
            s = sm.read()
            if s is not None and s.e_volt is not None:
                n += 1
        except Exception:
            pass
        time.sleep(1.0)
    log("   采到 %d 个界面读数（%g s）" % (n, run_sec))
    return rw


def finish(st, rw, tag):
    """完整收尾，与 runner5._finish_run 完全相同的顺序。"""
    ok = st.stop_run(rw)
    log("   ① 点「停止」→ %s" % ok)
    t = time.time()
    got = wait_endexp(log, method=tag, runwin=rw, timeout=40.0, fallback=8.0)
    log("   ② 等待收尾：%s，用了 %.1f s" % (got, time.time() - t))
    try:
        st.close_run(rw)
        log("   ③ 关闭运行窗口")
    except Exception as e:
        log("   ③ 关窗出错：%s" % e)
    time.sleep(10.0)
    log("   ④ 冷却 10 s 完成")
    try:
        n = st.cleanup_run_windows()
        log("   ⑤ 清理残留：%d 个" % n)
    except Exception as e:
        log("   ⑤ 清理出错：%s" % e)
    try:
        n = driver5.clear_modals(limit=4, prefer=("是(Y)", "是", "关闭", "确定"))
        if n:
            log("   顺带清掉 %d 个提示框" % n)
    except Exception:
        pass


def close_app(pid, hwnd):
    """关软件：先礼后兵（WM_CLOSE → 等 6 s → 强制结束）。"""
    try:
        for h, t in wins_of_pid(pid):
            if t.startswith("CS Studio"):
                win32gui.PostMessage(h, 0x0010, 0, 0)   # WM_CLOSE
                break
        time.sleep(6.0)
    except Exception as e:
        log("  WM_CLOSE 出错：%s" % e)
    try:
        p = psutil.Process(pid)
        if p.is_running():
            p.terminate()
            p.wait(timeout=10)
            log("已强制结束进程 pid=%s" % pid)
        else:
            log("软件已正常退出")
    except Exception as e:
        log("结束进程出错：%s" % e)


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    st = Studio5(log=log)
    if not st.launch():
        print("启动失败")
        return 1
    pid = st.hwnd and win32process.GetWindowThreadProcessId(st.hwnd)[1]
    log("已启动，pid=%s 标题=%r" % (pid, st.title()))
    if not st.is_demo() and not st.enter_demo():
        log("未进入演示模式（有真机时正常）")
    else:
        log("演示模式：%r" % st.title())

    # ---- 第 1 轮 ----
    rw1 = one_round(st, "A")
    if rw1 is not None:
        finish(st, rw1, "A")

    left = run_windows(pid)
    if left:
        log("❌ 第 1 轮收尾后仍有运行窗：%r" % left)
        FAIL.append("第 1 轮残留 %d 个运行窗" % len(left))
    else:
        log("✅ 第 1 轮收尾后没有残留运行窗")

    # ---- 第 2 轮：能开起来就证明软件真的空闲了 ----
    rw2 = one_round(st, "B")
    if rw2 is not None:
        finish(st, rw2, "B")
        log("✅ 第 2 轮能正常启动并结束")
    left = run_windows(pid)
    if left:
        FAIL.append("第 2 轮残留 %d 个运行窗" % len(left))
        log("❌ 第 2 轮收尾后仍有运行窗：%r" % left)
    else:
        log("✅ 第 2 轮收尾后没有残留运行窗")

    # ---- 全程结束后：还有没有活着的实验 ----
    left = run_windows(pid)
    if left:
        FAIL.append("全程结束后仍有运行窗")
    close_app(pid, st.hwnd)

    print()
    if FAIL:
        for f in FAIL:
            print("FAIL " + f)
        return 1
    print("全部 PASS：停止 → 收尾 → 再开一轮，全程无残留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
