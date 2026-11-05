# -*- coding: utf-8 -*-
"""selftest_cs5.py —— CS Studio5 全流程自测：开 OCP → 界面读数判稳 → 停止 → 读文件。

用法：
    python selftest_cs5.py [分钟数] [--quick]

--quick 把判稳的最短等待降到 30 s（只为验证链路，正式运行必须 600 s）。
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from driver5 import Studio5
from uiprobe import UiSampler
from stabilizer import OcpStabilizer, StabConfig

OUT_DIR = r"D:\deepseek\_probe\e2e5"


def log(*a):
    print(*a, flush=True)


def main():
    minutes = 3.0
    quick = "--quick" in sys.argv
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            try:
                minutes = float(a)
            except ValueError:
                pass

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    base = os.path.join(OUT_DIR, "%s-SELFTEST5-开路电位" % stamp)
    for p in (base, base + ".cor"):
        try:
            os.remove(p)
        except Exception:
            pass

    t0 = time.time()

    def T():
        return time.time() - t0

    d = Studio5(log=log)
    log("=== [%6.1fs] 连接 CS Studio5 ===" % T())
    if not d.launch():
        log("启动失败")
        return 2
    log("    标题=%r 演示=%s" % (d.title(), d.is_demo()))
    if not d.is_demo():
        if not d.enter_demo():
            log("进不了演示模式")
            return 2
        log("    标题=%r" % d.title())

    log("\n=== [%6.1fs] 打开 OCP 参数窗 ===" % T())
    panel = d.open_ocp()
    if panel is None:
        log("打不开 frmOCP")
        return 2
    log("    frmOCP OK")

    log("\n=== [%6.1fs] 填参数 ===" % T())
    ok = d.fill_ocp(panel, base, minutes, 10.0)
    ids = d.by_ids(panel)
    for k in ("Control_FileName_Text", "Ocp_Param_Text", "FrqControl_Frq_Text"):
        if k in ids:
            try:
                log("    %-26s = %r" % (k, ids[k].get_value()))
            except Exception:
                pass
    for k in ("Ocp_Param_Combo",):
        if k in ids:
            try:
                log("    %-26s = %r" % (k, ids[k].legacy_properties().get("Value")))
            except Exception:
                pass
    log("    填写结果 ok=%s" % ok)

    log("\n=== [%6.1fs] 点确定，开始实验 ===" % T())
    from driver5 import all_run_hwnds
    old_hwnds = set(all_run_hwnds())          # 启动前残留的运行窗口，稍后排除
    if old_hwnds:
        log("    （先记下 %d 个残留运行窗口，稍后排除）" % len(old_hwnds))
    if not d.press_ok(panel, "ocp"):
        log("点确定失败")
        return 2

    log("\n=== [%6.1fs] 等运行窗口 ===" % T())
    rw = d.find_run_window(timeout=15, exclude=old_hwnds)
    if rw is None:
        log("没出现运行窗口")
        return 2
    log("    运行窗口: %r" % rw.window_text())
    log("    状态栏: %r" % d.run_status(rw))

    sampler = UiSampler(rw, log=log)
    s = sampler.wait_first(timeout=25)
    if s is None:
        log("等不到第一个读数")
        d.stop_run(rw)
        return 2
    log("    首个读数: %r" % s)

    cfg = StabConfig(strict_until_sec=(30.0 if quick else 600.0))
    st = OcpStabilizer(cfg)
    log("\n=== [%6.1fs] 判稳（斜率<%.1f mV/min, 峰峰<%.1f mV, 窗口%g s, 保持%g s, 最短%g s）==="
        % (T(), cfg.slope_limit_mv_per_min, cfg.peak_to_peak_mv,
           cfg.window_sec, cfg.hold_sec, cfg.strict_until_sec))

    last_print = 0.0
    stable = False
    reason = ""
    stab_point = None
    last_t = -1.0
    stall = 0
    while True:
        if not sampler.alive():
            log("    运行窗口消失")
            break
        s = sampler.read()
        if s is None or s.e_volt is None:
            time.sleep(0.5)
            if T() > 60 * minutes + 60:
                break
            continue
        # 数据停滞检测：实验结束后界面数值不再变化
        if abs(s.t_sec - last_t) < 1e-6:
            stall += 1
        else:
            stall = 0
            last_t = s.t_sec
        if stall >= 40:      # 约 20 s 没有任何新数据
            log("    数据停滞 20 s，判定实验已结束（最后 t=%.2fs）" % s.t_sec)
            break
        ok_s, reason, metrics = None, "", None
        st.feed([(s.t_sec, s.e_volt)])
        state = st.state
        if time.time() - last_print >= 3.0:
            log("    t=%7.2fs  E=%+.6f V  斜率=%+.2f mV/min  峰峰=%.2f mV  保持=%.0fs  %s"
                % (s.t_sec, s.e_volt, state.slope_mv_per_min, state.ppt_mv,
                   state.held_sec, state.reason))
            last_print = time.time()
        if state.stable:
            stable = True
            stab_point = (s.t_sec, s.e_volt)
            log("    ★ 判稳 @ t=%.2fs  E=%+.6f V  reason=%s" % (s.t_sec, s.e_volt, state.reason))
            break
        if s.t_sec > 60 * minutes + 30:
            log("    超过设定时长，强制结束")
            break
        time.sleep(0.4)

    log("\n=== [%6.1fs] 停止实验 ===" % T())
    r = d.stop_run(rw)
    log("    停止=%s" % r)
    time.sleep(2.0)
    d.close_run(rw)
    log("    已关闭运行窗口")

    log("\n=== [%6.1fs] 文件结果 ===" % T())
    time.sleep(1.0)
    for p in (base, base + ".cor"):
        if os.path.exists(p):
            sz = os.path.getsize(p)
            log("    %s  %d 字节" % (p, sz))
            try:
                with open(p, "rb") as f:
                    head = f.read(260)
                log("    头部: %r" % head[:220])
                with open(p, "rb") as f:
                    lines = f.read().split(b"\r\n")
                log("    行数: %d" % len(lines))
                if len(lines) > 5:
                    log("    末数据行: %r" % lines[-2][:80])
            except Exception as e:
                log("    读取失败: %s" % e)

    log("\n=== 汇总 ===")
    log("  判稳: %s  %s" % (stable, stab_point))
    log("  用时: %.1f s" % T())
    log("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
