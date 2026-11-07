# -*- coding: utf-8 -*-
"""csdotnet.py —— 用纯 .NET 代码构造 CS Studio6 的实验参数（不点 GUI、不需要设备）。

原理
----
`CSStudio6.CorrData.dll`（版本 6.7.611.2）里的 `MethodParams.*` 参数类是
public 且**没有混淆**，都有无参构造。它们实现了 `IBaseParams`：

    string GetSaveString();          # 序列化成 "Key=Value&-&Key=Value..."
    void   InitByString(string s);   # 从该串反解

这个串就是软件自己存盘/读盘用的格式（同目录下的 .mtd 一类文件内容），
所以「代码里把参数设成想要的值」和「在参数窗里手点」产出的是**同一份数据**。

为什么有用
----------
1. 不需要 GUI、不需要设备就能得到"正确的参数"，可以当 golden 参照。
2. 没有设备时 GUI 打不开任何参数窗（6 版会弹通讯配置向导），
   这条路是唯一能在本机验证参数逻辑的方式。
3. 以后若要走"代码直接下发命令"，`ExpComSendClass.SendMethodBytes(IBaseParams)`
   要的正是这些对象，可以直接复用。

实现方式
--------
Python 侧不依赖 pythonnet（本机没装，且 pythonnet 3.x 只支持 .NET Core，
而这是 .NET Framework 4.5.2 的程序集）。改用 Windows PowerShell 5.1 作为
.NET 桥：Python 起 `powershell.exe -File csdotnet.ps1`，拿回 JSON。
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "csdotnet.ps1")
POWERSHELL = "powershell.exe"

KINDS = ("ocp", "step", "tafel")


class GenError(RuntimeError):
    pass


def _run(kind, area, density, temp, dangliang, timeout=120):
    if kind not in KINDS:
        raise GenError("未知的实验类型 %r（可选 %s）" % (kind, ", ".join(KINDS)))
    fd, out = tempfile.mkstemp(suffix=".json", prefix="csgen_")
    os.close(fd)
    try:
        cmd = [
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", PS1,
            "-Kind", kind,
            "-Area", repr(float(area)),
            "-Density", repr(float(density)),
            "-TempVal", repr(float(temp)),
            "-Dangliang", repr(float(dangliang)),
            "-Out", out,
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired as e:
            # 统一异常口径：调用方只认 GenError（2026-11-07 审查 P3）
            raise GenError("PowerShell 超时（%gs）：%s" % (timeout, e)) from e
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            # 不指定 encoding 让 text 模式用系统区域码页（中文系统 GBK）——
            # PowerShell 5.1 控制台输出是 OEM 码页，按 utf-8 解会乱码
            raise GenError("PowerShell 没产出结果：rc=%s stderr=%s"
                           % (p.returncode, (p.stderr or "")[-800:]))
        with open(out, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def gen(kind, area=1.0, density=7.93, temp=25.0, dangliang=28.0):
    """构造一份实验参数，返回 dict。

    返回键：
      kind        "ocp" / "step" / "tafel"
      type        完整 .NET 类型名
      savestring  软件自己的序列化串（可直接喂给 InitByString 还原）
      length      串长度
      roundtrip   {length, identical, fields{...}}  —— 用 InitByString 反解后的校验
      warnings    非致命问题

    典型用法：
        from csdotnet import gen
        p = gen("step", area=1.35)
        print(p["savestring"])
        assert p["roundtrip"]["fields"]["Cycles"] == "20"
    """
    return _run(kind, area, density, temp, dangliang)


def check(p, expect):
    """拿 gen() 的返回去核对若干字段，返回 (ok, 差异列表)。

    expect 例：{"Final_E": "0.5", "Cycles": "20", "Cell.Area": "1.35"}
    字段名与 roundtrip.fields 一致（Cell.* 是电解池参数）。
    """
    fields = (p.get("roundtrip") or {}).get("fields") or {}
    diffs = []
    for k, want in expect.items():
        got = fields.get(k)
        if str(got) != str(want):
            diffs.append("%s: 期望 %r 实际 %r" % (k, want, got))
    return (not diffs), diffs


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kinds = sys.argv[1:] or list(KINDS)
    for k in kinds:
        r = gen(k, area=1.35)
        print("=" * 70)
        print("%-6s %s" % (k, r["type"]))
        print("  串长 %d，往返字段 %s" % (r["length"], r["roundtrip"]["fields"]))
        if r["warnings"]:
            print("  警告 %s" % (r["warnings"],))
        print("  " + r["savestring"][:300].replace("&-&", "\n  "))
        print("  ...")
