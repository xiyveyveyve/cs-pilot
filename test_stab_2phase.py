# -*- coding: utf-8 -*-
"""两阶段判稳测试：前 600 s 严格（1 mV/min、峰峰 2 mV），之后放宽（5 mV/min、5 mV）。"""
from stabilizer import OcpStabilizer, StabConfig

cfg = StabConfig()          # 默认即两阶段
FAIL = []

def run(series, note):
    st = OcpStabilizer(cfg)
    last = None
    for t, v in series:
        last = st.feed([(t, v)])
    return last, note

def series_of(fn, t_end, dt=1.0):
    n = int(t_end / dt)
    return [(i * dt, fn(i * dt)) for i in range(n + 1)]

# 1) 极平稳（0.5 mV/min、峰峰 0.3 mV）→ 应在 600 s 之前就判稳（严格阶段）
s = series_of(lambda t: 0.1 + 0.0000083 * t, 400)
st, _ = run(s, "极平稳")
if st.stable and st.t_now < 600:
    print("PASS 1 极平稳→%.0f s 判稳（阶段%s）" % (st.t_now, st.phase))
else:
    FAIL.append("1 极平稳应提前判稳, got stable=%s t=%.0f phase=%s" % (st.stable, st.t_now, st.phase))

# 2) 2 mV/min（严格阶段过不了，放宽后能过）→ 应在 600 s 之后判稳
s = series_of(lambda t: 0.1 + 0.0000333 * t, 900)
st, _ = run(s, "2 mV/min")
if st.stable and st.t_now >= 600:
    print("PASS 2 2 mV/min→%.0f s 判稳（阶段%s）" % (st.t_now, st.phase))
else:
    FAIL.append("2 2mV/min 应在600s后判稳, got stable=%s t=%.0f" % (st.stable, st.t_now))

# 3) 6 mV/min（两阶段都过不了）→ 不判稳
s = series_of(lambda t: 0.1 + 0.0001 * t, 900)
st, _ = run(s, "6 mV/min")
if not st.stable:
    print("PASS 3 6 mV/min→不判稳（%s）" % st.reason[:50])
else:
    FAIL.append("3 6mV/min 不应判稳")

# 4) 4 mV/min（斜率过放宽、但 5 分钟漂 20 mV 被快照判据拦住）→ 不判稳
s = series_of(lambda t: 0.1 + 0.0000667 * t, 900)
st, _ = run(s, "4 mV/min")
if not st.stable and "快照差" in st.reason:
    print("PASS 4 4 mV/min→被 5 分钟快照拦住（%s）" % st.reason[:55])
else:
    FAIL.append("4 4mV/min 应被快照判据拦住, got stable=%s reason=%s" % (st.stable, st.reason[:60]))

# 5) 峰峰保护：斜率 0，但锯齿 ±3 mV（严格阶段峰峰 6 > 2 不过；放宽 6 > 5 也不过）→ 不判稳
s = [(t, 0.1 + (0.003 if int(t) % 2 else -0.003)) for t in range(0, 900)]
st, _ = run(s, "锯齿")
if not st.stable:
    print("PASS 5 锯齿 ±3mV→不判稳（%s）" % st.reason[:50])
else:
    FAIL.append("5 锯齿不应判稳")

# 6) 阶段切换：600 s 前 reason 应含"严格"与剩余秒数
s = series_of(lambda t: 0.1 + 0.0001 * t, 300)
st, _ = run(s, "阶段判定")
if st.phase == "strict" and "严格" in st.reason and "后放宽" in st.reason:
    print("PASS 6 阶段 A 提示正确：%s" % st.reason)
else:
    FAIL.append("6 阶段提示不对: %s / %s" % (st.phase, st.reason))

print()
if FAIL:
    print("FAILED:")
    for f in FAIL: print("  -", f)
    raise SystemExit(1)
print("全部 6 项 PASS ✅")
