# -*- coding: utf-8 -*-
"""寄生式自动化运行器。

设计原则（与用户需求一一对应）：
  1. 寄生：不新增实验、不改软件默认配置、只读序列 + 填参数 + 点按钮。
  2. 独立监控：判稳完全由本程序按数据文件算，不启用软件自带的 Δ电位停机条件。
  3. 外部使停：判稳达标后由本程序点软件「停止」按钮，让序列自动跳到下一项。
  4. 命名：输出文件 = 日期-样品型号-测试项目。

状态机由 GUI 每 ~200ms 调 tick() 驱动，所有 UIA 操作都在主线程完成，
避免 COM 跨线程问题。
"""
from __future__ import annotations

import os
import re
import time
import datetime
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Dict, Any

from studio_ui import Studio
from driver import (ParasiteDriver, OcpSpec, TafelSpec, StepSpec, EisSpec,
                    EXP_OCP, EXP_TAFEL, EXP_STEP, EXP_EIS)
from watch import CorFileTail
from stabilizer import OcpStabilizer, StabConfig


# ---------- 状态 ----------
ST_IDLE = "待机"
ST_CONNECT = "连接 CS Studio"
ST_PREPARE = "检查序列"
ST_AREA = "设置试样面积"
ST_CONF_OCP = "填写开路电位参数"
ST_CONF_EIS = "填写阻抗参数"
ST_CONF_TEST = "填写测试参数"
ST_START = "启动实验"
ST_MON_OCP = "监控开路电位（判稳中）"
ST_STOP_OCP = "停止开路电位"
ST_MON_TEST = "监控测试项"
ST_DONE = "完成"
ST_ERROR = "出错"
ST_ABORT = "已中止"


@dataclass
class RunConfig:
    sample: str = "样品"
    area_cm2: float = 1.0
    item: str = "Tafel"          # Tafel / Step
    out_dir: str = r"C:\Users\xiyve\Desktop\CS-Pilot数据"
    # 开路电位
    ocp_time_sec: int = 1800     # 软件侧的"测量时间"，须大于判稳所需，作兜底
    ocp_freq_hz: float = 10.0
    # 判稳（外部判据）
    stab: StabConfig = field(default_factory=lambda: StabConfig(
        strict_until_sec=600.0, strict_slope_mv_per_min=1.0,
        strict_peak_to_peak_mv=2.0, strict_hold_sec=120.0,
        slope_limit_mv_per_min=5.0, window_sec=60.0,
        peak_to_peak_mv=5.0, hold_sec=120.0, min_points=30))
    max_ocp_sec: float = 1800.0  # 最长等待，超时强制停止
    ocp_max_rounds: int = 3      # 开路电位最多测几轮（一轮 = ocp_time_sec 秒），没判稳就再来一轮
    # 测试项
    tafel_init_v: float = -0.5
    tafel_final_v: float = 1.5
    tafel_scan_mv_s: float = 0.33
    tafel_interval_s: float = 0.5
    test_stop_i_density: Optional[float] = 1e-3   # A/cm²，达到即停动电位
    # ---- 阶梯波（任意恒电位阶梯波，与 5 版同参）----
    step_init_v: float = -0.2
    step_final_v: float = 0.5
    step_delta_v: float = 0.05
    step_cycles: int = 20           # 循环 20 个周期（用户指定）
    step_use_steps: bool = False    # 中间电位都不选（用户指定）
    step_hold_s: float = 2.0       # 每步持续 2 s（用户指定）
    # ---- EIS（交流阻抗频率扫描-电位控制模式）----
    eis_enabled: bool = True
    eis_dc_v: float = 0.0
    eis_amp_mv: float = 10.0
    eis_init_freq: float = 100000.0
    eis_final_freq: float = 0.01
    eis_pts_per_decade: float = 10.0
    test_timeout_sec: float = 7200.0


def build_filenames(cfg: RunConfig) -> Dict[str, str]:
    """日期-样品-测试项目.txt"""
    day = datetime.date.today().strftime("%Y-%m-%d")
    safe = "".join(ch for ch in (cfg.sample or "样品") if ch not in r'\/:*?"<>|').strip() or "样品"
    out = {}
    out["ocp"] = os.path.join(cfg.out_dir, "%s-%s-开路电位.txt" % (day, safe))
    item_cn = "动电位" if cfg.item == "Tafel" else "阶梯波"
    out["test"] = os.path.join(cfg.out_dir, "%s-%s-%s.txt" % (day, safe, item_cn))
    if getattr(cfg, "eis_enabled", True):
        out["eis"] = os.path.join(cfg.out_dir, "%s-%s-交流阻抗.txt" % (day, safe))
    return out


def dedupe_paths(paths: Dict[str, str], log=None) -> Dict[str, str]:
    """目标文件已存在时自动加 _2/_3 序号。

    为什么必须做：软件遇到同名文件会弹「文件存在重复」提示并**覆盖写入**。
    覆盖的瞬间旧内容不会立刻消失，tail 会读到新旧混合的数据，
    判稳斜率会被污染（实测同名重跑时判稳从 24.5 s 拖到 46.7 s）。
    """
    out: Dict[str, str] = {}
    for k, p in paths.items():
        if not os.path.exists(p):
            out[k] = p
            continue
        base, ext = os.path.splitext(p)
        stem = re.sub(r"_\d+$", "", base)      # 剥掉已有序号，避免 _2_2 累积
        n = 2
        while os.path.exists("%s_%d%s" % (stem, n, ext)):
            n += 1
        new = "%s_%d%s" % (stem, n, ext)
        out[k] = new
        if log:
            log("目标文件已存在，改用 %s" % os.path.basename(new))
    return out


class Runner:
    def __init__(self, cfg: RunConfig,
                 log: Optional[Callable[[str], None]] = None,
                 on_state: Optional[Callable[[str, str], None]] = None,
                 on_sample: Optional[Callable[[float, float, Any], None]] = None):
        self.cfg = cfg
        self._log = log or (lambda m: None)
        self._on_state = on_state or (lambda a, b: None)
        self._on_sample = on_sample or (lambda t, e, st: None)

        self.ui: Optional[Studio] = None
        self.drv: Optional[ParasiteDriver] = None
        self.state = ST_IDLE
        self.error = ""
        self.running = False
        self.aborting = False

        self.files: Dict[str, str] = {}
        self.ocp_index = -1
        self.test_index = -1
        self.test_kind = ""
        self.tail_ocp: Optional[CorFileTail] = None
        self.tail_test: Optional[CorFileTail] = None
        self.stab = OcpStabilizer(cfg.stab)
        self.ocp_ok_volt: Optional[float] = None
        self.ocp_reason = ""
        self.ocp_elapsed = 0.0
        self.test_started_at: Optional[float] = None
        self.test_first_data_at: Optional[float] = None
        self._t0 = 0.0
        self._phase_deadline = 0.0
        self._last_progress = 0.0

    # ---------- 对外 ----------
    def log(self, msg: str):
        self._log("%s %s" % (time.strftime("%H:%M:%S"), msg))

    def set_state(self, st: str, detail: str = ""):
        self.state = st
        self._on_state(st, detail)
        if detail:
            self.log("[%s] %s" % (st, detail))
        else:
            self.log("[%s]" % st)

    def start(self):
        try:
            os.makedirs(self.cfg.out_dir, exist_ok=True)
        except Exception:
            pass
        if self.running:
            return
        self.running = True
        self.aborting = False
        self.error = ""
        self.ocp_ok_volt = None
        self._ocp_round = 0          # 开路电位已完成的轮数（多轮续测用）
        self._ocp_retry = False      # 标记：本轮未判稳，停完还要再来一轮
        self.ocp_reason = ""
        self.test_started_at = None
        self.test_first_data_at = None
        self.stab.reset()
        self.files = dedupe_paths(build_filenames(self.cfg), self.log)
        self.log("输出文件：%s" % self.files)
        self._t0 = time.time()
        self._i_hit = 0              # 电流达标连续计数（新点才累计）
        self._i_last_t = None        # 上次已判定的样本 t（判重）
        # 软件侧 OCP 测量时间 ≤ runner 最长等待时，软件会先自停并自动接续，
        # runner 的停止动作可能落到已接续的实验上（2026-11-07 审查 P2 提示）
        try:
            if float(getattr(self.cfg, "ocp_time_sec", 0)) <= float(self.cfg.max_ocp_sec):
                self.log("⚠ 软件侧 OCP 测量时间（%g s）≤ 最长等待（%g s）：软件到点会自停并"
                         "自动接续下一项。建议把 OCP 测量时间设为大于最长等待。"
                         % (self.cfg.ocp_time_sec, self.cfg.max_ocp_sec))
        except Exception:
            pass
        self.set_state(ST_CONNECT)

    def abort(self):
        self.aborting = True
        self.log("收到中止请求")

    def _fail(self, msg: str):
        """worker 异常出口：置错误态并停止运行（对齐 runner6._fail）。"""
        self.error = msg
        self.set_state(ST_ERROR, msg)
        self.running = False

    # ---------- 主循环 ----------
    def tick(self):
        if not self.running:
            return
        if self.aborting:
            self._do_abort()
            return
        try:
            self._step()
        except Exception as e:
            import traceback
            self.error = "%s: %s" % (type(e).__name__, e)
            self.log("异常：" + traceback.format_exc(limit=4))
            # 出异常也必须收尾：否则脚本退了、实验还在采集没人停
            # （2026-11-06 代码审查 P2，对齐 runner5 的异常收尾）。
            try:
                if self.drv is not None:
                    self.drv.stop_current()
                    self.ui.clear_modals(2)
            except Exception:
                pass
            self.set_state(ST_ERROR, self.error)
            self.running = False

    # ---------- 各阶段 ----------
    def _step(self):
        st = self.state

        if st == ST_CONNECT:
            self.ui = Studio()
            self.ui.log = self.log
            if self.ui.main is None:
                self.set_state(ST_ERROR, "连不上 CS Studio，请先打开软件")
                self.running = False
                return
            self.drv = ParasiteDriver(self.ui, log=self.log)
            self.set_state(ST_PREPARE)
            return

        if st == ST_PREPARE:
            self._do_prepare()
            return

        if st == ST_AREA:
            self._do_area()
            return

        if st == ST_CONF_OCP:
            ok = self.drv.configure_row(self.ocp_index, OcpSpec(
                file=self.files["ocp"],
                test_time_sec=self.cfg.ocp_time_sec,
                freq_hz=self.cfg.ocp_freq_hz,
                use_delta_stop=False,      # 关键：不用软件自带停机条件
            ))
            if not ok:
                self.log("开路电位参数填写失败，尝试停止残留实验后重试…")
                try:
                    self.drv.stop_current()
                    time.sleep(4.0)
                    self.ui.clear_modals(2)
                    ok = self.drv.configure_row(self.ocp_index, OcpSpec(
                        file=self.files["ocp"],
                        test_time_sec=self.cfg.ocp_time_sec,
                        freq_hz=self.cfg.ocp_freq_hz,
                        use_delta_stop=False,
                    ))
                except Exception as e:
                    self.log("重试异常：%s" % e)
            if not ok:
                self.set_state(ST_ERROR, "开路电位参数填写失败（序列可能仍被实验锁定）")
                self.running = False
                return
            self.set_state(ST_CONF_EIS if self.eis_index is not None else ST_CONF_TEST)
            return

        if st == ST_CONF_EIS:
            from driver import EisSpec
            spec = EisSpec(file=self.files["eis"],
                           dc_v=self.cfg.eis_dc_v,
                           amp_mv=self.cfg.eis_amp_mv,
                           init_freq=self.cfg.eis_init_freq,
                           final_freq=self.cfg.eis_final_freq,
                           pts_per_decade=self.cfg.eis_pts_per_decade)
            ok = self.drv.configure_row(self.eis_index, spec)
            if not ok:
                self.set_state(ST_ERROR, "阻抗参数填写失败")
                self.running = False
                return
            self.set_state(ST_CONF_TEST)
            return

        if st == ST_CONF_TEST:
            spec = self._make_test_spec()
            ok = self.drv.configure_row(self.test_index, spec)
            if not ok:
                self.set_state(ST_ERROR, "测试项参数填写失败")
                self.running = False
                return
            self.set_state(ST_START)
            return

        if st == ST_START:
            self.log("流程：开路电位 → %s → %s" % (
                "交流阻抗" if getattr(self, "eis_index", None) is not None else "(无阻抗)",
                self.cfg.item))
            if not self.drv.start():
                self.set_state(ST_ERROR, "启动实验失败（可能有对话框挡路）")
                self.running = False
                return
            self.tail_ocp = CorFileTail(self.files["ocp"])
            self._phase_deadline = time.time() + 60.0
            self.set_state(ST_MON_OCP, "等待数据文件出现")
            return

        if st == ST_MON_OCP:
            self._do_monitor_ocp()
            return

        if st == ST_STOP_OCP:
            ok = self.drv.stop_current()
            self.log("点「停止」-> %s" % ok)
            if not ok:
                self.set_state(ST_ERROR, "点停止失败")
                self.running = False
                return
            if getattr(self, "_ocp_retry", False):
                self._ocp_retry = False
                # 停止=自动接续下一项：停完 OCP 序列会自开 EIS/测试项把序列
                # 锁住，直接 configure_row 必失败——先循环停到序列真正空闲
                # （对齐 _do_abort 的做法，2026-11-07 审查 P1）
                self._stop_sequence_until_idle()
                # 轮号剥旧后缀必须在 splitext 之后按"根"剥：files["ocp"] 带
                # .txt，对整名 re.sub(r"_第\d+轮$") 永不匹配，第 3 轮起会累积
                # 成 "…_第2轮_第3轮.txt"（2026-11-07 审查 P3）
                root, ext = os.path.splitext(self.files.get("ocp", ""))
                root = re.sub(r"_第\d+轮$", "", root)
                cand = "%s_第%d轮%s" % (root, self._ocp_round + 1, ext or ".txt")
                k = 2
                while os.path.exists(cand):
                    cand = "%s_第%d轮_%d%s" % (root, self._ocp_round + 1, k, ext or ".txt")
                    k += 1
                self.files["ocp"] = cand
                self.stab.reset()
                self.log("→ 开始第 %d 轮开路电位：%s"
                         % (self._ocp_round + 1, os.path.basename(self.files["ocp"])))
                self.set_state(ST_CONF_OCP, "重新配置第 %d 轮开路电位" % (self._ocp_round + 1))
                return
            self.tail_test = CorFileTail(self.files["test"])
            self.test_started_at = time.time()
            # 软件停 OCP 后会自动接续跑 EIS（100kHz→0.01Hz 远超 120s），之后
            # 才轮到测试项——固定 120s 等测试文件必误报"数据文件没有出现"
            # （2026-11-07 审查 P1）。有 EIS 时按 eis_timeout_sec 量级给。
            if self.cfg.eis_enabled and getattr(self, "eis_index", None) is not None:
                wait = float(getattr(self.cfg, "eis_timeout_sec", 2400.0))
            else:
                wait = 120.0
            self._phase_deadline = time.time() + wait
            self.set_state(ST_MON_TEST, "等待测试项开始")
            return

        if st == ST_MON_TEST:
            self._do_monitor_test()
            return

    # ---------- 准备 ----------
    def _do_prepare(self):
        if not self.drv.ensure_channel():
            self.set_state(ST_ERROR, "找不到通道窗口，请在软件里打开「工作通道→通道1」")
            self.running = False
            return
        # 关掉上一轮残留的运行窗/参数窗——MDI 运行窗最大化时会把序列挡住，
        # 双击行会点到运行窗上（回归C 实测踩坑：上一轮直开模式留下的运行窗）
        try:
            from driver_direct import DirectDriver
            dd = DirectDriver(self.ui, self.drv, self.log)
            if dd.is_running():
                self.log("检测到实验在跑，先停止")
                dd.stop()
            if dd.close_run_windows():
                self.log("关掉了残留运行窗")
            dd.close_panels()
            self.ui.clear_modals()
        except Exception as e:
            self.log("清场跳过：%s" % e)
        rows = self.drv.read_sequence()
        if not rows:
            self.set_state(ST_ERROR, "序列为空，请先在软件里摆好「开路电位 + 测试项」")
            self.running = False
            return
        ocp = [r for r in rows if r["kind"] == EXP_OCP]
        want = EXP_TAFEL if self.cfg.item == "Tafel" else EXP_STEP
        test = [r for r in rows if r["kind"] == want]
        if not ocp:
            self.set_state(ST_ERROR, "序列里没有「开路电位测量」这一行")
            self.running = False
            return
        if not test:
            self.set_state(ST_ERROR, "序列里没有「%s」这一行，请先在软件里添加" % (
                "动电位扫描(Tafel)" if want == EXP_TAFEL else "任意恒电位阶梯波"))
            self.running = False
            return
        eis = [r for r in rows if r["kind"] == EXP_EIS]
        self.eis_index = eis[0]["index"] if eis else None
        if self.eis_index is not None and not self.cfg.eis_enabled:
            # 序列里留了 EIS 行但已取消勾选：build_filenames 不会生成 eis 文件名，
            # ST_CONF_EIS 会 KeyError('eis')（2026-11-07 审查 P2）
            self.set_state(ST_ERROR, "序列里仍有「频率扫描-电位控制模式」行，但已取消勾选④交流阻抗："
                                     "请在软件里移除该行，或重新勾选④")
            self.running = False
            return
        if self.cfg.eis_enabled and self.eis_index is None:
            self.set_state(ST_ERROR, "序列里没有「频率扫描-电位控制模式」这一行。请在软件里给该通道加一行：添加 → 测量方法 → 交流阻抗 → 频率扫描-电位控制模式(Nyquist, Bode)，放在开路电位之后、测试项之前。加一次即可（序列会被记住），或取消勾选「④ 交流阻抗」跳过这项。")
            self.running = False
            return
        self.ocp_index = ocp[0]["index"]
        self.test_index = test[0]["index"]
        self.test_kind = want
        if self.eis_index is not None:
            self.log("序列：OCP 第 %d 行，阻抗 第 %d 行，测试项 第 %d 行" % (
                self.ocp_index + 1, self.eis_index + 1, self.test_index + 1))
        else:
            self.log("序列：OCP 在第 %d 行，测试项在第 %d 行" % (
                self.ocp_index + 1, self.test_index + 1))
        if self.ocp_index > self.test_index:
            self.set_state(ST_ERROR, "开路电位必须在测试项之前执行")
            self.running = False
            return
        if self.eis_index is not None and not (self.ocp_index < self.eis_index < self.test_index):
            self.set_state(ST_ERROR, "阻抗必须排在开路电位之后、测试项之前")
            self.running = False
            return
        self.set_state(ST_AREA)

    def _set_area_on_row(self, index: int, label: str) -> bool:
        """在某一行设面积；失败多半是上一轮实验还在跑把序列锁住了，先停再试一次。"""
        ok = self.drv.set_cell_area(index, self.cfg.area_cm2)
        if not ok:
            self.log("%s 面积设置失败，可能有实验仍在运行；尝试停止后重试…" % label)
            try:
                self.drv.stop_current()
                time.sleep(4.0)
                self.ui.clear_modals(2)
                ok = self.drv.set_cell_area(index, self.cfg.area_cm2)
            except Exception as e:
                self.log("重试异常：%s" % e)
        if not ok:
            self.log("%s 面积设置仍失败，继续（面积只影响电流密度换算）" % label)
        return ok

    def _do_area(self):
        # 面积在每个实验里各自存，所以 OCP / 阻抗 / 测试 三行都要设
        self._set_area_on_row(self.ocp_index, "开路电位")
        if getattr(self, "eis_index", None) is not None:
            self._set_area_on_row(self.eis_index, "交流阻抗")
        self._set_area_on_row(self.test_index, "测试项")
        self.set_state(ST_CONF_OCP)

    def _make_test_spec(self):
        if self.test_kind == EXP_TAFEL:
            return TafelSpec(file=self.files["test"],
                             init_v=self.cfg.tafel_init_v,
                             final_v=self.cfg.tafel_final_v,
                             scan_mv_s=self.cfg.tafel_scan_mv_s,
                             sample_interval_s=self.cfg.tafel_interval_s,
                             vs_ocp=True)
        return StepSpec(file=self.files["test"],
                        init_v=self.cfg.step_init_v,
                        final_v=self.cfg.step_final_v,
                        delta_v=self.cfg.step_delta_v,
                        hold_s=self.cfg.step_hold_s,
                        freq_hz=self.cfg.ocp_freq_hz,
                        cycles=getattr(self.cfg, "step_cycles", 20),
                        use_steps=getattr(self.cfg, "step_use_steps", False))

    # ---------- 开路电位判稳 ----------
    def _do_monitor_ocp(self):
        now = time.time()
        if self.tail_ocp is None:
            self.set_state(ST_ERROR, "内部错误：未初始化文件监视")
            self.running = False
            return
        if not self.tail_ocp.exists():
            if now > self._phase_deadline:
                self.set_state(ST_ERROR, "等不到数据文件 %s，实验可能没启动" % self.files["ocp"])
                self.running = False
            return
        self.tail_ocp.poll()
        st = self.stab.feed(self.tail_ocp.series_ev())
        self.ocp_elapsed = st.t_now
        self._on_sample(st.t_now, st.mean_v, st)

        if now - self._last_progress > 5.0:
            self._last_progress = now
            self.set_state(ST_MON_OCP, "t=%.1fs E=%.6fV 斜率=%.2f mV/min 峰峰=%.2f mV 保持=%.0f/%.0fs"
                           % (st.t_now, st.mean_v, st.slope_mv_per_min, st.ppt_mv,
                              st.held_sec, self.cfg.stab.hold_sec))

        if st.stable:
            self.ocp_ok_volt = st.mean_v
            self.ocp_reason = st.reason
            self.log("判稳：E=%.6f V（%s）" % (st.mean_v, st.reason))
            self.set_state(ST_STOP_OCP, "开路电位已稳定，停当前实验并接续下一项")
            return
        # 数据停滞：软件侧 OCP 测量时间先到会自停（文件不再增长），runner 若
        # 干等会撞总超时并误报错误，期间 EIS/测试项在无人监视下跑完
        # （2026-11-07 审查 P2；对齐 runner5 的 _ocp_stall）
        if self.tail_ocp.samples and self.tail_ocp.finished_quiet(10.0):
            self.ocp_ok_volt = self.tail_ocp.samples[-1].e
            self.ocp_reason = "软件侧自停（数据 10s 未增长）"
            self.log("开路电位数据 10s 未增长 → 软件已自行结束本轮，按当前值接续")
            self.set_state(ST_STOP_OCP, self.ocp_reason)
            return
        if st.t_now >= self.cfg.max_ocp_sec:
            self.ocp_ok_volt = st.mean_v
            maxr = max(1, int(getattr(self.cfg, "ocp_max_rounds", 1) or 1))
            if self._ocp_round + 1 < maxr:
                self._ocp_round += 1
                self._ocp_retry = True
                self.ocp_reason = "本轮 %.0fs 未判稳，准备第 %d 轮" % (st.t_now, self._ocp_round + 1)
                self.log("本轮 %.0fs 未判稳 → 准备第 %d 轮（共最多 %d 轮）"
                         % (st.t_now, self._ocp_round + 1, maxr))
            else:
                self.ocp_reason = "超时（%.0fs，已测 %d 轮）强制切换" % (st.t_now, self._ocp_round + 1)
                self.log("开路电位等待超时（%.0fs，已测 %d 轮），按当前值 %.6f V 继续"
                         % (st.t_now, self._ocp_round + 1, st.mean_v))
            self.set_state(ST_STOP_OCP, self.ocp_reason)
            return
        # 总超时要按最大轮数放大：固定 max_ocp_sec+300 会在第 2 轮开跑约
        # 300 s 时把正常的重试误杀（审查 P1-6）
        _maxr = max(1, int(getattr(self.cfg, "ocp_max_rounds", 1) or 1))
        if now - self._t0 > self.cfg.max_ocp_sec * _maxr + 600:
            self.set_state(ST_ERROR, "开路电位阶段总超时")
            self.running = False

    # ---------- 测试项监控 ----------
    def _do_monitor_test(self):
        now = time.time()
        if self.tail_test is None:
            self.set_state(ST_ERROR, "内部错误：未初始化测试文件监视")
            self.running = False
            return
        if not self.tail_test.exists():
            # EIS 可能还在跑：其数据文件仍在增长时顺延等待
            # （有 EIS 时 deadline 只是个兜底上限，2026-11-07 审查 P1 配套）
            if getattr(self.cfg, "eis_enabled", False) and getattr(self, "eis_index", None) is not None:
                for ext in (".txt", ".z60"):
                    eis_p = self.files.get("eis", "") + ext
                    try:
                        if (os.path.exists(eis_p)
                                and time.time() - os.path.getmtime(eis_p) < 8.0):
                            self._phase_deadline = max(self._phase_deadline, now + 60.0)
                            break
                    except OSError:
                        continue
            if now > self._phase_deadline:
                self.set_state(ST_ERROR, "测试项数据文件没有出现，接续可能失败")
                self.running = False
            return
        got = self.tail_test.poll()
        if got and self.test_first_data_at is None:
            self.test_first_data_at = now
        # 至少见到 15 s 的数据、且文件 10 s 没再变，才认定测试结束
        # 主判据：电流密度达到 1×10⁻³ A/cm² 就停（文件第 2 列就是 A/cm²）。
        # 该判据只适用于动电位；阶梯波是恒电位台阶程序，走完即止，不看电流。
        thr = getattr(self.cfg, "test_stop_i_density", None)
        if (thr is not None and self.test_kind == EXP_TAFEL
                and self.tail_test.samples):
            s_last = self.tail_test.samples[-1]     # watch.Sample：t/e/i
            # ★ 只对"新到的点"计数：数据约 3s 才 flush 一次，而 tick 约 250ms
            # 跑一次——按 tick 对同一个 samples[-1] 反复 +1 的话，单点尖峰在
            # 一个 flush 间隔内就攒满 2，防噪设计失效（2026-11-07 审查 P1）
            s_t = getattr(s_last, "t", None)
            if s_t != getattr(self, "_i_last_t", None):
                self._i_last_t = s_t
                try:
                    if s_last.i is not None and abs(float(s_last.i)) >= float(thr):
                        self._i_hit = getattr(self, "_i_hit", 0) + 1
                    else:
                        self._i_hit = 0
                except (TypeError, ValueError):
                    self._i_hit = 0
                if self._i_hit >= 2:
                    self.log("电流密度 %+.4e A/cm² 连续 %d 点达标（t=%.1fs E=%+.4f V）→ 判定动电位结束"
                             % (float(s_last.i), self._i_hit, float(s_last.t),
                                float(s_last.e)))
                    # 达标后必须真的把实验停掉再结束（审查 P2-16）
                    try:
                        self.drv.stop_current()
                    except Exception as e:
                        self.log("点停止出错：%s" % e)
                    self.set_state(ST_DONE, "电流达标，测试完成")
                    self.running = False
                    return
        if self.test_first_data_at and now - self.test_first_data_at > 15:
            if self.tail_test.finished_quiet(quiet_sec=10.0):
                self.log("测试文件已 %d 字节、%d 点，10 s 未再增长 -> 判定结束"
                         % (self.tail_test.size(), len(self.tail_test.samples)))
                self.set_state(ST_DONE, "测试完成")
                self.running = False
                return
        if now - (self.test_started_at or now) > self.cfg.test_timeout_sec:
            self.set_state(ST_ERROR, "测试项超时")
            self.running = False

    def result_files(self):
        """看板上报用：列出已落盘的产物 (文件名, 字节数)。"""
        out = []
        for _k, v in getattr(self, "files", {}).items():
            if not v:
                continue
            for p in (v, os.path.splitext(v)[0] + ".cor", v + ".z60"):
                try:
                    if os.path.exists(p):
                        out.append((os.path.basename(p), os.path.getsize(p)))
                        break
                except OSError:
                    continue
        return out

    # ---------- 中止 ----------
    def _stop_sequence_until_idle(self, max_tries: int = 6) -> None:
        """循环停止直到序列真正空闲。

        「停止」的语义是"中止当前实验并自动接续下一项"——停完 OCP 后序列会
        自开 EIS/测试项，一次 stop_current 不够（2026-11-07 审查 P1）。
        与 _do_abort 同思路，但给多轮判稳的重配置让路，而不是清空序列。
        """
        for _ in range(max_tries):
            try:
                from driver_direct import DirectDriver
                dd = DirectDriver(self.ui, self.drv, self.log)
                if not dd.is_running():
                    return
                self.log("  序列已接续下一项，继续停止…")
                dd.stop()
            except Exception as e:      # noqa: BLE001
                self.log("  停序列异常（继续）：%s" % e)
                return
            time.sleep(2.0)
        self.log("  警告：多次停止后仍检测到运行，将尝试直接重配置")

    def _do_abort(self):
        """中止 = 终止整个序列。

        注意 CS Studio 的「停止」语义是"停当前实验并自动开始序列的下一项"，
        所以只点一次停止，Tafel 会立刻接着跑（实测中止后 2 s 就写出了
        动电位数据的 2002 B）。这里必须反复停止，直到序列重新可编辑。
        """
        try:
            if self.drv is not None:
                for i in range(6):
                    self.drv.stop_current()
                    time.sleep(1.2)
                    self.ui.clear_modals(2)
                    if self._sequence_idle():
                        if i:
                            self.log("已停止序列中后续自动接续的实验（第 %d 次）" % (i + 1))
                        break
                    self.log("序列仍在运行，继续停止…（第 %d 次）" % (i + 1))
        except Exception as e:
            self.log("中止时停止实验出错：%s" % e)
        self.set_state(ST_ABORT)
        self.running = False
        self.aborting = False

    def _sequence_idle(self) -> bool:
        """能否打开参数窗 = 序列是否已停止。"""
        try:
            pnl = self.ui.open_row_panel(self.ocp_index)
            if pnl is None:
                return False
            self.ui.press_cancel(pnl)
            time.sleep(0.4)
            self.ui.clear_modals(2)
            return True
        except Exception:
            return False

    # ---------- 汇总 ----------
    def summary(self) -> List[str]:
        lines = []
        lines.append("样品：%s    面积：%s cm²    测试项目：%s"
                     % (self.cfg.sample, self.cfg.area_cm2, self.cfg.item))
        if self.ocp_ok_volt is not None:
            lines.append("开路电位：%.6f V（%s，用时 %.1f s）"
                         % (self.ocp_ok_volt, self.ocp_reason, self.ocp_elapsed))
        for k, v in self.files.items():
            if v:
                label = {"ocp": "开路电位", "eis": "交流阻抗"}.get(k, self.cfg.item)
                lines.append("%s 文件：%s" % (label, v))
        if self.state == ST_DONE:
            lines.append("状态：完成")
        elif self.state == ST_ERROR:
            lines.append("状态：出错 - %s" % self.error)
        return lines
