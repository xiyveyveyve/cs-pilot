# -*- coding: utf-8 -*-
"""runner5.py —— CS Studio5（5.6.1202.2）的寄生式流程状态机。

与 6 版 runner.py 的根本差异
---------------------------
6 版：在「工作通道」里摆好 OCP+测试项两行序列，点一次「开始」，OCP 结束后
      软件**自动接续**下一项；脚本只需在判稳时点一次「停止」。

5 版：**没有序列概念**，一次只能开一个实验。所以流程变成：
      OCP 参数窗 → 填参 → 确定 → 界面读数判稳 → 停止/关闭
      → 动电位参数窗 → 填参 → 确定 → 等跑完 → 完成
      「自动接续」由本脚本完成（这正是寄生式自动化的价值）。

数据来源：5 版运行期间 **独占锁住 .cor 文件**（PermissionError），所以不能用
watch.CorFileTail，改用 uiprobe.UiSampler 读运行窗口上的实时数值。

判稳判据（与 6 版一致，来自旧会话调研）：
    斜率 |mV/min| < 5.0（=0.0833 mV/s，行业标准）
    且 窗口峰峰 < 5.0 mV（附加保护）
    且 已等待 >= 600 s（10 分钟硬下限，厂商手册/ASTM G59）
    且 上述连续保持 120 s
动电位停止：电流达到 5×10⁻³（mA/cm²）→ 由软件自带「扫描停止」或外部监视。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import driver5
import sync_barrier
from driver5 import Studio5, all_run_hwnds, find_run_hwnd
from uiprobe import UiSampler, EisSampler, EisFinishJudge
from stabilizer import OcpStabilizer, StabConfig


_RUN_PATH_RE = re.compile(r"([A-Za-z]:\\[^\s<>\"']*?\.(?:cor|z60|txt))", re.I)


def _data_path_from(runwin) -> Optional[str]:
    """从运行窗标题里抠出数据文件路径（标题形如 `开路电位 <2mA>  D:\\x\\1.cor `）。"""
    try:
        t = runwin.window_text() or ""
    except Exception:
        return None
    m = _RUN_PATH_RE.search(t)
    return m.group(1) if m else None


def _file_signature(path: str):
    """数据文件的 (大小, 修改时间纳秒)。文件不在时返回 None。"""
    try:
        st = os.stat(path)
        return (st.st_size, st.st_mtime_ns)
    except Exception:
        return None


def wait_endexp(log, method: str = "", runwin=None, path: Optional[str] = None,
                timeout: float = 40.0, fallback: float = 13.0,
                quiet: float = 3.0) -> bool:
    """等软件真正把实验收尾（而不是只把界面窗口关掉）。

    5 版实测：点「停止」后工作站还要十几秒做收尾，**运行窗口关掉不代表实验
    停了**，此时立刻开下一个实验必撞车（表现是「该方法还没有完成，是否关闭?」
    一直弹、下一个实验一个点都采不到）。

    更关键的反面事实（2026-11-05 实测）：5 版点了「停止」以后，运行窗标题、
    界面上的采样时间**会继续走**，光看界面永远等不到"停"；真正停没停，
    只有数据文件写没写才算数（探针实测：停止后 .cor 大小与 mtime 立刻冻结）。
    所以判据顺序改成：

      ① 数据文件心跳（最可靠）——size + mtime 连续 quiet 秒不变 → 已收尾
      ② 运行窗消失
      ③ 界面采样时间连续 3 s 不增长
      ④ 都判不了 → 超时返回 False（调用方继续走关窗/清理）
    """
    t0 = time.time()
    if runwin is None:
        time.sleep(min(fallback, max(0.0, timeout)))
        return False

    if path is None:
        path = _data_path_from(runwin)
    sm = UiSampler(runwin, log=None)
    last = None
    still = 0          # 读数不再更新
    gone = 0           # 窗口真的没了
    last_sig = None
    sig_still = 0      # 数据文件不再变化
    need_sig = max(1, int(round(quiet / 0.5)))

    while time.time() - t0 < timeout:
        time.sleep(0.5)

        # ① 数据文件心跳
        if path:
            sig = _file_signature(path)
            if sig is not None:
                if last_sig is not None and sig == last_sig:
                    sig_still += 1
                    if sig_still >= need_sig:
                        log("  软件已收尾（数据文件 %g s 未再写入，%.1f s）"
                            % (quiet, time.time() - t0))
                        return True
                else:
                    sig_still = 0
                last_sig = sig
                continue          # 有文件证据就不再猜界面

        alive = True
        try:
            alive = bool(sm.alive())
        except Exception:
            alive = True          # 判断不了就当还在，宁可不判结束
        if not alive:
            gone += 1
            if gone >= 3:
                log("  软件已收尾（运行窗已关闭，%.1f s）" % (time.time() - t0))
                return True
            continue
        gone = 0
        s = None
        try:
            s = sm.read()
        except Exception:
            s = None
        if s is None or s.t_sec is None:
            # 窗口还在但读不到数据：可能是 UIA 抖动，门槛放高（约 5 s）
            still += 1
            if still >= 10:
                log("  软件已收尾（连续约 5 s 读不到数据，%.1f s）"
                    % (time.time() - t0))
                return True
            continue
        still = 0
        if last is not None and abs(s.t_sec - last) < 1e-9:
            if still >= 6:
                log("  软件已收尾（采样时间停止增长，%.1f s）"
                    % (time.time() - t0))
                return True
            still += 1
        else:
            still = 0
        last = s.t_sec
    log("  等待收尾超时 %g s（%s），按当前状态继续" % (timeout, method))
    return False

S_IDLE = "待机"
S_CONNECT = "连接 CS Studio5"
S_OCP_OPEN = "打开开路电位参数窗"
S_OCP_FILL = "填写开路电位参数"
S_OCP_START = "启动开路电位"
S_MON_OCP = "监视开路电位"
S_STOP_OCP = "停止开路电位"
S_EIS_OPEN = "打开阻抗参数窗"
S_EIS_FILL = "填写阻抗参数"
S_EIS_START = "启动阻抗扫描"
S_MON_EIS = "监视阻抗扫描"
S_STOP_EIS = "停止阻抗扫描"
S_T_OPEN = "打开动电位参数窗"
S_T_FILL = "填写动电位参数"
S_T_START = "启动动电位扫描"
S_MON_TEST = "监视动电位扫描"
S_STEP_OPEN = "打开阶梯波参数窗"
S_STEP_FILL = "填写阶梯波参数"
S_STEP_START = "启动阶梯波"
S_MON_STEP = "监视阶梯波"
S_DONE = "完成"
S_ERROR = "出错"
S_ABORT = "已中止"
#: 停止批次屏障：停完先让位等别的实例也停，再统一进入下一阶段（用户 2026-11-09 规则）
S_SYNC_WAIT = "已停止待同步"

#: 需要独占全局 UI 锁的状态（含鼠标/键盘注入的交互段）。
#: 监视段（MON_*）只读窗口文本，不持锁——4 台实验可并行推进。
UI_STATES = {
    S_CONNECT, S_OCP_OPEN, S_OCP_FILL, S_OCP_START, S_STOP_OCP,
    S_EIS_OPEN, S_EIS_FILL, S_EIS_START, S_STOP_EIS,
    S_T_OPEN, S_T_FILL, S_T_START,
    S_STEP_OPEN, S_STEP_FILL, S_STEP_START,
}


@dataclass
class RunConfig5:
    sample: str = "样品"
    sn: str = ""                   # ★ 多实例并存：按序列号锁定本机 CS Studio 窗口
    cs_hwnd: int = 0               # ★ 更硬：fleet 按 pid 定位的实例句柄
    com: str = ""                  # ★ 真机串口（COMx）；空=网口/sim 模式
    baud: int = 115200
    port: str = ""                 # ★ 网口端口（如 0.0.0.0:30002 → 连 30002）
    area_cm2: float = 1.0
    item: str = "Tafel"            # Tafel | Step
    out_dir: str = r"C:\Users\xiyve\Desktop\CS-Pilot数据"
    ocp_time_sec: float = 1800.0
    ocp_freq_hz: float = 10.0
    stab: StabConfig = field(default_factory=StabConfig)
    max_ocp_sec: float = 1800.0
    ocp_max_rounds: int = 3   # 开路电位最多测几轮（一轮 = ocp_time_sec 秒）；0/负数 = 不限，直到判稳
    tafel_init_v: float = -0.5
    tafel_final_v: float = 1.5
    tafel_scan_mv_s: float = 0.33
    tafel_interval_s: float = 0.5
    tafel_stop_ma: Optional[float] = None   # None=不动软件设置
    # 动电位结束判据：界面电流绝对值达到该值即停（用户：1×10⁻³）
    test_stop_i_density: Optional[float] = 1e-3   # A/cm²，达到即停动电位
    test_timeout_sec: float = 7200.0
    # ---- 阶梯波（任意恒电位阶梯波 frmPotSquareWave）----
    step_init_v: float = -0.2
    step_final_v: float = 0.5
    step_delta_v: float = 0.05
    step_hold_s: float = 2.0        # 每步持续 2 s
    step_cycles: int = 20           # 循环 20 个周期
    step_use_steps: bool = False    # 中间电位都不选
    # ---- EIS（阻抗频率扫描 / 频率扫描-电位控制模式）----
    eis_enabled: bool = True
    eis_dc_v: float = 0.0            # 直流电位(V)，相对开路时 0 = 不外加极化
    eis_amp_mv: float = 10.0         # 交流幅值(mV)
    eis_init_freq: float = 100000.0  # 初始频率(Hz)
    eis_final_freq: float = 0.01     # 终止频率(Hz)
    eis_pts_per_decade: float = 10.0 # 点/10倍频
    eis_timeout_sec: float = 1800.0


def build_filenames5(cfg: RunConfig5):
    """CS Studio5 会自动给文件名加 .cor 后缀，所以查重按 .cor 判断。

    软件遇到同名文件会弹「是否覆盖当前文件?」并覆盖写入，覆盖期间
    读到的可能是旧数据，因此这里主动避开已存在的名字。
    """
    from datetime import datetime
    d = datetime.now().strftime("%Y-%m-%d")
    # 样品名清洗 Windows 非法字符（\/:*?"<>|），否则路径非法、查重恒 False
    # （2026-11-06 代码审查 P2，对齐 runner.build_filenames）
    safe = "".join(ch for ch in (cfg.sample or "样品") if ch not in r'\/:*?"<>|').strip() or "样品"

    def pick(tag: str) -> str:
        # 2026-11-11 用户指定：全用空格分隔（2026-11-11 6 号 动电位，对齐软件
        # 手动开的文件命名；早期是「样品-标签」连字符）
        base = os.path.join(cfg.out_dir, "%s %s %s" % (d, safe, tag))
        if not os.path.exists(base + ".cor"):
            return base
        n = 2
        while os.path.exists("%s_%d.cor" % (base, n)):
            n += 1
        return "%s_%d" % (base, n)

    out = {"ocp": pick("开路电位"),
           "test": pick("动电位" if cfg.item == "Tafel" else "阶梯波")}
    if getattr(cfg, "eis_enabled", True):
        out["eis"] = pick("交流阻抗")
    return out


class Runner5:
    def __init__(self, cfg: RunConfig5,
                 on_update: Optional[Callable] = None,
                 log: Optional[Callable] = None,
                 on_state: Optional[Callable] = None,
                 on_sample: Optional[Callable] = None):
        self.cfg = cfg
        self.on_update = on_update
        self.on_state = on_state
        self.on_sample = on_sample
        self._log = log or (lambda *a: None)
        self.state = S_IDLE
        self.detail = ""
        self.t0 = 0.0
        self.files = build_filenames5(cfg)
        self.studio: Optional[Studio5] = None
        self.stab = OcpStabilizer(cfg.stab)
        self.sampler: Optional[UiSampler] = None
        self.runwin = None
        self.stop_reason = ""
        self.stab_point = None
        self.ocp_done_at = None
        self.test_first_data_at = None
        self.error = ""
        self._step_at = 0.0
        self._old_hwnds = set()
        # 阻抗阶段
        self._eis_sampler = None
        self._eis_judge = None
        self._eis_last_log = 0.0
        self._eis_null = 0
        self.eis_first_at = None
        self._eis_last_key = None
        self._eis_stall = 0

    # ---------------- 基础 ----------------
    def log(self, m):
        self._log(m)

    def set_state(self, s, detail=""):
        self.state = s
        self.detail = detail
        if self.on_state:
            try:
                self.on_state(s, detail)
            except Exception:
                pass
        if self.on_update:
            try:
                self.on_update(self)
            except Exception:
                pass

    @property
    def running(self) -> bool:
        return self.state not in (S_IDLE, S_DONE, S_ERROR, S_ABORT)

    @property
    def ocp_ok_volt(self):
        return self.stab_point[1] if self.stab_point else None

    def _fail(self, msg: str):
        """worker 异常出口：置错误态并停止运行（对齐 runner6._fail）。"""
        self.error = msg
        self.set_state(S_ERROR, msg)

    def elapsed(self):
        return time.time() - self.t0 if self.t0 else 0.0

    def _ocp_elapsed(self) -> float:
        """本轮开路电位已经跑了多久。

        多轮开路电位时**不能**用 elapsed()：那是从整个任务开始算的，
        第 2 轮一启动就会超过 max_ocp_sec，立刻被判成「本轮超时」。
        """
        t0 = getattr(self, "_ocp_round_t0", None) or self.t0
        return time.time() - t0 if t0 else 0.0

    def start(self):
        try:
            os.makedirs(self.cfg.out_dir, exist_ok=True)
        except Exception:
            pass
        # item 口径统一（2026-11-07 审查 P3）：文件名标签用 == "Tafel" 判定、
        # 分流用 == "Step"，"step" 这类小写会文件名标对却跑错项
        self.cfg.item = {"tafel": "Tafel", "step": "Step"}.get(
            str(self.cfg.item or "").strip().lower(), self.cfg.item)
        if self.cfg.item not in ("Tafel", "Step"):
            self.error = "未知测试项目：%r（可选 Tafel / Step）" % self.cfg.item
            self.set_state(S_ERROR, self.error)
            self.running = False
            return
        self.t0 = time.time()
        self._step_at = time.time()
        self.error = ""
        self.log("=" * 52)
        self.log("开始：%s / 面积 %g cm² / 项目 %s" % (self.cfg.sample, self.cfg.area_cm2, self.cfg.item))
        self.log("输出：开路电位 → %s" % self.files["ocp"])
        if self.files.get("eis"):
            self.log("输出：交流阻抗 → %s" % self.files["eis"])
        self.log("输出：%s → %s" % (self.cfg.item, self.files["test"]))
        # OCP 重试轮计数：只在每次运行开始时清零（以前在 _do_mon_ocp 里
        # 每次读到数据都清零，导致超时分支计数恒 0、无限重试并覆盖上一轮
        # 数据——2026-11-06 代码审查发现）
        self._ocp_round = 0
        self._ocp_retry = False
        self.set_state(S_CONNECT)

    def result_files(self):
        """看板上报用：列出已落盘的产物 (文件名, 字节数)。5 版产物是 .cor。"""
        out = []
        for _k, v in getattr(self, "files", {}).items():
            if not v:
                continue
            for p in (v + ".cor", v + ".txt", v + ".z60"):
                try:
                    if os.path.exists(p):
                        out.append((os.path.basename(p), os.path.getsize(p)))
                        break
                except OSError:
                    continue
        return out

    def abort(self):
        self.stop_reason = "用户中止"
        self.log("用户中止")
        # 5 版没有"序列"，一个实验停了就是停；但必须走完整收尾，
        # 否则界面窗口关了、工作站里还在采，下一轮直接撞车。
        self._safe_finish("用户中止", idle_wait=6.0)
        self.set_state(S_ABORT)

    # ---------------- 主循环 ----------------
    def tick(self):
        if self.state in (S_IDLE, S_DONE, S_ERROR, S_ABORT):
            try:
                import ui_lock
                if ui_lock.ui_held():
                    ui_lock.ui_release()
            except Exception:
                pass
            return
        # ★ 全局 UI 互斥：4 实例同桌面时输入注入是全局的（SendInput 发给
        #   前台窗口），必须保证同一时刻只有一个 runner 在点菜单/填参数。
        #   监视段（只读窗口文本）不持锁，4 台实验并行。
        try:
            import ui_lock
            if self.state in UI_STATES:
                if not ui_lock.ui_acquire(0.0):
                    if not getattr(self, "_lock_wait_logged", False):
                        self._lock_wait_logged = True
                        self.log("等待全局 UI 锁（其它实例正在操作界面）…")
                    return
                self._lock_wait_logged = False
                # ★ 拿到锁立刻把本实例弹到前台：被遮挡的窗口点不准
                if not getattr(self, "_ui_act_done", False):
                    self._ui_act_done = True
                    try:
                        self.studio.activate()
                    except Exception:
                        pass
            elif ui_lock.ui_held():
                ui_lock.ui_release()
                self._ui_act_done = False
        except Exception:
            pass
        # 每个状态至少间隔 0.4 s，避免空转
        try:
            self.studio.ensure_main_visible()
        except Exception:
            pass
        # 「显示温度曲线」悬浮窗：CS5 每开一个测试都会弹一个（用户 2026-11-09
        # 要求删掉）。监视段顺手关——PostMessage 不需要前台，不持 UI 锁也安全；
        # 只按 pid 动自己的窗口，实例间无串扰。6s 节流防 EnumWindows 空转。
        if self.state in (S_MON_OCP, S_MON_EIS, S_MON_TEST, S_MON_STEP):
            if time.time() - getattr(self, "_tc_last", 0.0) > 6.0:
                self._tc_last = time.time()
                try:
                    self.studio.close_temp_curve()
                except Exception:
                    pass
        if time.time() - self._step_at < 0.4:
            return
        self._step_at = time.time()
        try:
            self._step()
        except Exception as e:
            import traceback
            self.error = "%s: %s" % (type(e).__name__, e)
            self.log("异常：" + traceback.format_exc(limit=3))
            # 出异常也必须收尾：否则脚本退了、工作站里还在采集，
            # 下一个实验一个点都采不到（用户反馈过的现象就是这个）。
            self._safe_finish("异常收尾", idle_wait=0.0)
            self.set_state(S_ERROR, self.error)

    def _step(self):
        s = self.state
        if s == S_CONNECT:
            self._do_connect()
        elif s == S_OCP_OPEN:
            self._do_ocp_open()
        elif s == S_OCP_FILL:
            self._do_ocp_fill()
        elif s == S_OCP_START:
            self._do_ocp_start()
        elif s == S_MON_OCP:
            self._do_mon_ocp()
        elif s == S_STOP_OCP:
            self._do_stop_ocp()
        elif s == S_EIS_OPEN:
            self._do_eis_open()
        elif s == S_EIS_FILL:
            self._do_eis_fill()
        elif s == S_EIS_START:
            self._do_eis_start()
        elif s == S_MON_EIS:
            self._do_mon_eis()
        elif s == S_STOP_EIS:
            self._do_stop_eis()
        elif s == S_SYNC_WAIT:
            self._do_sync_wait()
        elif s == S_T_OPEN:
            self._do_t_open()
        elif s == S_T_FILL:
            self._do_t_fill()
        elif s == S_T_START:
            self._do_t_start()
        elif s == S_MON_TEST:
            self._do_mon_test()
        elif s == S_STEP_OPEN:
            self._do_step_open()
        elif s == S_STEP_FILL:
            self._do_step_fill()
        elif s == S_STEP_START:
            self._do_step_start()
        elif s == S_MON_STEP:
            self._do_mon_step()

    def _next_test_state(self) -> str:
        """OCP/阻抗结束后下一个该进的测试项状态（按项目类型分流）。"""
        return S_STEP_OPEN if self.cfg.item == "Step" else S_T_OPEN

    def _expect_tag(self, kind: str) -> Optional[str]:
        """运行窗口标题里必须出现的片段 = 本次文件名（去掉目录与扩展名）。

        真机上启动瞬间旧窗口可能还没关干净，只靠 hwnd 排除会抓错窗口，
        导致监视到上一轮的数据、20 s 后误判"实验结束"。
        """
        try:
            p = self.files.get(kind) or ""
            base = os.path.basename(p)
            return os.path.splitext(base)[0] or None
        except Exception:
            return None

    # ---------------- 各步骤 ----------------
    def _do_connect(self):
        self.studio = Studio5(log=self.log, sn=self.cfg.sn,
                              hwnd=getattr(self.cfg, "cs_hwnd", 0))
        # 桌面模式：CS Studio 自动发现+连接要几十秒——轮询等窗口出现；
        # 手动配对模式（--port）跳过 SN 等待（app 会 churn，配对交给 connect_lan）
        wait_sn = not self.cfg.port
        end = time.time() + (75.0 if wait_sn else 20.0)
        while not self.studio.launch():
            if self.cfg.sn and self.cfg.sn in self.studio.title():
                break
            if time.time() > end:
                self.error = "启动 CS Studio5 失败（窗口未就绪）"
                return self.set_state(S_ERROR, self.error)
            time.sleep(2)
        self.log("主窗口：%r" % self.studio.title())
        com = getattr(self.cfg, "com", "")
        if com:
            # ★ 真机串口：通讯设置→USB→手动→选口；SN 从标题回读校验
            if ("in %s" % com) not in self.studio.title():
                try:
                    self.studio.close_user_settings()   # 真机新实例常弹用户设置框
                except Exception:
                    pass
                if not self.studio.connect_com(com, getattr(self.cfg, "baud", 115200)):
                    self.error = "串口连接 %s 失败" % com
                    return self.set_state(S_ERROR, self.error)
            t = self.studio.title()
            if self.cfg.sn and self.cfg.sn not in t:
                self.error = "串口 %s 连的不是 %s（标题：%s）" % (com, self.cfg.sn, t[:50])
                return self.set_state(S_ERROR, self.error)
            self.log("真机串口就绪：%s" % t[:60])
            self._old_hwnds = set(all_run_hwnds())
            if self._old_hwnds:
                self.log("排除 %d 个残留运行窗口" % len(self._old_hwnds))
            return self.set_state(S_OCP_OPEN)
        if self.cfg.port and self.cfg.sn and self.cfg.sn not in self.studio.title():
            # ★ 多实例：自动发现会连错别人的 sim——手动指定本机端口
            if not self.studio.connect_lan(self.cfg.port):
                self.error = "网口连接 %s 失败" % self.cfg.port
                return self.set_state(S_ERROR, self.error)
        if not self.studio.is_demo():
            # 真机连着的时候不需要、也进不了演示模式；这不是错误
            if self.studio.enter_demo():
                self.log("已进入演示模式")
            else:
                self.log("未进入演示模式（真机连接时正常）")
        self._old_hwnds = set(all_run_hwnds())
        if self._old_hwnds:
            self.log("排除 %d 个残留运行窗口" % len(self._old_hwnds))
        self.set_state(S_OCP_OPEN)

    def _do_ocp_open(self):
        panel = self.studio.open_ocp()
        if panel is None:
            self.error = "打不开『开路电位』参数窗"
            return self.set_state(S_ERROR, self.error)
        self._ocp_panel = panel
        self.log("开路电位参数窗已打开")
        self.set_state(S_OCP_FILL)

    def _do_ocp_fill(self):
        secs = max(1.0, float(self.cfg.ocp_time_sec))
        ok = self.studio.fill_ocp(self._ocp_panel, self.files["ocp"], secs, self.cfg.ocp_freq_hz)
        if not ok:
            self.error = "开路电位参数写入失败"
            return self.set_state(S_ERROR, self.error)
        self.log("开路电位参数：%g 秒 / %g Hz" % (secs, self.cfg.ocp_freq_hz))
        if not self.studio.set_cell_area(self._ocp_panel, self.cfg.area_cm2):
            self.log("  ⚠️ 开路电位阶段设面积失败，继续（软件会沿用上次的值）")
        self.set_state(S_OCP_START)

    def _do_ocp_start(self):
        self._old_hwnds = set(all_run_hwnds())
        if not self.studio.start_experiment(self._ocp_panel, kind="ocp", retries=2, wait=25.0):
            self.error = "点『确定』失败"
            return self.set_state(S_ERROR, self.error)
        rw = self.studio.find_run_window(timeout=20, exclude=self._old_hwnds,
                                         expect=self._expect_tag("ocp"))
        if rw is None:
            self.error = "实验没有启动（没出现运行窗口）"
            return self.set_state(S_ERROR, self.error)
        self.runwin = rw
        self.log("实验已启动：%r" % rw.window_text())
        self.log("状态栏：%r" % self.studio.run_status(rw))
        self.sampler = UiSampler(rw, log=None)
        self._ocp_round_t0 = time.time()   # 本轮计时基准
        self.set_state(S_MON_OCP)

    def _do_mon_ocp(self):
        if not self.sampler.alive():
            self.log("运行窗口消失，开路电位阶段结束")
            if not self.runwin:
                return self.set_state(self._next_test_state())
            # 窗口消失 = 这一轮跑完（软件的时间上限）；没判稳就再来一轮
            if self._ocp_can_retry():
                self._ocp_round += 1
                self._ocp_retry = True
                self.log("本轮 %g s 跑满未判稳 → 再来一轮（%s）"
                         % (self.cfg.ocp_time_sec, self._ocp_rounds_desc()))
            return self.set_state(S_STOP_OCP)
        s = self.sampler.read()
        if s is None or s.e_volt is None:
            if self._ocp_elapsed() > self.cfg.max_ocp_sec + 300:
                self.log("开路电位等待超时")
                return self.set_state(S_STOP_OCP)
            return
        # 数据停滞：实验自己结束了，界面时间不再增长（用 runner 自己的时钟兜底）
        if getattr(self, "_ocp_last_t", None) is not None and abs(s.t_sec - self._ocp_last_t) < 1e-9:
            self._ocp_stall = getattr(self, "_ocp_stall", 0) + 1
        else:
            self._ocp_stall = 0
        self._ocp_last_t = s.t_sec
        if self._ocp_stall >= 25:                     # 约 10 s（0.4 s/步）没有新点
            self.stab_point = (s.t_sec, s.e_volt)
            self.log("开路电位数据 10 s 未更新（t=%.1fs）→ 判定实验已自行结束" % s.t_sec)
            # 用户 2026-11-11：软件里那 1800 s 只是「一轮」，跑满没判稳就再来一轮
            if self._ocp_can_retry():
                self._ocp_round += 1
                self._ocp_retry = True
                self.log("本轮 %g s 跑满未判稳 → 再来一轮（%s）"
                         % (self.cfg.ocp_time_sec, self._ocp_rounds_desc()))
            return self.set_state(S_STOP_OCP)
        self.stab.feed([(s.t_sec, s.e_volt)])
        if self.on_sample:
            try:
                self.on_sample(s.t_sec, s.e_volt, self.stab.state)
            except Exception:
                pass
        st = self.stab.state
        if st.stable:
            self.stab_point = (s.t_sec, s.e_volt)
            self.log("★ 判稳 @ t=%.1fs  E=%+.6f V  (%s)" % (s.t_sec, s.e_volt, st.reason))
            return self.set_state(S_STOP_OCP)
        if self._ocp_elapsed() >= self.cfg.max_ocp_sec:
            self.stab_point = (s.t_sec, s.e_volt)
            if self._ocp_can_retry():
                self._ocp_round += 1
                self._ocp_retry = True
                self.log("本轮 %g s 未判稳 → 准备第 %d 轮（%s）"
                         % (self.cfg.max_ocp_sec, self._ocp_round + 1,
                            self._ocp_rounds_desc()))
            else:
                self.log("到达最长等待 %g s（已测 %d 轮）仍未判稳，按当前值 E=%+.6f V 继续"
                         % (self.cfg.max_ocp_sec, self._ocp_round + 1, s.e_volt))
            return self.set_state(S_STOP_OCP)

    def _ocp_max_rounds(self) -> int:
        try:
            return int(getattr(self.cfg, "ocp_max_rounds", 0) or 0)
        except Exception:
            return 0

    def _ocp_can_retry(self) -> bool:
        """还能再来一轮 OCP 吗？0/负数 = 不限轮数，一直测到判稳为止
        （用户 2026-11-11：「时间不设上限，30 分钟没稳就再来一遍」）。"""
        maxr = self._ocp_max_rounds()
        return maxr <= 0 or (self._ocp_round + 1 < maxr)

    def _ocp_rounds_desc(self) -> str:
        maxr = self._ocp_max_rounds()
        return "不限轮数，直到判稳" if maxr <= 0 else "共最多 %d 轮" % maxr

    def _safe_finish(self, label: str, idle_wait: float = 0.0) -> bool:
        """收尾的安全包装：任何异常都不许冒泡。

        它经常在 except 分支里被调用（异常收尾、用户中止），
        这时候再抛异常就会把原始错误盖掉，也会让收尾半途而废。
        """
        if self.studio is None:
            return False
        # 监视状态不持 UI 锁（4 台并行读数），但收尾要动界面：
        # 点停止/关运行窗/清模态框都是全局输入，必须自己拿锁。
        got = False
        try:
            import ui_lock
            got = ui_lock.ui_acquire(60.0)
        except Exception:
            got = False
        try:
            self._finish_run(label, idle_wait=idle_wait)
            return True
        except Exception as e:
            self.log("  收尾失败（%s）：%s" % (label, e))
            return False
        finally:
            if got:
                try:
                    import ui_lock as _ul
                    _ul.ui_release()
                except Exception:
                    pass

    def _finish_run(self, label: str, idle_wait: float = 10.0) -> None:
        """统一的实验收尾：① 点「停止」② 等软件真结束 ③ 关运行窗 ④ 冷却 ⑤ 清残留。

        5 版的坑（实测踩过）：**关掉界面窗口不等于实验停了**，工作站里可能还在
        采集，随即把下一个实验顶掉；而且刚停下来的几秒里开新实验必撞车
        （「该方法还没有完成，是否关闭?」一直弹）。所以顺序不能颠倒，
        每一步都要等软件真的响应完。OCP / 阻抗 / 动电位 / 阶梯波全部走这里。
        """
        rw = self.runwin
        if rw is not None:
            ok = False
            try:
                ok = self.studio.stop_run(rw)
            except Exception as e:
                self.log("  点「停止」出错：%s" % e)
            self.log("① %s：点「停止」→ %s" % (label, ok))
            ended = wait_endexp(self.log, method=label, runwin=rw,
                                timeout=40.0, fallback=8.0)
            if not ended:
                # wait_endexp False = 40s 内数据文件仍在写 = 停止未生效。
                # 此时关运行窗正是文档记录的「关窗后工作站继续采集」事故路径
                # （2026-11-07 审查 P2）：保留窗口，下次还能从它上面点停止。
                self.log("  ⚠️ %s：数据文件仍在写（停止未生效），保留运行窗待排查"
                         % label)
                return
            try:
                self.studio.close_run(rw)
                self.log("② %s：关闭运行窗口" % label)
            except Exception as e:
                self.log("  关运行窗出错：%s" % e)
            self.runwin = None
        if idle_wait > 0:
            self.log("③ 等待 %g s 让软件彻底回到空闲…" % idle_wait)
            time.sleep(idle_wait)
        try:
            n = self.studio.cleanup_run_windows()
            if n:
                self.log("   清掉 %d 个残留实验窗口" % n)
        except Exception as e:
            self.log("   清理残留窗口出错：%s" % e)
        try:
            # 注意：Studio5 类没有 clear_modals 方法，必须调模块级函数
            n = driver5.clear_modals(limit=4,
                                     prefer=("是(Y)", "是", "关闭", "确定"))
            if n:
                self.log("   顺带清掉 %d 个残留提示框" % n)
        except Exception:
            pass
        self.log("%s 收尾完成，可以开下一项" % label)

    def _do_stop_ocp(self):
        # 用户明确要求的三步：① 点「停止」 ② 关掉运行窗口 ③ 等几秒再开下一项
        # 背景：OCP 结束后立刻开 EIS，软件里那个方法还挂在「未完成」状态，
        # 表现就是「该方法还没有完成，是否关闭?」一直弹、EIS 一个点都采不到。
        self._finish_run("开路电位", idle_wait=10.0)
        self.ocp_done_at = time.time()
        if getattr(self, "_ocp_retry", False):
            self._ocp_retry = False
            base = re.sub(r"_第\d+轮$", "", self.files.get("ocp", ""))
            cand = "%s_第%d轮" % (base, self._ocp_round + 1)
            k = 2
            while (os.path.exists(cand + ".cor") or os.path.exists(cand + ".txt")
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
        else:
            self._enter_after_stop(self._next_test_state())

    # ---------------- 停止批次屏障（用户 2026-11-09 规则） ----------------
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

    # ---------------- EIS 阶段 ----------------
    def _do_eis_open(self):
        panel = self.studio.open_eis()
        if panel is None:
            self.error = "打不开『阻抗频率扫描』参数窗"
            return self.set_state(S_ERROR, self.error)
        self._eis_panel = panel
        self.log("阻抗频率扫描参数窗已打开")
        self.set_state(S_EIS_FILL)

    def _do_eis_fill(self):
        ok = self.studio.fill_eis(
            self._eis_panel, self.files["eis"],
            dc_v=self.cfg.eis_dc_v, amp_mv=self.cfg.eis_amp_mv,
            init_freq=self.cfg.eis_init_freq, final_freq=self.cfg.eis_final_freq,
            pts_per_decade=self.cfg.eis_pts_per_decade, vs_ocp=True)
        try:
            rb = self.studio.eis_readback(self._eis_panel)
        except Exception:
            rb = {}
        self.log("阻抗参数回读：%r" % (rb,))
        if not ok:
            self.error = "阻抗参数写入失败"
            return self.set_state(S_ERROR, self.error)
        self.log("阻抗参数：%g Hz → %g Hz，%g mV，%g 点/10倍频" %
                 (self.cfg.eis_init_freq, self.cfg.eis_final_freq,
                  self.cfg.eis_amp_mv, self.cfg.eis_pts_per_decade))
        if not self.studio.set_cell_area(self._eis_panel, self.cfg.area_cm2):
            self.log("  ⚠️ 阻抗阶段设面积失败，继续（软件会沿用上次的值）")
        self.set_state(S_EIS_START)

    def _do_eis_start(self):
        # 每次进入阻抗阶段都重置超时基准（_eis_t0 有 hasattr 缓存，不重置会跨轮失效）
        self._eis_t0 = time.time()
        self._old_hwnds = set(all_run_hwnds())
        if not self.studio.start_experiment(self._eis_panel, kind="eis", retries=2, wait=25.0):
            self.error = "点『确定』失败"
            return self.set_state(S_ERROR, self.error)
        rw = self.studio.find_run_window(
            timeout=25, exclude=self._old_hwnds,
            keywords=("阻抗", "图形显示", "频率"),
            expect=self._expect_tag("eis"))
        if rw is None:
            self.error = "阻抗扫描没有启动"
            return self.set_state(S_ERROR, self.error)
        self.runwin = rw
        self.sampler = UiSampler(rw, log=None)
        self._eis_sampler = EisSampler(rw, log=self.log)
        self._eis_judge = EisFinishJudge(min_sec=8.0, stable_n=5,
                                        final_freq=self.cfg.eis_final_freq,
                                        log=self.log)
        self._eis_last_log = 0.0
        self.eis_first_at = None
        self._eis_last_key = None
        self._eis_stall = 0
        self._eis_null = 0
        self.log("阻抗扫描已启动：%r" % rw.window_text())
        self.set_state(S_MON_EIS)

    def _do_mon_eis(self):
        # 阻抗扫完后窗口不消失（一直显示 Nyquist/Bode 图），所以不能靠 alive() 判结束。
        # 按用户说明：数据完成之后还会继续变化，必须看进度（右下角剩余时间 / 点数）。
        prog = None
        if self._eis_sampler is not None:
            try:
                prog = self._eis_sampler.read()
            except Exception:
                prog = None

        # 读不到数据就累积计数；连续 30 步（≈12 s）都读不到才认为窗口真的没了。
        # 不能用 alive()：刚拿到 wrapper 时 UIA 还没稳定，会立刻误判"窗口消失"。
        if prog is None:
            self._eis_null = getattr(self, "_eis_null", 0) + 1
            if self._eis_null >= 30:
                self.log("阻抗窗口连续 %d 次读不到数据 → 视为结束" % self._eis_null)
                return self.set_state(S_STOP_EIS)
        else:
            self._eis_null = 0
        if prog is not None and self.eis_first_at is None and prog.points:
            self.eis_first_at = time.time()

        done, why = self._eis_judge.update(prog, time.time())
        if done:
            self.log("阻抗扫描完成：%s" % why)
            return self.set_state(S_STOP_EIS)

        # 超时兜底必须用墙钟差：elapsed() 是相对秒，eis_t0 是 epoch 时间戳，
        # 两者相减恒约 -1.7e9 永不触发（2026-11-06 代码审查 P1）。
        # _eis_t0 由 _do_eis_start 每次启动时重置，避免 hasattr 缓存跨轮不刷新。
        if time.time() - self.getattr_eis_t0() > self.cfg.eis_timeout_sec:
            self.log("阻抗扫描超时 → 强制结束（%s）" % why)
            return self.set_state(S_STOP_EIS)

        now = time.time()
        if now - getattr(self, "_eis_last_log", 0.0) >= 5.0:
            self._eis_last_log = now
            if prog is not None:
                self.log("  阻抗进度：点数=%s 频率=%s Hz |Z|=%s Ω 剩余=%s 秒（%s）"
                         % (prog.points, prog.freq_hz, prog.z_abs,
                            prog.remain_sec, why))
        if self.on_sample:
            try:
                self.on_sample(0.0, None, "eis")
            except Exception:
                pass

    def getattr_eis_t0(self) -> float:
        if not hasattr(self, "_eis_t0"):
            self._eis_t0 = self.eis_first_at or time.time()
        return self._eis_t0

    def _do_stop_eis(self):
        # 阻抗跑完窗口不会自己消失（一直显示 Nyquist/Bode 图），
        # 所以必须走与 OCP 相同的收尾通道，否则下一个实验开局必撞车。
        self._finish_run("阻抗扫描", idle_wait=8.0)
        self._enter_after_stop(self._next_test_state())

    def _do_t_open(self):
        panel = self.studio.open_tafel()
        if panel is None:
            self.error = "打不开『动电位扫描』参数窗"
            return self.set_state(S_ERROR, self.error)
        self._t_panel = panel
        self.log("动电位扫描参数窗已打开")
        self.set_state(S_T_FILL)

    def _do_t_fill(self):
        ok = self.studio.fill_tafel(self._t_panel, self.files["test"],
                                    self.cfg.tafel_init_v, self.cfg.tafel_final_v,
                                    self.cfg.tafel_scan_mv_s, self.cfg.tafel_interval_s,
                                    stop_ma=self.cfg.tafel_stop_ma)
        if not ok:
            self.error = "动电位参数写入失败"
            return self.set_state(S_ERROR, self.error)
        self.log("动电位参数：%g → %g V，%g mV/s" %
                 (self.cfg.tafel_init_v, self.cfg.tafel_final_v, self.cfg.tafel_scan_mv_s))
        if not self.studio.set_cell_area(self._t_panel, self.cfg.area_cm2):
            self.log("  ⚠️ 动电位阶段设面积失败，继续（软件会沿用上次的值）")
        self.set_state(S_T_START)

    def _do_t_start(self):
        self._old_hwnds = set(all_run_hwnds())
        if not self.studio.start_experiment(self._t_panel, kind="tafel", retries=2, wait=25.0):
            self.error = "点『确定』失败"
            return self.set_state(S_ERROR, self.error)
        rw = self.studio.find_run_window(timeout=20, exclude=self._old_hwnds,
                                         expect=self._expect_tag("test"))
        if rw is None:
            self.error = "动电位实验没有启动"
            return self.set_state(S_ERROR, self.error)
        self.runwin = rw
        self.sampler = UiSampler(rw, log=None)
        self.test_first_data_at = None
        self._test_phase_t0 = time.time()   # 阶段时钟：超时判定不能用总 elapsed()
        self.log("动电位已启动：%r" % rw.window_text())
        self.set_state(S_MON_TEST)

    def _do_mon_test(self):
        if not self.sampler.alive():
            self.log("运行窗口消失 → 动电位结束")
            # 窗口没了不代表实验停了：5 版实测窗口关掉后工作站仍可能继续采集，
            # 会把下一个实验顶掉。旧版只补点一次停止（窗已没必失败）就 S_DONE，
            # 不走 wait_endexp/关窗/清残留/冷却——改用统一收尾（2026-11-07 审查 P2）
            self._safe_finish("动电位")
            return self.set_state(S_DONE)
        s = self.sampler.read()
        if s is not None and s.e_volt is not None:
            if self.test_first_data_at is None:
                self.test_first_data_at = time.time()
            self.last_sample = s

        # 主判据：电流密度达到 1×10⁻³ A/cm² 就停（用户 2026-11-04）
        # 界面给的是绝对电流 A，除以面积换成电流密度，与 6 版文件第 2 列口径一致。
        # 连续 2 次读数达标才停：单点噪声尖峰不应截断整条曲线（审查 P2-10）。
        thr = getattr(self.cfg, "test_stop_i_density", None)
        if thr is not None and s is not None and s.i_amp is not None:
            try:
                i_den = abs(float(s.i_amp)) / max(float(self.cfg.area_cm2), 1e-9)
                if i_den >= float(thr):
                    self._i_hit = getattr(self, "_i_hit", 0) + 1
                else:
                    self._i_hit = 0
                if self._i_hit >= 2:
                    self.log("电流密度 %+.4e A/cm² 连续 %d 次达标（阈值 %+.4e）→ 判定动电位结束"
                             % (i_den, self._i_hit, float(thr)))
                    self._safe_finish("动电位")
                    return self.set_state(S_DONE)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        if self.test_first_data_at is None:
            # 阶段时钟（2026-11-07 审查 P2）：elapsed() 是总时钟，多轮 OCP+EIS
            # 之后测试项一进场就"超时"
            if time.time() - getattr(self, "_test_phase_t0", self.t0) > self.cfg.test_timeout_sec:
                self.error = "动电位迟迟没有数据"
                # S_ERROR 不收尾 = 运行窗留着、工作站继续加电采集（审查 P1）
                self._safe_finish("动电位")
                return self.set_state(S_ERROR, self.error)
            return
        # 数据停滞判停：连续 50 个 tick（≈20 s）t_sec 没变才算结束。
        # 旧实现只比较相邻两次读数（0.4 s），UIA 一次抖动就误判（审查 P1-3）。
        if time.time() - self.test_first_data_at > 20 and s is not None:
            last_t = getattr(self, "_test_last_t", None)
            if last_t is not None and abs(s.t_sec - last_t) < 1e-9:
                self._test_stall = getattr(self, "_test_stall", 0) + 1
            else:
                self._test_stall = 0
            self._test_last_t = s.t_sec
            if self._test_stall >= 50:
                self.log("数据 20 s 未更新（t=%.1fs）→ 判定动电位结束" % s.t_sec)
                self._safe_finish("动电位")
                return self.set_state(S_DONE)
        if time.time() - getattr(self, "_test_phase_t0", self.t0) > self.cfg.test_timeout_sec:
            self.error = "动电位超时（阶段时钟）"
            self._safe_finish("动电位")
            return self.set_state(S_ERROR, self.error)

    # ---------------- 阶梯波（任意恒电位阶梯波）----------------
    def _do_step_open(self):
        panel = self.studio.open_step()
        if panel is None:
            self.error = "打不开『任意恒电位阶梯波』参数窗"
            return self.set_state(S_ERROR, self.error)
        self._step_panel = panel
        self.log("阶梯波参数窗已打开")
        self.set_state(S_STEP_FILL)

    def _do_step_fill(self):
        ok = self.studio.fill_step(
            self._step_panel, self.files["test"],
            self.cfg.step_init_v, self.cfg.step_final_v,
            self.cfg.step_delta_v, self.cfg.step_hold_s,
            freq_hz=self.cfg.ocp_freq_hz,
            cycles=getattr(self.cfg, "step_cycles", 20),
            use_steps=getattr(self.cfg, "step_use_steps", False))
        if not ok:
            self.error = "阶梯波参数写入失败"
            return self.set_state(S_ERROR, self.error)
        if not self.studio.set_cell_area(self._step_panel, self.cfg.area_cm2):
            self.log("  ⚠️ 阶梯波阶段设面积失败，继续（软件会沿用上次的值）")
        self.set_state(S_STEP_START)

    def _do_step_start(self):
        self._old_hwnds = set(all_run_hwnds())
        if not self.studio.start_experiment(self._step_panel, kind="step", retries=2, wait=25.0):
            self.error = "阶梯波点『确定』失败"
            return self.set_state(S_ERROR, self.error)
        rw = self.studio.find_run_window(timeout=20, exclude=self._old_hwnds,
                                         expect=self._expect_tag("test"))
        if rw is None:
            self.error = "阶梯波实验没有启动"
            return self.set_state(S_ERROR, self.error)
        self.runwin = rw
        self.sampler = UiSampler(rw, log=None)
        self.test_first_data_at = None
        self._test_phase_t0 = time.time()   # 阶段时钟：超时判定不能用总 elapsed()
        self._step_last_t = None
        self._step_stall = 0
        self.log("阶梯波已启动：%r" % rw.window_text())
        self.set_state(S_MON_STEP)

    def _do_mon_step(self):
        """阶梯波没有外部停止判据：走完全部步就结束。
        结束 = 数据停滞（约 20 s 不再有新点）或窗口消失或超时。"""
        if not self.sampler.alive():
            self.log("运行窗口消失 → 阶梯波结束")
            # 同 _do_mon_test：统一收尾，不做单次补点就放行（2026-11-07 审查 P2）
            self._safe_finish("阶梯波")
            return self.set_state(S_DONE)
        s = self.sampler.read()
        if s is not None and s.e_volt is not None:
            if self.test_first_data_at is None:
                self.test_first_data_at = time.time()
                self.log("收到第一个数据点 t=%.2f s" % s.t_sec)
            self.last_sample = s
            if self._step_last_t is not None and abs(s.t_sec - self._step_last_t) < 1e-9:
                self._step_stall += 1
            else:
                self._step_stall = 0
            self._step_last_t = s.t_sec
        if self.test_first_data_at is not None and self._step_stall >= 50:
            # 50 × 0.4 s ≈ 20 s 没有新点 → 阶梯程序已走完
            self.log("阶梯波数据 20 s 未更新（t=%s）→ 判定全部步走完"
                     % (getattr(s, "t_sec", "?")))
            # 自然结束也要完整收尾（停/关窗/冷却/清理），
            # 否则运行窗残留给下一项埋雷（2026-11-06 代码审查 P2）
            self._safe_finish("阶梯波")
            return self.set_state(S_DONE)
        if time.time() - getattr(self, "_test_phase_t0", self.t0) > self.cfg.test_timeout_sec:
            self.log("阶梯波超时 %g s（阶段时钟），强制结束"
                     % self.cfg.test_timeout_sec)
            try:
                self.studio.stop_run(self.runwin)
            except Exception:
                pass
            self._safe_finish("阶梯波")
            return self.set_state(S_DONE)
        if self.on_sample:
            try:
                if s is not None and s.e_volt is not None:
                    self.on_sample(s.t_sec, s.e_volt, None)
            except Exception:
                pass

    # ---------------- 汇总 ----------------
    def summary(self) -> List[str]:
        out = ["状态：%s %s" % (self.state, self.detail)]
        if self.stab_point:
            t, v = self.stab_point
            out.append("判稳点：t=%.1fs  E=%+.6f V" % (t, v))
        for k, p in self.files.items():
            for cand in (p, p + ".cor", p + ".txt", p + ".z60"):
                if os.path.exists(cand):
                    out.append("%s：%s (%d 字节)" % (k, cand, os.path.getsize(cand)))
                    break
        return out
