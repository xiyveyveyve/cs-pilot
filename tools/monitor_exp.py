# -*- coding: utf-8 -*-
"""monitor_exp.py —— 长时实验在线监视：读运行窗实时点位/时间/电压 + .cor 字节数，追加写日志。

用法：
  python tools/monitor_exp.py                  # 前台，每 60 s 一条（Ctrl+C 停）
  python tools/monitor_exp.py --interval 300   # 5 min 一条
"""
import sys, os, time, io
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import win32gui
from pywinauto import Application

LOGD = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs"
def _latest_cor():
    import glob
    fs = glob.glob(r"D:\deepseek\_probe\e2e5\exp48h*.cor")
    return max(fs, key=os.path.getmtime) if fs else ""
COR  = _latest_cor()
INTERVAL = 60
if "--interval" in sys.argv: INTERVAL = int(sys.argv[sys.argv.index("--interval")+1])

def log(m):
    t = time.strftime("%m-%d %H:%M:%S")
    print(t, m, flush=True)
    try:
        d = os.path.join(LOGD, "monitor_%s.txt" % time.strftime("%m%d"))
        with io.open(d, "a", encoding="utf-8") as f: f.write("%s\t%s\n" % (t, m))
    except Exception: pass

def find_run():
    hit = [None]
    def cb(h, _):
        t = win32gui.GetWindowText(h) or ""
        if win32gui.IsWindowVisible(h) and t.startswith("恒电流极化"):
            hit[0] = h
        return True
    win32gui.EnumWindows(cb, None)
    return hit[0]

def read_live():
    h = find_run()
    if not h: return None
    try:
        app = Application(backend="uia").connect(handle=h)
        w = app.window(handle=h)
        txt = [c.window_text() for c in w.descendants()
               if (c.element_info.control_type or "") == "Text" and c.window_text()]
        num = [t for t in txt if t.replace(".", "").replace("E+0", "").replace("E+", "").replace("-", "").isdigit()]
        pct = next((t for t in txt if t.endswith("%")), "?")
        E   = next((t for t in txt if "E+" in t or ("." in t and len(t) > 5 and t[0].isdigit() is False)), None)
        # 结构化：前 3 个数字依次是 点、秒、E
        import re
        cur = [t for t in txt if re.fullmatch(r"[+-]?\d+\.?\d*(E[+-]\d+)?", t)]
        pts = sec = ev = None
        if len(cur) >= 3:
            try:
                pts = int(float(cur[0])); sec = float(cur[1]); ev = float(cur[2])
            except Exception: pass
        return {"hwnd": h, "pct": pct, "pts": pts, "sec": sec, "E": ev, "raw": cur[:5]}
    except Exception as e:
        return {"hwnd": h, "err": str(e)}

def main():
    log("=== monitor 启动（间隔 %d s）===" % INTERVAL)
    while True:
        st = read_live()
        try: sz = os.path.getsize(COR) if os.path.exists(COR) else -1
        except Exception: sz = -2
        if st is None:
            log("运行窗不见了 —— 实验可能已结束（.cor=%s B）" % sz); return 0
        log("进度 %s | 点=%s 时间=%ss E=%s V | .cor=%s B" % (
            st.get("pct"), st.get("pts"), st.get("sec"),
            ("%.4f" % st["E"]) if st.get("E") is not None else "-", sz))
        time.sleep(INTERVAL)

if __name__ == "__main__":
    sys.exit(main())
