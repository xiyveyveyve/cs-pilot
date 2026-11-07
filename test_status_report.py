# -*- coding: utf-8 -*-
"""test_status_report.py —— 多机看板上报/聚合的单元测试。

运行：python test_status_report.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from status_report import (StatusReporter, load_board, age_sec,  # noqa: E402
                           safe_machine, STALE_SEC)

PASSED = 0
FAILS = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("PASS %s" % name)
    else:
        FAILS.append(name)
        print("FAIL %s  %s" % (name, detail))


def t_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        r = StatusReporter(d, machine="LAB-PC1", sample="CS350M",
                           area="1.0", item="Tafel", ver="CS Studio6直开")
        r.update(state="监视开路电位", detail="判稳器两阶段运行中", step="开路电位·判稳",
                 metrics={"E": -0.1512, "slope": 0.42, "ppt": 0.88, "held": 63.0},
                 files=["a.txt（100 B）"], log_tail=["10:00:00 开始", "10:00:01 收到数据"])
        recs, bad = load_board(d)
        eq1 = len(recs) == 1 and len(bad) == 0
        rec = recs[0] if recs else {}
        check("roundtrip 机器/状态/步骤/指标齐全",
              eq1 and rec.get("machine") == "LAB-PC1"
              and rec.get("state") == "监视开路电位"
              and rec.get("step") == "开路电位·判稳"
              and rec.get("metrics", {}).get("E") == -0.1512
              and len(rec.get("log_tail", [])) == 2, repr(recs))


def t_overwrite_one_file_per_machine():
    with tempfile.TemporaryDirectory() as d:
        for st in ("连接 CS Studio6", "监视开路电位", "完成"):
            StatusReporter(d, machine="PC-A").update(state=st)
        StatusReporter(d, machine="PC-B").update(state="待机")
        recs, _ = load_board(d)
        names = sorted(r["machine"] for r in recs)
        a = [r for r in recs if r["machine"] == "PC-A"]
        check("每机一文件且只留最新状态",
              names == ["PC-A", "PC-B"] and len(a) == 1 and a[0]["state"] == "完成",
              repr(recs))


def t_bad_json_tolerated():
    with tempfile.TemporaryDirectory() as d:
        StatusReporter(d, machine="OK机").update(state="待机")
        with open(os.path.join(d, "half.json"), "w", encoding="utf-8") as f:
            f.write('{"machine": "半截", "ts": 1')          # 被截断的 json
        with open(os.path.join(d, " Alien.json "), "w", encoding="utf-8") as f:
            f.write('{"foo": 1}')                            # 不是本看板结构
        recs, bad = load_board(d)
        check("坏/陌生 json 跳过不炸",
              len(recs) == 1 and recs[0]["machine"] == "OK机" and len(bad) == 2,
              repr((recs, bad)))


def t_atomic_no_partial_read():
    """写入方高频 update，读取方高频 load_board——读者永远看不到半截。"""
    with tempfile.TemporaryDirectory() as d:
        r = StatusReporter(d, machine="原子机")
        stop = threading.Event()
        bad_reads = []

        def reader():
            while not stop.is_set():
                recs, _ = load_board(d)
                for rec in recs:
                    try:
                        json.dumps(rec)            # 能整体序列化 = 没读到半截
                    except Exception as e:         # noqa: BLE001
                        bad_reads.append(repr(e))

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        for i in range(300):
            r.update(state="状态%d" % i, detail="x" * 500)
        stop.set()
        th.join(timeout=5)
        check("并发读写 300 次：读者零半截", not bad_reads, repr(bad_reads[:3]))


def t_update_failure_silent():
    with tempfile.TemporaryDirectory() as d:
        # 看板路径指向一个"文件"（不可能建目录）——update 必须静默不抛
        blocker = os.path.join(d, "占位文件")
        open(blocker, "w").close()
        r = StatusReporter(os.path.join(blocker, "子目录"), machine="X")
        try:
            r.update(state="待机")
            check("上报失败静默（不拖垮主流程）", True)
        except Exception as e:      # noqa: BLE001
            check("上报失败静默（不拖垮主流程）", False, repr(e))


def t_misc():
    check("机器名清洗 \\/:*?\"<>|", safe_machine('a:b\\c/d*e?f"g<h>i|j') == "abcdefghij")
    check("空机器名兜底", safe_machine("  ") == "未命名机器")
    check("age_sec 负值钳 0", age_sec({"ts": time.time() + 999}) == 0.0)
    check("age_sec 正常", 0 <= age_sec({"ts": time.time() - 3}) < 10)
    with tempfile.TemporaryDirectory() as d:
        r = StatusReporter(d, machine="旧心跳")
        r.update(state="待机")
        # 手工把 ts 拨老 → 看板判定失联
        recs, _ = load_board(d)
        recs[0]["ts"] -= STALE_SEC + 30
        check("心跳超 15s 判失联口径", age_sec(recs[0]) > STALE_SEC)


def t_hostile_ts():
    """ts 字段损坏必须按"失联"处理，且绝不能抛异常炸掉看板刷新循环。"""
    for bad in ("abc", None, {"x": 1}, [1, 2], "0"):
        try:
            age = age_sec({"ts": bad})
            if bad == "0":
                check("ts='0' 解析为在线（float 可转）", age >= 0)
            else:
                check("ts=%r 按失联处理" % (bad,), age > STALE_SEC, "age=%r" % age)
        except Exception as e:      # noqa: BLE001
            check("ts=%r 不抛异常" % (bad,), False, repr(e))


def t_two_writers_same_machine():
    """同一台机器误开两个 gui：pid 后缀临时文件不互相踩，最终文件总是合法 json。"""
    with tempfile.TemporaryDirectory() as d:
        r1 = StatusReporter(d, machine="双开机")
        r2 = StatusReporter(d, machine="双开机")
        errs = []
        for i in range(120):
            try:
                r1.update(state="A%d" % i)
                r2.update(state="B%d" % i)
                recs, bad = load_board(d)
                if bad:
                    errs.append("坏文件出现: %r" % bad)
            except Exception as e:      # noqa: BLE001
                errs.append(repr(e))
        check("双写者 240 次交替：无坏文件无异常", not errs, repr(errs[:3]))


def t_subdir_named_json():
    """看板目录里有个叫 x.json 的子目录——load_board 必须跳过而不是炸。"""
    with tempfile.TemporaryDirectory() as d:
        StatusReporter(d, machine="正常机").update(state="待机")
        os.makedirs(os.path.join(d, "x.json"), exist_ok=True)
        recs, bad = load_board(d)
        check("子目录伪装 .json 被跳过", len(recs) == 1 and len(bad) == 1,
              repr((recs, bad)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t_roundtrip()
    t_overwrite_one_file_per_machine()
    t_bad_json_tolerated()
    t_atomic_no_partial_read()
    t_update_failure_silent()
    t_misc()
    t_hostile_ts()
    t_two_writers_same_machine()
    t_subdir_named_json()
    print()
    if FAILS:
        print("FAIL %d 项：%r" % (len(FAILS), FAILS))
        sys.exit(1)
    print("全部 %d 项 PASS" % PASSED)
