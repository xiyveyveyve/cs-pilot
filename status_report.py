# -*- coding: utf-8 -*-
"""status_report.py —— 多机集中监控的状态上报（多台单通道机方案，2026-11-07）。

每台机器跑现有 gui.py（各自驱动自己的 CS Studio，单通道），把运行状态周期性
写成一个 status.json。多台机器把 status_report 指向**同一个共享目录**
（Windows 文件共享，如 \\\\主控机\\cspilot看板\\），主控机开 monitor.py 聚合
——全程不需要任何网络代码/服务，文件共享就是传输层。

写入用"临时文件 + os.replace 原子替换"：看板读到半截 JSON 的概率为零。
"""
from __future__ import annotations

import json
import os
import re
import socket
import time

_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def safe_machine(name: str) -> str:
    """机器名清洗文件名非法字符。"""
    return _SAFE_RE.sub("", str(name or "").strip()) or "未命名机器"


class StatusReporter:
    """本机状态 → <board_dir>/<机器名>.json（原子写）。"""

    def __init__(self, board_dir: str, machine: str | None = None,
                 sample: str = "", area: str = "", item: str = "", ver: str = ""):
        self.machine = safe_machine(machine or socket.gethostname())
        self.board_dir = board_dir
        self.sample = sample
        self.area = area
        self.item = item
        self.ver = ver
        self.path = os.path.join(board_dir, self.machine + ".json")
        self._last: dict = {}

    # ------------------------------------------------------------------
    def update(self, state: str, detail: str = "", step: str = "",
               metrics: dict | None = None, files: list | None = None,
               log_tail: list | None = None) -> None:
        """状态变化/周期心跳时调用。任何失败都不许影响主流程。"""
        rec = {
            "machine": self.machine,
            "ts": time.time(),
            "state": state,
            "detail": detail,
            "step": step,
            "sample": self.sample,
            "area": self.area,
            "item": self.item,
            "ver": self.ver,
            "metrics": metrics or {},
            "files": files or [],
            "log_tail": (log_tail or [])[-8:],
        }
        try:
            os.makedirs(self.board_dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
            os.replace(tmp, self.path)          # 原子替换：看板不会读到半截
            self._last = rec
        except Exception:
            # 上报失败静默：多机看板是锦上添花，不能拖垮测试主流程
            pass

    @property
    def last(self) -> dict:
        return self._last


def load_board(board_dir: str) -> tuple[list[dict], list[str]]:
    """看板侧：读目录下全部 *.json。返回 (记录列表, 坏文件列表)。"""
    recs, bad = [], []
    try:
        names = [n for n in os.listdir(board_dir) if n.lower().endswith(".json")]
    except OSError:
        return [], []
    for n in sorted(names):
        p = os.path.join(board_dir, n)
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
            if isinstance(rec, dict) and "machine" in rec and "ts" in rec:
                recs.append(rec)
            else:
                bad.append(n)
        except Exception:
            bad.append(n)          # 半截/非本看板的 json——跳过不炸
    recs.sort(key=lambda r: r.get("machine", ""))
    return recs, bad


def age_sec(rec: dict) -> float:
    """心跳年龄（秒）。时钟不准的机器最多显示成 0（不显示成几万秒失联）。"""
    return max(0.0, time.time() - float(rec.get("ts", 0)))


STALE_SEC = 15.0          # 超过此秒数没心跳 → 看板标"失联"
