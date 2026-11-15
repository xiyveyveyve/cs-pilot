# -*- coding: utf-8 -*-
"""5 版收尾流程测试：确保「停止 → 等真结束 → 关窗 → 冷却 → 清残留」真的按序执行。

不连软件、不碰设备，用假 studio / 假运行窗验证状态机的调用顺序与异常安全。
背景：以前 runner5._do_stop_ocp 调了未定义的 wait_endexp，一运行就 NameError，
收尾整段被跳过，实验留在后台把下一个实验顶掉。
"""

import os
import sys
import time

from runner5 import Runner5, wait_endexp

FAIL = []
TOTAL = 11


class FakeRunWin:
    """假运行窗：descendants 返回一组文本控件，模拟界面采样时间。"""

    def __init__(self, t_values=None, exists=True):
        self.t_values = list(t_values or [])
        self._i = 0
        self._exists = exists

    def exists(self):
        return self._exists

    def descendants(self, control_type=None):
        return []

    def window_text(self):
        return "开路电位 <2mA>  D:\\x\\1.txt"


class FakeStudio:
    def __init__(self, raise_on_stop=False):
        self.calls = []
        self.raise_on_stop = raise_on_stop

    def stop_run(self, runwin=None):
        self.calls.append("stop")
        if self.raise_on_stop:
            raise RuntimeError("模拟点停止失败")
        return True

    def close_run(self, runwin=None):
        self.calls.append("close")
        return True

    def cleanup_run_windows(self):
        self.calls.append("cleanup")
        return 0

    def _pid(self):
        return 4242


def make_runner(studio, runwin=None):
    r = Runner5.__new__(Runner5)      # 绕过 __init__，只要 _finish_run 用到的字段
    r.studio = studio
    r.runwin = runwin
    r.log = lambda *a: None
    return r


# 1) 正常路径：顺序必须是 stop → close
st = FakeStudio()
r = make_runner(st, FakeRunWin())
r._finish_run("开路电位", idle_wait=0)
if st.calls == ["stop", "close", "cleanup"]:
    print("PASS 1 收尾顺序 stop→close→cleanup")
else:
    FAIL.append("1 顺序不对：%r" % (st.calls,))

# 2) 点停止抛异常：不能炸，仍要关窗与清理
st = FakeStudio(raise_on_stop=True)
r = make_runner(st, FakeRunWin())
try:
    r._finish_run("阻抗扫描", idle_wait=0)
    if st.calls == ["stop", "close", "cleanup"]:
        print("PASS 2 点停止抛异常不中断收尾")
    else:
        FAIL.append("2 异常后调用不全：%r" % (st.calls,))
except Exception as e:
    FAIL.append("2 收尾把异常抛出去了：%s" % e)

# 3) 没有运行窗（实验已自行结束）：只做清理，不能炸
st = FakeStudio()
r = make_runner(st, None)
try:
    r._finish_run("动电位", idle_wait=0)
    if st.calls == ["cleanup"]:
        print("PASS 3 无运行窗时只清理残留")
    else:
        FAIL.append("3 无运行窗时调用异常：%r" % (st.calls,))
except Exception as e:
    FAIL.append("3 无运行窗时抛异常：%s" % e)

# 4) runwin 必须被清空，避免后续状态拿旧窗口做判断
st = FakeStudio()
r = make_runner(st, FakeRunWin())
r._finish_run("阶梯波", idle_wait=0)
if r.runwin is None:
    print("PASS 4 收尾后 runwin 已清空")
else:
    FAIL.append("4 runwin 没清空")

# 5) wait_endexp 在窗口读不到数据时，按 fallback 等待后返回 False（不卡死）
t0 = time.time()
got = wait_endexp(lambda *a: None, method="测试", runwin=FakeRunWin(),
                  timeout=2.0, fallback=0.3)
el = time.time() - t0
if got is False and el < 2.5:
    print("PASS 5 wait_endexp 读不到数据时按 fallback 返回（%.2fs）" % el)
else:
    FAIL.append("5 wait_endexp 行为异常：got=%r 用时 %.2fs" % (got, el))

# 6) wait_endexp 无运行窗时不应卡满 timeout
t0 = time.time()
wait_endexp(lambda *a: None, method="测试", runwin=None, timeout=30.0, fallback=0.2)
el = time.time() - t0
if el < 1.0:
    print("PASS 6 wait_endexp 无运行窗时用固定等待（%.2fs）" % el)
else:
    FAIL.append("6 wait_endexp 无运行窗时等太久：%.2fs" % el)

# 7) 运行窗真关闭时：应尽快返回 True（不用等满 timeout）
t0 = time.time()
got = wait_endexp(lambda *a: None, method="测试", runwin=FakeRunWin(exists=False),
                  timeout=10.0, fallback=13.0)
el = time.time() - t0
if got is True and el < 3.0:
    print("PASS 7 运行窗关闭时快速返回 True（%.2fs）" % el)
else:
    FAIL.append("7 关窗检测异常：got=%r 用时 %.2fs" % (got, el))

# 8) 数据文件不再增长 → 应按 quiet 秒返回 True（5 版停止后界面时间还在走，
#    文件才是权威证据）
import tempfile as _tf

fh = _tf.NamedTemporaryFile(delete=False, suffix=".cor")
fh.write(b"x" * 1000)
fh.close()
t0 = time.time()
got = wait_endexp(lambda *a: None, method="测试", runwin=FakeRunWin(),
                  path=fh.name, timeout=20.0, quiet=1.0)
el = time.time() - t0
if got is True and 4.0 > el > 0.8:
    print("PASS 8 数据文件停写后判定收尾（%.2fs）" % el)
else:
    FAIL.append("8 文件心跳判据异常：got=%r 用时 %.2fs" % (got, el))

# 9) 数据文件持续增长 → 不能误判成已收尾
import threading
_stop = [False]


def _writer():
    while not _stop[0]:
        try:
            with open(fh.name, "ab") as f:
                f.write(b"y")
        except Exception:
            pass
        time.sleep(0.2)


_th = threading.Thread(target=_writer, daemon=True)
_th.start()
got = wait_endexp(lambda *a: None, method="测试", runwin=FakeRunWin(),
                  path=fh.name, timeout=4.0, quiet=1.0)
_stop[0] = True
_th.join(timeout=2)
try:
    os.unlink(fh.name)
except Exception:
    pass
if got is False:
    print("PASS 9 数据文件仍在增长时不误判")
else:
    FAIL.append("9 文件在增长却判成收尾：got=%r" % (got,))

# 10) 停止 40s 仍未生效：必须关运行窗+应答「是」，之后停住则收尾成功
#     （2026-11-12 真机 1 号实测：原逻辑"保留运行窗继续"会挡住后续菜单）
import driver5 as _D5
import runner5 as _R5
from runner5 import S_ERROR as _S_ERROR

_orig_wait = _R5.wait_endexp
_orig_modal = _D5.clear_modals
try:
    _seq = [False, True]
    _calls = []

    def _fake_wait(log, method="", runwin=None, timeout=0, fallback=0, **kw):
        _calls.append("wait")
        return _seq.pop(0) if _seq else True

    _R5.wait_endexp = _fake_wait
    _pids = []
    _D5.clear_modals = lambda limit=4, prefer=None, pid=None: (
        _calls.append("modal"), _pids.append(pid), 1)[2]
    _st = FakeStudio()
    _r = make_runner(_st, FakeRunWin())
    _r.error = ""
    _ok = _r._finish_run("开路电位", idle_wait=0)
    if _ok is True and _st.calls and _st.calls[0] == "stop" and "close" in _st.calls \
            and "modal" in _calls and _pids and all(p == 4242 for p in _pids):
        print("PASS 10 停止未生效→关窗+应答「是」→收尾成功（清框按 pid 隔离）")
    else:
        FAIL.append("10 强制终止路径异常：ok=%r calls=%r st=%r"
                    % (_ok, _calls, _st.calls))
finally:
    _R5.wait_endexp = _orig_wait
    _D5.clear_modals = _orig_modal

# 11) 强制关窗后仍停不下来：必须报 S_ERROR 且返回 False，绝不继续开下一项
try:
    _R5.wait_endexp = lambda log, method="", runwin=None, timeout=0, fallback=0, **kw: False
    _D5.clear_modals = lambda limit=4, prefer=None, pid=None: 1
    _st = FakeStudio()
    _r = make_runner(_st, FakeRunWin())
    _r.error = ""
    _sts = []
    _r.set_state = lambda s, e="": _sts.append(s)
    _ok = _r._finish_run("开路电位", idle_wait=0)
    if _ok is False and _S_ERROR in _sts and _r.error:
        print("PASS 11 停止失败→报 S_ERROR 且返回 False")
    else:
        FAIL.append("11 失败路径异常：ok=%r sts=%r err=%r"
                    % (_ok, _sts, _r.error))
finally:
    _R5.wait_endexp = _orig_wait
    _D5.clear_modals = _orig_modal

print()
if FAIL:
    for f in FAIL:
        print("FAIL " + f)
    sys.exit(1)
print("全部 %d 项 PASS" % TOTAL)
