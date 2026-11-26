# -*- coding: utf-8 -*-
"""viewer.py —— 纯代码线实时波形显示窗口。

用法：
    python code/viewer.py logs/xxx_events.jsonl        # 尾随已有/正在写的事件文件
    python tests/run_case.py <job> --port 31001 --view # E2E 时自动拉起本窗口

显示内容（工作站输出）：
    上图 i(t)  —— 工作站输出的电流波形（恒流实验的受控量：方波/阶跃/扫描/充放电）
    下图 E(t)  —— 电位响应
数据源：宿主 CsPilotHost 的 JSONL 事件流（逐点 sample 事件，2026-11-13 加）。
多实验连续作业自动拼接时间轴（每实验的相对秒接续成全局时间轴）。
文件停止增长且已见 exp_done 后自动存 PNG（viewer_final.png），窗口保持可看。
"""
import json
import os
import sys
import time

import matplotlib
matplotlib.use("TkAgg")
# 中文显示：Windows 用微软雅黑（matplotlib 默认 DejaVu Sans 无中文字形 → 豆腐块）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DengXian"]
matplotlib.rcParams["axes.unicode_minus"] = False   # 负号用 ASCII 渲染
import matplotlib.pyplot as plt

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("用法: python code/viewer.py <events.jsonl>")
        sys.exit(1)
    # run_case 先删旧事件文件再拉起本窗口 → 启动时文件可能尚不存在，等待其出现
    t0 = time.time()
    while not os.path.exists(path):
        if time.time() - t0 > 120:
            print("[viewer] 等待事件文件超时：%s" % path)
            sys.exit(1)
        time.sleep(0.5)

    pos = 0
    toff = 0.0            # 多实验时间轴拼接偏移
    prev_t = None
    last_growth = time.time()
    seen_done = 0
    saved = False

    xs_i, is_i = [], []   # 电流
    xs_e, es_e = [], []   # 电位
    marks = []            # 实验边界 (x, kind)

    fig, (ax_i, ax_e) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))
    fig.suptitle("CS-Pilot · 实时波形（工作站输出）")
    li, = ax_i.plot([], [], "b-", lw=1.2)
    ax_i.set_ylabel("I (A)")
    ax_i.grid(True, alpha=0.3)
    le, = ax_e.plot([], [], "r-", lw=1.2)
    ax_e.set_ylabel("E (V)")
    ax_e.set_xlabel("T (s)")
    ax_e.grid(True, alpha=0.3)

    fig.canvas.manager.window.title("CS-Pilot 实时波形 · %s" % os.path.basename(path))

    def read_new():
        nonlocal pos, toff, prev_t, last_growth, seen_done, saved
        grew = False
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(pos)
            # 注意：for-line 迭代器内 f.tell() 会抛 OSError（"telling position
            # disabled by next() call"），必须用 readline 循环
            while True:
                line = f.readline()
                if not line:
                    break
                pos = f.tell()
                grew = True
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ev = d.get("ev")
                if ev == "sample":
                    t = float(d.get("t") or 0.0)
                    if prev_t is not None and t < prev_t - 1e-9:
                        toff += prev_t          # 新实验，时间轴接续
                    prev_t = t
                    x = toff + t
                    xs_i.append(x); is_i.append(float(d.get("i") or 0.0))
                    xs_e.append(x); es_e.append(float(d.get("e") or 0.0))
                elif ev == "exp_begin":
                    marks.append((toff + (prev_t or 0.0), d.get("kind")))
                elif ev == "exp_done":
                    seen_done += 1

        li.set_data(xs_i, is_i)
        le.set_data(xs_e, es_e)
        for ax in (ax_i, ax_e):
            ax.relim(); ax.autoscale_view()
        for x, kind in marks:
            ax_i.axvline(x, color="g", ls="--", alpha=0.35)
            ax_e.axvline(x, color="g", ls="--", alpha=0.35)
        fig.canvas.draw_idle()

        # 文件不再增长且至少一轮实验完成 → 自动存一次 PNG（收据）
        if grew:
            last_growth = time.time()
        if (not saved and seen_done > 0
                and time.time() - last_growth > 15.0):
            out = os.path.join(os.path.dirname(path), "viewer_final.png")
            fig.savefig(out, dpi=110)
            print("[viewer] 已保存 %s" % out)
            saved = True

    timer = fig.canvas.new_timer(interval=200)
    timer.add_callback(read_new)
    timer.start()
    plt.show()


if __name__ == "__main__":
    main()
