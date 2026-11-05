# -*- coding: utf-8 -*-
"""监视 CS Studio 自己写出来的数据文件。

为什么走文件而不是串口
----------------------
寄生式的核心约束是"不改软件默认数据、不抢设备"。软件本来就把每个实验点
实时写进自己选定的 .txt（实测 10 Hz OCP 约每 3 s flush 一次，写入后行完整、
不会出现半行）。所以脚本只需要 tail 这个文件，就能拿到与软件完全一致的数据，
既不碰串口也不影响采集。

文件格式（实测）
----------------
第 1 行  CSStudioFile,<ExpType>,<base64(gzip(CORRW ASCII 头))>
第 2 行  E(V)\ti(A/cm²)\tT(s)
第 3 行起 %0.5E\t%0.5E\t%0.5f    CRLF 换行

注意软件 flush 是整行追加的，但为了稳妥，读到不完整的尾行一律丢弃、等下次。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Sample:
    t: float
    e: float
    i: Optional[float] = None


class CorFileTail:
    """增量读取 .txt 数据文件。"""

    def __init__(self, path: str):
        self.path = path
        self._pos = 0
        self._buf = b""
        self.header: Optional[str] = None
        self.exp_type: Optional[str] = None
        self.samples: List[Sample] = []
        self._mtime = 0.0

    # ---------- 基础 ----------
    def exists(self) -> bool:
        return os.path.exists(self.path)

    def reset(self) -> None:
        self._pos = 0
        self._buf = b""
        self.header = None
        self.exp_type = None
        self.samples.clear()
        self._mtime = 0.0

    def size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def changed(self) -> bool:
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m != self._mtime:
            self._mtime = m
            return True
        return False

    # ---------- 读取 ----------
    def poll(self) -> List[Sample]:
        """读新增的完整行，返回新样本。

        文件被覆盖重建（同名实验重跑）时 size 会变小于已读位置，
        这时必须整体重置，否则 seek 越界会永远读不到数据，
        或把上一轮的残留内容当成新数据（会污染判稳）。
        """
        new: List[Sample] = []
        if not self.exists():
            return new
        cur = self.size()
        if cur < self._pos:
            self.reset()
        try:
            with open(self.path, "rb") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
        except OSError:
            return new
        if not chunk:
            return new

        data = self._buf + chunk
        lines = data.split(b"\r\n")
        # 最后一段可能不完整：留到下次
        self._buf = lines.pop() if lines else b""
        if not lines and not self._buf:
            return new

        for raw in lines:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if self.header is None:
                self.header = line
                parts = line.split(",")
                if len(parts) >= 2:
                    self.exp_type = parts[1]
                continue
            if line.startswith("E(") or line.startswith("E\t"):
                continue
            s = _parse_line(line)
            if s is not None:
                new.append(s)
                self.samples.append(s)
        return new

    # ---------- 便捷 ----------
    def series_ev(self, last_n: Optional[int] = None) -> List[Tuple[float, float]]:
        ss = self.samples if last_n is None else self.samples[-last_n:]
        return [(s.t, s.e) for s in ss]

    def series_ti(self, last_n: Optional[int] = None) -> List[Tuple[float, float]]:
        ss = self.samples if last_n is None else self.samples[-last_n:]
        out = []
        for s in ss:
            if s.i is not None:
                out.append((s.t, s.i))
        return out

    def last(self) -> Optional[Sample]:
        return self.samples[-1] if self.samples else None

    def finished_quiet(self, quiet_sec: float = 10.0) -> bool:
        """文件一段时间没再变 —— 软件已收尾（flush 间隔约 3 s，取 10 s 留足余量）。"""
        if not self.exists():
            return False
        try:
            age = time.time() - os.path.getmtime(self.path)
        except OSError:
            return False
        return age >= quiet_sec and len(self.samples) > 0


def _parse_line(line: str) -> Optional[Sample]:
    parts = line.split("\t")
    if len(parts) < 2:
        parts = line.split()
    if len(parts) < 2:
        return None
    try:
        e = float(parts[0])
        i = float(parts[1])
        t = float(parts[2]) if len(parts) >= 3 else 0.0
        return Sample(t=t, e=e, i=i)
    except ValueError:
        return None
