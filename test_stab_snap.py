# -*- coding: utf-8 -*-
"""5 分钟快照对比测试（ASTM G59 稳态思路）。"""
from stabilizer import OcpStabilizer, StabConfig

FAIL = []
def run_series(fn, t_end, dt=1.0, cfg=None):
    st = OcpStabilizer(cfg or StabConfig())
    last = None
    for i in range(int(t_end / dt) + 1):
        t = i * dt
        last = st.feed([(t, fn(t))])
    return st, last

# 1) 慢漂 4 mV/min（斜率放行）但 5min 快照差 20mV → 宽松阶段也不能判稳
st, s = run_series(lambda t: 0.1 + 0.0000667 * t, 900)
if not s.stable and "快照差" in s.reason:
    print("PASS 1 慢漂4mV/min 但快照差 20mV → 不判稳（%s）" % s.reason[:60])
else:
    FAIL.append("1 应该被快照判据拦住, got stable=%s reason=%s" % (s.stable, s.reason[:70]))

# 2) 完全平稳（0.2 mV/min）→ 严格阶段 400s 就停（快照判据不影响严格阶段）
st, s = run_series(lambda t: 0.1 + 0.0000033 * t, 500)
if s.stable and s.t_now < 600:
    print("PASS 2 极平稳 → %.0fs 严格阶段判稳（快照 %d 个）" % (s.t_now, s.snaps))
else:
    FAIL.append("2 极平稳应提前判稳, got stable=%s t=%.0f" % (s.stable, s.t_now))

# 3) 平稳（0.3 mV/min，快照差 1.5mV）→ 宽松阶段判稳
st, s = run_series(lambda t: 0.1 + 0.000005 * t, 900)
if s.stable and s.t_now >= 600 and s.snap_drift_mv < 5:
    print("PASS 3 平稳 → %.0fs 判稳，快照 %d 个、差 %.2f mV" % (s.t_now, s.snaps, s.snap_drift_mv))
else:
    FAIL.append("3 应判稳, got stable=%s t=%.0f drift=%.2f" % (s.stable, s.t_now, s.snap_drift_mv))

# 4) 跳变后稳定：200s 处跳 10mV，之后完全平坦 → 快照差会永久带偏一次，需后续快照拉回
def jump(t):
    return 0.1 + (0.010 if t >= 200 else 0.0)
st, s = run_series(jump, 1300)
print("INFO 4 跳变测试：t=%.0f stable=%s snaps=%d drift=%.2f reason=%s"
      % (s.t_now, s.stable, s.snaps, s.snap_drift_mv, s.reason[:50]))

# 5) 关掉快照判据（snapshot_required=False）→ 慢漂 4mV/min 又能在宽松段判稳
cfg = StabConfig(snapshot_required=False)
st, s = run_series(lambda t: 0.1 + 0.0000667 * t, 900, cfg=cfg)
if s.stable:
    print("PASS 5 关掉快照判据后 4mV/min 可判稳（%.0fs）" % s.t_now)
else:
    FAIL.append("5 关掉快照后应判稳, got reason=%s" % s.reason[:60])

print()
if FAIL:
    print("FAILED:")
    for f in FAIL: print("  -", f)
    raise SystemExit(1)
print("PASS ✅")
