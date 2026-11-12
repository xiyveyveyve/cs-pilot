# -*- coding: utf-8 -*-
"""test_i_hit_new_points_r5.py —— runner5 电流密度判停「只计新点」修复的回归测试。

背景：runner5 旧实现按 tick 计数（0.4s/tick），而 5 版数据走 UIA、软件约 3s 才
flush 一次——同一个读数在 flush 间隔内被反复读到，单点尖峰一次 flush 间隔就攒满
`_i_hit>=2` → 误停真机实验。runner6 已于 2026-11-07 审查 P1 修复（_i_last_t 以新点
计数）且有 test_judge_count 回归锁，runner5 漏修漏测；C2.2（2026-11-12）对齐同款修法。

不连软件、不碰设备：FakeSampler 注入受控读数序列，直接驱动 _do_mon_test。
"""
import time
import types

from runner5 import Runner5, RunConfig5, S_MON_TEST, S_DONE


class FakeSampler:
    """按调用次数吐出预置读数序列（末尾重复最后一个）。"""

    def __init__(self, samples):
        self._samples = list(samples)
        self._i = 0

    def alive(self):
        return True

    def read(self):
        s = self._samples[min(self._i, len(self._samples) - 1)]
        self._i += 1
        return s


def make_runner():
    cfg = RunConfig5(sample="t", area_cm2=1.0, item="Tafel",
                     test_stop_i_density=1e-3)
    r = Runner5(cfg)
    r.state = S_MON_TEST
    r.studio = None            # _safe_finish 首行判 studio None 直接返回，无 UI 副作用
    r.runwin = None
    r.t0 = time.time()
    r._test_phase_t0 = time.time()
    return r


def S(t, e=-0.1, i=2e-3):
    """i=2e-3 A → 密度 2e-3 ≥ 阈值 1e-3（达标）。"""
    return types.SimpleNamespace(t_sec=t, e_volt=e, i_amp=i)


# ---- 用例 1：同一个点被 tick 反复读（模拟 flush 间隔内 6 个 tick）——不得攒满判停
r = make_runner()
r.sampler = FakeSampler([S(1.0)] * 6)
for _ in range(6):
    r._do_mon_test()
assert r.state != S_DONE, "BUG：同一个点重复读就攒满判停（修复未生效）"
assert getattr(r, "_i_hit", 0) == 1, "首个新点只应计 1，实际 %r" % getattr(r, "_i_hit", None)
print("用例1 同点重复读不计满 …… PASS")

# ---- 用例 2：连续 2 个「不同的新点」达标 → 判停
r = make_runner()
r.sampler = FakeSampler([S(1.0), S(4.0), S(4.0)])
r._do_mon_test()                       # 新点 t=1.0 → _i_hit=1
assert r.state != S_DONE
r._do_mon_test()                       # 新点 t=4.0 → _i_hit=2 → 判停
assert r.state == S_DONE, "连续 2 个新点达标应判停，实际 %r" % r.state
print("用例2 两个新点达标判停 …… PASS")

# ---- 用例 3：低于阈值的点要清零计数
r = make_runner()
r.sampler = FakeSampler([S(1.0, i=5e-4), S(2.0, i=5e-4), S(3.0, i=2e-3), S(3.0, i=2e-3)])
for _ in range(4):
    r._do_mon_test()
assert r.state != S_DONE, "达标被低点打断后不应残留计数（t=1,2 低点清零，t=3 只 1 个新点）"
assert getattr(r, "_i_hit", 0) == 1
print("用例3 低点清零计数 …… PASS")

print("test_i_hit_new_points_r5: 全部 PASS")
