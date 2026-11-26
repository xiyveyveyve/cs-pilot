# -*- coding: utf-8 -*-
"""snap_cam.py —— 用 USB 摄像头抓帧，配合电压异常事件留证。

用法：
    python tools/snap_cam.py --list                      # 列出可用摄像头
    python tools/snap_cam.py --snap                      # 抓一张
    python tools/snap_cam.py --snap --tag L2             # 带标签
    python tools/snap_cam.py --snap --tag L2 --burst 3   # 连拍 3 张（间隔 5 s）
    python tools/snap_cam.py --snap --tag L4 --volt 1.632 --de -0.141

设计要点：
  · 每次抓帧后立即 release，避免摄像头长期占用掉线
  · 优先锁定曝光/白平衡（可比性比清晰度更重要）
  · 文件名带时间戳 + 电压 + 事件 + 级别，便于事后按事件检索
  · 不依赖任何第三方服务，纯 opencv

退出码：
  0  成功
  2  找不到摄像头
  3  抓帧失败（设备被占用 / 掉线）
"""
import os
import sys
import time
import argparse
from datetime import datetime

import cv2

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "logs", "snapshots")


BACKENDS = [("MSMF", cv2.CAP_MSMF), ("DSHOW", cv2.CAP_DSHOW), ("ANY", cv2.CAP_ANY)]


def _try_open(index, backend, warm=0):
    """尝试用指定后端打开并读一帧。成功返回 (cap, frame)，失败返回 (None, None)。"""
    try:
        cap = cv2.VideoCapture(index, backend)
    except Exception:
        return None, None
    if not cap.isOpened():
        cap.release()
        return None, None
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        return None, None
    return cap, frame


def list_cameras(max_index=6):
    """探测 index 0..max-1，逐个后端尝试。返回 [(index, w, h, backend_name)]。"""
    found = []
    for i in range(max_index):
        for name, be in BACKENDS:
            cap, frame = _try_open(i, be)
            if cap is not None:
                h, w = frame.shape[:2]
                found.append((i, w, h, name))
                cap.release()
                break
    return found


def open_cam(index=0):
    cap = None
    for name, be in BACKENDS:
        cap, _f = _try_open(index, be)
        if cap is not None:
            break
    if cap is None:
        return None
    # 分辨率
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # 尝试锁定曝光与白平衡（不同相机支持度不同，失败不影响）
    try:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # DSHOW: 0.25 = 手动
        cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    except Exception:
        pass
    # 丢掉前几帧（自动曝光/白平衡收敛）
    for _ in range(6):
        cap.read()
        time.sleep(0.05)
    return cap


def safe_num(x):
    """把数值变成文件名安全的形式：-0.141 → -0.141，1.6 → 1.600。"""
    try:
        return "%.3f" % float(x)
    except (TypeError, ValueError):
        return "na"


def snap_once(outdir, tag=None, volt=None, de=None, index=0, note=""):
    os.makedirs(outdir, exist_ok=True)
    cap = open_cam(index)
    if cap is None:
        print("[snap] 打不开摄像头 index=%d" % index, file=sys.stderr)
        return None
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("[snap] 抓帧失败（可能被其他程序占用）", file=sys.stderr)
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts = ["snap", ts]
        if volt is not None:
            parts.append("E" + safe_num(volt))
        if de is not None:
            parts.append("dE" + ("+" if float(de) >= 0 else "") + safe_num(de))
        if tag:
            parts.append(str(tag))
        name = "_".join(parts) + ".jpg"
        path = os.path.join(outdir, name)

        # 写一行元数据，方便后续检索
        cv2.imwrite(path, frame)

        meta = os.path.join(outdir, "snapshots.log")
        with open(meta, "a", encoding="utf-8") as f:
            f.write("%s\t%s\tE=%s\tdE=%s\ttag=%s\tnote=%s\n" %
                    (ts, name, safe_num(volt) if volt is not None else "-",
                     safe_num(de) if de is not None else "-", tag or "-", note or "-"))

        print("[snap] %s" % path)
        return path
    finally:
        cap.release()


def main():
    ap = argparse.ArgumentParser(description="USB 摄像头抓帧（配合电压事件）")
    ap.add_argument("--list", action="store_true", help="列出可用摄像头")
    ap.add_argument("--snap", action="store_true", help="抓一张")
    ap.add_argument("--index", type=int, default=0, help="摄像头序号，默认 0")
    ap.add_argument("--outdir", default=DEFAULT_OUT, help="保存目录")
    ap.add_argument("--tag", default=None, help="事件标签，如 L1/L2/L3/L4/TEST")
    ap.add_argument("--volt", type=float, default=None, help="当前电压（写入文件名）")
    ap.add_argument("--de", type=float, default=None, help="电压变化量（写入文件名）")
    ap.add_argument("--burst", type=int, default=1, help="连拍张数")
    ap.add_argument("--interval", type=float, default=5.0, help="连拍间隔秒")
    ap.add_argument("--note", default="", help="备注")
    a = ap.parse_args()

    if a.list:
        cams = list_cameras()
        if not cams:
            print("没有可用摄像头（检查是否插好/被占用）")
            sys.exit(2)
        for i, w, h, be in cams:
            print("index=%d  %dx%d  backend=%s" % (i, w, h, be))
        return

    if not a.snap:
        ap.print_help()
        return

    got = 0
    for k in range(max(1, a.burst)):
        p = snap_once(a.outdir, a.tag, a.volt, a.de, a.index, a.note)
        if p is None:
            sys.exit(3)
        got += 1
        if k + 1 < a.burst:
            time.sleep(a.interval)
    print("[snap] 完成，共 %d 张 → %s" % (got, a.outdir))


if __name__ == "__main__":
    main()
