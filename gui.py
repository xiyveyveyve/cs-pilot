# -*- coding: utf-8 -*-
"""独立运行窗口：输入样品信息 -> 寄生驱动 CS Studio -> 后台判稳 -> 自动停机接续。

启动：python gui.py
"""
from __future__ import annotations

import os
import sys
import time
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner as R
import runner5 as R5
import runner6 as R6
from stabilizer import StabConfig

_END_STATES = ("完成", "出错", "已中止")

FONT = ("Microsoft YaHei UI", 9)
FONT_B = ("Microsoft YaHei UI", 10, "bold")
FONT_T = ("Microsoft YaHei UI", 12, "bold")

BG = "#f7f9fb"
FG = "#1f2933"
ACCENT = "#2f7fd6"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.runner: R.Runner | None = None
        self.pts: list[tuple[float, float]] = []
        self.last_state = ""

        root.title("CS Pilot 寄生式自动检测")
        root.geometry("980x720")
        root.configure(bg=BG)
        root.minsize(880, 620)

        self._build_ui()
        self.root.after(250, self._tick)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = dict(padx=6, pady=3)

        # 标题
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(head, text="CS Pilot · 寄生式自动检测", font=FONT_T, bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(head, text="只填参数·不改软件默认设置", font=FONT, bg=BG, fg="#7b8794").pack(side="left", padx=10)

        # 输入区
        box1 = tk.LabelFrame(self.root, text=" 样品信息 ", font=FONT_B, bg=BG, fg=FG, bd=1, relief="groove")
        box1.pack(fill="x", padx=12, pady=6)
        row = tk.Frame(box1, bg=BG); row.pack(fill="x", **pad)
        tk.Label(row, text="样品型号", font=FONT, bg=BG).pack(side="left")
        self.var_sample = tk.StringVar(value="样品" + datetime.date.today().strftime("%m%d"))
        tk.Entry(row, textvariable=self.var_sample, font=FONT, width=16).pack(side="left", padx=(4, 14))

        tk.Label(row, text="试样面积", font=FONT, bg=BG).pack(side="left")
        self.var_area = tk.StringVar(value="1.0")
        tk.Entry(row, textvariable=self.var_area, font=FONT, width=8).pack(side="left", padx=(4, 2))
        tk.Label(row, text="cm²", font=FONT, bg=BG).pack(side="left", padx=(0, 14))

        tk.Label(row, text="软件版本", font=FONT, bg=BG).pack(side="left")
        self.var_ver = tk.StringVar(value="CS Studio6")
        ttk.Combobox(row, textvariable=self.var_ver,
                     values=["CS Studio6", "CS Studio5", "CS Studio6直开"],
                     state="readonly", width=15, font=FONT).pack(side="left", padx=(4, 14))

        tk.Label(row, text="测试项目", font=FONT, bg=BG).pack(side="left")
        self.var_item = tk.StringVar(value="Tafel")
        ttk.Combobox(row, textvariable=self.var_item, values=["Tafel", "Step"],
                     state="readonly", width=8, font=FONT).pack(side="left", padx=(4, 14))

        row_b = tk.Frame(box1, bg=BG); row_b.pack(fill="x", **pad)
        tk.Label(row_b, text="输出目录", font=FONT, bg=BG).pack(side="left")
        self.var_dir = tk.StringVar(value=r"C:\Users\xiyve\Desktop\CS-Pilot数据")
        tk.Entry(row_b, textvariable=self.var_dir, font=FONT, width=64).pack(side="left", padx=4)
        tk.Button(row_b, text="浏览", font=FONT, command=self._pick_dir).pack(side="left")

        # 参数区
        box2 = tk.LabelFrame(self.root, text=" 判稳与实验参数 ", font=FONT_B, bg=BG, fg=FG, bd=1, relief="groove")
        box2.pack(fill="x", padx=12, pady=6)

        def num(parent, label, default, width=6, unit=""):
            tk.Label(parent, text=label, font=FONT, bg=BG).pack(side="left")
            v = tk.StringVar(value=str(default))
            tk.Entry(parent, textvariable=v, font=FONT, width=width).pack(side="left", padx=(3, 1))
            if unit:
                tk.Label(parent, text=unit, font=FONT, bg=BG, fg="#7b8794").pack(side="left", padx=(0, 10))
            return v

        # 阶段 A：前 N 秒非常严格
        row2a = tk.Frame(box2, bg=BG); row2a.pack(fill="x", **pad)
        tk.Label(row2a, text="① 严格（前", font=FONT_B, bg=BG, fg="#c0392b").pack(side="left")
        self.v_strict_until = num(row2a, "", 600, 5, "s）  斜率<")
        self.v_slope_s = num(row2a, "", 1.0, 5, "mV/min   峰峰<")
        self.v_pp_s = num(row2a, "", 2.0, 5, "mV")

        # 阶段 B：之后放宽
        row2b = tk.Frame(box2, bg=BG); row2b.pack(fill="x", **pad)
        tk.Label(row2b, text="② 放宽", font=FONT_B, bg=BG, fg="#1f6bb8").pack(side="left", padx=(0, 8))
        self.v_slope = num(row2b, "斜率<", 5.0, 5, "mV/min")
        self.v_pp = num(row2b, "峰峰<", 5.0, 5, "mV")
        self.v_snap = num(row2b, "5min快照<", 15.0, 5, "mV")
        self.v_win = num(row2b, "窗口", 60, 4, "s")
        self.v_hold = num(row2b, "保持", 120, 4, "s")

        # 公共
        row2c = tk.Frame(box2, bg=BG); row2c.pack(fill="x", **pad)
        tk.Label(row2c, text="③ 公共", font=FONT_B, bg=BG, fg="#52606d").pack(side="left", padx=(0, 8))
        self.v_max = num(row2c, "最长等待", 1800, 6, "s")
        self.v_ocpt = num(row2c, "OCP测量时间", 1800, 6, "s")
        self.v_rounds = num(row2c, "最多轮数", 3, 2, "轮")

        # 交流阻抗（频率扫描-电位控制模式）
        row2d = tk.Frame(box2, bg=BG); row2d.pack(fill="x", **pad)
        self.var_eis = tk.BooleanVar(value=True)
        tk.Checkbutton(row2d, text="④ 交流阻抗", variable=self.var_eis,
                       font=FONT_B, bg=BG, fg="#7b3fa0", activebackground=BG,
                       selectcolor=BG).pack(side="left", padx=(0, 8))
        self.v_eis_amp = num(row2d, "幅值", 10.0, 5, "mV")
        self.v_eis_hi = num(row2d, "频率", 100000, 8, "Hz →")
        self.v_eis_lo = num(row2d, "", 0.01, 6, "Hz  ")
        self.v_eis_pts = num(row2d, "点/10倍频", 10, 4, "")

        # 按钮 + 状态
        box3 = tk.Frame(self.root, bg=BG)
        box3.pack(fill="x", padx=12, pady=4)
        self.btn_start = tk.Button(box3, text="开始检测", font=FONT_B, bg=ACCENT, fg="white",
                                   activebackground="#1f6bb8", relief="flat", width=14,
                                   command=self.on_start)
        self.btn_start.pack(side="left")
        self.btn_stop = tk.Button(box3, text="中止", font=FONT, width=8, state="disabled",
                                  command=self.on_abort)
        self.btn_stop.pack(side="left", padx=8)
        self.lbl_state = tk.Label(box3, text="待机", font=FONT_B, bg=BG, fg="#52606d")
        self.lbl_state.pack(side="left", padx=16)

        # 实时指标
        box4 = tk.Frame(self.root, bg="white", bd=1, relief="solid")
        box4.pack(fill="x", padx=12, pady=4)
        self.lbl_metrics = tk.Label(box4, text="E = —   斜率 = —   峰峰值 = —   保持 = —",
                                    font=("Consolas", 11), bg="white", fg=FG, anchor="w", padx=10, pady=8)
        self.lbl_metrics.pack(fill="x")

        # 曲线
        self.canvas = tk.Canvas(self.root, bg="white", height=220, bd=1, relief="solid",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=False, padx=12, pady=4)
        self.canvas.bind("<Configure>", lambda e: self._draw())

        # 日志
        box5 = tk.Frame(self.root, bg=BG)
        box5.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.txt = tk.Text(box5, font=("Consolas", 9), bg="#0f1720", fg="#c8d6e5",
                           insertbackground="#c8d6e5", bd=0, wrap="word")
        sb = tk.Scrollbar(box5, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_dir.get() or ".")
        if d:
            self.var_dir.set(d)

    # ---------------- 日志 ----------------
    def log(self, msg: str):
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    # ---------------- 交互 ----------------
    def on_start(self):
        if self.runner is not None and self.runner.running:
            return
        try:
            area = float(self.var_area.get())
            stab = StabConfig(
                # 阶段 A（前 N 秒，非常严格）
                strict_until_sec=float(self.v_strict_until.get()),
                strict_slope_mv_per_min=float(self.v_slope_s.get()),
                strict_peak_to_peak_mv=float(self.v_pp_s.get()),
                strict_hold_sec=float(self.v_hold.get()),
                # 阶段 B（之后放宽）
                slope_limit_mv_per_min=float(self.v_slope.get()),
                peak_to_peak_mv=float(self.v_pp.get()),
                snapshot_max_drift_mv=float(self.v_snap.get()),
                hold_sec=float(self.v_hold.get()),
                window_sec=float(self.v_win.get()),
                min_points=30)
            ver = self.var_ver.get()
            common = dict(
                sample=self.var_sample.get().strip() or "样品",
                area_cm2=area,
                item=self.var_item.get(),
                out_dir=self.var_dir.get().strip() or ".",
                stab=stab,
                max_ocp_sec=float(self.v_max.get()),
                ocp_max_rounds=int(self.v_rounds.get() or 1),
                # 交流阻抗（频率扫描-电位控制模式）
                eis_enabled=bool(self.var_eis.get()),
                eis_amp_mv=float(self.v_eis_amp.get()),
                eis_init_freq=float(self.v_eis_hi.get()),
                eis_final_freq=float(self.v_eis_lo.get()),
                eis_pts_per_decade=float(self.v_eis_pts.get()),
            )
            if ver == "CS Studio5":
                cfg = R5.RunConfig5(ocp_time_sec=int(float(self.v_ocpt.get())), **common)
            elif ver == "CS Studio6直开":
                cfg = R6.RunConfig6(ocp_time_sec=int(float(self.v_ocpt.get())), **common)
            else:
                cfg = R.RunConfig(ocp_time_sec=int(float(self.v_ocpt.get())), **common)
        except ValueError as e:
            messagebox.showerror("参数有误", "请检查数值输入：%s" % e)
            return

        self.pts.clear()
        self._draw()
        self.txt.delete("1.0", "end")
        if ver == "CS Studio5":
            mod, cls = R5, R5.Runner5
        elif ver == "CS Studio6直开":
            mod, cls = R6, R6.Runner6
        else:
            mod, cls = R, R.Runner
        self.log("软件版本：%s" % ver)
        self.runner = cls(cfg, log=self.log, on_state=self._on_state, on_sample=self._on_sample)
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.log("=" * 60)
        self.runner.start()

    def on_abort(self):
        if self.runner is not None and self.runner.running:
            self.btn_stop.configure(state="disabled")
            self.runner.abort()

    def _on_state(self, st: str, detail: str):
        color = "#52606d"
        if "出错" in st:
            color = "#c62828"
        elif "完成" in st:
            color = "#2e7d32"
        elif "中止" in st:
            color = "#ef6c00"
        elif "待机" not in st:
            color = ACCENT
        self.lbl_state.configure(text=st, fg=color)
        self.last_state = st
        if any(k in st for k in _END_STATES) and self.runner is not None:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            for line in self.runner.summary():
                self.log("  " + line)
            if "完成" in st:
                self.root.bell()

    def _on_sample(self, t: float, e: float, st):
        self.pts.append((t, e))
        if len(self.pts) > 20000:
            del self.pts[:5000]
        self.lbl_metrics.configure(
            text="E = %+.6f V    斜率 = %+.2f mV/min    峰峰值 = %.2f mV    保持 = %.0f / %.0f s"
                 % (e, st.slope_mv_per_min, st.ppt_mv, st.held_sec,
                    self.runner.cfg.stab.hold_sec if self.runner else 0))
        self._draw()

    # ---------------- 绘图 ----------------
    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 50 or h < 40:
            return
        m = 44
        x0, y0, x1, y1 = m, 14, w - 16, h - 26
        c.create_rectangle(x0, y0, x1, y1, outline="#cbd2d9")
        if not self.pts:
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="等待开路电位数据…",
                          fill="#9aa5b1", font=FONT)
            return
        ts = [p[0] for p in self.pts]
        es = [p[1] for p in self.pts]
        tmin, tmax = min(ts), max(ts)
        if tmax - tmin < 5:
            tmax = tmin + 5
        emin, emax = min(es), max(es)
        pad = max((emax - emin) * 0.15, 1e-4)
        emin -= pad
        emax += pad

        def sx(t):
            return x0 + (t - tmin) / (tmax - tmin) * (x1 - x0)

        def sy(e):
            return y1 - (e - emin) / (emax - emin) * (y1 - y0)

        # 网格 + 刻度
        for i in range(5):
            yy = y0 + (y1 - y0) * i / 4
            c.create_line(x0, yy, x1, yy, fill="#eef2f6")
            ev = emax - (emax - emin) * i / 4
            c.create_text(x0 - 8, yy, text="%.4f" % ev, anchor="e", fill="#616e7c",
                          font=("Consolas", 8))
        for i in range(5):
            xx = x0 + (x1 - x0) * i / 4
            tv = tmin + (tmax - tmin) * i / 4
            c.create_text(xx, y1 + 12, text="%.0f" % tv, fill="#616e7c", font=("Consolas", 8))
        c.create_text(x0, y0 - 8, text="E / V", anchor="w", fill="#3e4c59", font=("Consolas", 8))
        c.create_text(x1, y1 + 12, text="t / s", anchor="e", fill="#3e4c59", font=("Consolas", 8))

        step = max(1, len(self.pts) // 1200)
        coords = []
        for t, e in self.pts[::step]:
            coords.extend([sx(t), sy(e)])
        if len(coords) >= 4:
            c.create_line(*coords, fill="#d64545", width=1.6)

        # 判稳线
        if self.runner is not None and self.runner.ocp_ok_volt is not None:
            yy = sy(self.runner.ocp_ok_volt)
            c.create_line(x0, yy, x1, yy, fill="#2e7d32", dash=(6, 4))
            c.create_text(x1 - 6, yy - 9, text="判稳 %.6f V" % self.runner.ocp_ok_volt,
                          anchor="e", fill="#2e7d32", font=("Consolas", 8))

    # ---------------- 主循环 ----------------
    def _tick(self):
        if self.runner is not None and self.runner.running:
            self.runner.tick()
        self.root.after(250, self._tick)


def main():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
