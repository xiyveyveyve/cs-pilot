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
        # 自增序号：看板以"内容是否变化"判活（跨机时钟差不敏感），
        # 心跳必须每帧可分辨——即使全部业务字段没变
        self._seq = getattr(self, "_seq", 0) + 1
        rec = {
            "machine": self.machine,
            "ts": time.time(),
            "seq": self._seq,
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
            # tmp 带 pid：同一台机器误开两个 gui 时两个写者不共用同一临时文件
            tmp = "%s.%d.tmp" % (self.path, os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
            os.replace(tmp, self.path)          # 原子替换：看板不会读到半截
            self._last = rec
            # 顺带清掉历史残留的旧 pid tmp（写者中途崩溃会留下垃圾）
            try:
                for n in os.listdir(self.board_dir):
                    if (n.startswith(self.machine + ".json.")
                            and n.endswith(".tmp") and n != os.path.basename(tmp)):
                        try:
                            os.remove(os.path.join(self.board_dir, n))
                        except OSError:
                            pass
            except OSError:
                pass
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
    """心跳年龄（秒）。时钟不准的机器最多显示成 0（不显示成几万秒失联）。

    ts 字段损坏（非数值）按"早已失联"处理——监控语义上宁可误报失联，
    也不能把坏数据当成在线。注意：**失联判定不看这个值**（跨机时钟差
    不可假设，见 LivenessBook），它只用于展示。"""
    try:
        return max(0.0, time.time() - float(rec.get("ts", 0)))
    except (TypeError, ValueError):
        return 1e9


class LivenessBook:
    """看板侧活性账本：以"本机观察到内容变化"的时刻判活。

    共享目录方案里 ts 是各机器自己的时钟，跨机时钟差没有 NTP 保证——
    用 ts 判失联会把表慢的机器永远标成失联。改判"内容是否变化"：
    StatusReporter 每次心跳自增 seq，内容必然变化；本机两次观察到变化
    的间隔超过 stale_sec 才算失联。与各机器时钟完全无关。
    """

    def __init__(self, stale_sec: float | None = None):
        # 缺省延迟到构造时取 STALE_SEC（模块底部才定义，不能当默认参数）
        self.stale_sec = STALE_SEC if stale_sec is None else stale_sec
        self._seen = {}                      # machine -> (sig, first_ts)

    @staticmethod
    def _sig(rec: dict) -> str:
        return json.dumps({k: v for k, v in rec.items() if k != "ts"},
                          sort_keys=True, ensure_ascii=False)

    def feed(self, rec: dict, now: float | None = None) -> bool:
        """喂一条记录，返回是否失联（内容停滞超 stale_sec）。"""
        now = time.time() if now is None else now
        m = str(rec.get("machine", "?"))
        sig = self._sig(rec)
        prev = self._seen.get(m)
        if prev is None or prev[0] != sig:
            self._seen[m] = (sig, now)       # 内容变了：重新计时
            return False
        return (now - prev[1]) > self.stale_sec


STALE_SEC = 15.0          # 超过此秒数没心跳 → 看板标"失联"
