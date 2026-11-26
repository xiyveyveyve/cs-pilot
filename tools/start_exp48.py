# -*- coding: utf-8 -*-
"""start_exp48.py —— 启动长时恒流电解（CFRP 作阳极），启动后只做一次安全检查，不关运行窗。

用法：
  python tools/start_exp48.py --ma 0.5 --hours 48 --frq 0.2 --maxvolt 8
"""
import sys, os, time, io, json, win32gui, win32con, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")

import driver5

BASE = r"D:\deepseek\_probe\e2e5"
LOG = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\start_exp48.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception:
        pass

def arg(name, default):
    if name in sys.argv:
        return float(sys.argv[sys.argv.index(name) + 1])
    return default

def close_param_panels():
    n = 0
    def cb(h, _):
        nonlocal n
        t = win32gui.GetWindowText(h)
        if t.strip() == "恒电流阶跃" and win32gui.IsWindowVisible(h):
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0); n += 1
        return True
    win32gui.EnumWindows(cb, None)
    if n: time.sleep(1.2)
    return n

def open_panel(st):
    st.close_user_settings()
    try: st.main.set_focus()
    except Exception: pass
    time.sleep(0.5)
    st.click_main_menu("测试方法(E)"); time.sleep(0.8)
    for name in ("暂态极化(T)", "恒电流阶跃(G)"):
        hit = None
        for t, r, c in st.menu_items():
            if t == name and (r.right - r.left) > 10 and (r.bottom - r.top) > 6 and r.top > 0:
                hit = (r, c); break
        if hit is None:
            log("菜单 '%s' 不可见" % name); return None
        driver5.msg_click(hit[1]); time.sleep(0.9)
    return st.find_panel_by_title("恒电流阶跃", timeout=4.0)

def cor_tail_E(path, need=8):
    """读 .cor 尾部若干行的 E 中位数（列1=E, 列2=i, 列3=t）。"""
    try:
        lines = io.open(path, encoding="utf-8", errors="ignore").read().splitlines()
    except Exception:
        return None
    di = None
    for k, l in enumerate(lines):
        if l.startswith("E(") or l.startswith("E\t"):
            di = k; break
    if di is None:
        return None
    rows = []
    for l in lines[di + 1:]:
        p = l.split("\t") if "\t" in l else l.split()
        if len(p) >= 3:
            try: rows.append(tuple(float(x) for x in p[:3]))
            except ValueError: pass
    if not rows: return None
    tail = rows[-need:]
    return statistics.median([r[0] for r in tail]), statistics.median([r[2] for r in tail])

def main():
    ma = arg("--ma", 0.5)
    hours = arg("--hours", 48.0)
    frq = arg("--frq", 0.2)
    maxvolt = arg("--maxvolt", 8.0)
    ms = int(hours * 3600 * 1000)

    log("")
    log("================ start %s ================" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log("目标: %.3f mA（CFRP 阳极）  时长 %.1f h  采样 %.2f Hz  限压(仅告警) %.1f V" % (ma, hours, frq, maxvolt))

    st = driver5.Studio5(log=log)
    if not st.find_main():
        log("FATAL 主窗"); return 2
    log("主窗: " + st.title())
    if "CS350" not in st.title():
        log("FATAL 未连真机"); return 2

    log("关残留参数窗 %d 个" % close_param_panels())
    p = open_panel(st)
    if p is None:
        log("FATAL 参数窗没打开"); return 3
    ids = st.by_ids(p)

    fname = "exp48h_%smA_%s" % (("%g" % ma).replace(".", "p"), time.strftime("%m%d_%H%M"))
    pairs = [
        ("Control_FileName_Text", fname),
        ("GalJump_initCur_txt", "0"),
        ("GalJump_initTime_txt", "1000"),
        ("GalJump_Jump1_txt", "%g" % ma),
        ("GalJump_Jump1Time_txt", str(ms)),
        ("GalJump_frq_txt", "%g" % frq),
    ]
    for aid, val in pairs:
        c = ids.get(aid)
        if c is None:
            log("FATAL 缺控件 %s" % aid); return 4
        ok = st.set_edit(c, val)
        got = c.get_value()
        log("  %-26s = %-16s (set=%s, 读回=%r)" % (aid, val, ok, got))

    before = set(driver5.all_run_hwnds(keywords=("恒电流", "阶跃")))
    log("点确定…")
    driver5.msg_click(ids["GalJump_Ok_Btn"])

    rw = st.find_run_window(timeout=30, keywords=("恒电流", "阶跃"), exclude=before, expect=fname)
    if rw is None:
        log("FATAL 运行窗没出现"); return 5
    log("运行窗: " + rw.window_text()[:100])
    log("已启动，开始 20 s 观察（不关闭运行窗）")

    # 观察 20 s：看 .cor 是否出现并增长，超压则立即停
    cor = None
    lastE = None
    for k in range(10):
        time.sleep(2.0)
        cur = [os.path.join(BASE, f) for f in os.listdir(BASE)
               if f.startswith(fname) and f.endswith(".cor")]
        if cur:
            cor = max(cur, key=os.path.getmtime)
        if cor:
            t = cor_tail_E(cor)
            if t:
                lastE, lastt = t
        log("  +%2ds  cor=%s  E=%s" % ((k + 1) * 2,
                                       (os.path.basename(cor) if cor else "-"),
                                       ("%+.4f V (t=%.1fs)" % (lastE, lastt)) if lastE is not None else "-"))

    if lastE is not None and lastE > maxvolt:
        log("!! 电压 %+.3f V 超过 %.1f V，立即停止" % (lastE, maxvolt))
        try: st.stop_run(rw)
        except Exception as e: log("  stop 失败: %s" % e)
        time.sleep(1.0)
        log("RESULT_JSON " + json.dumps({"ok": False, "reason": "over-volt", "E": lastE}))
        return 6

    log("RESULT_JSON " + json.dumps({"ok": True, "file": fname, "ma": ma,
                                     "hours": hours, "frq": frq,
                                     "E_now": lastE, "cor": cor}, ensure_ascii=False))
    log("实验在跑，脚本退出。下电请手动在运行窗点「停止」。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
