# -*- coding: utf-8 -*-
"""fleet_gui.py —— 4 通道统一界面（主桌面方案版）。

功能
----
* 2×2 机器卡片：状态/完成态/屏障待同步/心跳年龄 · runner pid · CS Studio pid+hwnd ·
  sim pid+端口 · 回放标识 · 单机启停
* 全局工具栏：全部启动 · 全部急停 · 排列软件窗口 · 一键清场 · 打开机器清单
* 编排器内嵌：进程死亡自动复活（--resume 断点续跑）、双保险熔断、完成态不复活
* 每 2s 刷新；状态色：运行=蓝 / 待同步=橙 / 完成=绿 / 出错·熔断=红 / 失联=橙 / 未启动=灰

用法
----
  python fleet_gui.py [machines.json]
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
    if "待同步" in state:
        return WARN
    if "中止" in state or "失联" in state:
        return WARN
    return ACCENT


class FleetGUI:
    def __init__(self, root: tk.Tk, cfg_path: str):
        self.root = root
        self.cfg_path = cfg_path
        self.fleet = None               # F.Fleet 实例（全部启动后创建）
        self.q: queue.Queue = queue.Queue()
        self.cards = {}                 # name -> dict(label widgets)

        root.title("CS Pilot · 四通道编排（主桌面）")
        root.geometry("1280x780")
        root.configure(bg=BG)
        root.minsize(1100, 680)

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
        tk.Label(head, text="四通道编排", font=FONT_T, bg=BG,
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
        tk.Button(tools, text="🧹 一键清场", font=FONT, bg="#eef2f9", fg="#5a6478",
                  relief="flat", padx=10, command=self.on_cleanup).pack(side="left", padx=2)
        tk.Button(tools, text="打开机器清单…", font=FONT, bg="#eef2f9", fg="#5a6478",
                  relief="flat", padx=10, command=self.on_pick_cfg).pack(side="left", padx=2)
        tk.Label(tools, text=self.cfg_path, font=FONT_S, bg=BG, fg=SUB).pack(
            side="right")

        # 卡片区（2×2 网格）
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        for c in (0, 1):
            wrap.grid_columnconfigure(c, weight=1, uniform="card")
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)
        self.wrap = wrap

    # ---------------- 卡片 ----------------
    def _card(self, name, m, st, row, col):
        box = tk.Frame(self.wrap, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1)
        box.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)

        # --- 状态解析 ---
        state, color = "未启动", GREY
        pid, restarts, finished = None, 0, ""
        hb_age = None
        if st is not None:
            pid = st["proc"].pid
            alive = st["proc"].poll() is None
            restarts = st["restarts"]
            finished = st.get("finished", "")
            if st.get("failed"):
                state, color = "熔断（需人工排查）", ERR
            elif finished:
                state, color = finished, (OK if finished == "完成"
                                          else ERR if finished == "出错" else WARN)
            elif not alive:
                state, color = "进程已退出（未收尾）", GREY
            else:
                hb = os.path.join(F.HB_DIR, name + ".json")
                stage = ""
                if os.path.exists(hb):
                    try:
                        with open(hb, encoding="utf-8") as f:
                            d = json.load(f)
                        stage = d.get("stage", "")
                        hb_age = time.time() - d.get("ts", 0)
                        if hb_age > 30:
                            state, color = "失联 %.0fs" % hb_age, WARN
                    except Exception:
                        pass
                if hb_age is not None and hb_age <= 30:
                    if "待同步" in stage:
                        state, color = stage + "（屏障让位中）", WARN
                    elif stage:
                        state, color = stage, stage_color(stage)
                    else:
                        state, color = "运行中（无心跳）", ACCENT
                elif not stage and state == "未启动":
                    state, color = "运行中（无心跳）", ACCENT

        # --- 第一行：名字 + 状态 ---
        head = tk.Frame(box, bg=CARD)
        head.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(head, text=name, font=FONT_T, bg=CARD,
                 fg=color if st else FG).pack(side="left")
        tk.Label(head, text=" ● " + state, font=FONT_B, bg=CARD,
                 fg=color).pack(side="left", padx=10)
        tk.Label(head, text="runner pid=%s 重启#%d" % (pid or "-", restarts),
                 font=FONT_S, bg=CARD, fg=SUB).pack(side="right")

        # --- 第二行：配置摘要 ---
        sim = m.get("sim") or {}
        replay = " · 真机数据回放" if sim.get("replay_ocp") else ""
        tk.Label(box, text="v%s · %s cm² · %s%s%s"
                 % (m.get("version", 6), m.get("area", 1.0),
                    m.get("item", "Tafel"),
                    " · 无阻抗" if m.get("no_eis") else "", replay),
                 font=FONT_S, bg=CARD, fg=SUB, anchor="w").pack(
            fill="x", padx=14, pady=(2, 0))

        # --- 第三行：CS Studio / sim 实时信息 ---
        cs_hwnd = st.get("cs_hwnd", 0) if st else 0
        if self.fleet is not None:
            cs_hwnd = cs_hwnd or getattr(self.fleet, "_cs_hwnds", {}).get(name, 0)
        cs_pid = st.get("cs_pid") if st else None
        sim_pid = None
        if self.fleet is not None:
            sp = self.fleet.sims.get(name)
            sim_pid = sp.pid if sp is not None and sp.poll() is None else None
        info = []
        if cs_pid or cs_hwnd:
            info.append("CS Studio: pid=%s hwnd=%s" % (cs_pid or "-", cs_hwnd or "-"))
        else:
            info.append("CS Studio: 未拉起")
        if sim:
            info.append("sim: %s (:%s)" % (
                "pid=%s" % sim_pid if sim_pid else "离线",
                str(sim.get("port", "")).split(":")[-1]))
        if hb_age is not None and hb_age <= 30:
            info.append("心跳 %.0fs" % hb_age)
        if finished:
            info.append("已收尾，不再复活")
        tk.Label(box, text="  ·  ".join(info), font=FONT_S, bg=CARD, fg=SUB,
                 anchor="w").pack(fill="x", padx=14, pady=(2, 0))

        # --- 第四行：按钮 ---
        btns = tk.Frame(box, bg=CARD)
        btns.pack(side="bottom", anchor="e", padx=14, pady=(0, 10))
        if st is not None and st["proc"].poll() is None and not finished:
            tk.Button(btns, text="停止", font=FONT, bg="#eef2f9", fg="#5a6478",
                      relief="flat", padx=10,
                      command=lambda n=name: self.on_stop_one(n)).pack(side="left", padx=2)
        else:
            tk.Button(btns, text="启动", font=FONT, bg=ACCENT, fg="white",
                      relief="flat", padx=10,
                      command=lambda n=name: self.on_start_one(n)).pack(side="left", padx=2)

        self.cards[name] = {"box": box}

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

    def on_cleanup(self):
        """一键清场：杀全部 CS Studio + 本编排的 runner/sim + 删陈旧锁。"""
        if not messagebox.askyesno(
                "一键清场",
                "将强制结束：全部 CorrTest.CSStudio 实例、本清单的 runner/sim，\n"
                "并删除 runner 锁文件。\n\n确认？（不影响其它程序的 python 进程）"):
            return

        def work():
            import subprocess
            # 顺序红线（审查 #22）：先让 runner 停下（优雅收尾→兜底杀），
            # 再杀软件。旧顺序先杀 CSStudio：runner 还活着，会继续注入 UI、
            # 重连软件甚至重启实验，清场清不干净。
            f = self.fleet
            if f is not None:
                try:
                    f.stop_all()
                except Exception:
                    pass
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                  "Where-Object { $_.CommandLine -match "
                  "'simdevice|runner5_live|runner6_live|fleet\\.py machines' } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True)
            except Exception:
                pass
            try:
                subprocess.run(["taskkill", "/F", "/IM", "CorrTest.CSStudio.exe"],
                               capture_output=True)
            except Exception:
                pass
            tmp = os.environ.get("TEMP", r"C:\Users\Public")
            for lk in ("cspilot_cs5_runner.lock", "cspilot_cs6_runner.lock"):
                try:
                    os.remove(os.path.join(tmp, lk))
                except OSError:
                    pass
            self.fleet = None
            self.q.put("cleanup-done")

        threading.Thread(target=work, daemon=True).start()

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
        # 任何异常都不许打断 after 重排（11-12 挂起 30 分钟事故的同款防线，
        # 审查 #25）：异常时看板显示错误，2 s 后照常再刷。
        try:
            self._refresh_inner()
        except Exception as e:
            try:
                self.lbl_summary.configure(text="看板刷新异常：%s" % e)
            except Exception:
                pass
        finally:
            try:
                self.root.after(2000, self.refresh)
            except Exception:
                pass

    def _refresh_inner(self):
        # 收清场完成事件
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

        if not hasattr(self, "machines"):
            try:
                self.machines = F.load_config(self.cfg_path)
            except Exception:
                self.machines = []
        # 清空重建（2×2）
        for w in self.wrap.winfo_children():
            w.destroy()
        self.cards.clear()

        n_run = n_fin = n_err = 0
        for m in self.machines:
            st = self.fleet.state.get(m["name"]) if self.fleet else None
            if st is not None:
                if st.get("finished") == "完成":
                    n_fin += 1
                elif st.get("finished") == "出错" or st.get("failed"):
                    n_err += 1
                elif st["proc"].poll() is None:
                    n_run += 1
        self.lbl_summary.configure(
            text="%d 台机器 · %d 运行中 · %d 完成 · %d 出错"
                 % (len(self.machines), n_run, n_fin, n_err))

        for i, m in enumerate(self.machines):
            st = self.fleet.state.get(m["name"]) if self.fleet else None
            self._card(m["name"], m, st, row=i // 2, col=i % 2)


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
