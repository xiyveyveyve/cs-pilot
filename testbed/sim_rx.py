# -*- coding: utf-8 -*-
"""sim_rx.py -- B 端专用 CS350M 模拟器（Agent B · RX 收包入库测试床）。

基于 _probe/vp-channel/simdevice.py（SimDevice 复用），只改数据推送命令码：
CS6 BaseContext.PackReceive 实测只入库 0x60 CSDataE / 0x61 CSDataI / 0x62 CSDataEI，
0x68 CSDataOCP 是「未识别数据包类型：68」（2026-11-07 probe_rx3/rx4 运行期实测），
真实设备 OCP 流样本也是 0x60（55 AA 00 0A 60 CD 7B 0E BE 7D -> -0.139 V），
故 OCP 模式默认推 0x60。

用法：python testbed/sim_rx.py --port CNCB0 [--hz 10]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, r"D:\deepseek\_probe\vp-channel")
from simdevice import SimDevice, DEFAULT_SN          # noqa: E402
from cspilot.core import proto                        # noqa: E402  (vp-channel 已插好路径)


class SimRx(SimDevice):
    """只重写数据发射线程：OCP 模式推 0x60 CSDataE（1 个 float32 电位）。"""

    def __init__(self, *a, **kw):
        self.data_cmd_name = kw.pop("data_cmd", "CSDataE")
        SimDevice.__init__(self, *a, **kw)

    def _emitter(self):
        period = 1.0 / max(1.0, self.sample_hz)
        next_t = time.time()
        k = 0
        cmd = proto.C[self.data_cmd_name]
        while self.running:
            now = time.time()
            if now < next_t:
                time.sleep(min(0.005, next_t - now))
                continue
            next_t += period
            if self.mode == "ocp":
                drift = -0.00002 * k
                noise = self.rng.gauss(0, 1.5e-5)
                E = self._ocp_base + drift + noise
                self._send(proto.build_f(cmd, E))
                k += 1
            elif self.mode == "potdynamic":
                el = max(0.0, time.time() - (self._t_exp0 or time.time()))
                span = self._pot_final - self._pot_init
                if abs(span) > 1e-9 and abs(self._pot_rate) > 1e-12:
                    dur = abs(span / self._pot_rate)
                    frac = min(1.0, el / dur) if dur > 0 else 1.0
                else:
                    frac = 0.0
                E = self._pot_init + span * frac
                i = 1e-7 * (10 ** ((E - self._pot_init) / 0.12)) - 1e-8
                self._send(proto.build_f(cmd, E, i) if self.data_cmd_name == "CSDataEI"
                           else proto.build_f(cmd, E))
                k += 1
            else:
                k = 0


def main():
    ap = argparse.ArgumentParser(description="CS350M 模拟器（RX 测试床版，推 0x60）")
    ap.add_argument("--port", default="CNCB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--sn", default=DEFAULT_SN)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--data-cmd", default="CSDataE",
                    choices=["CSDataE", "CSDataOCP", "CSDataEI", "CSDataI"])
    args = ap.parse_args()

    dev = SimRx(args.port, args.baud, args.sn, args.hz, verbose=True,
                data_cmd=args.data_cmd)
    dev.start()
    print("sim_rx 运行中（data_cmd=%s），Ctrl+C 退出 ..." % args.data_cmd, flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        dev.stop()
        print("统计: %r" % (dev.summary(),), flush=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
