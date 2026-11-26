"""命令行执行一次恒电流极化。

    python tools/run_galstatic.py --port COM10 --curr 0.2 --unit mA --time 200
    python tools/run_galstatic.py --port /dev/ttyUSB0 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cs5 import galstatic  # noqa: E402
from cs5.session import CS350Session  # noqa: E402
from cs5.transport import SerialTransport, TcpTransport  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="CS350 恒电流极化")
    ap.add_argument("--port", default="/dev/ttyUSB0", help="串口，或 TCP:host:port")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--curr", type=float, default=0.2, help="极化电流")
    ap.add_argument("--unit", default="mA", choices=list(galstatic.CURR_UNIT_EXP))
    ap.add_argument("--time", type=float, default=200.0, help="保持时间")
    ap.add_argument("--tunit", default="s", choices=["s", "min", "h"])
    ap.add_argument("--frq", type=float, default=5.0, help="采样率 Hz")
    ap.add_argument("--out", default="", help="输出 .cor 路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要发送的帧")
    args = ap.parse_args()

    p = galstatic.GalStaticParams(
        por_curr=args.curr, curr_unit=args.unit,
        test_time=args.time, time_unit=args.tunit, sample_frq=args.frq,
    )

    print(f"参数: {p.summary()}")
    print(f"电流: {p.current_a:.6e} A")
    print(f"DA 输出: {p.da_volt:.4f} V")
    print(f"预计点数: {p.expected_points()}")
    for i, f in enumerate(p.method_frames()):
        from cs5 import frame as fr

        print(f"  帧{i}: {fr.hexs(f)}")

    if args.dry_run:
        return 0

    if args.port.upper().startswith("TCP:"):
        host, _, port = args.port[4:].partition(":")
        tp = TcpTransport(host, int(port or 4001))
    else:
        tp = SerialTransport(args.port, args.baud)

    sess = CS350Session(tp)
    print("连接中…")
    sess.connect()
    print(f"序列号: {sess.serial or '未知'}")
    print(f"OCP: {sess.read_ocp():.4f} V")

    t0 = time.monotonic()
    last = [0.0]

    def on_point(pt) -> None:
        if pt.t - last[0] >= 1.0:
            last[0] = pt.t
            print(f"  t={pt.t:7.2f}s  E={pt.e:+.5f} V  I={pt.i:.4e} A")

    print("开始采集，Ctrl+C 中止…")
    try:
        cor = sess.run_galstatic(p, on_point=on_point)
    except KeyboardInterrupt:
        sess.stop()
        print("\n已中止")
        return 130

    if args.out:
        out = Path(args.out)
    else:
        stamp = cor.started.strftime("%Y%m%d_%H%M%S") if cor.started else "out"
        out = Path.home() / "Corrtest" / "Data" / f"ID_GalStatic_{stamp}.cor"
    cor.save(out)
    print(f"完成，{len(cor.points)} 点 -> {out}  用时 {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())