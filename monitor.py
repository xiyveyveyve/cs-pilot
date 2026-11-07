# -*- coding: utf-8 -*-
"""monitor.py —— CS Pilot 多机集中看板（多台单通道机方案，2026-11-07）。

每台机器跑自己的 gui.py 并勾选"上报到多机看板"（指向同一共享目录），
主控机运行本脚本：每秒扫描目录聚合全部 <机器名>.json，
每台机器一张卡片（状态徽章 / 当前步骤 / 实时指标 / 产物 / 心跳年龄），
超过 15 秒没有心跳自动标"失联"变灰。

启动：python monitor.py [看板目录]
      目录缺省 C:\\Users\\xiyve\\Desktop\\CS-Pilot看板（与 gui.py 默认一致）
"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from status_report import load_board, age_sec, STALE_SEC   # noqa: E402

# 与 gui.py 同一套配色
BG = "#f4f6fa"
CARD = "#ffffff"
FG = "#1c2430"
SUB = "#7a8699"
LINE = "#dfe5ee"
ACCENT = "#2f6fed"
OK = "#188a42"
WARN = "#e07b00"
ERR = "#d23b3b"
GREY = "#9aa5b1"

FONT = ("Microsoft YaHei UI", 9)
FONT_S = ("Microsoft YaHei UI", 8)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_T = ("Microsoft YaHei UI", 13, "bold")
FONT_MONO = ("Consolas", 9)


def state_color(state: str):
    if "出错" in state:
        return ERR
    if "完成" in state:
        return OK
    if "中止" in state:
        return WARN
    return ACCENT


class Monitor:
    def __init__(self, root: tk.Tk, board_dir: str):
        self.root = root
        self.dir = board_dir
        root.title("CS Pilot · 多机看板")
        root.geometry("1180x760")
        root.configure(bg=BG)
        root.minsize(900, 560)

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(head, text="多机看板", font=FONT_T, bg=BG, fg=ACCENT).pack(side="left")
        self.lbl_sum = tk.Label(head, text="", font=FONT, bg=BG, fg=SUB)
        self.lbl_sum.pack(side="left", padx=12, pady=(6, 0))
        tk.Label(head, text=board_dir, font=FONT_S, bg=BG, fg=SUB).pack(side="right")

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.cv = tk.Canvas(self.body, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(self.body, command=self.cv.yview, width=10)
        self.inner = tk.Frame(self.cv, bg=BG)
        self.cv.create_window((0, 0), window=self.inner, anchor="nw",
                               tags="inner")
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.cv.configure(
            scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(
            "inner", width=e.width))
        # 滚轮
        self.cv.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        self.refresh()
        root.after(1000, self.refresh)

    # ------------------------------------------------------------------
    def refresh(self):
        # 整个刷新体必须防异常：refresh 是 after 链的一环，抛一次异常
        # 链就断了——看板永久冻结（比崩溃更糟，看起来像"没数据"）
        try:
            self._refresh_body()
        except Exception as e:      # noqa: BLE001
            try:
                self.lbl_sum.configure(text="刷新出错（已自动重试）：%r" % (e,))
            except Exception:
                pass
        self.root.after(1000, self.refresh)

    def _refresh_body(self):
        recs, bad = load_board(self.dir)
        now_cnt = sum(1 for r in recs if age_sec(r) <= STALE_SEC)
        stale_cnt = len(recs) - now_cnt
        self.lbl_sum.configure(
            text="%d 台机器 · %d 在线 · %d 失联%s"
                 % (len(recs), now_cnt, stale_cnt,
                    (" · %d 个坏文件" % len(bad)) if bad else ""))
        for w in self.inner.winfo_children():
            w.destroy()
        if not recs:
            tk.Label(self.inner, text="看板目录里还没有机器上报。\n"
                     "在每台机器的 gui.py 里勾选「上报到多机看板」并指向本目录。",
                     font=FONT, bg=BG, fg=SUB, justify="left", pady=40).pack()
        for rec in recs:
            try:
                self._card(rec)
            except Exception:       # noqa: BLE001
                # 单台机器字段损坏（metrics 不是字典之类）只影响它自己的卡片
                box = tk.Frame(self.inner, bg="#fdf0f0",
                               highlightbackground=ERR, highlightthickness=1)
                box.pack(fill="x", pady=5)
                tk.Label(box, text="%s · 状态数据异常（文件内容不符合看板格式）"
                         % rec.get("machine", "?"),
                         font=FONT, bg="#fdf0f0", fg=ERR, pady=8).pack()

    def _card(self, rec: dict):
        stale = age_sec(rec) > STALE_SEC
        box = tk.Frame(self.inner, bg=CARD if not stale else "#f0f1f4",
                       highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="x", pady=5)

        head = tk.Frame(box, bg=box["bg"])
        head.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(head, text=rec.get("machine", "?"), font=FONT_T,
                 bg=box["bg"], fg=FG if not stale else GREY).pack(side="left")

        state = rec.get("state", "?")
        color = GREY if stale else state_color(state)
        tk.Label(head, text=" ● " + state, font=FONT_B, bg=box["bg"],
                 fg=color).pack(side="left", padx=14)
        age = age_sec(rec)
        tk.Label(head,
                 text=("失联 %.0f s" % age) if stale else ("心跳 %.0f s 前" % age),
                 font=FONT_S, bg=box["bg"],
                 fg=ERR if stale else SUB).pack(side="right")

        meta = tk.Frame(box, bg=box["bg"])
        meta.pack(fill="x", padx=12, pady=(2, 0))
        tk.Label(meta, text="%s · %s cm² · %s · %s"
                 % (rec.get("sample") or "—", rec.get("area") or "—",
                    rec.get("item") or "—", rec.get("ver") or "—"),
                 font=FONT_S, bg=box["bg"], fg=SUB).pack(side="left")

        step = tk.Frame(box, bg=box["bg"])
        step.pack(fill="x", padx=12, pady=(4, 0))
        tk.Label(step, text="步骤", font=FONT_B, bg=box["bg"],
                 fg=FG if not stale else GREY).pack(side="left")
        tk.Label(step, text="　%s%s" % (rec.get("step") or "—",
                                       ("　·　" + rec["detail"]) if rec.get("detail") else ""),
                 font=FONT, bg=box["bg"], fg=FG if not stale else GREY,
                 anchor="w").pack(side="left", padx=4)

        m = rec.get("metrics") or {}
        mline = "E = —        斜率 = —        峰峰值 = —        保持 = —"
        if m.get("E") is not None:
            mline = ("E = %+.6f V      斜率 = %+.2f mV/min      峰峰值 = %.2f mV      保持 = %.0f s"
                     % (m.get("E", 0.0), m.get("slope", 0.0),
                        m.get("ppt", 0.0), m.get("held", 0.0)))
        tk.Label(box, text=mline, font=FONT_MONO, bg=box["bg"],
                 fg=FG if not stale else GREY, anchor="w").pack(fill="x", padx=12, pady=(4, 0))

        files = rec.get("files") or []
        if files:
            tk.Label(box, text="产物：" + "  ".join(files[:4])
                     + ("…" if len(files) > 4 else ""),
                     font=FONT_S, bg=box["bg"], fg=SUB, anchor="w").pack(
                fill="x", padx=12, pady=(2, 0))
        tail = rec.get("log_tail") or []
        if tail:
            tk.Label(box, text=tail[-1], font=FONT_S, bg=box["bg"], fg=SUB,
                     anchor="w").pack(fill="x", padx=12, pady=(2, 8))


def main():
    board = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\xiyve\Desktop\CS-Pilot看板"
    os.makedirs(board, exist_ok=True)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    Monitor(root, board)
    root.mainloop()


if __name__ == "__main__":
    main()
