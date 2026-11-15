# -*- coding: utf-8 -*-
"""resume_tafel.py —— 续跑：只起动电位（OCP/阻抗已完成，等待用户口令后执行）。

流程：连接 → 清场（顺带收掉阻抗残留窗）→ 跳过 OCP/阻抗 → 直接 Tafel。
用法：python resume_tafel.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import runner6 as R6
import graceful_exit

LOG = r"D:\deepseek\_probe\live_jkf\resume_tafel.log"
_lines = []


def log(m):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    _lines.append(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    cfg = R6.RunConfig6(
        sample="JK-O",
        area_cm2=1.2,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
    )
    r = R6.Runner6(cfg, log=log)
    log("=" * 60)
    log("续跑：只起动电位（JK-O / 1.2 cm²，OCP/阻抗已完成）")
    log("=" * 60)
    r.start()
    graceful_exit.install(lambda: r, log)

    # 等连接+清场完成：状态一到 S_OCP_OPEN（清场完毕、OCP 窗还没开）就
    # 立即改道 S_T_OPEN——旧条件只认 S_CONNECT，在 S_PREPARE 就退出循环，
    # 跳转被错过、OCP 照跑（2026-11-07 真机纠正）
    t_end = time.time() + 120
    while r.running and r.state != R6.S_OCP_OPEN and time.time() < t_end:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        time.sleep(0.25)
    if r.state == R6.S_OCP_OPEN:
        # 跳过了 OCP 阶段 → 从已完成的 OCP 数据文件里取判稳值，
        # 喂给 runner（「相对开路」基准的偏移量要用它，见 runner6._do_t_fill）
        # 找最新的 JK-O 开路电位数据文件（本轮 files["ocp"] 是去重后的新名，
        # 真正的判稳数据在上一轮的文件里）
        import glob
        cands = glob.glob(os.path.join(cfg.out_dir, "*JK-O-开路电位*.txt"))
        ocp_file = max(cands, key=os.path.getmtime) if cands else None
        try:
            rows = [l.split() for l in open(ocp_file, encoding="utf-8",
                                            errors="replace") if l.strip()][2:]
            r.ocp_ok_volt = float(rows[-1][0])
            log("OCP 判稳值（来自 %s）: %.6f V" % (os.path.basename(ocp_file),
                                                   r.ocp_ok_volt))
        except Exception as e:
            log("!! 读不到 OCP 判稳值（%s）→ 相对开路基准会错，拒绝继续" % e)
            r._fail("无 OCP 判稳值")
            return
        log("清场完成 → 直接进入动电位阶段（跳过 OCP）")
        r.set_state(R6.S_T_OPEN)
        r.stage_t0 = time.time()
    while r.running:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        time.sleep(0.25)
    if r.state not in ("完成", "出错", "已中止") and r.running:
        graceful_exit.drain(r, log, lambda: r.tick())
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
