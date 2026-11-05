# -*- coding: utf-8 -*-
"""make_alias2.py —— DefineDosDeviceW + DDD_RAW_TARGET_PATH 造 COM 别名。"""
import ctypes
import sys

DDD_RAW_TARGET_PATH = 0x1
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

BS = chr(92)
target = BS + "Device" + BS + "com0com10"          # CNCA0（pair1 的 A 端）
alias = sys.argv[1] if len(sys.argv) > 1 else "COM90"

# 先清掉旧映射（忽略失败）
k32.DefineDosDeviceW(0x2, alias, target)
k32.DefineDosDeviceW(0x2, alias, "C:" + BS + "Device" + BS + "com0com10")

ok = k32.DefineDosDeviceW(DDD_RAW_TARGET_PATH, alias, target)
print("DefineDosDevice(%s -> %s, RAW) = %s" % (alias, target, bool(ok)))
buf = ctypes.create_unicode_buffer(512)
n = k32.QueryDosDeviceW(alias, buf, 512)
print("Query ->", buf.value if n else "?")
sys.exit(0 if ok else 1)
