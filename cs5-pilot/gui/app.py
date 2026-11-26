"""CS350 恒电流极化上位机（Kivy，桌面 Linux / Android 通用）。"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cs5 import frame, galstatic  # noqa: E402
from cs5.datalog import CorFile, CorPoint  # noqa: E402
from cs5.session import CS350Session  # noqa: E402
from cs5.transport import SerialTransport, TcpTransport  # noqa: E402

BAUDS = ["9600", "19200", "38400", "57600", "115200"]
UNITS = ["mA", "uA", "nA", "A", "pA"]
TIME_UNITS = ["s", "min", "h"]


class Plot(BoxLayout):
    """E-t 曲线，纯 canvas 绘制，不依赖 matplotlib。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.es: list[float] = []
        self.ts: list[float] = []
        self._line = None
        self._bg = None
        self.bind(pos=self._redraw, size=self._redraw)

    def add_point(self, t: float, e: float) -> None:
        self.es.append(e)
        self.ts.append(t)
        if len(self.es) > 20000:
            self.es = self.es[-20000:]
            self.ts = self.ts[-20000:]
        self._redraw()

    def clear(self) -> None:
        self.es.clear()
        self.ts.clear()
        self._redraw()

    def _redraw(self, *_) -> None:
        self.canvas.clear()
        with self.canvas:
            Color(0.07, 0.09, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.3, 0.8, 0.9, 1)
            if len(self.es) >= 2:
                self._line = Line(points=self._points(), width=1.4)
            Color(0.35, 0.4, 0.45, 1)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)

    def _points(self) -> list[float]:
        n = len(self.es)
        t0, t1 = self.ts[0], self.ts[-1]
        if t1 - t0 < 1e-9:
            t1 = t0 + 1.0
        e0, e1 = min(self.es), max(self.es)
        if e1 - e0 < 1e-9:
            e0 -= 0.1
            e1 += 0.1
        pad = 0.06
        w = self.width * (1 - 2 * pad)
        h = self.height * (1 - 2 * pad)
        xs = self.x + self.width * pad
        ys = self.y + self.height * pad
        pts: list[float] = []
        for t, e in zip(self.ts, self.es):
            pts.append(xs + (t - t0) / (t1 - t0) * w)
            pts.append(ys + (e - e0) / (e1 - e0) * h)
        return pts


@dataclass
class Runner:
    session: CS350Session | None = None
    thread: threading.Thread | None = None
    stop_flag: threading.Event | None = None
    q: queue.Queue | None = None


class ParamRow(GridLayout):
    def __init__(self, label: str, default: str, **kw):
        super().__init__(cols=2, size_hint_y=None, height=44, spacing=6, **kw)
        self.add_widget(Label(text=label, size_hint_x=0.45))
        # 注意不能用 input_filter="float"：它会吃掉负号，而阴极极化常要负电流
        self.input = TextInput(text=default, multiline=False,
                               font_size=18, size_hint_x=0.55)
        self.add_widget(self.input)

    @property
    def value(self) -> float:
        try:
            return float(self.input.text)
        except ValueError:
            return 0.0


class Root(BoxLayout):
    status = StringProperty("就绪")
    progress = NumericProperty(0.0)
    running = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=10, spacing=8, **kw)
        self.runner = Runner()

        # 连接行
        top = GridLayout(cols=3, size_hint_y=None, height=44, spacing=6)
        self.port_in = TextInput(text=self._default_port(), multiline=False, font_size=16)
        self.baud = Spinner(text="9600", values=BAUDS, size_hint_x=0.35)
        self.btn_conn = Button(text="连接", size_hint_x=0.3, on_release=self.on_connect)
        top.add_widget(self.port_in)
        top.add_widget(self.baud)
        top.add_widget(self.btn_conn)
        self.add_widget(top)

        # 曲线
        self.plot = Plot()
        self.add_widget(self.plot)

        # 参数
        self.curr_row = ParamRow("极化电流", "0.2")
        self.unit = Spinner(text="mA", values=UNITS, size_hint_y=None, height=44, font_size=18)
        self.time_row = ParamRow("保持时间", "200")
        self.tunit = Spinner(text="s", values=TIME_UNITS, size_hint_y=None, height=44, font_size=18)
        self.add_widget(self.curr_row)
        self.add_widget(self.unit)
        self.add_widget(self.time_row)
        self.add_widget(self.tunit)

        # 操作
        btns = GridLayout(cols=2, size_hint_y=None, height=56, spacing=8)
        self.btn_start = Button(text="开始", font_size=20, background_color=(0.15, 0.6, 0.4, 1),
                                on_release=self.on_start)
        self.btn_stop = Button(text="停止", font_size=20, background_color=(0.7, 0.25, 0.25, 1),
                               on_release=self.on_stop, disabled=True)
        btns.add_widget(self.btn_start)
        btns.add_widget(self.btn_stop)
        self.add_widget(btns)

        self.info = Label(text="就绪", size_hint_y=None, height=52, font_size=15,
                          text_size=(None, None), halign="left", valign="middle")
        self.add_widget(self.info)
        Clock.schedule_interval(self._tick, 0.1)

    @staticmethod
    def _default_port() -> str:
        import sys

        if sys.platform.startswith("win"):
            return "COM10"
        return "/dev/ttyUSB0"

    # ---------- 连接 ----------

    def on_connect(self, *_):
        if self.running:
            self._say("采集进行中，先停止再断开")
            return
        if self.runner.session is not None:
            self._disconnect()
            return
        port = self.port_in.text.strip()
        try:
            if port.upper().startswith("TCP:"):
                host, _, p = port[4:].partition(":")
                tp = TcpTransport(host, int(p or 4001))
            else:
                tp = SerialTransport(port, int(self.baud.text))
            sess = CS350Session(tp)
            sess.connect()
            self.runner.session = sess
            self.btn_conn.text = "断开"
            self._say(f"已连接 {port},SN={sess.serial or '未知'},OCP={sess.read_ocp():.4f} V")
        except Exception as exc:  # noqa: BLE001
            self._say(f"连接失败:{exc}")

    def _disconnect(self) -> None:
        try:
            self.runner.session.close()
        except Exception:  # noqa: BLE001
            pass
        self.runner.session = None
        self.btn_conn.text = "连接"
        self._say("已断开")

    # ---------- 采集 ----------

    def on_start(self, *_):
        if self.runner.session is None:
            self._say("请先连接设备")
            return
        if self.running:
            return
        try:
            params = galstatic.GalStaticParams(
                por_curr=self.curr_row.value,
                curr_unit=self.unit.text,
                test_time=self.time_row.value,
                time_unit=self.tunit.text,
            )
        except ValueError as exc:
            self._say(f"参数错误:{exc}")
            return

        self.plot.clear()
        self.running = True
        self.progress = 0.0
        self.btn_start.disabled = True
        self.btn_stop.disabled = False
        self._say(f"开始:{params.summary()},DA={params.da_volt:.4f} V")

        q: queue.Queue = queue.Queue()
        stop_ev = threading.Event()
        self.runner.q = q
        self.runner.stop_flag = stop_ev

        def work() -> None:
            sess: CS350Session = self.runner.session
            try:
                cor = sess.run_galstatic(
                    params,
                    on_point=lambda p: q.put(("pt", p.t, p.e, p.i)),
                    should_stop=stop_ev.is_set,
                )
                out = Path.home() / "Corrtest" / "Data" / f"ID_GalStatic_{datetime.now():%Y%m%d_%H%M%S}.cor"
                cor.save(out)
                q.put(("done", str(out), len(cor.points)))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", repr(exc), 0))

        th = threading.Thread(target=work, daemon=True)
        self.runner.thread = th
        th.start()

    def on_stop(self, *_):
        if self.runner.stop_flag is not None:
            self.runner.stop_flag.set()
            self._say("正在停止…")

    def _tick(self, _dt: float) -> None:
        q = self.runner.q
        if q is None:
            return
        while True:
            try:
                kind, a, b, *rest = q.get_nowait()
            except queue.Empty:
                break
            if kind == "pt":
                self.plot.add_point(a, b)
            elif kind == "done":
                self._finish(f"完成:{a}（{b} 点）")
            elif kind == "err":
                self._finish(f"出错:{a}")

    def _finish(self, msg: str) -> None:
        self.running = False
        self.progress = 1.0
        self.btn_start.disabled = False
        self.btn_stop.disabled = True
        self.runner.q = None
        self._say(msg)

    def _say(self, msg: str) -> None:
        self.status = msg
        self.info.text = msg


class CS5PilotApp(App):
    title = "CS5 Pilot — 恒电流极化"

    def build(self):
        return Root()

    def on_stop(self):
        root = self.root
        if isinstance(root, Root):
            root._disconnect()


if __name__ == "__main__":
    CS5PilotApp().run()