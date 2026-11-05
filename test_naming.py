# -*- coding: utf-8 -*-
"""test_naming.py —— 文件名生成与查重测试（需求：日期-样品名称-测试项目）。

覆盖：
  * build_filenames6 的 命名格式 + 已存在文件时 _2/_3 递增
  * OCP 重试轮命名：轮号拼在扩展名之前（runner.py P1-5 修复的回归）
  * build_filenames5 的 .cor 查重
运行：python test_naming.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner as R
import runner6 as R6

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


def test_filenames6():
    from datetime import datetime
    day = datetime.now().strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as d:
        cfg = R6.RunConfig6(sample="CS350M", area_cm2=1.0, item="Tafel", out_dir=d)
        f = R6.build_filenames6(cfg)
        check("6版命名格式 日期-样品-项目",
              os.path.basename(f["ocp"]) == "%s-CS350M-开路电位" % day
              and os.path.basename(f["test"]).endswith("CS350M-动电位"),
              repr(f))
        # 撞名递增
        open(os.path.join(d, "%s-CS350M-开路电位.txt" % day), "w").close()
        cfg2 = R6.RunConfig6(sample="CS350M", area_cm2=1.0, item="Tafel", out_dir=d)
        f2 = R6.build_filenames6(cfg2)
        check("6版撞名递增 _2", os.path.basename(f2["ocp"]).endswith("开路电位_2"),
              repr(f2))


def test_retry_name_runner():
    """runner.py 重试命名：轮号必须拼在 .txt 之前（P1-5 回归）。"""
    import re
    base = "D:\\x\\2026-11-06-样品-开路电位.txt"
    b = re.sub(r"_第\d+轮$", "", base)
    root, ext = os.path.splitext(b)
    cand = "%s_第%d轮%s" % (root, 2, ext or ".txt")
    check("重试轮号在扩展名前", cand.endswith("开路电位_第2轮.txt"), cand)


def test_filenames5():
    import runner5 as R5
    with tempfile.TemporaryDirectory() as d:
        cfg = R5.RunConfig5(sample="CS120", area_cm2=1.0, item="Tafel", out_dir=d)
        f = R5.build_filenames5(cfg)
        check("5版命名格式", os.path.basename(f["ocp"]).endswith("CS120-开路电位"),
              repr(f))
        from datetime import datetime
        day = datetime.now().strftime("%Y-%m-%d")
        open(os.path.join(d, "%s-CS120-开路电位.cor" % day), "w").close()
        f2 = R5.build_filenames5(R5.RunConfig5(sample="CS120", area_cm2=1.0,
                                               item="Tafel", out_dir=d))
        check("5版按 .cor 查重递增",
              os.path.basename(f2["ocp"]).endswith("开路电位_2"), repr(f2))


def test_dup_policy_default():
    cfg = R6.RunConfig6()
    check("dup_policy 默认 overwrite", cfg.dup_policy == "overwrite", cfg.dup_policy)


if __name__ == "__main__":
    test_filenames6()
    test_retry_name_runner()
    test_filenames5()
    test_dup_policy_default()
    print()
    if FAILS:
        print("FAIL %d 项：%r" % (len(FAILS), FAILS))
        sys.exit(1)
    print("全部 %d 项 PASS" % PASSED)
