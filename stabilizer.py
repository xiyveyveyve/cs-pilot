# -*- coding: utf-8 -*-
"""开路电位判稳算法（两阶段判据）。

判据来源（2026-10-31 会话 session-a581934c + 2026-11-02 用户补充）
---------------------------------------------------------------
**两阶段设计**：前 10 分钟用非常严格的标准（满足也能停），
10 分钟后切到放宽的标准（避免在噪声体系上干等）。

  阶段 A（0 ≤ t < 600 s）"严格"
      斜率 |dE/dt| < 1 mV/min  且  窗口峰峰值 < 2 mV
  阶段 B（t ≥ 600 s）"宽松"
      斜率 |dE/dt| < 5 mV/min  且  窗口峰峰值 < 5 mV
      **并且**相邻 5 分钟快照的电位差 < 5 mV（ASTM G59 的稳态思路）
  两阶段都要求达标后连续保持 hold_sec（默认 120 s）；最长等待兜底 1800 s。

数值依据：
  * 通用文献 / ASTM G59 主流：OCP 漂移 < 1 mV/min 才开扫（严格体系 0.5 mV/min）→ 阶段 A
  * 厂商科思特（就是 CS Studio 的厂）实验操作手册：
    「该过程也可以按照行业标准里写的**等待 10 分钟**后，即开始进行动电位扫描测试」→ 600 s 切点
  * **ASTM G59 / ISO 17475（Bio-Logic、Metrohm 复现）**：
    「the OCP of the sample is measured at 5 and 55 minutes to ensure the system stationarity」
    —— 即"隔一段时间取一次 OCP 快照，两次接近才算稳" → 本实现做成**每满 5 分钟取一次快照**，
    相邻快照差 < 15 mV（≈3 mV/min）才算稳（比只在 5/55 min 两点取值更适合自动化，也符合"一直稳"的语义）
  * Pine Research：几分钟内 OCP 变化在 ±5 mV 以内即可；Metrohm 复现 ASTM G59 的例子是 50 分钟差 20 mV（0.4 mV/min）→ 快照阈值取 15 mV（3 mV/min 等效）

为什么软件里设了也不管用
------------------------
CS Studio6 的 OcpWave 条件写成
  `测量终止:电位变化<0.0833mV/s and 时间>=600s`
界面上显示 and，**实际执行是"时间到就结束"**（会话里已实测证实），
漂移条件形同虚设 —— 所以必须在外部判稳、再由外部让软件停机。

峰峰值判据是本项目额外加的：真实 994 s 数据里电位先降后升，逐段斜率正负抵消，
单看斜率会在电位仍明显漂移时"提前判稳"。可把峰峰值设成很大来关掉。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class StabConfig:
    # ---- 阶段 A（严格，前 strict_until_sec 秒）----
    strict_until_sec: float = 600.0            # 10 分钟切换点
    strict_slope_mv_per_min: float = 1.0       # 文献主流严格值
    strict_peak_to_peak_mv: float = 2.0
    strict_hold_sec: float = 120.0
    # ---- 阶段 B（宽松，>= strict_until_sec）----
    slope_limit_mv_per_min: float = 5.0        # 0.0833 mV/s，厂商手册放宽值
    peak_to_peak_mv: float = 5.0
    hold_sec: float = 120.0
    # ---- 快照对比（ASTM G59 稳态思路，每满 N 秒取一次，相邻差 < 阈值）----
    snapshot_every_sec: float = 300.0          # 5 分钟一个快照
    snapshot_max_drift_mv: float = 15.0   # 3 mV/min 等效，比斜率判据稍严，专治"缓漂"
    snapshot_required: bool = True             # 阶段 B 判稳时必须至少两个快照且达标
    # ---- 公共 ----
    window_sec: float = 60.0
    min_points: int = 30

    def phase_of(self, t_sec: float) -> str:
        return "strict" if t_sec < self.strict_until_sec else "loose"

    def limits_of(self, t_sec: float) -> Tuple[float, float, float]:
        """返回 (斜率上限 mV/min, 峰峰上限 mV, 保持秒数)。"""
        if t_sec < self.strict_until_sec:
            return (self.strict_slope_mv_per_min, self.strict_peak_to_peak_mv,
                    self.strict_hold_sec)
        return (self.slope_limit_mv_per_min, self.peak_to_peak_mv, self.hold_sec)


@dataclass
class StabState:
    stable: bool = False
    reason: str = ""
    slope_mv_per_min: float = 0.0
    ppt_mv: float = 0.0
    mean_v: float = 0.0
    window_n: int = 0
    held_sec: float = 0.0
    t_now: float = 0.0
    phase: str = ""          # "strict" / "loose"
    need_hold: float = 0.0   # 当前阶段要求的保持秒数
    snaps: int = 0           # 已有快照数
    snap_drift_mv: float = 0.0   # 相邻快照差值（mV），不足两个快照时为 0


class OcpStabilizer:
    """增量式判稳：每来一批点调用 feed()，返回当前状态。"""

    def __init__(self, cfg: Optional[StabConfig] = None):
        self.cfg = cfg or StabConfig()
        self.ts: List[float] = []
        self.vs: List[float] = []
        self._hold_start: Optional[float] = None
        self._snaps: List[Tuple[float, float]] = []   # [(t, E_mean)]
        self._snap_next: float = self.cfg.snapshot_every_sec
        self.state = StabState()

    def reset(self) -> None:
        self.ts.clear()
        self.vs.clear()
        self._hold_start = None
        self._snaps.clear()
        self._snap_next = self.cfg.snapshot_every_sec
        self.state = StabState()

    def _maybe_snapshot(self, t_end: float) -> None:
        """每满 snapshot_every_sec 秒记录一次电位快照（取该时刻附近窗口的均值）。"""
        cfg = self.cfg
        if cfg.snapshot_every_sec <= 0:
            return
        while t_end >= self._snap_next:
            due = self._snap_next
            # 快照时刻 due，取 [due-10, due+10] 内的点求均值
            vals = [v for t, v in zip(self.ts, self.vs) if abs(t - due) <= 10.0]
            if not vals:
                vals = [self.vs[-1]]
            self._snaps.append((due, sum(vals) / len(vals)))
            self._snap_next += cfg.snapshot_every_sec

    def feed(self, series: List[Tuple[float, float]]) -> StabState:
        """series: [(t_sec, E_V)]，可重复喂已读过的点，内部按 t 去重。"""
        for t, v in series:
            if self.ts and t < self.ts[-1]:
                # 时间回退 = 文件被覆盖重建/新一轮实验：旧序列作废，从新点
                # 重新积累（旧代码把回退后的新点全部静默丢弃，判稳永久瘫痪，
                # 审查 #23）
                self.reset()
            if not self.ts or t > self.ts[-1]:
                self.ts.append(float(t))
                self.vs.append(float(v))
            elif t == self.ts[-1]:
                self.vs[-1] = float(v)
        return self.evaluate()

    def evaluate(self) -> StabState:
        cfg = self.cfg
        st = StabState()
        if len(self.ts) < 2:
            self.state = st
            return st

        st.t_now = self.ts[-1]
        t_end = self.ts[-1]
        t_lo = t_end - cfg.window_sec
        idx = [i for i, t in enumerate(self.ts) if t >= t_lo]
        if len(idx) < 5:
            st.reason = "窗口内点数不足"
            self.state = st
            return st

        tw = [self.ts[i] for i in idx]
        vw = [self.vs[i] for i in idx]
        st.window_n = len(tw)
        st.mean_v = sum(vw) / len(vw)
        st.ppt_mv = (max(vw) - min(vw)) * 1000.0
        st.slope_mv_per_min = _slope_mv_per_min(tw, vw)

        # 按当前时刻选阶段
        st.phase = cfg.phase_of(t_end)
        slope_lim, ppt_lim, hold_req = cfg.limits_of(t_end)
        st.need_hold = hold_req
        tag = "严格" if st.phase == "strict" else "宽松"

        # 快照（每满 N 秒一个）
        self._maybe_snapshot(t_end)
        st.snaps = len(self._snaps)
        if st.snaps >= 2:
            st.snap_drift_mv = abs(self._snaps[-1][1] - self._snaps[-2][1]) * 1000.0

        ok_slope = abs(st.slope_mv_per_min) < slope_lim
        ok_ppt = st.ppt_mv < ppt_lim
        ok_n = st.window_n >= cfg.min_points
        # 快照判据只在宽松阶段生效（严格阶段本来就严到不需要）
        ok_snap = True
        if st.phase == "loose" and cfg.snapshot_required:
            ok_snap = st.snaps >= 2 and st.snap_drift_mv < cfg.snapshot_max_drift_mv

        if ok_slope and ok_ppt and ok_n and ok_snap:
            if self._hold_start is None:
                self._hold_start = t_end
            st.held_sec = t_end - self._hold_start
            if st.held_sec >= hold_req:
                st.stable = True
                st.reason = "%s阶段：斜率与峰峰值达标并保持 %.0f s" % (tag, st.held_sec)
            else:
                st.reason = "%s阶段：指标达标，保持中 %.0f/%.0f s" % (tag, st.held_sec, hold_req)
        else:
            self._hold_start = None
            st.held_sec = 0.0
            bits = ["%s阶段" % tag]
            if not ok_slope:
                bits.append("|斜率| %.2f ≥ %.2f mV/min" % (abs(st.slope_mv_per_min), slope_lim))
            if not ok_ppt:
                bits.append("峰峰 %.2f ≥ %.2f mV" % (st.ppt_mv, ppt_lim))
            if not ok_n:
                bits.append("点少 %d" % st.window_n)
            if not ok_snap:
                if st.snaps < 2:
                    bits.append("快照不足(需 2 个，现 %d)" % st.snaps)
                else:
                    bits.append("相邻5min快照差 %.1f ≥ %.1f mV" % (st.snap_drift_mv, cfg.snapshot_max_drift_mv))
            if st.phase == "strict":
                bits.append("%.0fs 后放宽" % (cfg.strict_until_sec - t_end))
            st.reason = "；".join(bits)

        self.state = st
        return st


def _slope_mv_per_min(t: List[float], v: List[float]) -> float:
    """最小二乘斜率，单位 mV/min。"""
    n = len(t)
    if n < 2:
        return 0.0
    mt = sum(t) / n
    mv = sum(v) / n
    num = sum((t[i] - mt) * (v[i] - mv) for i in range(n))
    den = sum((t[i] - mt) ** 2 for i in range(n))
    if den <= 0:
        return 0.0
    return (num / den) * 60.0 * 1000.0
