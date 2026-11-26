# -*- coding: utf-8 -*-
"""real_r_gui4.py —— 复测电阻（修 real_r_gui3 的两个坑）。

修复：
  1. find_run_window 抓到上一轮残留窗 → before 用相同 keywords 收集 +
     expect=本轮文件名精确匹配；每轮结束关掉运行窗。
  2. 不用界面 UiSampler 读数（可能被残留窗干扰），改读 .cor 稳态段中位数。
流程：每档双极性 ±I 各一轮 → 从 .cor 解析稳态 E/i → 线性与 R 一并算。

用法：python tools/real_r_gui4.py --curr 0.1 0.15
"""
import sys, os, time, io, json, statistics, win32gui, win32con
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")

import driver5

OUT = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\real_r_gui4.txt"
BASE = r"D:\deepseek\_probe\e2e5"

def log(m):
    print(m, flush=True)
    try:
        with io.open(OUT, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass

def close_run_windows():
    n = 0
    def cb(h, _):
        nonlocal n
        t = win32gui.GetWindowText(h)
        if "恒电流阶跃" in t and ".cor" in t and win32gui.IsWindowVisible(h):
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            n += 1
        return True
    win32gui.EnumWindows(cb, None)
    if n: time.sleep(1.0)
    return n

def open_panel(st):
    st.close_user_settings()
    try: st.main.set_focus()
    except Exception: pass
    time.sleep(0.4)
    st.click_main_menu("测试方法(E)")
    time.sleep(0.7)
    for name in ("暂态极化(T)", "恒电流阶跃(G)"):
        hit = None
        for t, r, c in st.menu_items():
            if t == name and (r.right - r.left) > 10 and (r.bottom - r.top) > 6 and r.top > 0:
                hit = (r, c); break
        if hit is None:
            log("  菜单 '%s' 不可见" % name); return None
        driver5.msg_click(hit[1])
        time.sleep(0.8)
    return st.find_panel_by_title("恒电流阶跃", timeout=3.0)

def run_one(st, curr_ma, tag):
    """跑一轮，返回 .cor 路径（成功）/ None。"""
    p = open_panel(st)
    if p is None: log("  FATAL 参数窗没打开"); return None
    ids = st.by_ids(p)

    def setv(aid, val):
        c = ids.get(aid)
        if c is None: return False
        return st.set_edit(c, str(val))

    fname = "real_R2_%s_%s" % (tag, time.strftime("%H%M%S"))
    setv("Control_FileName_Text", fname)
    setv("GalJump_initCur_txt", 0)
    setv("GalJump_initTime_txt", 1000)
    setv("GalJump_Jump1_txt", curr_ma)
    setv("GalJump_Jump1Time_txt", 6000)
    setv("GalJump_frq_txt", 10)     # 10 Hz
    ocp = ""
    try: ocp = str(ids["Control_Ocp_Text"].legacy_properties().get("Value") or "")
    except Exception: pass
    log("  参数: I=%s mA, OCP字段=%s, 文件=%s" % (curr_ma, ocp, fname))

    # ★ 用相同关键字收集已有运行窗，并用 expect 精确匹配本轮文件名
    kw = ("恒电流", "阶跃")
    before = set(driver5.all_run_hwnds(keywords=kw))
    driver5.msg_click(ids["GalJump_Ok_Btn"])
    log("  已点确定，等运行窗（expect=%s）…" % fname)
    rw = st.find_run_window(timeout=25, keywords=kw, exclude=before, expect=fname)
    if rw is None:
        log("  运行窗没出现"); return None
    log("  运行窗: " + rw.window_text()[:70])

    # 等实验跑完（阶跃 6s + 余量），期间不干扰
    time.sleep(8.0)
    # 停 + 关窗
    try: st.stop_run(rw)
    except Exception: pass
    time.sleep(0.8)

    # 找本轮 .cor
    paths = [os.path.join(BASE, f) for f in os.listdir(BASE)
             if f.startswith(fname) and f.endswith(".cor")]
    if not paths:
        log("  .cor 未落盘"); return None
    cor = max(paths, key=os.path.getmtime)
    log("  .cor: %s (%d B)" % (os.path.basename(cor), os.path.getsize(cor)))
    close_run_windows()
    return cor

def parse_cor(path):
    """返回 (E_med, i_med, n) —— 稳态段 t>=2.8s 中位数。"""
    lines = io.open(path, encoding="utf-8", errors="ignore").read().splitlines()
    di = next(i for i, l in enumerate(lines) if l.startswith("E(") or l.startswith("E\t"))
    rows = []
    for l in lines[di + 1:]:
        p = l.split("\t") if "\t" in l else l.split()
        if len(p) >= 3:
            try: rows.append(tuple(float(x) for x in p[:3]))
            except ValueError: pass
    steady = [r for r in rows if r[2] >= 2.8]
    if len(steady) < 5: return None
    return (statistics.median([r[0] for r in steady]),
            statistics.median([r[1] for r in steady]), len(steady))

def main():
    currs = [0.1, 0.15]
    if "--curr" in sys.argv:
        i = sys.argv.index("--curr")
        currs = [float(x) for x in sys.argv[i + 1:] if not x.startswith("--")]

    st = driver5.Studio5(log=log)
    if not st.find_main(): log("FATAL 主窗"); return 2
    log("主窗: " + st.title())
    if "CS350" not in st.title(): log("FATAL 未连真机"); return 2
    log("先关残留运行窗 %d 个" % close_run_windows())

    results = []
    for mA in currs:
        log("")
        log("======== 档 ±%.3f mA ========" % mA)
        pos = run_one(st, mA, "p")
        time.sleep(1.5)
        neg = run_one(st, -mA, "n")
        if pos and neg:
            a, b = parse_cor(pos), parse_cor(neg)
            if a and b:
                dE, di = a[0] - b[0], a[1] - b[1]
                R_set = dE / (2 * mA * 1e-3)
                R_col = dE / di
                results.append(dict(mA=mA, Ep=a[0], En=b[0], ip=a[1], inn=b[1],
                                    dE=dE, di=di, R_set=R_set, R_col=R_col,
                                    npos=a[2], nneg=b[2]))
                log("  稳态 E+=%+.6f E−=%+.6f  ΔE=%.6f V" % (a[0], b[0], dE))
                log("  i+=%+.4e i−=%+.4e  Δi=%.4e" % (a[1], b[1], di))
                log("  R(设定电流)=%.1f Ω   R(i列)=%.1f Ω" % (R_set, R_col))
            else:
                log("  .cor 稳态解析失败")
        else:
            log("  本档有轮次失败（pos=%s neg=%s）" % (bool(pos), bool(neg)))

    log("")
    log("======== 汇总 ========")
    if not results:
        log("RESULT_JSON " + json.dumps({"ok": False})); return 6
    for r in results:
        log("  ±%.3f mA: ΔE=%.6f V  R_set=%.1f Ω  R_col=%.1f Ω  (n=%d/%d)"
            % (r["mA"], r["dE"], r["R_set"], r["R_col"], r["npos"], r["nneg"]))
    # 跨档线性检验：ΔE 对设定电流做最小二乘斜率 → R = slope/2（双极性）
    if len(results) >= 2:
        xs = [2 * r["mA"] * 1e-3 for r in results]   # ΔI(设定)
        ys = [r["dE"] for r in results]
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
        den = sum((x-mx)**2 for x in xs)
        R_fit = num/den if den else float("nan")
        log("  跨档线性拟合 R = %.1f Ω（斜率法，最抗偏置）" % R_fit)
        # 重复性：各档 R_set 的离散
        rs = [r["R_set"] for r in results]
        log("  各档 R_set 离散: mean=%.1f Ω  spread=%.1f Ω" % (sum(rs)/len(rs), max(rs)-min(rs)))
        log("RESULT_JSON " + json.dumps({"ok": True, "R_fit_ohm": round(R_fit, 1),
              "runs": [{"mA": r["mA"], "R_set": round(r["R_set"], 1),
                        "R_col": round(r["R_col"], 1), "dE": round(r["dE"], 6)}
                       for r in results]}))
    else:
        log("RESULT_JSON " + json.dumps({"ok": True,
              "R_set": round(results[0]["R_set"], 1), "R_col": round(results[0]["R_col"], 1)}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
