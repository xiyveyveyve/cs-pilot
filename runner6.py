# -*- coding: utf-8 -*-
"""CS Studio6 · 直开窗口模式的运行器（不依赖序列）。

流程：开路电位 → （可选）交流阻抗 → 动电位/阶梯波

与 `runner.py`（序列模式）的区别：
  * 不读也不改序列，用主工具栏按钮直接弹参数窗，点「确定」即开跑；
  * 每个实验独立开窗、独立填参、独立开跑，脚本自己做接续；
  * 因此不需要用户预先在软件里摆序列，也不需要应付「添加」对话框那个
    会随使用历史漂移的自绘下拉。

数据源用软件自己写的 .txt/.cor（6 版运行期间不锁文件，可以随时 tail）。
"""
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

import driver as D6
import driver_direct as DD
import stabilizer as ST
import studio_ui as S
import watch as W


# ---------------- 状态 ----------------
S_IDLE = "待机"
S_CONNECT = "连接 CS Studio6"
S_PREPARE = "准备（清场）"
S_OCP_OPEN = "打开开路电位参数窗"
S_OCP_FILL = "填写开路电位参数"
S_OCP_START = "启动开路电位"
S_MON_OCP = "监视开路电位"
S_STOP_OCP = "停止开路电位"
S_EIS_OPEN = "打开阻抗参数窗"
S_EIS_FILL = "填写阻抗参数"
S_EIS_START = "启动交流阻抗"
S_MON_EIS = "监视交流阻抗"
S_STOP_EIS = "结束交流阻抗"
S_STEP_OPEN = "打开阶梯波参数窗"
S_STEP_FILL = "填写阶梯波参数"
S_STEP_START = "启动阶梯波"
S_MON_STEP = "监视阶梯波"
S_T_OPEN = "打开测试项参数窗"
S_T_FILL = "填写测试项参数"
S_T_START = "启动测试项"
S_MON_TEST = "监视测试项"
S_DONE = "完成"
S_ERROR = "出错"
S_ABORT = "已中止"


@dataclass
class RunConfig6:
    sample: str = "样品"
    area_cm2: float = 1.0
    item: str = "Tafel"                 # Tafel | Step
    out_dir: str = r"C:\Users\xiyve\Desktop\CS-Pilot数据"

    ocp_time_sec: float = 1800.0        # 测量时间统一 1800 秒
    ocp_freq_hz: float = 10.0           # 采样频率 10 Hz
    use_delta_stop: bool = False        # 不勾「基于Δ电位停止」
    max_ocp_sec: float = 1800.0
    ocp_max_rounds: int = 3   # 开路电位最多测几轮（一轮 = ocp_time_sec 秒），没判稳就再来一轮

    stab: ST.StabConfig = field(default_factory=ST.StabConfig)

    eis_enabled: bool = True
    eis_dc_v: float = 0.0
    eis_amp_mv: float = 10.0
    eis_init_freq: float = 100000.0
    eis_final_freq: float = 0.01
    eis_pts_per_decade: float = 10.0

    tafel_init_v: float = -0.5
    tafel_final_v: float = 1.5
    tafel_scan_mv_s: float = 0.33
    tafel_interval_s: float = 0.5

    step_init_v: float = -0.2
    step_final_v: float = 0.5
    step_delta_v: float = 0.05
    step_hold_s: float = 2.0        # 每步持续 2 s
    step_cycles: int = 20           # 循环 20 个周期
    step_use_steps: bool = False    # 中间电位都不选

    density: float = 7.93
    temperature: float = 25.0

    test_stop_i_density: Optional[float] = 1e-3   # 动电位：电流密度到 1e-3 A/cm² 停
    test_timeout_sec: float = 7200.0
    eis_timeout_sec: float = 2400.0


def build_filenames6(cfg: RunConfig6) -> dict:
    day = datetime.now().strftime("%Y-%m-%d")

    def pick(tag: str) -> str:
        base = os.path.join(cfg.out_dir, "%s-%s-%s" % (day, cfg.sample, tag))
        p, i = base, 2
        while (os.path.exists(p + ".txt") or os.path.exists(p + ".cor")
               or os.path.exists(p + ".z60")):
            p = "%s_%d" % (base, i)
            i += 1
        return p

    out = {"ocp": pick("开路电位")}
    if cfg.eis_enabled:
        out["eis"] = pick("交流阻抗")
    out["test"] = pick("动电位" if cfg.item == "Tafel" else "阶梯波")
    return out


class Runner6:
    """tick 驱动的状态机。GUI 里用 after() 调 tick()，命令行里 while 循环调。"""

    def __init__(self, cfg: RunConfig6, log: Callable[[str], None] = print,
                 on_state: Optional[Callable[[str, str], None]] = None,
                 on_sample: Optional[Callable[[float, float, object], None]] = None):
        self.cfg = cfg
        self.log = log
        self.on_state = on_state
        self.on_sample = on_sample

        self.state = S_IDLE
        self.detail = ""
        self.error = ""
        self.running = False

        self.t0 = 0.0
        self.stage_t0 = 0.0
        self.files = {}
        self.ocp_ok_volt = None
        self.stab = ST.OcpStabilizer(cfg.stab)
        self.stab_point = None
        self._ocp_round = 0
        self._ocp_retry = False

        self.tail_ocp: Optional[W.CorFileTail] = None
        self.tail_test: Optional[W.CorFileTail] = None
        self.tail_eis: Optional[W.CorFileTail] = None
        self.test_first_data_at = None
        self._test_stall = 0
        self._eis_stall = 0
        self._last_eis_size = -1
        self.last_samples: List[W.Sample] = []

        self.ui = None
        self.drv = None
        self.dd = None
        self._ch_tried_at = None

    # ---------- 基础 ----------
    def elapsed(self) -> float:
        return time.time() - self.t0 if self.t0 else 0.0

    def stage_elapsed(self) -> float:
        return time.time() - self.stage_t0 if self.stage_t0 else 0.0

    def set_state(self, s: str, detail: str = ""):
        self.state = s
        self.detail = detail
        msg = "[%s] %s%s" % (self._hms(), s, (" " + detail) if detail else "")
        try:
            self.log(msg)
            if self.on_state:
                self.on_state(s, detail)
        except Exception:
            pass

    def _hms(self) -> str:
        e = int(self.elapsed())
        return "%02d:%02d:%02d" % (e // 3600, (e % 3600) // 60, e % 60)

    def start(self):
        try:
            os.makedirs(self.cfg.out_dir, exist_ok=True)
        except Exception:
            pass
        cfg = self.cfg
        self.files = build_filenames6(cfg)
        self.log("样品：%s / 面积 %g cm² / 测试项目 %s" % (cfg.sample, cfg.area_cm2, cfg.item))
        for k, v in self.files.items():
            self.log("  输出[%s] → %s" % (k, v))
        self.t0 = time.time()
        self.running = True
        self.set_state(S_CONNECT)
        self.stage_t0 = time.time()

    def abort(self):
        self.log("用户中止")
        try:
            if self.dd:
                self.dd.stop()
        except Exception:
            pass
        self.running = False
        self.set_state(S_ABORT)

    def _fail(self, msg: str):
        self.error = msg
        self.running = False
        self.set_state(S_ERROR, msg)

    # ---------- 单个 tick ----------
    def tick(self):
        if not self.running:
            return
        try:
            st = self.state
            fn = {
                S_CONNECT: self._do_connect,
                S_PREPARE: self._do_prepare,
                S_OCP_OPEN: self._do_ocp_open,
                S_OCP_FILL: self._do_ocp_fill,
                S_OCP_START: self._do_ocp_start,
                S_MON_OCP: self._do_mon_ocp,
                S_STOP_OCP: self._do_stop_ocp,
                S_EIS_OPEN: self._do_eis_open,
                S_EIS_FILL: self._do_eis_fill,
                S_EIS_START: self._do_eis_start,
                S_MON_EIS: self._do_mon_eis,
                S_STOP_EIS: self._do_stop_eis,
                S_T_OPEN: self._do_t_open,
                S_T_FILL: self._do_t_fill,
                S_T_START: self._do_t_start,
                S_STEP_OPEN: self._do_step_open,
                S_STEP_FILL: self._do_step_fill,
                S_STEP_START: self._do_step_start,
                S_MON_STEP: self._do_mon_step,
                S_MON_TEST: self._do_mon_test,
            }.get(st)
            if fn is None:
                return
            fn()
        except Exception as e:
            import traceback
            self.log("异常：%s" % e)
            self.log(traceback.format_exc()[-800:])
            self._fail("异常：%s" % e)

    # ---------- 各状态实现 ----------
    def _do_connect(self):
        """连接并建通道。不用时间阈值判断首 tick（GUI 250ms 节拍会跳过），改看对象状态。"""
        if self.dd is not None:
            self.set_state(S_PREPARE)
            self.stage_t0 = time.time()
            return
        if self.ui is None:
            self.ui = S.Studio(log=self.log)
        if self.ui.main is None and not self.ui.acquire(2.0):
            if self.stage_elapsed() >= 20:
                self._fail("找不到 CS Studio6 主窗")
            return
        if self._ch_tried_at is None or time.time() - self._ch_tried_at >= 2.0:
            self._ch_tried_at = time.time()
            self.log("已连接：%r（演示模式=%s）" % (self.ui.title, self.ui.is_demo))
            base = D6.ParasiteDriver(self.ui, self.log)
            if base.ensure_channel():
                self.log("通道：%r" % (base.channel_title,))
            else:
                # 6 版有时「工作通道」菜单整个消失（通道 MDI 窗被关掉后无法从 UI 重建），
                # 但主工具栏按钮仍是可用的——直开模式不依赖序列窗口，照跑。
                self.log("没有通道窗（工作通道菜单消失）→ 走直开模式，直接用主工具栏按钮")
            self.dd = DD.DirectDriver(self.ui, base, self.log)
            return

    def _do_prepare(self):
        self.dd.prepare()
        self.log("清场完成，开始开路电位")
        self.set_state(S_OCP_OPEN)
        self.stage_t0 = time.time()

    def _do_ocp_open(self):
        panel = self.dd.open("ocp")
        if panel is None:
            self._fail("打不开开路电位参数窗")
            return
        self._ocp_panel = panel
        self.set_state(S_OCP_FILL)
        self.stage_t0 = time.time()

    def _do_ocp_fill(self):
        cfg = self.cfg
        p = self._ocp_panel
        ui = self.ui
        ok = True
        ok &= bool(ui.set_edit("Control_FileName_Text", self.files["ocp"], p))
        ok &= bool(ui.set_edit("FrqControl_Frq_Text", "%g" % cfg.ocp_freq_hz, p))
        ok &= bool(ui.set_edit("Ocp_Param_Text", "%g" % cfg.ocp_time_sec, p))
        # 单位切到「秒」
        try:
            cb = ui.by_id("Ocp_Param_Combo", p)
            if cb is not None:
                cb.set_focus()
                from pywinauto import keyboard
                keyboard.send_keys("{HOME}")
                time.sleep(0.2)
        except Exception:
            pass
        # 不勾任何终止条件
        for cid in ("chkStopByE", "chkStopByDeltaE"):
            try:
                c = ui.by_id(cid, p)
                if c is not None and c.get_toggle_state() == 1:
                    c.click_input()
                    self.log("  取消勾选 %s" % cid)
            except Exception:
                pass
        self.log("开路电位参数：%g 秒 / %g Hz → %s" % (cfg.ocp_time_sec, cfg.ocp_freq_hz, self.files["ocp"]))
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density, temperature=cfg.temperature)
        self.files["ocp_real"] = self.files["ocp"] + ".txt"
        self.tail_ocp = W.CorFileTail(self.files["ocp_real"])
        self.stab.reset()
        self.set_state(S_OCP_START)
        self.stage_t0 = time.time()

    def _do_ocp_start(self):
        if not self.dd.press_ok(self._ocp_panel):
            self._fail("开路电位没能启动")
            return
        self.log("开路电位已启动")
        self.set_state(S_MON_OCP)
        self.stage_t0 = time.time()

    def _do_mon_ocp(self):
        cfg = self.cfg
        self.tail_ocp.poll()
        series = self.tail_ocp.series_ev()
        if len(series) >= cfg.stab.min_points:
            st = self.stab.feed(series)
            try:
                if self.on_sample:
                    self.on_sample(st.t_now, st.mean_v, st)
            except Exception:
                pass
            if st.stable:
                self.stab_point = (st.t_now, st.mean_v)
                self.ocp_ok_volt = st.mean_v
                self.set_state(S_STOP_OCP, "判稳 E=%.6f V（%s）" % (st.mean_v, st.reason))
                self.stage_t0 = time.time()
                return
        if self.elapsed() >= cfg.max_ocp_sec:
            v = series[-1][1] if series else 0.0
            self.stab_point = (series[-1][0] if series else 0.0, v)
            self.ocp_ok_volt = v
            maxr = max(1, int(getattr(cfg, "ocp_max_rounds", 1) or 1))
            if self._ocp_round + 1 < maxr:
                self._ocp_round += 1
                self._ocp_retry = True
                self.set_state(S_STOP_OCP, "本轮 %g s 未判稳 → 准备第 %d 轮（共最多 %d 轮）"
                               % (cfg.max_ocp_sec, self._ocp_round + 1, maxr))
            else:
                self.set_state(S_STOP_OCP, "到达最长等待 %g s（已测 %d 轮）仍未判稳，按当前 E=%.6f V 继续"
                               % (cfg.max_ocp_sec, self._ocp_round + 1, v))
            self.stage_t0 = time.time()

    def _do_stop_ocp(self):
        if self.stage_elapsed() < 0.5:
            return
        self.dd.stop()
        self.log("开路电位已停止")
        if getattr(self, "_ocp_retry", False):
            self._ocp_retry = False
            base = re.sub(r"_第\d+轮$", "", self.files.get("ocp", ""))
            self.files["ocp"] = "%s_第%d轮" % (base, self._ocp_round + 1)
            self.stab.reset()
            self.log("→ 开始第 %d 轮开路电位：%s"
                     % (self._ocp_round + 1, os.path.basename(self.files["ocp"])))
            return self.set_state(S_OCP_OPEN)
        if self.cfg.eis_enabled:
            self.set_state(S_EIS_OPEN)
        else:
            self.set_state(S_T_OPEN)
        self.stage_t0 = time.time()

    # ---- 阻抗 ----
    def _do_eis_open(self):
        panel = self.dd.open("eis")
        if panel is None:
            self.log("打不开阻抗参数窗 → 跳过阻抗")
            self.set_state(S_T_OPEN)
            self.stage_t0 = time.time()
            return
        self._eis_panel = panel
        self.set_state(S_EIS_FILL)
        self.stage_t0 = time.time()

    def _do_eis_fill(self):
        cfg = self.cfg
        p, ui = self._eis_panel, self.ui
        ok = True
        ok &= bool(ui.set_edit("Control_FileName_Text", self.files["eis"], p))
        ok &= bool(ui.set_edit("EISVSfrq_SineAmp_Text", "%g" % cfg.eis_amp_mv, p))
        ok &= bool(ui.set_edit("EISVSfrq_SineBias_Text", "%g" % cfg.eis_dc_v, p))
        ok &= bool(ui.set_edit("EISVSfrq_InitFre_Text", "%g" % cfg.eis_init_freq, p))
        ok &= bool(ui.set_edit("EISVSfrq_FinalFre_Text", "%g" % cfg.eis_final_freq, p))
        ok &= bool(ui.set_edit("EISVSfrq_TenTwice_Text", "%g" % cfg.eis_pts_per_decade, p))
        self.log("阻抗参数：%g→%g Hz，%g mV，%g 点/十倍频（%s）" % (
            cfg.eis_init_freq, cfg.eis_final_freq, cfg.eis_amp_mv,
            cfg.eis_pts_per_decade, "OK" if ok else "部分失败"))
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density, temperature=cfg.temperature)
        # 阻抗文件后缀实测为 .txt（演示）/.z60（真机），两种都盯
        self.tail_eis = W.CorFileTail(self.files["eis"] + ".txt")
        self._eis_stall = 0
        self._last_eis_size = -1
        self.set_state(S_EIS_START)
        self.stage_t0 = time.time()

    def _do_eis_start(self):
        if not self.dd.press_ok(self._eis_panel):
            self.log("阻抗没能启动 → 跳过")
            self.set_state(S_T_OPEN)
            self.stage_t0 = time.time()
            return
        self.log("交流阻抗已启动")
        self.set_state(S_MON_EIS)
        self.stage_t0 = time.time()

    def _do_mon_eis(self):
        cfg = self.cfg
        self.tail_eis.poll()
        cur = self.tail_eis.size()
        if cur == self._last_eis_size:
            self._eis_stall += 1
        else:
            self._eis_stall = 0
            self._last_eis_size = cur
        # 10 s（0.4 s/步 ≈ 25 步）没长就认为扫完
        if self._eis_stall >= 25 and cur > 0:
            self.set_state(S_STOP_EIS, "文件 %d 字节 10 s 未增长 → 判定阻抗结束" % cur)
            self.stage_t0 = time.time()
            return
        if self.stage_elapsed() >= cfg.eis_timeout_sec:
            self.set_state(S_STOP_EIS, "阻抗超时 %g s" % cfg.eis_timeout_sec)
            self.stage_t0 = time.time()
            return
        if int(self.stage_elapsed()) % 10 == 0 and self._eis_stall in (0,):
            self.log("  阻抗中：%d 字节" % cur)

    def _do_stop_eis(self):
        if self.stage_elapsed() < 0.3:
            return
        if self.dd.is_running():
            self.dd.stop()
        self.log("阻抗阶段结束")
        self.set_state(self._next_test_state())
        self.stage_t0 = time.time()

    # ---- 测试项 ----
    # ---------- 阶梯波（6 版走「测试方法→暂态极化→任意恒电位阶梯波」） ----------
    def _do_step_open(self):
        panel = self.dd.open("step")
        if panel is None:
            self._fail("打不开阶梯波参数窗（测试方法(E)→暂态极化→任意恒电位阶梯波）")
            return
        self._t_panel = panel
        self.log("阶梯波参数窗已打开")
        self.set_state(S_STEP_FILL)
        self.stage_t0 = time.time()

    def _select_combo(self, panel, auto_id, want):
        """把下拉切到包含 want 的选项（6 版自绘下拉，尽力而为）。"""
        c = self.ui.by_id(auto_id, panel)
        if c is None:
            return False
        try:
            cur = c.legacy_properties().get("Value") or ""
            if want in str(cur):
                return True
        except Exception:
            pass
        try:
            c.set_focus()
            c.type_keys("{HOME}")
            for _ in range(10):
                v = ""
                try:
                    v = str(c.legacy_properties().get("Value") or "")
                except Exception:
                    pass
                if want in v:
                    return True
                c.type_keys("{DOWN}")
                time.sleep(0.12)
        except Exception:
            return False
        return False

    def _do_step_fill(self):
        cfg = self.cfg
        p, ui = self._t_panel, self.ui
        ok = bool(ui.set_edit("Control_FileName_Text", self.files["test"], p))

        try:
            self._select_combo(p, "PotSquare_TimeUnit_cbo", "s")
            self._select_combo(p, "Vs_Combo", "开路")
        except Exception as e:
            self.log("  下拉选择异常（可忽略）：%s" % e)

        for aid, val in (
            ("PotSquare_InitialE_txt", "%.4f" % cfg.step_init_v),
            ("PotSquare_InitTime_txt", "%g" % cfg.step_hold_s),
            ("PotSquare_FinalE_txt", "%.4f" % cfg.step_final_v),
            ("PotSquare_FinalTime_txt", "%g" % cfg.step_hold_s),
        ):
            if ui.by_id(aid, p) is None:
                self.log("  [警告] 未找到控件 %s（6 版阶梯波控件表可能不同）" % aid)
                continue
            ok &= bool(ui.set_edit(aid, val, p))

        # 中间电位：use_steps=False（默认）时全部不勾选
        for i in range(1, 11):
            chb = ui.by_id("PotSquare_Step%d_chb" % i, p)
            if chb is None:
                continue
            try:
                if chb.get_toggle_state() == 1:
                    chb.click_input()
                    time.sleep(0.15)
            except Exception:
                pass

        # 循环圈数（2026-11-05 实测 6 版参数窗确证：aid=PotSquare_Cycles_txt，
        # 窗口标题「任意恒电位阶梯波(多电位阶跃)」，96 控件 86 个带 aid，
        # 5 版表全部命中——见 _probe/step6_combo/dump_pot_square.json）
        for aid in ("PotSquare_Cycles_txt",
                    "PotSquare_CycleNum_txt", "PotSquare_Cycle_txt", "txtCycle"):
            if ui.by_id(aid, p) is not None:
                ui.set_edit(aid, "%d" % cfg.step_cycles, p)
                self.log("  循环圈数写入 %s = %d" % (aid, cfg.step_cycles))
                break
        else:
            self.log("  [警告] 未找到循环圈数控件，保持软件默认")

        self.log("阶梯波参数：%g → %g V，中间不选，每步 %g s，循环 %d 圈（写入 %s）"
                 % (cfg.step_init_v, cfg.step_final_v, cfg.step_hold_s,
                    cfg.step_cycles, "成功" if ok else "部分失败"))
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density,
                         temperature=cfg.temperature)
        self.tail_test = W.CorFileTail(self.files["test"] + ".txt")
        self.test_first_data_at = None
        self._test_stall = 0
        self.set_state(S_STEP_START)
        self.stage_t0 = time.time()

    def _do_step_start(self):
        if not self.dd.press_ok(self._t_panel):
            self._fail("阶梯波没能启动")
            return
        self.log("阶梯波已启动")
        self.set_state(S_MON_STEP)
        self.stage_t0 = time.time()

    def _do_mon_step(self):
        cfg = self.cfg
        self.tail_test.poll()
        samples = self.tail_test.samples if hasattr(self.tail_test, "samples") else []
        if samples and self.test_first_data_at is None:
            self.test_first_data_at = time.time()
            self.log("阶梯波收到第一个数据点 t=%.2f s" % samples[-1].t)

        if self.test_first_data_at and (time.time() - self.test_first_data_at) > 15:
            if self.tail_test.finished_quiet(10.0):
                self.log("阶梯波文件已 %d 字节、%d 点，10 s 未再增长 → 判定结束"
                         % (self.tail_test.size(), len(samples)))
                self._finish()
                return
        if self.stage_elapsed() >= cfg.test_timeout_sec:
            self.log("阶梯波超时 %g s，强制结束" % cfg.test_timeout_sec)
            self._finish()

    def _next_test_state(self) -> str:
        """OCP/阻抗结束后下一个该进的测试项状态（按项目类型分流）。"""
        return S_STEP_OPEN if self.cfg.item == "Step" else S_T_OPEN

    def _do_t_open(self):
        panel = self.dd.open("tafel")
        if panel is None:
            self._fail("打不开动电位参数窗")
            return
        self._t_panel = panel
        self.set_state(S_T_FILL)
        self.stage_t0 = time.time()

    def _do_t_fill(self):
        cfg = self.cfg
        p, ui = self._t_panel, self.ui
        ui.set_edit("Control_FileName_Text", self.files["test"], p)
        ui.set_edit("PotDynamic_InitialPot_txt", "%g" % cfg.tafel_init_v, p)
        ui.set_edit("PotDynamic_FinalPot_txt", "%g" % cfg.tafel_final_v, p)
        ui.set_edit("PotDynamic_ScanRate_txt", "%g" % cfg.tafel_scan_mv_s, p)
        ui.set_edit("SampleInterval_txt", "%g" % cfg.tafel_interval_s, p)
        self.log("动电位参数：%g → %g V @ %g mV/s" % (
            cfg.tafel_init_v, cfg.tafel_final_v, cfg.tafel_scan_mv_s))
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density, temperature=cfg.temperature)
        self.tail_test = W.CorFileTail(self.files["test"] + ".txt")
        self.test_first_data_at = None
        self._test_stall = 0
        self.set_state(S_T_START)
        self.stage_t0 = time.time()

    def _do_t_start(self):
        if not self.dd.press_ok(self._t_panel):
            self._fail("动电位没能启动")
            return
        self.log("动电位已启动")
        self.set_state(S_MON_TEST)
        self.stage_t0 = time.time()

    def _do_mon_test(self):
        cfg = self.cfg
        cfg = self.cfg
        self.tail_test.poll()
        samples = self.tail_test.samples if hasattr(self.tail_test, "samples") else []
        if samples and self.test_first_data_at is None:
            self.test_first_data_at = time.time()
            self.log("收到第一个数据点 t=%.2f s" % samples[-1].t)
        self.last_samples = samples

        # 判停：电流密度到 1e-3 A/cm²（文件第 2 列就是 A/cm²）
        if samples and cfg.test_stop_i_density:
            i = abs(samples[-1].i)
            if i >= cfg.test_stop_i_density:
                self.dd.stop()
                self.log("电流密度 %.3e A/cm² 达到阈值 → 停止" % i)
                self._finish()
                return

        if self.test_first_data_at and (time.time() - self.test_first_data_at) > 15:
            if self.tail_test.finished_quiet(10.0):
                self.log("测试文件已 %d 字节、%d 点，10 s 未再增长 → 判定结束" % (
                    self.tail_test.size(), len(samples)))
                self._finish()
                return
        if self.stage_elapsed() >= cfg.test_timeout_sec:
            self.log("测试项超时 %g s，强制结束" % cfg.test_timeout_sec)
            self._finish()

    def _finish(self):
        try:
            if self.dd and self.dd.is_running():
                self.dd.stop()
        except Exception:
            pass
        self.running = False
        self.set_state(S_DONE, "测试完成")

    # ---------- 结果 ----------
    def result_files(self):
        out = []
        for k, v in self.files.items():
            if k.endswith("_real"):      # ocp_real 是 tail 用的真名，不是产物键
                continue
            for ext in (".txt", ".cor", ".z60"):
                p = v + ext
                if os.path.exists(p):
                    out.append((os.path.basename(p), os.path.getsize(p)))
        return out

    def summary(self) -> List[str]:
        """结束状态时列产物，接口与 runner.Runner.summary() 一致（GUI 依赖）。"""
        lines = ["样品：%s    面积：%s cm²    测试项目：%s"
                 % (self.cfg.sample, self.cfg.area_cm2, self.cfg.item)]
        if self.ocp_ok_volt is not None:
            lines.append("开路电位判稳：%.6f V" % self.ocp_ok_volt)
        files = self.result_files()
        if files:
            for name, size in files:
                lines.append("产物：%s（%d B）" % (name, size))
        else:
            lines.append("产物：(无)")
        if self.state == S_DONE:
            lines.append("状态：完成（总用时 %s）" % self._hms())
        elif self.state == S_ERROR:
            lines.append("状态：出错 - %s" % self.error)
        elif self.state == S_ABORT:
            lines.append("状态：已中止（总用时 %s）" % self._hms())
        return lines
