# -*- coding: utf-8 -*-
"""runner5_live.py —— 真机运行入口（CS Studio5 链路：OCP→动电位，无阻抗）。

用法：python runner5_live.py [样品型号] [面积cm2]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from runner5 import Runner5, RunConfig5
import graceful_exit
from stabilizer import StabConfig

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
LOG = None          # 运行时按 样品+时间 生成（避免多轮日志交织）
_lines = []


def log(m):
    global LOG
    if LOG is None:
        LOG = os.path.join(_LOG_DIR, "run_%s.log" % time.strftime("%H%M%S"))
    line = "%s  %s" % (time.strftime("%H:%M:%S"), m)
    print(line, flush=True)
    _lines.append(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass




def _single_instance_guard(lock_name: str) -> bool:
    """单实例锁：同一套软件上绝不允许第二个 runner（真机上两个 runner
    会互相停/开实验——对真实电解池是危险操作）。

    2026-11-11 改用命名 Mutex：pid 文件锁会被 Windows pid 复用骗过
    （旧 runner 崩溃不删锁 → pid 被无关进程占用 → OpenProcess 成功 →
    永远拒绝启动，4 台全灭实证）。Mutex 由 OS 在进程退出时自动释放，
    无陈旧锁问题。"""
    import ctypes

    k32 = ctypes.WinDLL("kernel32")
    h = k32.CreateMutexW(None, True, "Global\\cspilot_" + lock_name)
    if not h:
        print("!! 创建互斥锁失败: %s" % lock_name)
        return False
    if k32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        print("!! 已有实例在运行（互斥锁 %s 被持），拒绝启动。" % lock_name)
        return False
    globals()["_lock_mutex_handle"] = h   # 持有到进程退出，防 GC
    return True

HB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_auto", "hb")


def _write_hb(sample, r):
    import json
    try:
        os.makedirs(HB_DIR, exist_ok=True)
        hb = {"machine": sample, "pid": os.getpid(), "ts": time.time(),
              "stage": r.state,
              "stopping": (("停止" in r.state or "结束" in r.state) and "已停止待同步" not in r.state), "detail": getattr(r, "detail", "")}
        p = os.path.join(HB_DIR, "%s.json" % sample)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hb, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass


def _read_hb(sample):
    import json
    try:
        p = os.path.join(HB_DIR, "%s.json" % sample)
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def main():
    args = sys.argv
    lock = args[args.index("--lock") + 1] if "--lock" in args else "cspilot_cs5_runner.lock"
    if not _single_instance_guard(lock):
        return 1
    sample = sys.argv[1] if len(sys.argv) > 1 else "JK-N"
    area = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
    do_resume = "--resume" in sys.argv
    skip_ocp = False
    if do_resume:
        hb = _read_hb(sample)
        if hb:
            stage = hb.get("stage", "")
            if any(k in stage for k in ("动电位", "测试", "阶梯")):
                skip_ocp = True
                print("断点续跑：上一轮阶段「%s」→ 本轮跳过 OCP" % stage)
            else:
                print("上一轮阶段「%s」→ 正常从头跑" % stage)
    global LOG
    LOG = os.path.join(_LOG_DIR, "run_%s_%s.log" % (sample, time.strftime("%m%d_%H%M")))
    def _argval(name, default):
        return float(args[args.index(name) + 1]) if name in args else default

    cfg = RunConfig5(
        sn=(args[args.index("--sn") + 1] if "--sn" in args else ""),
        cs_hwnd=int(_argval("--cs-hwnd", 0)),
        com=(args[args.index("--com") + 1] if "--com" in args else ""),
        baud=int(_argval("--baud", 115200)),
        port=(args[args.index("--port") + 1] if "--port" in args else ""),
        sample=sample,
        area_cm2=area,
        item="Tafel",
        out_dir=r"C:\Users\xiyve\Desktop\CS-Pilot数据",
        eis_enabled=("no-eis" not in sys.argv),   # fleet 传 no-eis = 不测阻抗
        ocp_time_sec=_argval("--ocp-time", 1800.0),
        ocp_freq_hz=10.0,
        max_ocp_sec=_argval("--max-ocp", 1800.0),
        ocp_max_rounds=int(_argval("--ocp-rounds", 3)),  # 最多 3 轮；0=不限
        tafel_init_v=_argval("--init", -0.5),
        tafel_final_v=_argval("--final", 1.5),
        tafel_scan_mv_s=_argval("--rate", 0.33),
        tafel_interval_s=0.5,
    )
    # 5 版动电位「自动停止」：运行窗不显示电流、UIA 判停读不到值，
    # 只能靠软件自带的「扫描停止电流」(PotDynamic_ScanStop_chk) 生效。
    # 软件默认 ±4.5 mA（比常见量程 2 mA 还大 → 只能靠超量程被动终止）。
    # 界面实测（2026-11-15 演示模式 dump）：PotDynamic_Max/MinCurrent 是
    # **绝对电流 mA**（标签「当电流(mA)>」「或电流(mA)<」），不随面积换算；
    # 用户口径 1×10⁻³ A = 1 mA 直接填。
    cfg.tafel_stop_ma = float(cfg.test_stop_i_density or 1e-3) * 1000.0
    r = Runner5(cfg, log=log)
    log("=" * 60)
    log("真机运行（5 版 CS120）：%s / %g cm² / OCP→%s（%s）"
        % (sample, area,
           "阻抗→动电位" if cfg.eis_enabled else "动电位",
           "断点续跑" if do_resume else "无阻抗" if not cfg.eis_enabled else ""))
    log("=" * 60)
    r.start()
    # ★ 同屏预览：本桌面 CS Studio 主窗 2s 一截 → fleet_gui 四格拼屏
    import threading as _th
    try:
        import preview as _pv
        _preview_stop = _th.Event()
        _pv.start_preview(sample, _preview_stop, log=log)
    except Exception as _e:
        print("preview 线程未启动: %r" % _e)
    graceful_exit.install(lambda: r, log)
    t0 = time.time()
    last_beat = 0.0
    last_state = ""
    while r.running:
        r.tick()
        graceful_exit.consume_abort(lambda: r, log)
        # 断点跳转：连接完成进入 OCP 前改道直奔动电位
        if skip_ocp and r.state == "打开开路电位参数窗":
            log("断点续跑：跳过 OCP，直接动电位")
            r.set_state("打开动电位参数窗")
            skip_ocp = False
        time.sleep(0.25)
        if r.state != last_state:
            last_state = r.state
            log("[状态] %s  %s" % (r.state, r.detail))
        if time.time() - last_beat > 60.0:
            last_beat = time.time()
            log("[心跳] state=%s detail=%s 运行 %.0f s" % (r.state, r.detail, time.time() - t0))
        _write_hb(sample, r)
    if r.running:
        graceful_exit.drain(r, log, lambda: r.tick())
    try:
        _preview_stop.set()
    except Exception:
        pass
    for line in r.summary():
        log("  " + line)
    log("VERDICT: %s" % r.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
