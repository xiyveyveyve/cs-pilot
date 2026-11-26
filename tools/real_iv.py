# -*- coding: utf-8 -*-
"""real_iv.py —— 单极性正向 E–I 曲线（CFRP 作阳极），判断 ~1 V 是接触电阻还是反应开启电压。

用法：python tools/real_iv.py --curr 0.1 0.2 0.5 1 2
"""
import sys, os, time, io, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import real_r_gui4 as R

OUT = r"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\real_iv.txt"

def log(m):
    print(m, flush=True)
    try:
        with io.open(OUT, "a", encoding="utf-8") as f: f.write(m + "\n")
    except Exception:
        pass

def main():
    currs = [0.1, 0.2, 0.5, 1.0, 2.0]
    if "--curr" in sys.argv:
        i = sys.argv.index("--curr")
        currs = [float(x) for x in sys.argv[i + 1:] if not x.startswith("--")]

    st = R.driver5.Studio5(log=log)
    if not st.find_main():
        log("FATAL 主窗"); return 2
    log("主窗: " + st.title())
    log("先关残留运行窗 %d 个" % R.close_run_windows())

    res = []
    for mA in currs:
        log("")
        log("---- 正向 %+.3f mA ----" % mA)
        cor = R.run_one(st, mA, "iv")
        time.sleep(1.0)
        if not cor:
            log("  本轮失败"); continue
        a = R.parse_cor(cor)
        if not a:
            log("  .cor 解析失败"); continue
        E, iA, n = a
        Rq = E / (mA * 1e-3)
        log("  稳态 E=%+.6f V   i列=%.3e A   等效R=%.1f Ω" % (E, iA, Rq))
        res.append((mA, E, Rq, n))

    log("")
    log("======== E–I 汇总（CFRP 作阳极）========")
    for mA, E, Rq, n in res:
        log("  %6.3f mA   E=%+8.4f V   R=%8.0f Ω   (n=%d)" % (mA, E, Rq, n))
    if len(res) >= 2:
        log("  ---- 万用表式差分电阻 dE/dI（判断线性度）----")
        for k in range(1, len(res)):
            dE = res[k][1] - res[k-1][1]
            dI = (res[k][0] - res[k-1][0]) * 1e-3
            log("  %.3f→%.3f mA :  dE=%+.4f V   dR=%8.0f Ω"
                % (res[k-1][0], res[k][0], dE, (dE / dI) if dI else float('nan')))
    log("RESULT_JSON " + json.dumps({"ok": True, "points": [
        {"mA": m, "E": round(E, 4), "R": round(Rq)} for m, E, Rq, _ in res]}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
