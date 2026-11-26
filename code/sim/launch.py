# -*- coding: utf-8 -*-
"""sim/launch.py —— 起一个虚拟设备（simdevice.py 的薄封装，不改原脚本）。

复用前序 testbed/simdevice.py（只读复制，sha256 见本目录 MANIFEST.txt）：
  * 串口模式：--port CNCB0（com0com 对端），宿主连 COM90 别名
  * 网口模式：--tcp --port 0.0.0.0:31001，宿主连 127.0.0.1:31001
  * 回放模式：--replay-ocp / --replay-pot 用真机曲线当输入

红线：绝不使用 COM16/COM10/COM6/COM4/COM5/COM11/COM12（真机/蓝牙口）。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "simdevice.py")

FORBIDDEN = {"COM16", "COM10", "COM6", "COM4", "COM5", "COM11", "COM12"}


class Sim:
    def __init__(self, port="CNCB0", tcp=False, lan=False, sn=None, hz=10.0,
                 points=30, replay_ocp=None, replay_pot=None, wait_start=False,
                 log_path=None, quiet=False, python="python"):
        self.port = port
        self.tcp = tcp
        self.lan = lan
        self.sn = sn
        self.hz = hz
        self.points = points
        self.replay_ocp = replay_ocp
        self.replay_pot = replay_pot
        self.wait_start = wait_start
        self.log_path = log_path
        self.quiet = quiet
        self.python = python
        self.proc = None
        self._out = None

    def argv(self):
        a = [self.python, SIM, "--port", self.port, "--hz", str(self.hz),
             "--points", str(self.points)]
        if self.tcp:
            a.append("--tcp")
        if self.lan:
            a.append("--lan")
        if self.sn:
            a += ["--sn", self.sn]
        if self.replay_ocp:
            a += ["--replay-ocp", self.replay_ocp]
        if self.replay_pot:
            a += ["--replay-pot", self.replay_pot]
        if self.wait_start:
            a.append("--wait-start")
        if self.log_path:
            a += ["--log", self.log_path]
        if self.quiet:
            a.append("--quiet")
        return a

    def start(self, ready_wait=2.0):
        if not self.tcp:
            base = self.port.upper().replace("\\\\.\\", "")
            if base in FORBIDDEN:
                raise RuntimeError("红线：拒绝打开真机/蓝牙端口 %r" % self.port)
        os.makedirs(os.path.dirname(self.log_path or ""), exist_ok=True) if self.log_path else None
        self._out = open(os.path.join(os.path.dirname(self.log_path or HERE),
                                      "sim_%s.out.log" % _safe(self.port)), "w",
                         encoding="utf-8", errors="replace") if self.log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(self.argv(), stdout=self._out, stderr=subprocess.STDOUT)
        time.sleep(ready_wait)
        if self.proc.poll() is not None:
            raise RuntimeError("模拟器启动即退出，rc=%s（看 %s）" % (self.proc.returncode, self.log_path))
        return self

    def stop(self, timeout=5):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        finally:
            if self._out not in (None, subprocess.DEVNULL):
                try:
                    self._out.close()
                except Exception:
                    pass
            self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False


def _safe(s):
    return "".join(c if c.isalnum() else "_" for c in s)


if __name__ == "__main__":
    # 自测：起 3 秒就关，确认模拟器能在这个目录下跑起来
    import tempfile
    d = tempfile.mkdtemp(prefix="cspilot_sim_")
    s = Sim(port="0.0.0.0:31999", tcp=True, log_path=os.path.join(d, "sim.jsonl"))
    s.start()
    print("sim up pid=%s argv=%s" % (s.proc.pid, " ".join(s.argv())))
    time.sleep(3)
    s.stop()
    print("sim down ok")
