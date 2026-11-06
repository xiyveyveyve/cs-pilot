# -*- coding: utf-8 -*-
r"""make_alias.py —— DefineDosDeviceW + DDD_RAW_TARGET_PATH 造 COM 别名（参数化版）。

用法:
    python testbed/make_alias.py <别名> <目标设备名>
    python testbed/make_alias.py COM91 \\Device\\com0com11     # CNCA1（Agent C 三实验测试床）
    python testbed/make_alias.py COM90 \\Device\\com0com10     # CNCA0（等价旧 make_alias2.py 默认）

说明:
* 目标必须是 \Device\com0comNN 这类内核设备名（CNCA0=\com0com10、CNCB0=\com0com20、
  CNCA1=\com0com11、CNCB1=\com0com21，QueryDosDeviceW 实测 2026-11-07）。
* 别名用 DDD_RAW_TARGET_PATH 造，用户态别名不进 SERIALCOMM 枚举，但 .NET/pyserial 都能开。
* 先清旧映射（DDD_REMOVE_DEFINITION 两次，含 C: 前缀形态）再建新的，幂等可重复执行。
"""
import ctypes
import sys

DDD_RAW_TARGET_PATH = 0x1
DDD_REMOVE_DEFINITION = 0x2
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

BS = chr(92)

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)

alias = sys.argv[1]
target = sys.argv[2]
if not target.startswith(BS + "Device" + BS):
    print("目标必须是 \\Device\\ 形式的内核设备名，收到: %r" % target)
    sys.exit(2)

# 先清掉旧映射（两种形态都清，忽略失败）
k32.DefineDosDeviceW(DDD_REMOVE_DEFINITION, alias, target)
k32.DefineDosDeviceW(DDD_REMOVE_DEFINITION, alias, "C:" + target)

ok = k32.DefineDosDeviceW(DDD_RAW_TARGET_PATH, alias, target)
print("DefineDosDevice(%s -> %s, RAW) = %s" % (alias, target, bool(ok)))
buf = ctypes.create_unicode_buffer(512)
n = k32.QueryDosDeviceW(alias, buf, 512)
print("Query ->", buf.value if n else "?")
sys.exit(0 if ok else 1)
