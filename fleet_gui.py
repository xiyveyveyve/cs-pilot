# -*- coding: utf-8 -*-
"""fleet_gui.py —— 多通道统一界面（4 台机器的编排+监控打包成一个窗口）。

功能
----
* 机器清单（machines.json）：每台一张卡片（样品/阶段/心跳/重启次数/停止钮）
* 全局工具栏：全部启动 · 全部急停 · 排列软件窗口
* 编排器内嵌：进程死亡自动复活（--resume 断点续跑）、连死熔断
* 每 2s 刷新；状态色：运行=蓝 / 完成=绿 / 出错=红 / 失联=灰

用法
----
  python fleet_gui.py [machines.json]
机器清单格式（machines.example.json 有全字段说明）：
  {"machines": [
     {"name": "JK-O", "version": 6, "area": 1.2, "item": "Tafel",
      "no_eis": true, "lock": "cspilot_cs6_runner.lock"},
     {"name": "JK-N", "version": 5, "area": 1.2, "item": "Tafel",
      "no_eis": true, "lock": "cspilot_cs5_runner.lock"} ]}
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fleet as F

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(ROOT_DIR, "machines.json")

# 配色（与 gui.py 一致）
BG, CARD, FG, SUB = "#f4f6fa", "#ffffff", "#1c2430", "#7a8699"
LINE, ACCENT = "#dfe5ee", "#2f6fed"
OK, WARN, ERR, GREY = "#188a42", "#e07b00", "#d23b3b", "#9aa5b1"
FONT = ("Microsoft YaHei UI", 9)
FONT_S = ("Microsoft YaHei UI", 8)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_T = ("Microsoft YaHei UI", 13, "bold")


def stage_color(state: str):
    if any(k in state for k in ("出错", "熔断")):
        return ERR
    if "完成" in state:
        return OK
    if "中止" in state or "失联" in state:
        return WARN
    return ACCENT


class FleetGUI:
    def __init__(self, root: tk.Tk, cfg_path: str):
        self.root = root
        self.cfg_path = cfg_path
        self.fleet = None               # F.Fleet 实例（全部启动后创建）
        self.q: queue.Queue = queue.Queue()
        self.cards = {}                 # name -> frame

        root.title("CS Pilot · 多通道编排")
        root.geometry("1240x860")
        root.configure(bg=BG)
        root.minsize(1100, 700)

        if not hasattr(self, "machines"):
            try:
                self.machines = F.load_config(cfg_path)
            except Exception:
                self.machines = []
        self._build_ui()
        self.refresh()

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(head, text="多通道编排", font=FONT_T, bg=BG,
                 fg=ACCENT).pack(side="left")
        self.lbl_summary = tk.Label(head, text="", font=FONT, bg=BG, fg=SUB)
        self.lbl_summary.pack(side="left", padx=14)

        # 工具行
        tools = tk.Frame(self.root, bg=BG)
        tools.pack(fill="x", padx=12, pady=2)
        tk.Button(tools, text="▶ 全部启动", font=FONT_B, bg=ACCENT, fg="white",
                  relief="flat", padx=12, command=self.on_start_all).pack(side="left")
        tk.Button(tools, text="■ 全部急停", font=FONT_B, bg="#eef2f9", fg="#5a6478",
                  relief="flat", padx=12, command=self.on_stop_all).pack(side="left", padx=8)
        tk.Button(tools, text="排列软件窗口", font=FONT, bg="#eef2f9", fg="#5a6478",
                  relief="flat", padx=10, command=self.on_arrange).pack(side="left", padx=2)
        tk.Button(tools, text="打开机器清单…", font=FONT, bg="#eef2f9", fg="#5a6478",
                  relief="flat", padx=10, command=self.on_pick_cfg).pack(side="left", padx=2)
        tk.Label(tools, text=self.cfg_path, font=FONT_S, bg=BG, fg=SUB).pack(
            side="right")

        # 卡片区（滚动）
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(wrap, command=self.canvas.yview, width=10)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw",
                                  tags="inner")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        # ★ 同屏预览栏（右侧 2×2）：每桌面 runner 截图 → PNG → 此处轮显
        try:
            import preview as _PV
            self.prev_dir = _PV.PREVIEW_DIR
        except Exception:
            self.prev_dir = None
        prevbar = tk.Frame(self.root, bg=BG)
        prevbar.pack(side="right", fill="y", padx=(0, 10), pady=(4, 10))
        tk.Label(prevbar, text="同屏预览", font=FONT_B, bg=BG, fg=ACCENT).pack(
            anchor="w", pady=(0, 4))
        self.prev_labels = {}
        self._prev_imgs = {}            # 防 PhotoImage 被 GC
        for m in (getattr(self, "machines", None) or self._load_machines()):
            f = tk.Frame(prevbar, bg=CARD, highlightbackground=LINE,
                         highlightthickness=1)
            f.pack(pady=3)
            tk.Label(f, text=m["name"], font=FONT_S, bg=CARD, fg=SUB).pack()
            lbl = tk.Label(f, bg="#10131a", width=40, height=13)
            lbl.pack(padx=3, pady=(0, 3))
            self.prev_labels[m["name"]] = lbl
        self.root.after(1500, self._refresh_previews)

    def _load_machines(self):
        try:
            return F.load_config(self.cfg_path)
        except Exception:
            return []

    def _refresh_previews(self):
        import os as _os
        for name, lbl in self.prev_labels.items():
            p = _os.path.join(self.prev_dir, "%s.png" % name) if self.prev_dir else None
            if p and _os.path.exists(p):
                try:
                    ph = tk.PhotoImage(file=p)
                    # 缩到 260 宽
                    w, h = ph.width(), ph.height()
                    if w > 260:
                        ph = ph.subsample(max(1, w // 260))
                    self._prev_imgs[name] = ph
                    lbl.configure(image=ph, width=ph.width(), height=ph.height())
                except Exception:
                    pass
        self.root.after(2000, self._refresh_previews)

    # ---------------- 卡片 ----------------
    def _card(self, name, m, st):
        box = tk.Frame(self.inner, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1)
        box.pack(fill="x", pady=5, padx=2)
        head = tk.Frame(box, bg=CARD)
        head.pack(fill="x", padx=12, pady=(8, 0))

        state = "未启动"
        color = GREY
        pid = None
        restarts = 0
        if st is not None:
            pid = st["proc"].pid
            alive = st["proc"].poll() is None
            restarts = st["restarts"]
            if st.get("failed"):
                state, color = "熔断（需人工排查）", ERR
            elif not alive:
                state, color = "进程已退出", GREY
            else:
                hb = os.path.join(F.HB_DIR, name + ".json")
                stage = ""
                if os.path.exists(hb):
                    try:
                        with open(hb, encoding="utf-8") as f:
                            d = json.load(f)
                        stage = d.get("stage", "")
                        age = time.time() - d.get("ts", 0)
                        if age > 30:
                            state, color = "失联 %.0fs" % age, WARN
                    except Exception:
                        pass
                if not stage:
                    state, color = "运行中（无心跳）", ACCENT
                else:
                    state = stage
                    color = stage_color(stage)

        tk.Label(head, text=name, font=FONT_T, bg=CARD,
                 fg=FG if not st else color).pack(side="left")
        tk.Label(head, text=" ● " + state, font=FONT_B, bg=CARD,
                 fg=color).pack(side="left", padx=12)
        tk.Label(head, text="pid=%s 重启#%d" % (pid or "-", restarts),
                 font=FONT_S, bg=CARD, fg=SUB).pack(side="right")

        meta = tk.Frame(box, bg=CARD)
        meta.pack(fill="x", padx=12, pady=(2, 4))
        tk.Label(meta, text="版本 v%s · %s cm² · %s%s"
                 % (m.get("version", 6), m.get("area", 1.0),
                    m.get("item", "Tafel"),
                    " · 无阻抗" if m.get("no_eis") else ""),
                 font=FONT_S, bg=CARD, fg=SUB).pack(side="left")

        btns = tk.Frame(box, bg=CARD)
        btns.pack(side="right", padx=(0, 10))
        if st is not None and st["proc"].poll() is None:
            tk.Button(btns, text="停止", font=FONT, bg="#eef2f9", fg="#5a6478",
                      relief="flat", padx=8,
                      command=lambda n=name: self.on_stop_one(n)).pack(side="left", padx=2)
        else:
            tk.Button(btns, text="启动", font=FONT, bg=ACCENT, fg="white",
                      relief="flat", padx=8,
                      command=lambda n=name: self.on_start_one(n)).pack(side="left", padx=2)
        tk.Frame(box, bg=LINE, height=1).pack(fill="x", padx=12, pady=(4, 6))

    # ---------------- 动作 ----------------
    def on_start_all(self):
        if self.fleet is not None and any(
                st["proc"].poll() is None for st in self.fleet.state.values()):
            messagebox.showinfo("已有实例", "已有机器在运行（编排器监督中）。"
                                "\n停止的机器可单独用卡片上的「启动」。")
            return
        self.fleet = F.Fleet(self.machines)
        self.fleet.launch_all(resume=False)
        self._spawn_supervisor()

    def on_stop_all(self):
        if self.fleet is None:
            return
        if not messagebox.askyesno("全局急停", "将逐台 CTRL_BREAK 优雅停止"
                                   "（runner 会中止实验并收尾）。确认？"):
            return
        threading.Thread(target=self._do_stop_all, daemon=True).start()

    def _do_stop_all(self):
        self.fleet.stop_all()

    def on_stop_one(self, name):
        st = self.fleet.state.get(name) if self.fleet else None
        if st is None or st["proc"].poll() is not None:
            return
        threading.Thread(target=lambda: F.stop_machine(st["proc"]),
                         daemon=True).start()

    def on_start_one(self, name):
        if self.fleet is None:
            self.fleet = F.Fleet(self.machines)
        m = next((x for x in self.machines if x["name"] == name), None)
        if m is None:
            return
        resume = self._had_running_stage(name)
        threading.Thread(target=lambda: self.fleet.launch(dict(m, resume=resume),
                                                          resume=resume),
                         daemon=True).start()
        self._spawn_supervisor()

    def _had_running_stage(self, name) -> bool:
        hb = os.path.join(F.HB_DIR, name + ".json")
        try:
            with open(hb, encoding="utf-8") as f:
                d = json.load(f)
            return any(k in d.get("stage", "") for k in ("动电位", "测试", "阻抗"))
        except Exception:
            return False

    def _spawn_supervisor(self):
        """监督循环只挂一份。"""
        if getattr(self, "_sup_alive", False):
            return
        self._sup_alive = True
        threading.Thread(target=self._sup_loop, daemon=True).start()

    def _sup_loop(self):
        while True:
            time.sleep(2)
            try:
                self.fleet.supervise_round()
            except Exception:
                pass

    def on_arrange(self):
        threading.Thread(target=self._arrange_async, daemon=True).start()

    def _arrange_async(self):
        try:
            import subprocess
            subprocess.Popen([sys.executable,
                              os.path.join(ROOT_DIR, "position_windows.py")])
        except Exception:
            pass

    def on_pick_cfg(self):
        p = filedialog.askopenfilename(initialdir=ROOT_DIR,
                                       filetypes=[("JSON", "*.json")])
        if p:
            self.cfg_path = p
            try:
                self.machines = F.load_config(p)
                self.refresh()
            except Exception as e:
                messagebox.showerror("配置错误", str(e))

    # ---------------- 刷新 ----------------
    def refresh(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.cards.clear()
        if not hasattr(self, "machines"):
            try:
                self.machines = F.load_config(self.cfg_path)
            except Exception:
                self.machines = []
        n_run = sum(1 for st in self.fleet.state.values()
                    if st["proc"].poll() is None) if self.fleet else 0
        self.lbl_summary.configure(
            text="%d 台机器 · %d 运行中" % (len(self.machines), n_run))
        for m in self.machines:
            st = self.fleet.state.get(m["name"]) if self.fleet else None
            self._card(m["name"], m, st)
        self.root.after(2000, self.refresh)


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CFG
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        g = FleetGUI(root, cfg)
    except Exception as e:
        messagebox.showerror("启动失败", "机器清单加载失败：%s" % e)
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
