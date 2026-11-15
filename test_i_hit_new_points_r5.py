# -*- coding: utf-8 -*-
"""test_i_hit_new_points_r5.py —— runner5 动电位「脚本侧不再做电流判停」守护测试。

背景（2026-11-15 用户指令）：删掉脚本里的动电位停止组件，改为软件自带
「扫描停止电流」——PotDynamic_ScanStop_chk + Max/MinCurrent，各入口按
面积×1 mA（= 1e-3 A/cm²）写入，driver5.fill_tafel 成对写入并回读核验。
本测试锁死新行为：哪怕 UIA 读到的电流远超阈值，runner5 也不会自己判停
（否则会跟软件侧判停抢跑，把曲线提前截断）。

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
    """i=2e-3 A → 密度 2e-3 ≥ 阈值 1e-3（旧的脚本判停会在这里触发）。"""
    return types.SimpleNamespace(t_sec=t, e_volt=e, i_amp=i)


# ---- 用例 1：同一个点被 tick 反复读（电流远超阈值）——不得判停
r = make_runner()
r.sampler = FakeSampler([S(1.0)] * 6)
for _ in range(6):
    r._do_mon_test()
assert r.state != S_DONE, "脚本侧不该再判停（软件自带停止电流才是唯一判据）"
assert not hasattr(r, "_i_hit"), "判停计数逻辑应已移除，实际 _i_hit=%r" % getattr(r, "_i_hit", None)
print("用例1 同点重复读不判停 …… PASS")

# ---- 用例 2：连续多个「不同的新点」都超阈值 → 仍不得判停
r = make_runner()
r.sampler = FakeSampler([S(1.0), S(4.0), S(8.0), S(12.0)])
for _ in range(4):
    r._do_mon_test()
assert r.state != S_DONE, "连续超阈值新点也不该由脚本判停，实际 %r" % r.state
print("用例2 连续超阈值新点不判停 …… PASS")

# ---- 用例 3：低电流点同样不判停（只等软件/窗口/文件判据）
r = make_runner()
r.sampler = FakeSampler([S(1.0, i=5e-4), S(2.0, i=5e-4)])
for _ in range(2):
    r._do_mon_test()
assert r.state != S_DONE
print("用例3 低点不判停 …… PASS")

print("test_i_hit_new_points_r5: 全部 PASS")
