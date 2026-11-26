# -*- coding: utf-8 -*-
"""code/policies.py —— 判稳 / 判停策略（与 C# 宿主里的 Policy 保持同一套数学）。

为什么要 Python 版：
  1. 可以在**离线真机曲线**上先标定，不占用任何设备/端口；
  2. 可以写单元测试（C# 侧只能端到端验证）；
  3. 宿主和这里用同样的公式与默认值，改参数时两边一起改。

纪律（来自 00 文档 §5.2 的标定结论）：
  * **只用斜率判不了稳** —— 真实 OCP 数据在 250s 附近斜率会被正负抵消算成 0，
    必须同时约束「窗口内峰峰值」；
  * 判稳要求斜率与峰峰值**同时**达标，并且**连续保持 hold_sec 秒**；
  * 永远保留最长等待兜底（max_sec），因为真实样品会一直缓慢漂移。

数据形状：series 是 [(t, E, I, Q), ...]，t 秒、E 伏、I 安（或 A/cm²）、Q 库仑。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

Series = List[Tuple[float, float, float, float]]


# ------------------------------------------------------------------ 读真实数据
def read_csstudio_txt(path: str) -> Series:
    """读 CS Studio 的 .txt（第 1 行 CSV 头 + gzip base64，第 2 行列名，第 3 行起数据）。"""
    out: Series = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for line in lines[2:]:
        line = line.strip()
        if not line or line[0].isalpha():
            continue
        parts = line.replace(",", "\t").split("\t")
        parts = [p for p in parts if p.strip()]
        if len(parts) < 3:
            continue
        try:
            e = float(parts[0])
            i = float(parts[1])
            t = float(parts[2])
        except ValueError:
            continue
        out.append((t, e, i, math.nan))
    return out


def read_cor(path: str) -> Series:
    """读原生 .cor（前若干行是头，数据行是三列 E\\ti\\tt）。"""
    out: Series = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or not (line[0].isdigit() or line[0] == "-"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                e = float(parts[0])
                i = float(parts[1])
                t = float(parts[2])
            except ValueError:
                continue
            out.append((t, e, i, math.nan))
    return out


# ------------------------------------------------------------------ 判稳
@dataclass
class StabilizeDetector:
    """OCP 判稳：窗口内斜率(mV/min) 与 峰峰值(mV) 双约束 + 连续保持。"""

    slope_mv_per_min: float = 5.0
    peak_to_peak_mv: float = 5.0
    window_sec: float = 30.0
    hold_sec: float = 60.0

    _hold_start: Optional[float] = field(default=None, init=False, repr=False)

    def window_stats(self, series: Sequence[Tuple[float, float, float, float]]) -> Optional[dict]:
        if len(series) < 4:
            return None
        t_last = series[-1][0]
        t_from = t_last - self.window_sec
        i0 = len(series) - 1
        while i0 > 0 and series[i0][0] > t_from:
            i0 -= 1

        n = 0
        s_t = s_e = s_tt = s_te = 0.0
        lo, hi = math.inf, -math.inf
        for t, e, _i, _q in series[i0:]:
            if math.isnan(e):
                continue
            lo = min(lo, e)
            hi = max(hi, e)
            s_t += t
            s_e += e
            s_tt += t * t
            s_te += t * e
            n += 1
        if n < 4:
            return None
        den = n * s_tt - s_t * s_t
        slope = math.inf if den == 0 else ((n * s_te - s_t * s_e) / den) * 60.0 * 1000.0
        return {
            "n": n,
            "t_from": series[i0][0],
            "t_to": t_last,
            "slope_mv_per_min": slope,
            "peak_to_peak_mv": (hi - lo) * 1000.0,
            "mean_v": s_e / n,
        }

    def ok_now(self, series) -> Tuple[bool, Optional[dict]]:
        st = self.window_stats(series)
        if st is None:
            return False, None
        good = (abs(st["slope_mv_per_min"]) <= self.slope_mv_per_min
                and st["peak_to_peak_mv"] <= self.peak_to_peak_mv)
        return good, st

    # 与宿主同接口：吃全序列 + 已用时间
    def update(self, series, elapsed: float) -> Tuple[bool, Optional[str], Optional[dict]]:
        good, st = self.ok_now(series)
        if not good:
            self._hold_start = None
            return False, None, st
        if self._hold_start is None:
            self._hold_start = elapsed
        if elapsed - self._hold_start >= self.hold_sec:
            return True, "stabilized", st
        return False, None, st


def scan_stabilize(series: Sequence[Tuple[float, float, float, float]],
                   **kw) -> Optional[dict]:
    """离线扫一遍，返回首次判稳的点（用于标定/回归）。

    关键字名与 job 文件一致（slope_mv_per_min 等），内部映射到 dataclass 字段。
    """
    det = StabilizeDetector(**kw)
    for k in range(len(series)):
        sub = series[: k + 1]
        elapsed = sub[-1][0]
        done, why, st = det.update(sub, elapsed)
        if done:
            return {"t": elapsed, "E": sub[-1][1], "stats": st}
    return None


# ------------------------------------------------------------------ 判停
@dataclass
class CurrentDensityStopper:
    """Tafel 判停：电流密度连续 confirm_n 个点超阈值。"""

    limit: float = 5.0
    confirm_n: int = 2

    _hit: int = field(default=0, init=False, repr=False)

    def update(self, series, elapsed: float) -> Tuple[bool, Optional[str]]:
        if not series:
            return False, None
        i = abs(series[-1][2])
        if math.isnan(i):
            return False, None
        if i >= self.limit:
            self._hit += 1
            if self._hit >= self.confirm_n:
                return True, "current_density"
        else:
            self._hit = 0
        return False, None


@dataclass
class TimeLimit:
    sec: float = 60.0

    def update(self, series, elapsed: float):
        return (elapsed >= self.sec), ("max_sec" if elapsed >= self.sec else None)


def make_policy(spec: dict):
    """按宿主的 stop 规格构造策略（键名与此前 job 文件一致）。"""
    kind = (spec or {}).get("type", "max_sec")
    if kind == "stabilize":
        return StabilizeDetector(
            slope_mv_per_min=spec.get("slope_mv_per_min", 5.0),
            peak_to_peak_mv=spec.get("peak_to_peak_mv", 5.0),
            window_sec=spec.get("window_sec", 30.0),
            hold_sec=spec.get("hold_sec", 60.0),
        )
    if kind == "current_density":
        return CurrentDensityStopper(limit=spec.get("limit", 5.0),
                                    confirm_n=int(spec.get("confirm_n", 2)))
    return TimeLimit(sec=spec.get("sec", 60.0))


# ------------------------------------------------------------------ 自测
if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        # 合成一段：先漂移后稳
        series = []
        for k in range(600):
            t = k * 0.5
            e = -0.16 + min(t, 200) * 0.0002 + (0.00002 * math.sin(k))
            series.append((t, e, 1e-10, math.nan))
        hit = scan_stabilize(series, window_sec=30, hold_sec=60,
                             slope_mv_per_min=5.0, peak_to_peak_mv=5.0)
        print("合成数据判稳点:", hit)
    else:
        s = read_csstudio_txt(path) if path.endswith(".txt") else read_cor(path)
        print("样本 %d 点，t=%.1f..%.1f s" % (len(s), s[0][0], s[-1][0]))
        for w in (30, 60):
            for h in (30, 60):
                hit = scan_stabilize(s, window_sec=w, hold_sec=h)
                print("  window=%ds hold=%ds -> %s" % (
                    w, h,
                    ("t=%.1fs E=%.6f V (slope=%.2f mV/min, ptp=%.2f mV)"
                     % (hit["t"], hit["E"], hit["stats"]["slope_mv_per_min"],
                        hit["stats"]["peak_to_peak_mv"])) if hit else "未判稳"))
