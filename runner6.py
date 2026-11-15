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
import sync_barrier
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
#: 停止批次屏障：停完先让位等别的实例也停，再统一进入下一阶段（用户 2026-11-09 规则）
S_SYNC_WAIT = "已停止待同步"

#: 需要独占全局 UI 锁的状态（交互段）；监视段只读，不持锁。
UI_STATES = {
    S_CONNECT, S_PREPARE, S_OCP_OPEN, S_OCP_FILL, S_OCP_START, S_STOP_OCP,
    S_EIS_OPEN, S_EIS_FILL, S_EIS_START, S_STOP_EIS,
    S_T_OPEN, S_T_FILL, S_T_START,
    S_STEP_OPEN, S_STEP_FILL, S_STEP_START,
}


@dataclass
class RunConfig6:
    sample: str = "样品"
    sn: str = ""                   # ★ 多实例并存：按序列号锁定本机 CS Studio 窗口
    cs_hwnd: int = 0               # ★ 更硬：fleet 按 pid 定位的实例句柄
    com: str = ""                  # ★ 真机串口（COMx）；空=网口/sim 模式
    baud: int = 115200
    area_cm2: float = 1.0
    item: str = "Tafel"                 # Tafel | Step
    out_dir: str = r"C:\Users\xiyve\Desktop\CS-Pilot数据"

    ocp_time_sec: float = 1800.0        # 测量时间统一 1800 秒
    ocp_freq_hz: float = 10.0           # 采样频率 10 Hz
    use_delta_stop: bool = False        # 不勾「基于Δ电位停止」
    max_ocp_sec: float = 1800.0
    ocp_max_rounds: int = 3   # 开路电位最多测几轮（一轮 = ocp_time_sec 秒）；0/负数 = 不限，直到判稳
    ocp_fixed: bool = False   # True=固定时长模式：跑满 max_ocp_sec，忽略判稳/停滞提前出口（正式实验）

    stab: ST.StabConfig = field(default_factory=ST.StabConfig)

    eis_enabled: bool = True
    tafel_enabled: bool = True   # False=只测开路(+阻抗)，不跑动电位（用户 2026-11-12 需求）
    eis_dc_v: float = 0.0
    eis_amp_mv: float = 10.0
    eis_init_freq: float = 100000.0
    eis_final_freq: float = 0.01
    eis_pts_per_decade: float = 10.0

    tafel_init_v: float = -0.5
    tafel_final_v: float = 1.5
    tafel_scan_mv_s: float = 0.33
    tafel_interval_s: float = 0.5
    tafel_vs_ocp: bool = True         # True=相对开路（真机口径，需 OCP 基准字段）；
                                      # False=相对参比（--abs，模拟链验证用，
                                      # 不依赖 Control_Ocp_Text——网口模拟实证
                                      # 该字段外部写不进/读不出且自动填充不触发）

    step_init_v: float = -0.2
    step_final_v: float = 0.5
    step_delta_v: float = 0.05
    step_hold_s: float = 2.0        # 每步持续 2 s
    step_cycles: int = 20           # 循环 20 个周期
    step_use_steps: bool = False    # 中间电位都不选

    density: float = 7.93
    temperature: float = 25.0

    # 「数据文件重复」提示框策略（A4，2026-11-06 定型）：overwrite|extend|cancel
    dup_policy: str = "overwrite"

    test_stop_i_density: Optional[float] = 1e-3   # 动电位：电流密度到 1e-3 A/cm² 停
    test_timeout_sec: float = 7200.0
    eis_timeout_sec: float = 2400.0


def build_filenames6(cfg: RunConfig6) -> dict:
    day = datetime.now().strftime("%Y-%m-%d")
    # 样品名清洗 Windows 非法字符（\/:*?"<>|），否则路径非法、查重恒 False
    # （2026-11-06 代码审查 P2，对齐 runner.build_filenames）
    safe = "".join(ch for ch in (cfg.sample or "样品") if ch not in r'\/:*?"<>|').strip() or "样品"

    def pick(tag: str) -> str:
        # 2026-11-11 用户指定：全用空格分隔（2026-11-11 6 号 开路电位）。
        # 早期是「样品-标签」连字符，软件手动开的文件是空格，统一成空格免混淆。
        base = os.path.join(cfg.out_dir, "%s %s %s" % (day, safe, tag))
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
        self.tail_eis_z: Optional[W.CorFileTail] = None
        self.test_first_data_at = None
        self._test_stall = 0
        self._i_hit = 0                  # 电流密度连续达标计数（防单点噪声尖峰）
        self._eis_quiet_t0 = None
        self._eis_last_size = -1
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
            try:
                import ui_lock
                if ui_lock.ui_held():
                    ui_lock.ui_release()
            except Exception:
                pass
            return
        # ★ 全局 UI 互斥：4 实例同桌面时输入注入是全局的，交互段必须串行；
        #   监视段（只读窗口文本）不持锁，4 台并行。
        try:
            import ui_lock
            if self.state in UI_STATES:
                if not ui_lock.ui_acquire(0.0):
                    if not getattr(self, "_lock_wait_logged", False):
                        self._lock_wait_logged = True
                        self.log("等待全局 UI 锁（其它实例正在操作界面）…")
                    return
                self._lock_wait_logged = False
                # ★ 拿到锁立刻把本实例弹到前台（同上：遮挡 → 点不准）
                if not getattr(self, "_ui_act_done", False):
                    self._ui_act_done = True
                    try:
                        self.ui.activate()
                    except Exception:
                        pass
            elif ui_lock.ui_held():
                ui_lock.ui_release()
                self._ui_act_done = False
        except Exception:
            pass
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
                S_SYNC_WAIT: self._do_sync_wait,
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
            # 出异常也必须收尾：否则脚本退了、实验还在采集没人管
            # （2026-11-06 代码审查 P2，对齐 runner5 的异常收尾）。
            try:
                if self.dd is not None:
                    self.dd.stop()
            except Exception:
                pass
            self._fail("异常：%s" % e)

    # ---------- 各状态实现 ----------
    def _do_connect(self):
        """连接并建通道。不用时间阈值判断首 tick（GUI 250ms 节拍会跳过），改看对象状态。"""
        if self.dd is not None:
            self.set_state(S_PREPARE)
            self.stage_t0 = time.time()
            return
        if self.ui is None:
            self.ui = S.Studio(log=self.log, sn=self.cfg.sn,
                               hwnd=getattr(self.cfg, "cs_hwnd", 0))
        if self.ui.main is None and not self.ui.acquire(
                75.0 if getattr(self.cfg, "sn", "") else 2.0,
                sn=getattr(self.cfg, "sn", "")):
            if self.stage_elapsed() >= 20:
                self._fail("找不到 CS Studio6 主窗")
            return
        if self.dd is None:
            # ★ 真机串口：通讯设置→USB→手动→选口（幂等：已连直接过）
            com = getattr(self.cfg, "com", "")
            if com and ("in %s" % com) not in self.ui.title:
                if not self.ui.connect_com(com, getattr(self.cfg, "baud", 115200)):
                    self._fail("串口连接 %s 失败" % com)
                    return
                t = self.ui.title
                if getattr(self.cfg, "sn", "") and self.cfg.sn not in t:
                    self._fail("串口 %s 连的不是 %s（标题：%s）"
                               % (com, self.cfg.sn, t[:50]))
                    return
                self.log("真机串口就绪：%s" % t[:60])
            # 连接只试一次：ensure_channel 失败也照走直开模式（dd 一旦赋值
            # 本分支就不再进——旧的 2s 节流分支实际不可达，2026-11-07 审查 P3）
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
        # 单位切到「秒」——必须回读校验：切挡失败时 1800 会被按错误单位解释
        # （秒级自停、判稳空转 3 轮×1800s），与阶梯波 TimeUnit 的口径一致
        # （2026-11-07 审查 P2）
        try:
            if not self._select_combo(p, "Ocp_Param_Combo", "秒"):
                self._fail("开路电位时间单位切「秒」失败（回读不符），拒绝开跑")
                return
        except Exception as e:
            self._fail("开路电位时间单位切换异常：%s" % e)
            return
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
        if not ok:
            # 填参失败还点确定，实验会带软件默认参数开跑（审查 P2-11）
            self._fail("开路电位参数填写失败（回读不一致），拒绝开跑")
            return
        self.files["ocp_real"] = self.files["ocp"] + ".txt"
        self.tail_ocp = W.CorFileTail(self.files["ocp_real"])
        self.stab.reset()
        self.set_state(S_OCP_START)
        self.stage_t0 = time.time()

    def _do_ocp_start(self):
        cfg = self.cfg
        if not self.dd.press_ok(self._ocp_panel, dup_policy=cfg.dup_policy):
            self._fail("开路电位没能启动")
            return
        self.log("开路电位已启动")
        self.set_state(S_MON_OCP)
        self.stage_t0 = time.time()

    def _do_mon_ocp(self):
        cfg = self.cfg
        self.tail_ocp.poll()
        self._warn_tail_health(self.tail_ocp, "开路电位")
        series = self.tail_ocp.series_ev()
        if len(series) >= cfg.stab.min_points:
            st = self.stab.feed(series)
            try:
                if self.on_sample:
                    self.on_sample(st.t_now, st.mean_v, st)
            except Exception:
                pass
            if st.stable and not cfg.ocp_fixed:
                self.stab_point = (st.t_now, st.mean_v)
                self.ocp_ok_volt = st.mean_v
                self.set_state(S_STOP_OCP, "判稳 E=%.6f V（%s）" % (st.mean_v, st.reason))
                self.stage_t0 = time.time()
                return
        # ★ 数据停滞 = 软件实验已按「开路电位时间」自行结束（2026-11-09 补，
        #   对齐 runner5 的同款逻辑）。没有这条时 max_ocp≈ocp_time 的「快测」
        #   配置会在软件刚结束的一瞬间抢点停止 → 弹出「测试还没有完成，是否
        #   立即停止?」模态框 → 第 2/3 轮打开参数窗被模态框打断（JK-O 实证）。
        if series:
            last_t = series[-1][0]
            if (getattr(self, "_ocp_last_t", None) is not None
                    and abs(last_t - self._ocp_last_t) < 1e-9):
                self._ocp_stall = getattr(self, "_ocp_stall", 0) + 1
            else:
                self._ocp_stall = 0
            self._ocp_last_t = last_t
            if self._ocp_stall >= 30 and not cfg.ocp_fixed:   # 约 7.5 s（0.25 s/tick）没有新点
                if not self._menu_idle():
                    # 数据停滞但菜单仍禁用 → 实验可能还在跑，不能判"自行结束"
                    # （11-14 真机：误判后硬开下一轮 → COMError 崩溃）
                    if self._ocp_stall == 30:
                        self.log("开路电位数据停滞 7.5 s 但「测试方法」菜单仍禁用 → 不判自行结束，继续监视")
                else:
                    v = series[-1][1]
                    self.stab_point = (last_t, v)
                    self.ocp_ok_volt = v
                    self.log("开路电位数据 7.5 s 未更新（t=%.1fs）→ 判定实验已自行结束"
                             % last_t)
                    # 用户 2026-11-11：软件里那 1800 s 只是「一轮」的时间上限，
                    # 跑满还没判稳就再来一轮，脚本侧不设总时长上限。
                    if self._ocp_can_retry():
                        self._ocp_round += 1
                        self._ocp_retry = True
                        self.set_state(S_STOP_OCP,
                                       "第 %d 轮跑满 %g s 未判稳 → 再来一轮（%s）"
                                       % (self._ocp_round, cfg.ocp_time_sec,
                                          self._ocp_rounds_desc()))
                    else:
                        self.set_state(S_STOP_OCP, "实验自行结束（数据停滞）")
                    self.stage_t0 = time.time()
                    return
        if self.stage_elapsed() >= cfg.max_ocp_sec:
            # 注意必须用 stage_elapsed（本轮时钟）：elapsed 是总时钟，
            # 第 2 轮进监视时它早已超过 max_ocp_sec，重试轮会刚启动就被停
            # （2026-11-06 代码审查发现的真 bug）。
            if not series:
                # 全程无数据不许拿 0 V 当开路基准（审查 #26）。_fail 不做界面
                # 收尾 → 借 S_STOP_OCP 先停止确认，收尾后再报错。
                self._ocp_no_data = True
                self.set_state(S_STOP_OCP, "OCP 无数据 → 停止并报错")
                self.stage_t0 = time.time()
                return
            v = series[-1][1]
            self.stab_point = (series[-1][0], v)
            self.ocp_ok_volt = v
            maxr = self._ocp_max_rounds()
            if self._ocp_can_retry():
                self._ocp_round += 1
                self._ocp_retry = True
                self.set_state(S_STOP_OCP, "本轮 %g s 未判稳 → 准备第 %d 轮（%s）"
                               % (cfg.max_ocp_sec, self._ocp_round + 1,
                                  self._ocp_rounds_desc()))
            else:
                self.set_state(S_STOP_OCP, "到达最长等待 %g s（已测 %d 轮）仍未判稳，按当前 E=%.6f V 继续"
                               % (cfg.max_ocp_sec, self._ocp_round + 1, v))
            self.stage_t0 = time.time()

    def _ocp_max_rounds(self) -> int:
        try:
            return int(getattr(self.cfg, "ocp_max_rounds", 0) or 0)
        except Exception:
            return 0

    def _ocp_can_retry(self) -> bool:
        """还能再来一轮 OCP 吗？0/负数 = 不限轮数，一直测到判稳为止
        （用户 2026-11-11：「时间不设上限，30 分钟没稳就再来一遍」）。
        固定时长模式（ocp_fixed）例外：用户要的就是单轮跑满，不重试（审查 #18）。"""
        if getattr(self.cfg, "ocp_fixed", False):
            return False
        maxr = self._ocp_max_rounds()
        return maxr <= 0 or (self._ocp_round + 1 < maxr)

    def _ocp_rounds_desc(self) -> str:
        maxr = self._ocp_max_rounds()
        return "不限轮数，直到判稳" if maxr <= 0 else "共最多 %d 轮" % maxr

    @staticmethod
    def _file_growing(path: str, window: float = 3.0) -> bool:
        """数据文件 window 秒内还在变大 = 实验仍在采样。"""
        if not path:
            return False
        try:
            s1 = os.path.getsize(path)
        except Exception:
            return False
        time.sleep(window)
        try:
            return os.path.getsize(path) > s1
        except Exception:
            return False

    def _data_paths(self):
        """当前各阶段可能落盘的数据文件（带扩展名，只收真实存在的）。

        files 存无扩展名基名：OCP/动电位产 .txt、阻抗产 .z60（个别 .cor）。
        旧代码基名不存在就一律补 .txt → 阻抗的 .z60 永远监视不到，
        「文件还在长」判据对阻抗全盲（2026-11-14 审查 #11）。
        """
        paths = []
        for k in ("ocp_real", "test", "eis"):
            v = self.files.get(k)
            if not v:
                continue
            if os.path.exists(v):
                paths.append(v)
                continue
            for ext in (".txt", ".cor", ".z60"):
                p = v + ext
                if os.path.exists(p):
                    paths.append(p)
        return paths

    def _settle_after_stop(self, label: str, idle: float = 8.0):
        """停止后把软件等回空闲，再允许开下一项。

        返回 False = 软件未回空闲（菜单栏禁用），调用方必须停止自动接续
        （11-14 红线：带着没恢复的软件硬开下一项 → COMError 崩溃）。

        6 版实测（2026-11-09 四机 19:01，JK-O 连着两次点 Tafel 都没有参数窗）：
        stop() 返回只代表「停止键点掉了」，软件内部还要落盘/复位会话；
        不等它就开下一个实验会撞「测试还没有完成，是否立即停止?」，
        应答后参数窗仍可能出不来——最后被误判成「无设备/未连接」。
        """
        try:
            self.dd.stop()
        except Exception as e:
            self.log("点停止出错：%s" % e)
        # ⓪ 当前阶段的数据文件：文件还在长 = 实验真的还在跑。
        #    比 is_running() 硬——2026-11-09 四机实测 JK-O 停止键点了，
        #    运行窗也关了，可软件内部 OCP 仍在跑，后面开 Tafel 被
        #    「测试还没有完成」挡死。文件增长是唯一骗不了人的判据。
        paths = self._data_paths()
        # ① 等实验真正停：连续 2 轮数据文件不增长才算停；
        #    20s 还在长 = 数据栏「停止」无效 → force_stop（关运行窗→应答
        #    「是」，v8 实测唯一有效的停止通道），不带着没停的实验进下一阶段
        t0 = time.time()
        quiet = 0
        forced = False
        while time.time() - t0 < 60.0:
            growing = any(self._file_growing(p, window=2.0) for p in paths)
            if not growing:
                quiet += 1
                if quiet >= 2:
                    break
                time.sleep(0.5)
                continue
            quiet = 0
            if not forced and time.time() - t0 > 20.0:
                self.log("  %s 停止键无效 → 强制停止（关运行窗→应答『是』）" % label)
                try:
                    self.dd.force_stop(timeout=30.0)
                except Exception as e:
                    self.log("  强制停止出错：%s" % e)
                forced = True
                continue
            self.log("  %s 数据文件仍在增长 → 实验还在跑，再点一次停止" % label)
            try:
                self.dd.stop(tries=1)
            except Exception:
                pass
            time.sleep(0.5)
        else:
            # 关窗≠实验停（红线）：60s 还在写 = 停止未生效，绝不带病进下一项
            self.log("✗ %s：60s 数据文件仍在增长，停止未生效 → 停止自动接续（交人工）" % label)
            return False
        # ② 关运行窗（内部先点窗内停止；停不下来会保留窗口）
        try:
            n = self.dd.close_run_windows()
            if n:
                self.log("关闭 %d 个运行窗" % n)
        except Exception as e:
            self.log("关运行窗出错：%s" % e)
        # ③ 清掉「测试还没有完成」这类模态框
        try:
            if self.ui is not None:
                self.ui.clear_modals(limit=4)
        except Exception:
            pass
        # ④ 冷却：等软件落盘/复位
        if idle > 0:
            self.log("等待 %g s 让软件彻底回到空闲…" % idle)
            time.sleep(idle)
        # ⑤ 等「测试方法(E)」菜单恢复可用——4 机并存时 6 版停止后会慢半拍
        #    重建菜单栏（19:14 实测「菜单栏里没有测试方法(E)」），此时去开下一项
        #    必被「测试还没有完成」挡回，最后还会被误判成无设备。
        if not self._wait_idle_menu(timeout=60.0):
            self.log("✗ %s：60s 内菜单栏没恢复可用 → 软件未回空闲，停止自动接续（交人工）"
                     % label)
            return False
        # ⑥ CS6 在停止弹窗应答「是」后会自动拉起 CSAnalysis（v9 21:10:18 实证，
        #    父进程=CS6 自身、命令行带数据路径）——不需要它，直接关
        try:
            self.dd.close_analysis()
        except Exception:
            pass
        return True

    def _menu_idle(self) -> bool:
        """「测试方法」菜单存在且可用 = 软件空闲。判不了（无 ui/找不到菜单/
        读取出错）时返回 True 保持原行为；只有明确禁用才返回 False。"""
        try:
            if self.ui is None:
                return True
            for m in self.ui.main.descendants(control_type="MenuItem"):
                if "测试方法" in (m.window_text() or ""):
                    return bool(m.is_enabled())
        except Exception:
            return True
        return True

    def _wait_idle_menu(self, timeout: float = 60.0) -> bool:
        """等软件回到可操作的空闲态：菜单栏「测试方法」项存在且可用。"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.ui is not None:
                    self.ui.clear_modals(limit=2)
            except Exception:
                pass
            try:
                for m in self.ui.main.descendants(control_type="MenuItem"):
                    if "测试方法" in (m.window_text() or ""):
                        if m.is_enabled():
                            return True
            except Exception:
                pass
            time.sleep(1.5)
        return False

    def _warn_tail_health(self, tail, label):
        n = getattr(tail, "read_errors", 0) + getattr(tail, "bad_lines", 0)
        if n and n != getattr(self, "_tail_warn_n", 0):
            self._tail_warn_n = n
            self.log("⚠ %s 数据文件读取异常累计 %d 次（读失败 %d / 坏行 %d）→ 数据可能不完整，检查磁盘占用"
                     % (label, n, getattr(tail, "read_errors", 0),
                        getattr(tail, "bad_lines", 0)))

    def _do_stop_ocp(self):
        if self.stage_elapsed() < 0.5:
            return
        if not self._settle_after_stop("开路电位", idle=8.0):
            self._fail("开路电位收尾后软件未回空闲（菜单栏禁用），停止自动接续")
            return
        self.log("开路电位已停止")
        if getattr(self, "_ocp_no_data", False):
            self._fail("OCP 全程无数据（文件为空或路径不对），拒绝以 0 V 基准继续")
            return
        if getattr(self, "_ocp_retry", False):
            self._ocp_retry = False
            base = re.sub(r"_第\d+轮$", "", self.files.get("ocp", ""))
            cand = "%s_第%d轮" % (base, self._ocp_round + 1)
            # 重试轮名字也要查重：撞上历史文件会触发覆盖框并盖掉旧数据（审查 P2-14）
            k = 2
            while (os.path.exists(cand + ".txt") or os.path.exists(cand + ".cor")
                   or os.path.exists(cand + ".z60")):
                cand = "%s_第%d轮_%d" % (base, self._ocp_round + 1, k)
                k += 1
            self.files["ocp"] = cand
            self.stab.reset()
            self._ocp_stall = 0
            self._ocp_last_t = None
            self.log("→ 开始第 %d 轮开路电位：%s"
                     % (self._ocp_round + 1, os.path.basename(self.files["ocp"])))
            return self.set_state(S_OCP_OPEN)
        if self.cfg.eis_enabled:
            self._enter_after_stop(S_EIS_OPEN)
        elif self.cfg.tafel_enabled:
            self._enter_after_stop(self._next_test_state())
        else:
            self._done_no_test()
        self.stage_t0 = time.time()

    # ---- 停止批次屏障（用户 2026-11-09 规则） ----
    def _enter_after_stop(self, target: str):
        """停止收尾完成后：有别的实例正在停 → 让位等它，再切回自己进 target。"""
        try:
            peers = sync_barrier.stopping_peers(getattr(self.cfg, "sample", ""))
        except Exception:
            peers = {}
        if peers:
            self._sync_target = target
            self._sync_t0 = time.time()
            self.log("停止已收尾；让位等其它实例停止：%s（先不进入下一阶段）"
                     % "、".join("%s=%s" % kv for kv in sorted(peers.items())))
            return self.set_state(S_SYNC_WAIT)
        self.set_state(target)

    def _do_sync_wait(self):
        if time.time() - getattr(self, "_sync_t0", time.time()) > sync_barrier.SYNC_TIMEOUT:
            self.log("⚠ 停止同步等待超时（%gs），继续下一阶段" % sync_barrier.SYNC_TIMEOUT)
            return self.set_state(self._sync_target)
        try:
            peers = sync_barrier.stopping_peers(getattr(self.cfg, "sample", ""))
        except Exception:
            peers = {}
        if peers:
            return                       # 让位：不持 UI 锁、不推进，等它们停完
        self.log("其它实例已停止，继续：%s" % self._sync_target)
        self.set_state(self._sync_target)

    # ---- 阻抗 ----
    def _do_eis_open(self):
        panel = self.dd.open("eis")
        if panel is None:
            self.log("打不开阻抗参数窗 → 跳过阻抗")
            self.set_state(self._next_test_state())
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
        if not ok:
            self._fail("阻抗参数填写失败（回读不一致）")
            return
        # 阻抗文件后缀实测为 .txt（演示）/.z60（真机），两种都盯
        self.tail_eis = W.CorFileTail(self.files["eis"] + ".txt")
        self.tail_eis_z = W.CorFileTail(self.files["eis"] + ".z60")
        self._eis_quiet_t0 = None      # 文件尺寸最后一次变化的时间
        self._eis_last_size = -1
        self.set_state(S_EIS_START)
        self.stage_t0 = time.time()

    def _do_eis_start(self):
        cfg = self.cfg
        if not self.dd.press_ok(self._eis_panel, dup_policy=cfg.dup_policy):
            self.log("阻抗没能启动 → 跳过")
            self.set_state(self._next_test_state())
            self.stage_t0 = time.time()
            return
        self.log("交流阻抗已启动")
        self.set_state(S_MON_EIS)
        self.stage_t0 = time.time()

    def _do_mon_eis(self):
        cfg = self.cfg
        self.tail_eis.poll()
        self.tail_eis_z.poll()
        # .txt（演示）与 .z60（真机）哪个在长看哪个
        cur = max(self.tail_eis.size(), self.tail_eis_z.size())
        now = time.time()
        if cur != self._eis_last_size:
            self._eis_last_size = cur
            self._eis_quiet_t0 = now
        if self._eis_quiet_t0 is None:
            self._eis_quiet_t0 = now
        # 墙钟判稳：终频 0.01 Hz 时单点周期可达 100 s+，按 tick 计数
        # 会在低频段误判"结束"把扫描截断（2026-11-06 审查发现），改 120 s 静默
        if cur > 0 and now - self._eis_quiet_t0 >= 120.0:
            self.set_state(S_STOP_EIS, "文件 %d 字节 120 s 未增长 → 判定阻抗结束" % cur)
            self.stage_t0 = time.time()
            return
        if self.stage_elapsed() >= cfg.eis_timeout_sec:
            self.set_state(S_STOP_EIS, "阻抗超时 %g s" % cfg.eis_timeout_sec)
            self.stage_t0 = time.time()
            return
        # 进度日志按墙钟节流（%30 秒取模在同一秒内会命中 4 个 tick，连发重复）
        if now - getattr(self, "_eis_last_log", 0.0) >= 30.0:
            self._eis_last_log = now
            self.log("  阻抗中：%d 字节（静默 %.0f s）" % (cur, now - self._eis_quiet_t0))

    def _do_stop_eis(self):
        if self.stage_elapsed() < 0.3:
            return
        # is_running() 是启发式，有假阴性（工具栏/标题判据）；判「没跑」
        # 也可能文件还在写 → 无条件走 settle，由文件心跳裁决（审查 #15）
        if not self._settle_after_stop("交流阻抗", idle=6.0):
            self._fail("阻抗收尾后软件未回空闲（菜单栏禁用），停止自动接续")
            return
        self.log("阻抗阶段结束")
        if self.cfg.tafel_enabled:
            self._enter_after_stop(self._next_test_state())
        else:
            self._done_no_test()
        self.stage_t0 = time.time()

    def _done_no_test(self):
        """只测开路电位(+阻抗)时收尾：不进测试项，直接判定完成。"""
        self.log("按配置跳过测试项（只测开路电位%s）"
                 % ("+阻抗" if self.cfg.eis_enabled else ""))
        self.running = False
        self.set_state(S_DONE, "测试完成")

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

    def _navigate_combo(self, c, want: str, max_try: int = 10) -> bool:
        """委托给 studio_ui.navigate_combo（共用实现）。"""
        return S.navigate_combo(c, want, max_try)

    def _select_combo(self, panel, auto_id, want: str) -> bool:
        """把面板里 auto_id 下拉切到包含 want 的项。"""
        c = self.ui.by_id(auto_id, panel)
        if c is None:
            return False
        return self._navigate_combo(c, want)

    def _do_step_fill(self):
        cfg = self.cfg
        p, ui = self._t_panel, self.ui
        ok = bool(ui.set_edit("Control_FileName_Text", self.files["test"], p))

        try:
            if not self._select_combo(p, "PotSquare_TimeUnit_cbo", "s"):
                self._fail("阶梯波时间单位切到 s 失败（默认是 ms，不修正量纲全错）")
                return
            # 电位基准（相对开路 vs 相对参比）直接决定施加电位，选错整套参数作废
            # （审查 P2-15：不能再"可忽略"）
            if not self._select_combo(p, "Vs_Combo", "开路"):
                self._fail("阶梯波极化电位基准切「相对开路」失败")
                return
        except Exception as e:
            self._fail("阶梯波下拉选择异常：%s" % e)
            return

        for aid, val in (
            ("PotSquare_InitialE_txt", "%.4f" % cfg.step_init_v),
            ("PotSquare_InitTime_txt", "%g" % cfg.step_hold_s),
            ("PotSquare_FinalE_txt", "%.4f" % cfg.step_final_v),
            ("PotSquare_FinalTime_txt", "%g" % cfg.step_hold_s),
        ):
            if ui.by_id(aid, p) is None:
                # 控件缺失 = 该参数没写上，实验会带软件默认电位/时间开跑
                # ——与 _do_t_fill 的"回读不符拒绝开跑"口径一致
                # （2026-11-07 审查 P2，旧版只告警就放行）
                self._fail("阶梯波控件 %s 未找到（6 版控件表可能不同），拒绝开跑" % aid)
                return
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
        if not ok:
            self._fail("阶梯波参数填写失败（回读不一致），拒绝开跑")
            return
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density,
                         temperature=cfg.temperature)
        self.tail_test = W.CorFileTail(self.files["test"] + ".txt")
        self.test_first_data_at = None
        self._test_stall = 0
        self.set_state(S_STEP_START)
        self.stage_t0 = time.time()

    def _do_step_start(self):
        cfg = self.cfg
        if not self.dd.press_ok(self._t_panel, dup_policy=cfg.dup_policy):
            self._fail("阶梯波没能启动")
            return
        self.log("阶梯波已启动")
        self.set_state(S_MON_STEP)
        self.stage_t0 = time.time()

    def _do_mon_step(self):
        cfg = self.cfg
        self.tail_test.poll()
        self._warn_tail_health(self.tail_test, "阶梯波")
        samples = self.tail_test.samples  # C2.3：CorFileTail 恒有 samples（watch.py），hasattr 防御无意义
        if samples and self.test_first_data_at is None:
            self.test_first_data_at = time.time()
            self.log("阶梯波收到第一个数据点 t=%.2f s" % samples[-1].t)

        if self.test_first_data_at and (time.time() - self.test_first_data_at) > 15:
            # 静默判停必须叠加菜单恢复：文件安静≠实验结束（审查 #21）
            if self.tail_test.finished_quiet(10.0) and self._menu_idle():
                self.log("阶梯波文件已 %d 字节、%d 点，写入静默超时且菜单已恢复 → 判定结束"
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
        ok = True
        ok &= bool(ui.set_edit("Control_FileName_Text", self.files["test"], p))
        ok &= bool(ui.set_edit("PotDynamic_InitialPot_txt", "%g" % cfg.tafel_init_v, p))
        ok &= bool(ui.set_edit("PotDynamic_FinalPot_txt", "%g" % cfg.tafel_final_v, p))
        ok &= bool(ui.set_edit("PotDynamic_ScanRate_txt", "%g" % cfg.tafel_scan_mv_s, p))
        ok &= bool(ui.set_edit("SampleInterval_txt", "%g" % cfg.tafel_interval_s, p))
        # 电位基准：相对开路（2026-11-07 真机首跑发现：这个下拉从没被设置过，
        # 窗口默认停在「相对参比」→ JK-O 扫成了绝对电位，与 JK-F 的
        # vs-OCP 数据不可比）。必须回读校验，失败拒绝开跑。
        # 电位基准：相对开路。★ Tafel 窗口里有 4 个 Vs_Combo 实例（多个子
        # 面板），by_id 只设第一个不一定是扫描用的那个——全部都设
        # （2026-11-07 真机首跑：只设第一个 → JK-O 扫成绝对基准）
        try:
            # 只导航"可见且在窗口内"的 Vs_Combo：窗口里有 4 个实例（隐藏子
            # 面板里的也算），对不可见的盲发键盘会误触发别的控件
            # （2026-11-07 真机：键进了隐藏面板 → 弹「另存为」死循环）
            wr = p.rectangle()
            combos = []
            for c in self.ui.by_ids("Vs_Combo"):
                try:
                    r = c.rectangle()
                    if (r.width() > 10 and r.height() > 5
                            and r.left >= wr.left - 5 and r.right <= wr.right + 5
                            and r.top >= wr.top - 5 and r.bottom <= wr.bottom + 5):
                        combos.append(c)
                except Exception:
                    continue
            if not combos:
                self._fail("动电位窗口找不到可见的 Vs_Combo 电位基准下拉")
                return
            vs_ok = True
            vs_want = "开路" if cfg.tafel_vs_ocp else "参比"
            nav_cnt = 0
            for c in combos:
                # 只导航启用的下拉（禁用=未启用段，软件不用它的值；
                # 2026-11-08 实证：禁用下拉 set_focus/type_keys 直接失败）
                try:
                    if not c.is_enabled():
                        continue
                except Exception:
                    pass
                if self._navigate_combo(c, vs_want):
                    nav_cnt += 1
                else:
                    vs_ok = False
            if not vs_ok or nav_cnt == 0:
                self._fail("动电位电位基准切「相对%s」失败（回读不符），拒绝开跑"
                           % ("开路" if cfg.tafel_vs_ocp else "参比"))
                return
            if not cfg.tafel_vs_ocp:
                self.log("  电位基准=相对参比（--abs：不依赖 OCP 基准字段）")
            # ★「相对开路」的偏移量取自窗口的「开路电位(V)」字段
            # （Control_Ocp_Text）：前序 OCP 被打断/强杀时该字段是 0.00000，
            # 相对开路就退化成绝对电位（JK-O 真机首跑实测）。
            # 把判稳得到的 OCP 写进去，基准才正确且与 JK-F 口径一致。
            elif self.ocp_ok_volt is not None:
                # 先读后写（2026-11-08 网口模拟实证）：软件会在 OCP 轮完成后
                # 自动填充该字段（外部写入回读为空——疑似只读），值对就免写；
                # 值不对才写，写不进且自动值无效才拒跑（JK-O 退化教训保留）。
                cur = ""
                try:
                    cur = str(ui.by_id("Control_Ocp_Text", p)
                              .legacy_properties().get("Value") or "").strip()
                except Exception:
                    cur = ""
                try:
                    cur_v = float(cur)
                except ValueError:
                    cur_v = None
                if cur_v is not None and abs(cur_v - self.ocp_ok_volt) <= 0.01:
                    self.log("  开路电位(V) 已由软件自动填充 %.6f（与判稳值一致，免写）"
                             % cur_v)
                elif cur_v is not None and cur_v != 0.0:
                    # 2026-11-11 真机实证（JK-O/CS350M）：自动值是软件自己测的
                    # 当前 OCP（时点比 runner 判稳晚，电位仍在漂，差 0.025V 属
                    # 正常时点差）；字段只读写不进，软件执行实验用的就是这个
                    # 自动值——采信它并告警，不再因时点差拒跑。
                    self.log("  ⚠ 开路电位(V) 用软件自动值 %.6f（runner 判稳值 "
                             "%.6f，时点差属正常）" % (cur_v, self.ocp_ok_volt))
                    self.ocp_ok_volt = cur_v
                else:
                    w_ok = bool(ui.set_edit("Control_Ocp_Text",
                                            "%.6f" % self.ocp_ok_volt, p))
                    if w_ok:
                        self.log("  开路电位(V) ← %.6f（判稳值）" % self.ocp_ok_volt)
                    else:
                        self._fail("开路电位(V) 字段无法写入且自动值(%r)≠判稳值"
                                   "——相对开路基准会错，拒绝开跑" % cur)
                        return
            else:
                self._fail("没有判稳 OCP 值可填（相对开路基准会错），拒绝开跑")
                return
        except Exception as e:
            self._fail("动电位电位基准切换异常：%s" % e)
            return
        self.log("动电位参数：%g → %g V @ %g mV/s（写入 %s）" % (
            cfg.tafel_init_v, cfg.tafel_final_v, cfg.tafel_scan_mv_s,
            "成功" if ok else "部分失败"))
        if not ok:
            self._fail("动电位参数填写失败（回读不一致），拒绝开跑")
            return
        self.dd.set_cell(p, area_cm2=cfg.area_cm2, density=cfg.density, temperature=cfg.temperature)
        self.tail_test = W.CorFileTail(self.files["test"] + ".txt")
        self.test_first_data_at = None
        self._test_stall = 0
        self.set_state(S_T_START)
        self.stage_t0 = time.time()

    def _do_t_start(self):
        cfg = self.cfg
        if not self.dd.press_ok(self._t_panel, dup_policy=cfg.dup_policy):
            self._fail("动电位没能启动")
            return
        self.log("动电位已启动")
        self.set_state(S_MON_TEST)
        self.stage_t0 = time.time()

    def _do_mon_test(self):
        cfg = self.cfg
        self.tail_test.poll()
        self._warn_tail_health(self.tail_test, "动电位")
        samples = self.tail_test.samples  # C2.3：CorFileTail 恒有 samples（watch.py），hasattr 防御无意义
        if samples and self.test_first_data_at is None:
            self.test_first_data_at = time.time()
            self.log("收到第一个数据点 t=%.2f s" % samples[-1].t)
            # 首点基准校验：基准=相对开路时，首点 E ≈ init_v + OCP。
            # 偏差大 = 基准下拉实际没生效（JK-O 真机首跑教训），
            # 大声告警让操作者立刻知道数据口径不对。
            if self.ocp_ok_volt is not None and self.cfg.item == "Tafel":
                expect = self.cfg.tafel_init_v + self.ocp_ok_volt
                dev = abs(samples[-1].e - expect)
                if dev > 0.1:
                    self.log("⚠⚠ 首点 E=%+.4f 偏离预期 %+.4f（差 %+.3f V）——"
                             "电位基准可能不是「相对开路」，本组数据口径注意！"
                             % (samples[-1].e, expect, samples[-1].e - expect))
        self.last_samples = samples

        # 判停：电流密度到 1e-3 A/cm²（文件第 2 列就是 A/cm²）
        # 连续 2 个"新到的点"达标才停——单点尖峰不应截断整条曲线。
        # ★ 计数必须以新点为单位：数据约 3s 才 flush 一次而 tick 250ms 一次，
        #   按 tick 对同一个 samples[-1] 反复 +1 的话单点尖峰一次 flush 间隔
        #   就攒满 2（2026-11-07 审查 P1，与 runner.py 同修）
        if samples and cfg.test_stop_i_density:
            s_last = samples[-1]
            if getattr(s_last, "t", None) != getattr(self, "_i_last_t", None):
                self._i_last_t = s_last.t
                i = abs(s_last.i)
                if i >= cfg.test_stop_i_density:
                    self._i_hit += 1
                else:
                    self._i_hit = 0
                if self._i_hit >= 2:
                    self.log("电流密度 %.3e A/cm² 连续 %d 点达到阈值 → 停止"
                             % (i, self._i_hit))
                    self._finish()
                    return

        if self.test_first_data_at and (time.time() - self.test_first_data_at) > 15:
            # 静默判停必须叠加菜单恢复：文件安静≠实验结束（审查 #21）
            if self.tail_test.finished_quiet(10.0) and self._menu_idle():
                self.log("测试文件已 %d 字节、%d 点，写入静默超时且菜单已恢复 → 判定结束" % (
                    self.tail_test.size(), len(samples)))
                self._finish()
                return
        if self.stage_elapsed() >= cfg.test_timeout_sec:
            self.log("测试项超时 %g s，强制结束" % cfg.test_timeout_sec)
            self._finish()

    def _finish(self):
        # 监视状态（S_MON_TEST）不持 UI 锁，收尾要动界面——自己拿锁。
        # 收尾走 _settle_after_stop（点停止 → 文件增长确认 → 关窗 → 清模态框
        # → 冷却 → 等菜单恢复），否则下一项/下个样品会被「测试还没有完成」挡死。
        got = False
        try:
            import ui_lock
            got = ui_lock.ui_acquire(60.0)
        except Exception:
            got = False
        settled = False
        if not got:
            # 拿不到锁 = 别台正在注入界面，此时动手会互相打架（审查 #13）
            self.log("60 s 内拿不到 UI 锁 → 不做界面收尾，停止自动接续")
        else:
            try:
                if self.dd is not None:
                    settled = self._settle_after_stop("测试项", idle=6.0)
            except Exception as e:
                self.log("收尾出错：%s" % e)
                settled = False
            finally:
                try:
                    import ui_lock as _ul
                    _ul.ui_release()
                except Exception:
                    pass
        self.running = False
        if not settled:
            self._fail("测试项收尾未完成（软件未回空闲或拿不到 UI 锁），停止自动接续")
            return
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
