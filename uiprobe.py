# -*- coding: utf-8 -*-
"""uiprobe.py —— 从 CS Studio 实验运行窗口的界面控件读取实时数据。

为什么需要它：
    CS Studio6 运行中数据会持续落盘（约 3 s flush 一次），所以 cspilot 用
    watch.CorFileTail 直接 tail 文件即可。
    **CS Studio5 运行期间独占锁住数据文件**（Python 打开抛 PermissionError），
    文件路线走不通，只能改从运行窗口的数值显示控件读数。

实测（CS Studio5 5.6.1202.2，演示模式，OCP 10 Hz）：
    运行窗口标题形如 `开路电位 <2mA>  D:\\path\\xxx.txt.cor`
    窗口内 Text 控件按 UIA 遍历顺序成对出现（数值 + 单位）：
        图形坐标 / 527 / 点 / 52.60 / 秒 / -3.45277E-02 / V / 1.00000E-10 / A / 2mA
    每 2 s 采样一次，电位、时间、点数**每次都变** → 可作判稳数据源。
    状态栏还有 `采样频率(Hz):10,测量时间(s):180`。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

# 数值文本：允许 1.23E-04 / -0.123 / 45.6 等
_NUM_RE = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?$")


@dataclass
class UiSample:
    """一次界面读数。"""
    t_sec: float            # 已运行时间（秒）
    e_volt: Optional[float]  # 电位（V）
    i_amp: Optional[float]   # 电流（A）
    points: Optional[int]    # 已采集点数
    progress_pct: Optional[float]
    raw: dict

    def __repr__(self) -> str:
        return ("UiSample(t=%.2f, E=%s, I=%s, n=%s, %s%%)" %
                (self.t_sec, _fmt(self.e_volt), _fmt(self.i_amp), self.points,
                 _fmt(self.progress_pct)))


def _fmt(v) -> str:
    return "-" if v is None else ("%.6g" % v)


class UiSampler:
    """对某个实验运行窗口做只读采样。

    不点击、不输入，只读 Text 控件；失败时返回 None 而不是抛异常，
    让上层判稳循环可以容忍偶发的 UIA 抖动。
    """

    def __init__(self, window, log=None):
        self.win = window
        self.log = log or (lambda *a: None)
        self._t0 = time.time()

    # ---- 低层 ----
    def texts(self):
        out = []
        try:
            for c in self.win.descendants(control_type="Text"):
                try:
                    t = (c.window_text() or "").strip()
                    if t:
                        out.append(t)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    @staticmethod
    def _to_float(s):
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    def read(self) -> Optional[UiSample]:
        ts = self.texts()
        if not ts:
            return None

        e_val = None
        i_val = None
        t_sec = None
        points = None
        pct = None

        for idx, txt in enumerate(ts):
            # 电位：单位 "V" 的前一个数字
            if txt == "V" and idx > 0:
                v = self._to_float(ts[idx - 1])
                if v is not None:
                    e_val = v
            # 电流：单位 "A" 的前一个数字
            elif txt == "A" and idx > 0:
                v = self._to_float(ts[idx - 1])
                if v is not None:
                    i_val = v
            # 秒：单位 "秒" 的前一个数字
            elif txt == "秒" and idx > 0:
                v = self._to_float(ts[idx - 1])
                if v is not None:
                    t_sec = v
            # 点数：单位 "点" 的前一个整数
            elif txt == "点" and idx > 0:
                try:
                    points = int(float(ts[idx - 1]))
                except (TypeError, ValueError):
                    pass
            elif txt.endswith("%"):
                v = self._to_float(txt[:-1])
                if v is not None:
                    pct = v

        if t_sec is None:
            # 界面还没出时间 → 用墙钟兜底
            t_sec = time.time() - self._t0

        return UiSample(t_sec=t_sec, e_volt=e_val, i_amp=i_val,
                        points=points, progress_pct=pct,
                        raw={t: 1 for t in ts})

    # ---- 高层 ----
    def alive(self) -> bool:
        try:
            return bool(self.win.exists())
        except Exception:
            try:
                return self.win.window_text() != ""
            except Exception:
                return False

    def wait_first(self, timeout=30.0, poll=0.5) -> Optional[UiSample]:
        """等第一个有效读数（有 E 值）。"""
        end = time.time() + timeout
        while time.time() < end:
            s = self.read()
            if s is not None and s.e_volt is not None:
                return s
            time.sleep(poll)
        return None


def find_run_window(desktop, keywords=("开路电位", "动电位", "恒电位", "阶梯波"),
                    exclude=("CS Studio",), log=None):
    """在所有顶层窗口里找实验运行窗口（不在主窗 UIA 树里的独立窗口）。"""
    log = log or (lambda *a: None)
    try:
        wins = desktop.windows()
    except Exception as e:
        log("枚举窗口失败: %s" % e)
        return None
    for w in wins:
        try:
            t = w.window_text() or ""
        except Exception:
            continue
        if not t:
            continue
        if any(k in t for k in exclude):
            continue
        if any(k in t for k in keywords):
            return w
    return None


# ---------------------------------------------------------------- EIS 采样
class EisProgress:
    """阻抗扫描窗口的一次快照。"""

    __slots__ = ("points", "freq_hz", "z_re", "z_im", "z_abs", "theta",
                 "remain_sec", "total_points", "raw")

    def __init__(self, points=None, freq_hz=None, z_re=None, z_im=None,
                 z_abs=None, theta=None, remain_sec=None, total_points=None,
                 raw=None):
        self.points = points
        self.freq_hz = freq_hz
        self.z_re = z_re
        self.z_im = z_im
        self.z_abs = z_abs
        self.theta = theta
        self.remain_sec = remain_sec
        self.total_points = total_points
        self.raw = raw or []

    def __repr__(self):
        return ("EisProgress(points=%r freq=%r |Z|=%r remain=%r total=%r)"
                % (self.points, self.freq_hz, self.z_abs, self.remain_sec,
                   self.total_points))


class EisSampler:
    """只读阻抗运行窗口，解析 Points / 剩余时间 / 频率 / 总点数。"""

    def __init__(self, window, log=None):
        self.win = window
        self.log = log or (lambda *a: None)

    def alive(self) -> bool:
        try:
            return bool(self.win.exists() and self.win.is_visible())
        except Exception:
            return False

    def texts(self):
        out = []
        try:
            for c in self.win.descendants(control_type="Text"):
                try:
                    t = (c.window_text() or "").strip()
                    if t:
                        out.append(t)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    @staticmethod
    def _f(s):
        try:
            return float(str(s).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _after(txt, sep):
        """取 'X: 123' 里冒号后面的第一个数字。"""
        try:
            if sep not in txt:
                return None
            tail = txt.split(sep, 1)[1]
            buf = ""
            started = False
            for ch in tail:
                if ch.isdigit() or ch in "+-.eE":
                    buf += ch
                    started = True
                elif started:
                    break
            return float(buf) if buf else None
        except Exception:
            return None

    def read(self):
        ts = self.texts()
        if not ts:
            return None
        p = EisProgress(raw=ts)
        for txt in ts:
            low = txt.lower()
            if txt.startswith("Points:") or low.startswith("points:"):
                v = self._after(txt, ":")
                if v is not None:
                    p.points = int(v)
            elif "剩余时间" in txt:
                v = self._after(txt, "：")
                if v is None:
                    v = self._after(txt, ":")
                if v is not None:
                    p.remain_sec = v   # 注意：可能是 0.0，别用 `or` 链
            elif "总点数" in txt:
                v = self._after(txt, "总点数:")
                if v is not None:
                    p.total_points = int(v)
            elif "Freq" in txt or "freq" in txt:
                v = self._after(txt, ":")
                if v is not None:
                    p.freq_hz = v
            elif "|Z|" in txt:
                v = self._after(txt, ":")
                if v is not None:
                    p.z_abs = v
            elif "Z'" in txt:
                v = self._after(txt, ":")
                if v is not None:
                    p.z_re = v
            elif 'Z"' in txt:
                v = self._after(txt, ":")
                if v is not None:
                    p.z_im = v
            elif "θ" in txt:
                v = self._after(txt, ":")
                if v is not None:
                    p.theta = v
        return p


class EisFinishJudge:
    """判断阻抗扫描是否真的结束。

    用户原话：「阻抗测试完成后还会有数据变化，看右下角进度条判断完成与否」——
    也就是说数据还在动不代表没跑完，必须看进度。

    判据（全部满足才算结束）：
      1. 已经跑了 >= min_sec（默认 8 s）
      2. 「剩余时间」读到 0
      3. Points 连续 stable_n 次（默认 5 次 ≈ 2 s）没有增长
    """

    def __init__(self, min_sec=8.0, stable_n=5, final_freq=None, log=None):
        self.min_sec = min_sec
        self.stable_n = stable_n
        self.final_freq = final_freq      # 终止频率(Hz)；给了就按频率判到底
        self.log = log or (lambda *a: None)
        self.t0 = None
        self._last_points = None
        self._stable = 0
        self._seen_remain0 = False
        self._min_freq = None

    def update(self, prog, now):
        """prog=EisProgress 或 None；now=time.time()。返回 (done, reason)。"""
        if self.t0 is None:
            self.t0 = now
        if prog is None:
            return False, "读不到读数"
        if prog.remain_sec is not None and prog.remain_sec <= 0:
            self._seen_remain0 = True
        if prog.points is not None:
            if self._last_points is not None and prog.points <= self._last_points:
                self._stable += 1
            else:
                self._stable = 0
            self._last_points = prog.points
        elapsed = now - self.t0
        if prog.freq_hz is not None:
            if self._min_freq is None or prog.freq_hz < self._min_freq:
                self._min_freq = prog.freq_hz

        if elapsed < self.min_sec:
            return False, "刚开始 %.1fs" % elapsed

        # 用户要求：显示剩余时间为 0（相当于右下角进度条 100%）即算完成。
        # 先给止步条件留个最短时间保护，避免刚启动时剩余时间尚未算出。
        if self._seen_remain0 and self._stable >= self.stable_n:
            return True, ("剩余时间为 0 且点数 %r 稳定 %d 次"
                          % (prog.points, self._stable))

        # 备用判据：频率已到达终止频率（留 15% 余量）
        if self.final_freq is not None:
            limit = float(self.final_freq) * 1.15
            lowest = self._min_freq
            if lowest is None or lowest > limit:
                return False, ("频率未到终止值（最低 %r / 目标 %g）"
                               % (lowest, self.final_freq))
            if self._stable < self.stable_n:
                return False, ("已到终止频率，等点数稳定 %d/%d"
                               % (self._stable, self.stable_n))
            return True, ("频率已到 %r Hz（终止 %g）且点数 %r 稳定 %d 次"
                          % (lowest, self.final_freq, prog.points, self._stable))

        # 退化路径（没给终止频率）：剩余时间 0 + 点数稳定
        if not self._seen_remain0:
            return False, "剩余时间未到 0（%r）" % (prog.remain_sec,)
        if self._stable < self.stable_n:
            return False, "剩余时间已 0，等点数稳定 %d/%d" % (self._stable, self.stable_n)
        return True, "剩余时间 0 且点数 %r 稳定 %d 次" % (prog.points, self._stable)
