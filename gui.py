# -*- coding: utf-8 -*-
"""CS Pilot · 寄生式自动检测 —— 独立运行窗口 v2

v2 改造（2026-11-06）
--------------------
1. **架构**：runner 移入单个 worker 线程（UIA 操作全部留在该线程，无 COM
   跨线程问题）；UI 回调经 queue.Queue 由 Tk 主线程 250ms after 循环排空。
   旧版在 Tk 主线程里直接 tick()，打开参数窗/收尾的 10~50 s 会把整窗卡成
   "未响应"、中止按钮点不动（2026-11-06 代码审查结论）。
2. **步骤时间线**：把运行阶段画成 5 个节点（连接准备 → 开路电位 → 交流阻抗
   → 测试项 → 完成），当前节点高亮 + 进度详情实时刷新。
3. **文件名预览**：输入样品型号/面积/测试项时实时预览"日期-样品-测试项目"。
4. 视觉统一：卡片化分区、扁平按钮、状态徽章、等宽指标栏、暗色日志台。

启动：python gui.py
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner as R
import runner5 as R5
import runner6 as R6
from stabilizer import StabConfig
from status_report import StatusReporter

# ---------------- 主题 ----------------
BG = "#f4f6fa"          # 窗体底
CARD = "#ffffff"        # 卡片
FG = "#1c2430"          # 主文字
SUB = "#7a8699"         # 次文字
LINE = "#dfe5ee"        # 描边
ACCENT = "#2f6fed"      # 主色
ACCENT_DK = "#1d54c7"
OK = "#188a42"
WARN = "#e07b00"
ERR = "#d23b3b"
PANEL_DK = "#101826"    # 日志台
PANEL_FG = "#c9d7e8"

FONT = ("Microsoft YaHei UI", 9)
FONT_S = ("Microsoft YaHei UI", 8)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_T = ("Microsoft YaHei UI", 13, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_S = ("Consolas", 8)

# 步骤节点：key → (标题, 命中该节点的状态关键字)
STEPS = [
    ("connect", "连接准备", ("连接", "准备")),
    ("ocp", "开路电位·判稳", ("开路电位",)),
    ("eis", "交流阻抗", ("阻抗",)),
    ("test", "测试项", ("测试项", "动电位", "阶梯波")),
    ("done", "完成", ("完成", "出错", "已中止")),
]


def step_of(state: str) -> int:
    for i, (_k, _t, kws) in enumerate(STEPS):
        if any(kw in state for kw in kws):
            return i
    return 0


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.runner = None
        self.worker: threading.Thread | None = None
        self.q: queue.Queue = queue.Queue()
        self._abort_requested = False
        self.pts: list[tuple[float, float]] = []
        self.reporter: StatusReporter | None = None   # 多机看板上报
        self._last_report = 0.0
        self._log_tail: list[str] = []
        self.last_state = ""

        root.title("CS Pilot · 寄生式自动检测")
        root.geometry("1020x1004")
        root.configure(bg=BG)
        root.minsize(960, 940)

        self._build_ui()
        self.root.after(120, self._drain_queue)
        self.root.after(250, self._tick_clock)
        self._preview_names()

    # ================= UI 构建 =================
    def _card(self, parent, title=None, pad=(12, 4)) -> tk.Frame:
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1)
        if isinstance(pad, tuple) and pad[1] == 0:
            box.pack(fill="x", padx=pad[0])
        else:
            box.pack(fill="x", padx=pad[0], pady=pad[1])
        if title:
            head = tk.Frame(box, bg=CARD)
            head.pack(fill="x", padx=12, pady=(8, 0))
            tk.Label(head, text=title, font=FONT_B, bg=CARD, fg=FG).pack(side="left")
            tk.Frame(head, bg=LINE, height=1).pack(fill="x", pady=(6, 0))
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="x", padx=12, pady=6)
        return inner

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        # ---- 标题行 ----
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(head, text="CS Pilot", font=FONT_T, bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(head, text="  寄生式自动检测 · 不改软件默认设置 · 独立判稳停机",
                 font=FONT, bg=BG, fg=SUB).pack(side="left", padx=6, pady=(6, 0))
        self.lbl_clock = tk.Label(head, text="00:00:00", font=FONT_MONO, bg=BG, fg=SUB)
        self.lbl_clock.pack(side="right")

        # ---- ① 样品信息 ----
        c1 = self._card(outer, "① 样品与输出")
        row = tk.Frame(c1, bg=CARD)
        row.pack(fill="x")

        def field(parent, label, width, side="left", extra=None):
            tk.Label(parent, text=label, font=FONT, bg=CARD, fg=SUB).pack(side=side, padx=(0, 3))
            v = tk.StringVar()
            e = tk.Entry(parent, textvariable=v, font=FONT, width=width,
                         relief="flat", highlightthickness=1,
                         highlightbackground=LINE, highlightcolor=ACCENT)
            e.pack(side=side, padx=(0, 12), ipady=3)
            if extra:
                tk.Label(parent, text=extra, font=FONT, bg=CARD, fg=SUB).pack(side=side, padx=(0, 12))
            return v

        self.var_sample = field(row, "样品型号", 14)
        self.var_sample.set("样品" + datetime.date.today().strftime("%m%d"))
        self.var_sample.trace_add("write", lambda *_: self._preview_names())
        self.var_area = field(row, "试样面积", 7, extra="cm²")
        self.var_area.set("1.0")

        tk.Label(row, text="软件版本", font=FONT, bg=CARD, fg=SUB).pack(side="left", padx=(0, 3))
        self.var_ver = tk.StringVar(value="CS Studio6直开")
        ttk.Combobox(row, textvariable=self.var_ver,
                     values=["CS Studio6", "CS Studio5", "CS Studio6直开"],
                     state="readonly", width=14, font=FONT).pack(side="left", padx=(0, 12))

        tk.Label(row, text="测试项目", font=FONT, bg=CARD, fg=SUB).pack(side="left", padx=(0, 3))
        self.var_item = tk.StringVar(value="Tafel")
        cb_item = ttk.Combobox(row, textvariable=self.var_item, values=["Tafel", "Step"],
                               state="readonly", width=7, font=FONT)
        cb_item.pack(side="left", padx=(0, 12))
        cb_item.bind("<<ComboboxSelected>>", lambda *_: self._preview_names())

        row2 = tk.Frame(c1, bg=CARD)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="输出目录", font=FONT, bg=CARD, fg=SUB).pack(side="left", padx=(0, 3))
        self.var_dir = tk.StringVar(value=r"C:\Users\xiyve\Desktop\CS-Pilot数据")
        tk.Entry(row2, textvariable=self.var_dir, font=FONT, relief="flat",
                 highlightthickness=1, highlightbackground=LINE,
                 highlightcolor=ACCENT).pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
        tk.Button(row2, text="浏览…", font=FONT, relief="flat", bg="#eef2f9",
                  activebackground="#e2e9f5", padx=10, command=self._pick_dir).pack(side="left")

        # 多机看板上报：多台单通道机各跑一个 gui，指向同一共享目录即可聚合
        row3 = tk.Frame(c1, bg=CARD)
        row3.pack(fill="x", pady=(8, 0))
        self.var_board = tk.BooleanVar(value=False)
        tk.Checkbutton(row3, text="上报到多机看板", variable=self.var_board,
                       font=FONT_B, bg=CARD, fg="#6b3fa0", activebackground=CARD,
                       selectcolor=CARD, relief="flat").pack(side="left", padx=(0, 10))
        tk.Label(row3, text="看板目录", font=FONT, bg=CARD, fg=SUB).pack(side="left")
        self.var_board_dir = tk.StringVar(value=r"C:\Users\xiyve\Desktop\CS-Pilot看板")
        tk.Entry(row3, textvariable=self.var_board_dir, font=FONT, relief="flat",
                 highlightthickness=1, highlightbackground=LINE,
                 highlightcolor=ACCENT).pack(side="left", fill="x", expand=True,
                                             ipady=3, padx=(6, 0))
        tk.Label(c1, text="多台机器把\"看板目录\"指向同一共享文件夹（如 \\\\主控机\\cspilot看板），"
                          "主控机运行 monitor.py 即可集中监控全部机器。",
                 font=FONT_S, bg=CARD, fg=SUB, anchor="w").pack(fill="x", pady=(4, 0))

        self.lbl_files = tk.Label(c1, text="", font=FONT_MONO_S, bg=CARD, fg=SUB,
                                  anchor="w", justify="left")
        self.lbl_files.pack(fill="x", pady=(8, 0))

        # ---- ② 步骤时间线 ----
        c2 = self._card(outer, "② 运行步骤")
        self.cv_steps = tk.Canvas(c2, bg=CARD, height=72, highlightthickness=0)
        self.cv_steps.pack(fill="x")
        self.lbl_step_detail = tk.Label(c2, text="待机 —— 尚未开始", font=FONT_B,
                                        bg=CARD, fg=SUB, anchor="w")
        self.lbl_step_detail.pack(fill="x", pady=(2, 0))
        self._cur_step = -1
        # 首次布局前 winfo_width() 返回 1，直接画会把节点全叠在一起；
        # 绑定 <Configure>：容器宽度变化（含首次排布）时重画时间线。
        self.cv_steps.bind("<Configure>",
                           lambda e: self._draw_steps() if e.width > 1 else None)
        self._draw_steps()

        # ---- ③ 实时指标 + 曲线 ----
        c3 = self._card(outer, "③ 实时数据")
        self.lbl_metrics = tk.Label(c3, text="E = —        斜率 = —        峰峰值 = —        保持 = —",
                                    font=FONT_MONO, bg=CARD, fg=FG, anchor="w")
        self.lbl_metrics.pack(fill="x")
        self.cv_plot = tk.Canvas(c3, bg=CARD, height=142, highlightthickness=0,
                                 highlightbackground=LINE)
        self.cv_plot.pack(fill="x", pady=(6, 0))
        self.cv_plot.bind("<Configure>", lambda e: self._draw_plot())

        # ---- ④ 参数（左：判稳三阶段；右：实验参数）----
        c4 = self._card(outer, "④ 判稳与实验参数")

        def num(parent, label, default, width=6, unit=""):
            tk.Label(parent, text=label, font=FONT, bg=CARD, fg=SUB).pack(side="left")
            v = tk.StringVar(value=str(default))
            tk.Entry(parent, textvariable=v, font=FONT, width=width, relief="flat",
                     highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACCENT).pack(side="left", padx=(3, 1), ipady=2)
            if unit:
                tk.Label(parent, text=unit, font=FONT_S, bg=CARD, fg=SUB).pack(side="left", padx=(0, 10))
            return v

        colA = tk.Frame(c4, bg=CARD); colA.pack(side="left", fill="both", expand=True, padx=(0, 14))
        colB = tk.Frame(c4, bg=CARD); colB.pack(side="left", fill="both", expand=True)

        tk.Label(colA, text="判稳判据（两阶段 + 公共）", font=FONT_B, bg=CARD, fg=FG).pack(anchor="w")
        tk.Label(colA, text="阶段 A · 前 600 s 严格", font=FONT_S, bg=CARD, fg="#b3423f"
                 ).pack(anchor="w", pady=(4, 0))
        rA1 = tk.Frame(colA, bg=CARD); rA1.pack(anchor="w")
        self.v_strict_until = num(rA1, "持续", 600, 6, "s")
        self.v_slope_s = num(rA1, "斜率 <", 1.0, 4, "mV/min")
        self.v_pp_s = num(rA1, "峰峰 <", 2.0, 4, "mV")
        tk.Label(colA, text="阶段 B · 之后放宽", font=FONT_S, bg=CARD, fg=ACCENT
                 ).pack(anchor="w", pady=(4, 0))
        rA2 = tk.Frame(colA, bg=CARD); rA2.pack(anchor="w")
        self.v_slope = num(rA2, "斜率 <", 5.0, 4, "mV/min")
        self.v_pp = num(rA2, "峰峰 <", 5.0, 4, "mV")
        self.v_snap = num(rA2, "5min快照 <", 15.0, 4, "mV")
        rA3 = tk.Frame(colA, bg=CARD); rA3.pack(anchor="w", pady=(4, 0))
        self.v_win = num(rA3, "窗口", 60, 5, "s")
        self.v_hold = num(rA3, "保持", 120, 5, "s")

        tk.Label(colB, text="实验参数", font=FONT_B, bg=CARD, fg=FG).pack(anchor="w")
        rB1 = tk.Frame(colB, bg=CARD); rB1.pack(anchor="w", pady=(4, 0))
        self.v_ocpt = num(rB1, "OCP测量时间", 1800, 6, "s")
        self.v_max = num(rB1, "最长等待", 1800, 6, "s")
        rB2 = tk.Frame(colB, bg=CARD); rB2.pack(anchor="w")
        self.v_rounds = num(rB2, "最多轮数", 3, 3, "轮")
        self.var_eis = tk.BooleanVar(value=True)
        tk.Checkbutton(rB2, text="测交流阻抗", variable=self.var_eis, font=FONT,
                       bg=CARD, fg="#6b3fa0", activebackground=CARD,
                       selectcolor=CARD, relief="flat").pack(side="left", padx=(10, 0))
        rB3 = tk.Frame(colB, bg=CARD); rB3.pack(anchor="w", pady=(4, 0))
        self.v_eis_amp = num(rB3, "阻抗幅值", 10.0, 4, "mV")
        self.v_eis_hi = num(rB3, "频率", 100000, 6, "Hz→")
        self.v_eis_lo = num(rB3, "", 0.01, 4, "Hz")
        self.v_eis_pts = num(rB3, "点/dec", 10, 3, "")

        # ---- ⑤ 控制按钮 ----
        c5 = tk.Frame(outer, bg=BG)
        c5.pack(fill="x", padx=16, pady=8)
        self.btn_start = tk.Button(c5, text="▶  开始检测", font=FONT_B, bg=ACCENT,
                                   fg="white", activebackground=ACCENT_DK,
                                   activeforeground="white", relief="flat", width=16,
                                   pady=6, cursor="hand2", command=self.on_start)
        self.btn_start.pack(side="left")
        self.btn_stop = tk.Button(c5, text="■  中止", font=FONT_B, bg="#eef2f9", fg="#5a6478",
                                  activebackground="#e2e9f5", relief="flat", width=12,
                                  pady=6, state="disabled", cursor="hand2",
                                  command=self.on_abort)
        self.btn_stop.pack(side="left", padx=10)
        self.lbl_state = self._badge(c5, "待机", SUB)

        # ---- ⑥ 日志 ----
        c6 = tk.Frame(outer, bg=PANEL_DK, highlightbackground=LINE, highlightthickness=1)
        c6.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.txt = tk.Text(c6, font=FONT_MONO_S, bg=PANEL_DK, fg=PANEL_FG,
                           insertbackground=PANEL_FG, bd=0, wrap="word",
                           selectbackground="#2a3b55")
        sb = tk.Scrollbar(c6, command=self.txt.yview, width=10)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6)
        for line in ("CS Pilot 就绪。选择软件版本、填样品信息后点「开始检测」。",
                     "提示：判稳只认数据，不用软件自带停机条件；判稳达标后自动停止并接续下一项。"):
            self.txt.insert("end", line + "\n")

    def _badge(self, parent, text, color) -> tk.Label:
        return tk.Label(parent, text=" ● " + text, font=FONT_B, bg=CARD, fg=color,
                        padx=2)

    # ================= 文件名预览 =================
    def _preview_names(self):
        day = datetime.date.today().strftime("%Y-%m-%d")
        sample = self.var_sample.get().strip() or "样品"
        item = self.var_item.get()
        tag = "动电位" if item == "Tafel" else "阶梯波"
        names = ["%s-%s-开路电位.txt" % (day, sample)]
        if self.var_eis.get():
            names.append("%s-%s-交流阻抗.txt/.z60" % (day, sample))
        names.append("%s-%s-%s.txt" % (day, sample, tag))
        self.lbl_files.configure(text="输出文件预览：\n    " + "\n    ".join(names))

    # ================= 步骤时间线 =================
    def _draw_steps(self):
        c = self.cv_steps
        c.delete("all")
        w = c.winfo_width()
        if w <= 1:  # 尚未完成首次布局，用请求宽度兜底
            w = c.winfo_reqwidth() or 960
        h = 86
        n = len(STEPS)
        m = 70
        gap = (w - 2 * m) / (n - 1)
        cy = 30
        cur = self._cur_step
        for i, (k, title, _kws) in enumerate(STEPS):
            x = m + i * gap
            done = cur > i
            active = cur == i
            if cur < 0:
                color, fill = LINE, CARD
            elif done:
                color, fill = OK, OK
            elif active:
                color, fill = ACCENT, "#e8effd"
            else:
                color, fill = LINE, CARD
            r = 11
            c.create_oval(x - r, cy - r, x + r, cy + r, fill=fill,
                          outline=color, width=2)
            if done:
                c.create_line(x - 5, cy, x - 1, cy + 4, fill="white", width=2)
                c.create_line(x - 1, cy + 4, x + 5, cy - 4, fill="white", width=2)
            elif active:
                c.create_oval(x - 4, cy - 4, x + 4, cy + 4, fill=ACCENT, outline="")
            c.create_text(x, cy + 26, text=title, fill=(FG if (active or done) else SUB),
                          font=FONT_B if active else FONT)
            if i < n - 1:
                x2 = m + (i + 1) * gap
                line_color = OK if (cur > i) else LINE
                c.create_line(x + r + 4, cy, x2 - r - 4, cy, fill=line_color, width=2)

    def _set_step(self, idx: int, detail: str = ""):
        if idx != self._cur_step:
            self._cur_step = idx
            self._draw_steps()
        state = STEPS[idx][1] if idx >= 0 else "待机"
        self.lbl_step_detail.configure(text="%s%s" % (state, ("　·　" + detail) if detail else ""))

    # ================= 队列/时钟 =================
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                try:
                    if kind == "log":
                        self._log(payload)
                    elif kind == "state":
                        st, detail = payload
                        self._on_state(st, detail)
                    elif kind == "sample":
                        t, e, st_ = payload
                        self._on_sample(t, e, st_)
                    elif kind == "done":
                        self._on_worker_done(payload)
                except Exception:
                    # 单条消息的回调异常不允许杀死轮询循环——
                    # 否则 after 链断掉，窗口整体假死（日志/曲线/状态全冻结）
                    import traceback
                    self._log("[UI] 回调异常：%s" % traceback.format_exc(limit=2))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def _tick_clock(self):
        if self.runner is not None and self.runner.running:
            e = int(self.runner.elapsed())
            self.lbl_clock.configure(text="%02d:%02d:%02d" % (e // 3600, (e % 3600) // 60, e % 60))
        # 看板心跳：运行中每秒（随采样节流），空闲/结束后每 5s 保一次活
        if self.reporter is not None and time.time() - self._last_report > 5.0:
            self._report(self.last_state or "待机")
        self.root.after(500, self._tick_clock)

    # ================= 多机看板上报 =================
    def _report(self, state: str, detail: str = "", metrics: dict | None = None):
        if self.reporter is None:
            return
        try:
            files = []
            if self.runner is not None:
                try:
                    files = ["%s（%d B）" % (n, s) for n, s in self.runner.result_files()]
                except Exception:
                    files = []
            self.reporter.update(
                state=state, detail=detail,
                step=STEPS[step_of(state)][1],
                metrics=metrics or {},
                files=files, log_tail=list(self._log_tail))
            self._last_report = time.time()
        except Exception:
            pass                                  # 上报永不影响主流程

    # ================= 日志 =================
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.txt.insert("end", "%s  %s\n" % (ts, msg))
        self.txt.see("end")
        self._log_tail.append("%s %s" % (ts, msg))
        if len(self._log_tail) > 8:
            del self._log_tail[:len(self._log_tail) - 8]
        if self.txt.index("end-1c").split(".")[0] and \
                int(self.txt.index("end-1c").split(".")[0]) > 3000:
            self.txt.delete("1.0", "1000.0")

    # ================= 交互 =================
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_dir.get() or ".")
        if d:
            self.var_dir.set(d)

    def on_start(self):
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            area = float(self.var_area.get())
            stab = StabConfig(
                strict_until_sec=float(self.v_strict_until.get()),
                strict_slope_mv_per_min=float(self.v_slope_s.get()),
                strict_peak_to_peak_mv=float(self.v_pp_s.get()),
                strict_hold_sec=float(self.v_hold.get()),
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
        self._draw_plot()
        self.txt.delete("1.0", "end")
        self._log("软件版本：%s" % ver)
        if ver == "CS Studio5":
            mod, cls = R5, R5.Runner5
        elif ver == "CS Studio6直开":
            mod, cls = R6, R6.Runner6
        else:
            mod, cls = R, R.Runner
        self.runner = cls(cfg, log=lambda m: self.q.put(("log", m)),
                          on_state=lambda s, d: self.q.put(("state", (s, d))),
                          on_sample=lambda t, e, s: self.q.put(("sample", (t, e, s))))
        # 多机看板上报（勾选才建；共享目录聚合，见 status_report.py）
        if self.var_board.get():
            self.reporter = StatusReporter(
                self.var_board_dir.get().strip() or r"C:\Users\xiyve\Desktop\CS-Pilot看板",
                machine=None,
                sample=self.var_sample.get().strip(),
                area=self.var_area.get().strip(),
                item=self.var_item.get(), ver=ver)
            self._log("多机看板上报已开启 → %s" % self.reporter.path)
        else:
            self.reporter = None
        self._abort_requested = False
        self.btn_start.configure(state="disabled", bg="#9db4dd")
        self.btn_stop.configure(state="normal")
        self._log("=" * 56)
        self.worker = threading.Thread(target=self._worker_main, daemon=True)
        self.worker.start()

    def on_abort(self):
        if self.worker is not None and self.worker.is_alive():
            self._abort_requested = True
            self._log("已请求中止：等当前步骤收尾后停止（UIA 操作不可中途打断）…")
            self.btn_stop.configure(state="disabled")

    def _worker_main(self):
        r = self.runner
        try:
            r.start()
            while r.running and not self._abort_requested:
                r.tick()
                time.sleep(0.25)
            if self._abort_requested and r.running:
                r.abort()
        except Exception as e:
            import traceback
            self.q.put(("log", "worker 异常：%s" % e))
            self.q.put(("log", traceback.format_exc()[-600:]))
            try:
                r._fail(str(e))
            except Exception:
                pass
        self.q.put(("done", None))

    def _on_worker_done(self, _payload):
        self.btn_start.configure(state="normal", bg=ACCENT)
        self.btn_stop.configure(state="disabled")
        if self.runner is not None:
            for line in self.runner.summary():
                self._log("  " + line)

    # ================= 状态回调（主线程） =================
    def _on_state(self, st: str, detail: str):
        color = SUB
        if "出错" in st:
            color = ERR
        elif "完成" in st:
            color = OK
        elif "中止" in st:
            color = WARN
        else:
            color = ACCENT
        self.lbl_state.configure(text=" ● " + st, fg=color)
        self._set_step(step_of(st), detail or st)
        self.last_state = st
        self._report(st, detail)          # 多机看板：状态变化即上报
        if any(k in st for k in ("完成", "出错", "已中止")):
            self.btn_start.configure(state="normal", bg=ACCENT)
            self.btn_stop.configure(state="disabled")
            if "完成" in st:
                try:
                    self.root.bell()
                except Exception:
                    pass

    def _on_sample(self, t: float, e: float, st):
        if e is not None:  # 阻抗阶段 e=None，不能混进曲线数据（min/max 会炸）
            self.pts.append((t, e))
            if len(self.pts) > 20000:
                del self.pts[:5000]
        hold_total = 0
        try:
            hold_total = self.runner.cfg.stab.hold_sec
        except Exception:
            pass
        # runner5 阻抗阶段传的是字符串 "eis"、e=None——没有 OCP 指标可显示
        if not hasattr(st, "slope_mv_per_min") or e is None:
            self.lbl_metrics.configure(
                text="E = —        斜率 = —        峰峰值 = —        保持 = —  （阻抗扫描进行中）")
            return
        self.lbl_metrics.configure(
            text="E = %+.6f V      斜率 = %+.2f mV/min      峰峰值 = %.2f mV      保持 = %.0f / %.0f s"
                 % (e, st.slope_mv_per_min, st.ppt_mv, st.held_sec, hold_total))
        self._draw_plot()
        # 看板指标节流到 1Hz（采样是 10Hz，文件系统不需要那么勤）
        if time.time() - self._last_report >= 1.0:
            self._report(self.last_state or "监视中",
                         metrics={"E": e, "slope": st.slope_mv_per_min,
                                  "ppt": st.ppt_mv, "held": st.held_sec})

    # ================= 曲线 =================
    def _draw_plot(self):
        c = self.cv_plot
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 60 or h < 40:
            return
        m = 52
        x0, y0, x1, y1 = m, 12, w - 18, h - 26
        c.create_rectangle(x0, y0, x1, y1, outline=LINE)
        if not self.pts:
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="等待开路电位数据…",
                          fill=SUB, font=FONT)
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

        for i in range(5):
            yy = y0 + (y1 - y0) * i / 4
            c.create_line(x0, yy, x1, yy, fill="#f0f3f8")
            ev = emax - (emax - emin) * i / 4
            c.create_text(x0 - 8, yy, text="%.4f" % ev, anchor="e", fill=SUB,
                          font=FONT_MONO_S)
        for i in range(5):
            xx = x0 + (x1 - x0) * i / 4
            tv = tmin + (tmax - tmin) * i / 4
            c.create_text(xx, y1 + 12, text="%.0f" % tv, fill=SUB, font=FONT_MONO_S)
        c.create_text(x0, y0 - 8, text="E / V", anchor="w", fill=SUB, font=FONT_MONO_S)
        c.create_text(x1, y1 + 12, text="t / s", anchor="e", fill=SUB, font=FONT_MONO_S)

        step = max(1, len(self.pts) // 1400)
        coords = []
        for t, e in self.pts[::step]:
            coords.extend([sx(t), sy(e)])
        if len(coords) >= 4:
            c.create_line(*coords, fill="#d64545", width=1.6)

        if self.runner is not None and self.runner.ocp_ok_volt is not None:
            yy = sy(self.runner.ocp_ok_volt)
            c.create_line(x0, yy, x1, yy, fill=OK, dash=(6, 4))
            c.create_text(x1 - 6, yy - 9, text="判稳 %.6f V" % self.runner.ocp_ok_volt,
                          anchor="e", fill=OK, font=FONT_MONO_S)


def main():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
