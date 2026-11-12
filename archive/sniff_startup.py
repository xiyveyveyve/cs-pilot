# -*- coding: utf-8 -*-
"""sniff_startup.py —— 抓 CS Studio6 启动时对 COM16(CNCA0) 的原始串口流量。

链路：软件 → COM16(别名→CNCA0) ↔ [本记录器监听 CNCB0] → 记录全部字节。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import serial

LOG = r"D:\deepseek\_probe\live\sniff_startup.log"

with open(LOG, "w", encoding="utf-8") as lf:
    def log(m):
        line = "%7.2f  %s" % (time.time() % 10000, m)
        print(line, flush=True)
        lf.write(line + "\n")
        lf.flush()

    ser = serial.Serial(r"\\.\CNCB0", 115200, timeout=0.2)
    log("记录器就绪（CNCB0 @115200）")
    buf = b""
    t0 = time.time()
    while time.time() - t0 < 40:
        data = ser.read(256)
        if data:
            ts = time.time() - t0
            log("%.3f RX %d B: %s" % (ts, len(data), data.hex(" ").upper()))
            buf += data
        time.sleep(0.1)
    ser.close()
    log("40s 记录完成，总 %d 字节" % len(buf))
    with open(LOG + ".bin", "wb") as f:
        f.write(buf)
