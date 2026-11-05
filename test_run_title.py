# -*- coding: utf-8 -*-
"""test_run_title.py —— is_run_title() 判据测试（样例全部来自实测窗口标题）。

运行：python test_run_title.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from driver_direct import is_run_title

CASES = [
    # (标题, 期望)
    ("[通道1]-开路电位测量(OCP) <D:\\probe\\a.txt> [2mA]", True),   # 6版真机运行窗
    ("[通道1]-开路电位测量(OCP) <D:\\probe\\a.txt>", True),          # 6版演示运行窗（无量程）
    ("[通道1]-动电位扫描(Tafel,LPR) <D:\\probe\\b.txt> [200uA]", True),
    ("[通道12]-交流阻抗  频率扫描-电位控制模式", True),               # 通道号两位数
    ("波形图", True),
    ("图形显示", True),
    ("通道1【型号：DEMOSN in Demo】", False),   # 通道窗（无 "-" 前缀），绝不能算运行窗
    ("CS Studio6  演示模式", False),             # 主窗
    ("CS Studio6   在串口和局域网内均未找到设备", False),
    ("添加", False),
    ("用户设置", False),
    ("开路电位测量(OCP)", False),                # 参数窗
    ("", False),
    (None, False),
]

fails = []
for title, want in CASES:
    got = is_run_title(title)
    tag = "PASS" if got == want else "FAIL"
    if got != want:
        fails.append(title)
    print("%s is_run_title(%r) = %s (期望 %s)" % (tag, title, got, want))

print()
if fails:
    print("FAIL %d 项：%r" % (len(fails), fails))
    sys.exit(1)
print("全部 %d 项 PASS" % len(CASES))
