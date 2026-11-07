# -*- coding: utf-8 -*-
"""plot_jkf.py —— JK-F 真机首跑数据三联图（OCP / EIS / 动电位）。

数据源（C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\）：
  * 2026-11-07-JK-F-开路电位_2.txt   E(V) / i(A/cm2) / T(s)
  * 2026-11-07-JK-F-交流阻抗.txt     Freq(Hz) / ... / Z' / Z'' / |Z| / Phase
  * 2026-11-07-JK-F-动电位.txt       E(V) / i(A/cm2) / T(s)
输出：plot_jkf.png（300dpi）+ plot_jkf.pdf
"""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = r"C:\Users\xiyve\Desktop\CS-Pilot数据"
OUT = r"D:\deepseek\_probe\plot_jkf.png"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def load_pot(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
                except ValueError:
                    continue
    rows = rows[2:] if len(rows) > 100 else rows      # 跳过表头（大文件才有）
    e = np.array([r[0] for r in rows])
    i = np.array([r[1] for r in rows])
    t = np.array([r[2] for r in rows])
    return e, i, t


def load_eis(path):
    freq, zre, zim, zmod, ph = [], [], [], [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 8 and parts[0].startswith(("+", "-", "+1", "-1", "1")):
                try:
                    freq.append(float(parts[0]))
                    zre.append(float(parts[4]))
                    zim.append(float(parts[5]))
                    zmod.append(float(parts[6]))
                    ph.append(float(parts[7]))
                except (ValueError, IndexError):
                    continue
    return (np.array(freq), np.array(zre), np.array(zim),
            np.array(zmod), np.array(ph))


def main():
    ocp = load_pot(os.path.join(D, "2026-11-07-JK-F-开路电位.txt"))   # 首轮 OCP（_2 已被清理）
    tafel = load_pot(os.path.join(D, "2026-11-07-JK-F-动电位.txt"))
    freq, zre, zim, zmod, ph = load_eis(os.path.join(D, "2026-11-07-JK-F-交流阻抗.txt"))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    fig.suptitle("JK-F 真机首跑 · CS350M · 2026-11-07（面积 1.0 cm²）",
                 fontsize=13, fontweight="bold")

    # ---- 1) OCP ----
    ax = axes[0]
    e, i, t = ocp
    ax.plot(t / 60.0, e, lw=0.9, color="#d64545")
    ax.axhline(e[-1], color="#2e7d32", ls="--", lw=0.9)
    ax.annotate("末值 %.4f V" % e[-1], xy=(t[-1] / 60.0, e[-1]),
                xytext=(0.55, 0.08), textcoords="axes fraction",
                fontsize=9, color="#2e7d32")
    ax.set_xlabel("时间 / min")
    ax.set_ylabel("E vs 参比 / V")
    ax.set_title("(a) 开路电位（首轮片段 7 min）", fontsize=10)
    ax.grid(alpha=0.3)

    # ---- 2) EIS Nyquist ----
    ax = axes[1]
    ax.plot(zre, -zim, "o-", ms=3.5, lw=0.9, color="#2f6fed")
    ax.set_xlabel("Z' / Ω·cm²")
    ax.set_ylabel("−Z'' / Ω·cm²")
    ax.set_title("(b) 交流阻抗 Nyquist（10 mV，10⁵→10⁻² Hz）", fontsize=10)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    # 标注首末频率
    if len(freq):
        ax.annotate("%.0e Hz" % freq[0], xy=(zre[0], -zim[0]), fontsize=8,
                    color=SUB_GREY if False else "#555")
        ax.annotate("%.0e Hz" % freq[-1], xy=(zre[-1], -zim[-1]), fontsize=8,
                    color="#d64545")

    # ---- 3) Tafel ----
    ax = axes[2]
    e, i, t = tafel
    ai = np.abs(i)
    ax.semilogy(ai, e, lw=0.9, color="#d64545")
    ax.axvline(1e-3, color="#2e7d32", ls="--", lw=0.9)
    ax.annotate("判停 1.0e-3 A/cm²", xy=(1e-3, 0.1), xytext=(0.35, 0.12),
                textcoords="axes fraction", fontsize=9, color="#2e7d32")
    ax.set_xlabel("|i| / A/cm²（对数轴）")
    ax.set_ylabel("E vs 参比 / V")
    ax.set_title("(c) 动电位极化（0.33 mV/s）", fontsize=10)
    ax.set_xlim(1e-7, 3e-3)
    ax.grid(alpha=0.3, which="both")

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT, dpi=300)
    fig.savefig(OUT.replace(".png", ".pdf"))
    print("已输出:", OUT)
    print("EIS 点数:", len(freq), " OCP 点数:", len(ocp[0]), " Tafel 点数:", len(tafel[0]))
    return 0


SUB_GREY = "#555"

if __name__ == "__main__":
    sys.exit(main())
