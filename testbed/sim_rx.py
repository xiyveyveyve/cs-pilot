# -*- coding: utf-8 -*-
"""sim_rx.py -- B 端专用 CS350M 模拟器（Agent B · RX 收包入库测试床）。

基于正式资产 testbed/simdevice.py（同目录，2026-11-07 审查修正：原依赖仓库外
D:\\deepseek\\_probe\\vp-channel 临时版与 D:\\deepseek\\CSDirect 的 cspilot.core.proto，
已改为只依赖本目录正式资产），只重写数据发射线程：OCP 模式推 0x60 CSDataE
单点帧（每点一帧，与 Phase 2 正式 simdevice 的 --points 1 模式等价但发射线程独立）。

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simdevice import SimDevice, DEFAULT_SN, CMD, build_f   # noqa: E402（同目录正式资产）


class SimRx(SimDevice):
    """只重写数据发射线程：OCP 模式推 0x60 CSDataE（1 个 float32 电位）。"""

    def __init__(self, *a, **kw):
        self.data_cmd_name = kw.pop("data_cmd", "CSDataE")
        # data_cmd 必须转发给基类：ReadOcp 应答/停止冲刷的命令码要与推流码
        # 一致（2026-11-07 审查 P3，旧版 --data-cmd CSDataOCP 时两者不一致）
        SimDevice.__init__(self, *a, data_cmd=self.data_cmd_name, **kw)

    def _emitter(self):
        next_t = time.time()
        k = 0
        cmd = CMD[self.data_cmd_name]
        while self.running:
            now = time.time()
            # 每拍重算节拍 + 停顿丢账：与正式 simdevice._emitter 同修
            # （0x51 改率要生效；停顿后不许以 CPU 速度补帧灌串口）
            period = self._emitter_period()
            if now < next_t:
                time.sleep(min(0.005, max(0.0, next_t - now)))
                continue
            next_t = self._emitter_advance(next_t, now, period)
            with self._lock:
                mode = self.mode
            # 正式 simdevice 的模式名："ocp" / "potdyn"（旧临时版叫 "potdynamic"）
            if mode == "ocp":
                # 锁内生成：rng 与 ReadOcp 路径互斥（gauss 缓存对经不起并发）
                with self._lock:
                    drift = -0.00002 * k
                    E = self._ocp_base + drift + self.rng.gauss(0, 1.5e-5)
                self._send(build_f(cmd, E))
                k += 1
            elif mode == "potdyn":
                with self._lock:
                    el = max(0.0, now - (self._t_exp0 or now))
                    span = self._pot_final - self._pot_init
                    if abs(span) > 1e-9 and abs(self._pot_rate) > 1e-12:
                        dur = abs(span / self._pot_rate)
                        frac = min(1.0, el / dur) if dur > 0 else 1.0
                    else:
                        frac = 0.0
                    E = self._pot_init + span * frac
                    i = 1e-7 * (10 ** ((E - self._pot_init) / 0.12)) - 1e-8
                self._send(build_f(cmd, E, i) if self.data_cmd_name == "CSDataEI"
                           else build_f(cmd, E))
                k += 1
            elif mode in ("step", "eis"):
                # 基类分发已 ACK 0x56/0x70 并置 mode——旧版对这两种模式静默
                # 一帧不推（2026-11-07 审查 P3）：复用基类信号发生器
                with self._lock:
                    frame = self.make_ei_frame(max(0.0, now - (self._t_exp0 or now)))
                self._send(frame)
                k += 1
            else:
                k = 0


def main():
    ap = argparse.ArgumentParser(description="CS350M 模拟器（RX 测试床版，推 0x60 单点流）")
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
