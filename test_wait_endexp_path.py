# -*- coding: utf-8 -*-
"""回归：wait_endexp 的数据文件判据必须真的能用（11-14 真机事故）。

根因：_RUN_PATH_RE 旧写法 [^\\s] 不容空格，11-11 命名口径改空格分隔后
从运行窗标题永远抠不出路径 → 文件心跳判据失效 → CS5 停止后界面时间继续走
→ wait_endexp 永远超时误判"未停" → 6 轮空转 + 关窗兜底，甚至误报 S_ERROR
（11-14 进口老DC-6V 阻抗：.z60 已冻结仍报"数据文件一直在增长"）。

锁定三件事：
  ① 正则容空格（用 11-14 真实标题），旧无空格路径保持兼容
  ② _data_file_for 按收尾标签给出真实数据文件路径
  ③ _finish_run 把显式路径传给 wait_endexp（不再依赖标题）
运行：python test_wait_endexp_path.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import runner5
from runner5 import Runner5, _RUN_PATH_RE, wait_endexp

FAIL = []
TOTAL = [0]


def check(cond, label):
    TOTAL[0] += 1
    if cond:
        print("PASS %s" % label)
    else:
        FAIL.append(label)
        print("FAIL %s" % label)


# 11-14 真机运行窗标题（原库 logs/resume_ocp_1114_1507.log 等）
T_TAFEL = ("动电位扫描 <20μA>  C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
           "2026-11-14 国产 钝化 26V 动电位.cor ")
P_TAFEL = ("C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
           "2026-11-14 国产 钝化 26V 动电位.cor")
T_OCP = ("开路电位 <2mA>  C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
         "2026-11-14 国产 钝化 26V 开路电位.cor ")
P_OCP = ("C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
         "2026-11-14 国产 钝化 26V 开路电位.cor")
T_CS6 = ("[通道1]-开路电位测量(OCP) <C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
         "2026-11-12 4号 开路电位.txt>")
P_CS6 = ("C:\\Users\\xiyve\\Desktop\\CS-Pilot数据\\"
         "2026-11-12 4号 开路电位.txt")


def match(t):
    m = _RUN_PATH_RE.search(t)
    return m.group(1) if m else None


check(match(T_TAFEL) == P_TAFEL, "1 空格命名的动电位标题能抠出完整路径")
check(match(T_OCP) == P_OCP, "2 空格命名的开路电位标题能抠出完整路径")
check(match(T_CS6) == P_CS6, "3 CS6 带尖括号装饰的空格路径能抠出")
check(match("开路电位 <2mA>  D:\\x\\1.cor ") == "D:\\x\\1.cor",
      "4 旧无空格路径保持兼容")
check(match("开路电位") is None, "5 无路径标题返回 None")


class FakeRunWin:
    def __init__(self, title="开路电位", exists=True):
        self._t = title
        self._exists = exists

    def exists(self):
        return self._exists

    def descendants(self, control_type=None):
        return []

    def window_text(self):
        return self._t


class FakeStudio:
    def __init__(self):
        self.calls = []

    def stop_run(self, runwin=None):
        self.calls.append("stop")
        return True

    def close_run(self, runwin=None):
        self.calls.append("close")
        return True

    def cleanup_run_windows(self):
        self.calls.append("cleanup")
        return 0

    def _pid(self):
        return 4242


def make_runner(studio, runwin, files=None):
    r = Runner5.__new__(Runner5)
    r.studio = studio
    r.runwin = runwin
    r.files = files or {}
    r.error = ""
    r.log = lambda *a: None
    r.set_state = lambda s, e="": None
    return r


with tempfile.TemporaryDirectory() as td:
    base_ocp = os.path.join(td, "2026-11-14 样品 开路电位")
    base_eis = os.path.join(td, "2026-11-14 样品 交流阻抗")
    open(base_ocp + ".cor", "wb").write(b"x" * 100)
    open(base_eis + ".z60", "wb").write(b"x" * 100)

    r = make_runner(FakeStudio(), FakeRunWin(),
                    {"ocp": base_ocp, "eis": base_eis, "test": base_ocp})
    check(r._data_file_for("开路电位") == base_ocp + ".cor",
          "6 _data_file_for 开路电位 → .cor")
    check(r._data_file_for("阻抗扫描") == base_eis + ".z60",
          "7 _data_file_for 阻抗扫描 → .z60")
    check(r._data_file_for("动电位") == base_ocp + ".cor",
          "8 _data_file_for 动电位 → .cor")
    check(r._data_file_for("用户中止") is None,
          "9 未知标签返回 None（回退标题抠路径）")
    r2 = make_runner(FakeStudio(), FakeRunWin(), {"ocp": base_ocp + "_不存在"})
    check(r2._data_file_for("开路电位") is None,
          "10 文件不存在返回 None（不误传幽灵路径）")

    # 显式路径优先：标题抠不出路径时，冻结的数据文件仍应快速判"已收尾"
    t0 = time.time()
    got = wait_endexp(lambda *a: None, method="动电位",
                      runwin=FakeRunWin(title="动电位扫描"),
                      path=base_ocp + ".cor", timeout=8.0, quiet=1.0)
    el = time.time() - t0
    check(got is True and el < 5.0,
          "11 标题无路径+显式冻结文件 → 快速判已收尾（%.2fs）" % el)

    # _finish_run 必须把显式路径传给 wait_endexp（正常轮与强制轮都传）
    import driver5 as _D5
    seen = []
    _orig_wait = runner5.wait_endexp
    _orig_modal = _D5.clear_modals

    def _capture(log, method="", runwin=None, path=None, timeout=0,
                 fallback=0, **kw):
        seen.append(path)
        return True

    try:
        runner5.wait_endexp = _capture
        _D5.clear_modals = lambda limit=4, prefer=None, pid=None: 0
        st = FakeStudio()
        rr = make_runner(st, FakeRunWin(title="开路电位"), {"ocp": base_ocp})
        ok = rr._finish_run("开路电位", idle_wait=0)
        check(ok is True and seen and seen[0] == base_ocp + ".cor",
              "12 _finish_run 正常轮显式传数据文件路径")

        seen.clear()
        _seq = [False, True]

        def _capture2(log, method="", runwin=None, path=None, timeout=0,
                      fallback=0, **kw):
            seen.append(path)
            return _seq.pop(0) if _seq else True

        runner5.wait_endexp = _capture2
        st = FakeStudio()
        rr = make_runner(st, FakeRunWin(title="开路电位"), {"ocp": base_ocp})
        ok = rr._finish_run("开路电位", idle_wait=0)
        check(ok is True and len(seen) >= 2
              and all(p == base_ocp + ".cor" for p in seen),
              "13 _finish_run 强制终止轮也显式传路径")
    finally:
        runner5.wait_endexp = _orig_wait
        _D5.clear_modals = _orig_modal

print()
if FAIL:
    for f in FAIL:
        print("FAIL " + f)
    sys.exit(1)
print("全部 %d 项 PASS" % TOTAL[0])