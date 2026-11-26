# -*- coding: utf-8 -*-
"""tools/notify.py —— 把消息推到手机（企业微信机器人 / Server 酱 / 邮件）。

用法:
    python tools/notify.py --text "实验完成" [--title "CS350"]
    python tools/notify.py --monitor          # 读运行窗电压，超阈值才推

配置: 与本文件同目录的 notify.json（gitignore 掉），形如
{
  "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=XXXX",
  "serverchan_key": "SCTxxxxx",
  "smtp": {"host":"smtp.qq.com","port":465,"user":"xx@qq.com","pass":"授权码","to":"xx@qq.com"}
}
只填其中一个即可，都填就都发。
"""
import sys, os, json, time, urllib.request, urllib.parse, ssl, smtplib, win32gui
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.json")

def load_cfg():
    if not os.path.exists(CFG):
        return {}
    try:
        return json.load(open(CFG, encoding="utf-8"))
    except Exception as e:
        print("[notify] 配置读取失败:", e); return {}

def push_wecom(url, text):
    body = json.dumps({"msgtype":"text","text":{"content":text}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8","ignore")

def push_serverchan(key, title, text):
    body = urllib.parse.urlencode({"title":title,"desp":text}).encode("utf-8")
    req = urllib.request.Request("https://sctapi.ftqq.com/%s.send" % key, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8","ignore")

def push_mail(c, title, text):
    msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n%s" % (c["user"], c["to"], title, text)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(c["host"], int(c.get("port",465)), context=ctx, timeout=15) as s:
        s.login(c["user"], c["pass"]); s.sendmail(c["user"], [c["to"]], msg.encode("utf-8"))
    return "mail ok"

def notify(title, text):
    cfg = load_cfg(); outs = []
    if cfg.get("wecom_webhook"):
        try: outs.append("wecom:" + push_wecom(cfg["wecom_webhook"], title + "\n" + text)[:120])
        except Exception as e: outs.append("wecom 失败:%s" % type(e).__name__)
    if cfg.get("serverchan_key"):
        try: outs.append("sct:" + push_serverchan(cfg["serverchan_key"], title, text)[:120])
        except Exception as e: outs.append("sct 失败:%s" % type(e).__name__)
    if cfg.get("smtp"):
        try: outs.append(push_mail(cfg["smtp"], title, text))
        except Exception as e: outs.append("mail 失败:%s" % type(e).__name__)
    if not outs:
        outs.append("未配置任何通道（写 tools/notify.json）")
    return " | ".join(outs)

def read_runwin():
    """读当前恒电流极化运行窗: (点数, 秒, 电压)"""
    from pywinauto import Application
    found=[]
    def cb(h,_):
        t = win32gui.GetWindowText(h) or ""
        if win32gui.IsWindowVisible(h) and t.startswith("恒电流极化"): found.append(h)
        return True
    win32gui.EnumWindows(cb,None)
    if not found: return None
    app = Application(backend="uia").connect(handle=found[0]); w = app.window(handle=found[0])
    tx = [c.window_text() for c in w.descendants(control_type="Text") if c.window_text()]
    E = None
    for t in tx:
        if "E" in t and t.replace("E","").replace("+","").replace("-","").replace(".","").isdigit():
            E = float(t); break
    nums = [float(t) for t in tx if t.replace(".","").replace(" ","").isdigit() and float(t) > 10]
    return (nums[0] if nums else None, nums[1] if len(nums)>1 else None, E)

if __name__ == "__main__":
    if "--text" in sys.argv:
        i = sys.argv.index("--text")
        text = sys.argv[i+1] if len(sys.argv) > i+1 else ""
        title = "CS350 实验"
        if "--title" in sys.argv:
            j = sys.argv.index("--title"); title = sys.argv[j+1]
        print(notify(title, text))
    elif "--monitor" in sys.argv:
        r = read_runwin()
        print("运行窗读数:", r)
        if r:
            n, t, E = r
            print(notify("CS350 进度", "点=%s 时间=%ss 电压=%.4f V" % (n, t, E) if E else str(r)))
        else:
            print(notify("CS350 警告", "找不到运行窗：实验可能已停止"))
    else:
        print("用法见文件头")
