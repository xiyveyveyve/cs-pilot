"""sync_barrier.py —— 多实例「停止批次屏障」公共件。

用户规则（2026-11-09）：多台同时达到停止门槛时，**先停最早到门槛的那台**；
停完之后不要立刻进入下一阶段，而是让位给另一台去停，等它也停完了，
再切回早停的那台继续剩下的任务。这样停止动作在全局 UI 锁上成批串行，
跨窗口切换次数最少，也不会出现「一台刚停完就抢着开下一个参数窗，
把正要停止的另一台挤到后面」的情况。

实现（无中心协调器，靠心跳文件分布式判断）：
  · runner 停止完成后调用 enter_after_stop(target)：
      若其它实例正处于「停止中」→ 进 SYNC_STAGE（已停止待同步）等；
      否则直接进 target。
  · 等 SYNC_STAGE 时每 tick 读 _auto/hb/*.json：
      只要还有别家在停止中就让位（不持 UI 锁、不推进）；
      没有了就放行进 target。
  · 超时 180s 兜底（防止某台卡在停止阶段把别人永久堵住）。
  · 出错/中止的实例 stage 不含「停止/结束」，天然不进同步集合。
"""
import glob
import json
import os
import time

HB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_auto", "hb")

SYNC_STAGE = "已停止待同步"   # 进 hb 的 stage 文本
SYNC_TIMEOUT = 180.0          # 兜底秒数
STALE_SEC = 120.0             # 心跳过期（runner 已死）不算


def read_stages(exclude=""):
    """{machine: stage}：读所有实例心跳，跳过自己与过期心跳。"""
    out = {}
    for p in glob.glob(os.path.join(HB_DIR, "*.json")):
        name = os.path.basename(p)[:-5]
        if name == exclude:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                hb = json.load(f)
        except Exception:
            continue
        try:
            age = time.time() - float(hb.get("ts") or 0)
        except Exception:
            age = STALE_SEC + 1
        if age > STALE_SEC:
            continue
        out[name] = hb.get("stage", "") or ""
    return out


def is_stopping(stage):
    """stage 是否处于「停止中」（5/6 两版文案不同：停止/结束）。"""
    if not stage:
        return False
    if SYNC_STAGE in stage:
        return False
    return ("停止" in stage) or ("结束" in stage)


def stopping_peers(me):
    return {n: s for n, s in read_stages(me).items() if is_stopping(s)}
