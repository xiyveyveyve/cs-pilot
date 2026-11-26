# -*- coding: utf-8 -*-
"""tools/watch_exp.py —— 盯实验，关键时刻发邮件。

python tools/watch_exp.py --interval 300 --to 2248644356@qq.com
事件：
  * 运行窗消失（含软件崩溃）→ 发「实验停止」
  * 槽压 > 6 V → 发「电压异常」（接近 8 V 限压）
  * 累计时间 >= 目标 → 发「实验完成」（只发一次）
每轮都写 logs/watch_MMDD.txt
"""
import sys, os, time, json, subprocess, datetime
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CLI = os.path.join(os.path.expanduser("~"), ".dsh/profiles/web/node_modules/@tencent-qqmail/agently-cli")
LOGDIR = "logs"; os.makedirs(LOGDIR, exist_ok=True)

def mail(to, subj, body):
    try:
        r = subprocess.run(["node", "scripts/run.js", "message", "+send", "--confirmed",
                            "--to", to, "--subject", subj, "--body", body],
                           cwd=CLI, capture_output=True, text=True, timeout=90)
        ok = '"ok": true' in (r.stdout or "")
        print("[mail]", ok, (r.stdout or "")[:120].replace("\n", " "))
        return ok
    except Exception as e:
        print("[mail] 失败", type(e).__name__, e); return False

def read_runwin():
    from pywinauto import Application
    import win32gui
    found = []
    def cb(h, _):
        t = win32gui.GetWindowText(h) or ""
        if win32gui.IsWindowVisible(h) and t.startswith("恒电流极化"):
            found.append((h, t))
        return True
    win32gui.EnumWindows(cb, None)
    if not found:
        return None
    h, title = found[0]
    try:
        app = Application(backend="uia").connect(handle=h)
        w = app.window(handle=h)
        tx = [c.window_text() for c in w.descendants(control_type="Text") if c.window_text()]
    except Exception as e:
        return {"hwnd": h, "title": title, "err": str(e), "texts": []}
    import re
    nums, secs, pts = [], [], []
    for t in tx:
        s0 = t.strip()
        if not s0:
            continue
        if re.fullmatch(r"\d+\.\d{2}", s0):      # 15xxx.00 = 秒
            secs.append(float(s0)); continue
        if re.fullmatch(r"\d+", s0):                # 3164 = 点数
            pts.append(int(s0)); continue
        try:
            nums.append(float(s0.replace(" ", "")))
        except Exception:
            pass
    return {"hwnd": h, "title": title, "texts": tx, "nums": nums,
            "secs": secs, "pts": pts}

def main():
    interval = 300
    to = "2248644356@qq.com"
    target_s = 86400.0
    if "--interval" in sys.argv: interval = float(sys.argv[sys.argv.index("--interval")+1])
    if "--to" in sys.argv: to = sys.argv[sys.argv.index("--to")+1]
    if "--target" in sys.argv: target_s = float(sys.argv[sys.argv.index("--target")+1])
    log = os.path.join(LOGDIR, "watch_%s.txt" % datetime.datetime.now().strftime("%m%d"))
    done = False; warned = 0; gone = 0; last = None
    print("[watch] start interval=%ss to=%s target=%ss" % (interval, to, target_s))
    while True:
        r = read_runwin()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = ""
        if r is None:
            gone += 1
            line = "%s 运行窗不存在（连续 %d 次）" % (ts, gone)
            if gone in (2, 6):   # 10 min / 30 min 各报一次，避免抖噪
                mail(to, "CS350 实验似乎已停止", "在 %s 找不到恒电流极化运行窗（连续 %d 次检查）。可能：实验结束/被停/软件关掉。\n请回电脑确认，或让我读 .cor 文件。" % (ts, gone))
        else:
            gone = 0
            nums = r.get("nums", [])
            secs = r.get("secs", []); pts = r.get("pts", [])
            E = None
            for v in nums:
                if 0.1 <= v <= 12.0: E = v; break
            T = secs[0] if secs else None
            N = pts[0] if pts else None
            line = "%s hwnd=%s E=%s T=%s N=%s texts=%s" % (ts, r["hwnd"], E, T, N, r.get("texts", [])[:6])
            if E is not None and E > 6.0 and warned < 3:
                warned += 1
                mail(to, "CS350 电压异常 %.2f V" % E, "槽压已到 %.2f V（限压 8 V）。常见原因：液膜干涸、接触断开、溶液耗尽。\n时间 %s\n建议回来看一眼。" % (E, ts))
            if T is not None and T >= target_s * 0.999 and not done:
                done = True
                mail(to, "CS350 实验已跑满 %d h" % int(target_s/3600), "运行窗读数：T=%s 秒、E=%s V。\n可以关运行窗，我来解析 .cor 出报告。" % (T, E))
        print(line); open(log, "a", encoding="utf-8").write(line + "\n")
        time.sleep(interval)

if __name__ == "__main__":
    main()
