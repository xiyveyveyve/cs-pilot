# -*- coding: utf-8 -*-
"""real_r_gui3.py —— 软件本体连真机，恒电流阶跃测电阻（完整流程）。

菜单：测试方法(E) → 暂态极化(T) → 恒电流阶跃(G)（注意是暂态极化支）。
控件：GalJump_*（软件内部 GalJump=ID_GalJump）。
测量：Jump1 电流 I 阶跃，读运行窗 E 稳定值，R = E/I。
双极性可选：--neg 再跑一轮 -I，R = (E+ - E-)/(2I) 消偏移。
"""
import sys, os, time, io, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")

import driver5, studio_ui as SU
from uiprobe import UiSampler

OUT = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\real_r_gui3.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(OUT, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass

def open_panel(st):
    """逐级展开三级菜单打开恒电流阶跃参数窗。"""
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
        log("  点 '%s'" % name)
        time.sleep(0.8)
    return st.find_panel_by_title("恒电流阶跃", timeout=3.0)

def run_one(st, curr_ma, tag):
    p = open_panel(st)
    if p is None: log("  FATAL 参数窗没打开"); return None
    ids = st.by_ids(p)
    log("  参数窗: " + p.window_text())

    def setv(aid, val):
        c = ids.get(aid)
        if c is None: log("  缺控件 " + aid); return False
        ok = st.set_edit(c, str(val))
        log("  %-26s <- %-10s %s" % (aid, val, "OK" if ok else "FAIL"))
        return ok

    fname = "real_R_%s_%s" % (tag, time.strftime("%H%M%S"))
    setv("Control_FileName_Text", fname)
    setv("GalJump_initCur_txt", 0)             # 初始电流 0
    setv("GalJump_initTime_txt", 1000)          # 初始 1s
    setv("GalJump_Jump1_txt", curr_ma)          # 阶跃电流 mA
    setv("GalJump_Jump1Time_txt", 6000)         # 阶跃持续 6s
    setv("GalJump_Jump2_txt", 0)
    setv("GalJump_Jump2Time_txt", 0)
    setv("GalJump_frq_txt", 10)                 # 10Hz
    # 单位下拉保持默认 mA / ms
    log("  OCP 字段(活读数): " + str(ids.get("Control_Ocp_Text").legacy_properties().get("Value")))

    # 记录启动前已有运行窗
    before = set(driver5.all_run_hwnds())
    driver5.msg_click(ids["GalJump_Ok_Btn"])
    log("  已点确定，等运行窗…")
    # ★ 恒电流阶跃运行窗标题不含默认关键字，必须显式加
    rw = st.find_run_window(timeout=25, exclude=before, keywords=("恒电流", "阶跃"))
    if rw is None: log("  运行窗没出现"); return None
    log("  运行窗: " + rw.window_text()[:70])

    # 读界面 E（UiSampler）
    samp = UiSampler(rw, log=None)
    vals = []
    t0 = time.time()
    while time.time() - t0 < 9:
        time.sleep(0.5)
        try:
            s = samp.read()
            if s and s.e_volt is not None:
                vals.append((s.t_sec, s.e_volt, s.i_amp))
        except Exception: pass
    log("  采样 %d 点" % len(vals))
    if len(vals) < 5: return None
    # 取阶跃稳定段（后半）中位数
    tail = [v[1] for v in vals[len(vals)//3:]]
    tail.sort()
    e_med = tail[len(tail)//2]
    log("  E_med = %.6f V   (首 %.6f 末 %.6f)" % (e_med, vals[0][1], vals[-1][1]))
    # 停止实验（点运行窗数据栏停止键）
    try: st.stop_run(rw)
    except Exception as e: log("  stop 失败(忽略): %s" % e)
    time.sleep(1.0)
    return {"I_mA": curr_ma, "E": e_med, "n": len(vals), "file": fname}

def main():
    curr = 0.1
    for i, a in enumerate(sys.argv[1:]):
        if a == "--curr" and i + 2 <= len(sys.argv): curr = float(sys.argv[i+2])
    st = driver5.Studio5(log=log)
    if not st.find_main(): log("FATAL 主窗"); return 2
    log("主窗: " + st.title())
    if "CS350" not in st.title(): log("FATAL 未连真机"); return 2

    pos = run_one(st, curr, "pos")
    time.sleep(2)
    neg = run_one(st, -curr, "neg")
    if pos and neg:
        di = (pos["I_mA"] - neg["I_mA"]) * 1e-3
        de = pos["E"] - neg["E"]
        R = de / di
        log("=== 双极性 R = ΔE/ΔI = %.6f / %.6g = %.2f Ω ===" % (de, di, R))
        log("RESULT_JSON " + json.dumps({"ok": True, "R_ohm": round(R, 2),
              "E_pos": round(pos["E"], 6), "E_neg": round(neg["E"], 6),
              "I_mA": curr, "n_pos": pos["n"], "n_neg": neg["n"]}))
    elif pos:
        R = pos["E"] / (pos["I_mA"] * 1e-3)
        log("=== 单极性 R = E/I = %.2f Ω ===" % R)
        log("RESULT_JSON " + json.dumps({"ok": True, "R_ohm": round(R, 2),
              "E": round(pos["E"], 6), "I_mA": curr, "n": pos["n"], "single": True}))
    else:
        log("RESULT_JSON {\"ok\": false}")
        return 6
    return 0

if __name__ == "__main__":
    sys.exit(main())
