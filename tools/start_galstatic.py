# -*- coding: utf-8 -*-
"""start_galstatic.py —— 用「稳态极化→恒电流极化」跑长时恒流电解（时间单位=秒，有停止电压）。

用法：python tools/start_galstatic.py --ma 0.5 --sec 172800 --stopv 8 --inter 5 --tag s1
"""
import sys, os, time, io, json, statistics, win32gui, win32con
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseek\cspilot-parasite")
import driver5

BASE = r"D:\deepseek\_probe\e2e5"
LOG  = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\start_galstatic.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception: pass
def A(n,d): return float(sys.argv[sys.argv.index(n)+1]) if n in sys.argv else d
def S(n,d): return sys.argv[sys.argv.index(n)+1] if n in sys.argv else d

def kill(kw):
    n=0
    def cb(h,_):
        nonlocal n
        t=win32gui.GetWindowText(h) or ""
        if kw in t and win32gui.IsWindowVisible(h):
            win32gui.PostMessage(h, win32con.WM_CLOSE,0,0); n+=1
        return True
    win32gui.EnumWindows(cb,None); return n

def items(st):
    return [(t,r,c) for t,r,c in st.menu_items() if (r.right-r.left)>8 and (r.bottom-r.top)>4]

def open_panel(st):
    st.close_user_settings()
    try: st.main.set_focus()
    except Exception: pass
    time.sleep(0.5)
    st.click_main_menu("测试方法(E)"); time.sleep(0.8)
    for name in ("稳态极化(S)", "恒电流极化(G)"):
        hit=None
        for t,r,c in items(st):
            if t==name: hit=(r,c); break
        if hit is None:
            log("菜单 '%s' 不可见" % name); return None
        driver5.msg_click(hit[1]); time.sleep(0.9)
    return st.find_panel_by_title("恒电流极化", timeout=4.0)

def snap_new(pre, f=None):
    out=[]
    def cb(h,_):
        if win32gui.IsWindowVisible(h):
            t=win32gui.GetWindowText(h) or ""
            if t.strip() and t not in pre:
                kids=[]
                def cb2(hc,_2):
                    tc=win32gui.GetWindowText(hc) or ""
                    if tc.strip(): kids.append(tc)
                    return True
                win32gui.EnumChildWindows(h,cb2,None)
                out.append((t,kids))
        return True
    win32gui.EnumWindows(cb,None)
    return out

def main():
    ma=A("--ma",0.5); sec=int(A("--sec",172800)); stopv=A("--stopv",8.0)
    inter=A("--inter",5.0); tag=S("--tag","s1")
    log("")
    log("======== galstatic %s @ %s ========" % (tag, time.strftime("%Y-%m-%d %H:%M:%S")))
    log("目标 %.3f mA / %d s (%.2f h) / 间隔 %.1f s / 停止电压上限 %.1f V" % (ma, sec, sec/3600., inter, stopv))

    st=driver5.Studio5(log=log)
    if not st.find_main(): log("FATAL 主窗"); return 2
    if "CS350" not in st.title(): log("FATAL 未连真机"); return 2
    log("主窗: "+st.title())
    log("清理: 输入错误=%d" % kill("输入错误")); time.sleep(0.6)
    log("清理: 旧面板=%d" % kill("恒电流极化")); time.sleep(0.8)

    p=open_panel(st)
    if p is None: log("FATAL 面板"); return 3
    ids=st.by_ids(p)
    btns=[(c.window_text() or "", c) for c in p.descendants(control_type="Button")]
    log("按钮: %s" % [b[0] for b in btns])

    fname="exp48h_%s_%s" % (tag, time.strftime("%m%d_%H%M"))
    pairs=[("Control_FileName_Text", fname),
           ("GalStatic_Param_Curr_Text", "%g" % ma),
           ("GalStatic_Param_Time_Text", str(sec)),
           ("FrqControl_Inter_Text", "%g" % inter)]
    for aid,v in pairs:
        c=ids.get(aid)
        if c is None: log("FATAL 缺控件 %s" % aid); return 4
        ok=st.set_edit(c,v)
        log("  %-32s = %-14s set=%s 读回=%r" % (aid, v, ok, c.get_value()))

    # 采样切「间隔」模式
    for aid in ("FrqControl_Inter_Radio",):
        c=ids.get(aid)
        if c is not None:
            try: c.click_input(); time.sleep(0.3); log("  已选 %s" % aid)
            except Exception as e: log("  %s 点击失败 %s" % (aid, e))
    # 停止条件：电压
    c=ids.get("GalStatic_Stop_Volt_Radio")
    if c is not None:
        try: c.click_input(); time.sleep(0.3); log("  已选停止条件=电压")
        except Exception as e: log("  停止条件点击失败 %s" % e)
    for aid,v in [("GalStatic_Stop_Volt_More_Text", "%g" % stopv),
                  ("GalStatic_Stop_Volt_Less_Text", "-8")]:
        c=ids.get(aid)
        if c is not None:
            ok=st.set_edit(c,v)
            log("  %-32s = %-8s set=%s 读回=%r" % (aid, v, ok, c.get_value()))

    ok_btn=None
    for t,c in btns:
        if "确定" in t or "OK" in t.upper(): ok_btn=c; break
    if ok_btn is None:
        log("FATAL 找不到确定按钮"); return 5

    pre={t for t,_ in snap_new(set())}
    log("点确定…")
    ok_btn.click_input()
    time.sleep(0.5)

    rw=None
    for k in range(30):
        time.sleep(0.5)
        new=snap_new(pre)
        for t,kids in new:
            if "阶跃" in t or "极化" in t:
                if ".cor" in t or "<" in t: rw=t
            log("  [新窗] %s | %s" % (t[:50], " | ".join(x[:60] for x in kids[:3])))
        pre={t for t,_ in snap_new(set())}
        if rw: break
    if rw is None:
        log("FATAL 运行窗没出现（见上方 [新窗] 的错误文本）"); return 6
    log("运行窗: %s" % rw[:110])

    cor=None; lastE=None
    for k in range(8):
        time.sleep(2.5)
        cur=[os.path.join(BASE,f) for f in os.listdir(BASE) if f.startswith(fname) and f.endswith(".cor")]
        if cur:
            cor=max(cur,key=os.path.getmtime)
            try:
                lines=io.open(cor,encoding="utf-8",errors="ignore").read().splitlines()
                di=next(i for i,l in enumerate(lines) if l.startswith("E(") or l.startswith("E\t"))
                vals=[]
                for l in lines[di+1:]:
                    q=l.split("\t") if "\t" in l else l.split()
                    if len(q)>=3:
                        try: vals.append(float(q[0]))
                        except ValueError: pass
                if vals: lastE=statistics.median(vals[-5:])
            except Exception: pass
        log("  +%.0fs  %s  E=%s" % ((k+1)*2.5, os.path.basename(cor) if cor else "-",
                                    ("%+.4f V" % lastE) if lastE is not None else "-"))
    log("RESULT_JSON " + json.dumps({"ok": True, "file": fname, "ma": ma, "sec": sec,
                                     "E": lastE, "cor": cor}, ensure_ascii=False))
    return 0

if __name__=="__main__":
    sys.exit(main())
