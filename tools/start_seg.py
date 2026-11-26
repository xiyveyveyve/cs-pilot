# -*- coding: utf-8 -*-
"""start_seg.py —— 启动一段长时恒流电解（单位=秒，最长 65535 s）。

用法：python tools/start_seg.py --ma 0.5 --sec 64800 --frq 1 --tag s1
"""
import sys, os, time, io, json, statistics, win32gui, win32con
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")
import driver5

BASE = r"D:\deepseek\_probe\e2e5"
LOG  = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\start_seg.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass

def A(n, d):
    return float(sys.argv[sys.argv.index(n)+1]) if n in sys.argv else d
def S(n, d):
    return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d

def kill(kw):
    n = 0
    def cb(h, _):
        nonlocal n
        t = win32gui.GetWindowText(h) or ""
        if kw in t and win32gui.IsWindowVisible(h):
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0); n += 1
        return True
    win32gui.EnumWindows(cb, None)
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
            if t == name and (r.right-r.left) > 10 and (r.bottom-r.top) > 6 and r.top > 0:
                hit = (r, c); break
        if hit is None:
            log("菜单 '%s' 不可见" % name); return None
        driver5.msg_click(hit[1]); time.sleep(0.9)
    return st.find_panel_by_title("恒电流阶跃", timeout=4.0)

def set_unit_sec(cbo):
    """把时间单位从 ms 切到 s（UIA 只能 click_input + DOWN）。"""
    def val():
        try: return cbo.legacy_properties().get("Value")
        except Exception: return "<?>"
    if val() == "s":
        return True
    for _ in range(4):
        cbo.click_input(); time.sleep(0.35)
        cbo.type_keys("{DOWN}"); time.sleep(0.5)
        if val() == "s":
            return True
    return val() == "s"

def main():
    ma   = A("--ma", 0.5)
    sec  = int(A("--sec", 64800))
    frq  = A("--frq", 1)
    tag  = S("--tag", "s1")
    maxv = A("--maxvolt", 8.0)
    if sec > 65535:
        log("!! 段时长 %d s 超过面板上限 65535，已截断" % sec); sec = 65535

    log("")
    log("======== start_seg %s @ %s ========" % (tag, time.strftime("%Y-%m-%d %H:%M:%S")))
    log("目标 %.3f mA / %d s (%.2f h) / %.1f Hz" % (ma, sec, sec/3600.0, frq))

    st = driver5.Studio5(log=log)
    if not st.find_main():
        log("FATAL 主窗"); return 2
    if "CS350" not in st.title():
        log("FATAL 未连真机"); return 2
    log("主窗: " + st.title())
    log("清理残留: 输入错误=%d 参数窗=%d" % (kill("输入错误"), (time.sleep(0.6) or kill("恒电流阶跃"))))
    time.sleep(0.8)

    p = open_panel(st)
    if p is None:
        log("FATAL 面板"); return 3
    ids = st.by_ids(p)

    if not set_unit_sec(ids["GalJump_TimeUnit_cbo"]):
        log("FATAL 时间单位切不到 s"); kill("恒电流阶跃"); return 4
    log("  时间单位: %s" % ids["GalJump_TimeUnit_cbo"].legacy_properties().get("Value"))

    fname = "exp48h_%s_%s" % (tag, time.strftime("%m%d_%H%M"))
    pairs = [("Control_FileName_Text", fname),
             ("GalJump_initCur_txt", "0"), ("GalJump_initTime_txt", "1000"),
             ("GalJump_Jump1_txt", "%g" % ma),
             ("GalJump_Jump1Time_txt", str(sec)),
             ("GalJump_frq_txt", "%g" % frq)]
    for aid, v in pairs:
        c = ids.get(aid)
        if c is None:
            log("FATAL 缺控件 %s" % aid); return 5
        ok = st.set_edit(c, v)
        log("  %-26s = %-16s set=%s 读回=%r" % (aid, v, ok, c.get_value()))

    before = set(driver5.all_run_hwnds(keywords=("恒电流", "阶跃")))
    log("点确定…")
    driver5.msg_click(ids["GalJump_Ok_Btn"])
    rw = st.find_run_window(timeout=30, keywords=("恒电流", "阶跃"), exclude=before, expect=fname)
    if rw is None:
        log("FATAL 运行窗没出现")
        kill("输入错误")
        return 6
    log("运行窗: " + rw.window_text()[:110])

    cor, lastE = None, None
    for k in range(8):
        time.sleep(2.5)
        cur = [os.path.join(BASE, f) for f in os.listdir(BASE)
               if f.startswith(fname) and f.endswith(".cor")]
        if cur:
            cor = max(cur, key=os.path.getmtime)
            try:
                lines = io.open(cor, encoding="utf-8", errors="ignore").read().splitlines()
                di = next(i for i, l in enumerate(lines) if l.startswith("E(") or l.startswith("E\t"))
                rows = []
                for l in lines[di+1:]:
                    q = l.split("\t") if "\t" in l else l.split()
                    if len(q) >= 3:
                        try: rows.append(float(q[0]))
                        except ValueError: pass
                if rows: lastE = statistics.median(rows[-5:])
            except Exception: pass
        log("  +%.0fs  %s  E=%s" % ((k+1)*2.5, (os.path.basename(cor) if cor else "-"),
                                    ("%+.4f V" % lastE) if lastE is not None else "-"))

    if lastE is not None and lastE > maxv:
        log("!! 电压 %+.3f V > %.1f V，判为异常，停止" % (lastE, maxv))
        try: st.stop_run(rw)
        except Exception: pass
        return 7

    log("RESULT_JSON " + json.dumps({"ok": True, "file": fname, "ma": ma, "sec": sec,
                                    "frq": frq, "E": lastE, "cor": cor}, ensure_ascii=False))
    log("实验运行中，脚本退出（运行窗保留）。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
