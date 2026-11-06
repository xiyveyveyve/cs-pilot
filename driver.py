# -*- coding: utf-8 -*-
"""CS Studio6 寄生驱动：只用界面完成"配序列 → 启动 → 停止当前 → 接续"。

不做什么
--------
* 不写 Config 目录里任何 .ini / .NewParams（软件默认数据保持原样）
* 不发任何串口/TCP 报文（设备通讯完全由软件自己负责）
* 不调用软件的"条件停机"（实测那套 Δ 电位判据形同虚设）

做什么
------
用 UIA 在通道窗口里把实验序列摆好，点「开始」，然后监视软件自己写的
数据文件；判稳达标后点数据窗口工具栏的「停止」把当前实验收尾 ——
实测该按钮会**中止当前实验并自动开始序列里的下一项**，正好满足
"OCP 达标才停、停完自动接 Tafel"的要求。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import ClassVar, List, Optional

from studio_ui import Studio, ensure_foreground

# 实验类型 → 参数窗 automation_id / 下拉显示名
EXP_OCP = "OCP"
EXP_TAFEL = "Tafel"
EXP_STEP = "Step"          # 任意恒电位阶梯波(多电位阶跃)
EXP_EIS = "EIS"            # 交流阻抗-频率扫描(电位控制模式)

EXP_PANEL = {
    EXP_OCP: "frmOCP",
    EXP_TAFEL: "frmPotDynamic",
    EXP_EIS: "frmEISVSfrq",
}
EXP_COMBO_TEXT = {
    EXP_OCP: "开路电位测量(OCP)",
    EXP_TAFEL: "动电位扫描(Tafel,LPR)",
    EXP_STEP: "任意恒电位阶梯波",
    EXP_EIS: "频率扫描-电位控制模式",
}

# 「添加」对话框里 cboExp 是 owner-draw 自绘下拉：条目文字读不到，但选中后
# 的 Value 能读回。行高 32px，第 i 行中心在 combo 底边 +8+32i（p28 实测）。
# 下面是历史命中行（「常用」分组会漂，只作快路径，失败后全表扫描兜底）。
EXP_PICK_ROW = {
    EXP_OCP: (4, 3, 5),
    EXP_TAFEL: (3, 2, 4),
    EXP_STEP: (10, 11, 9),
    EXP_EIS: (7,),
}


@dataclass
class OcpSpec:
    KIND: ClassVar[str] = EXP_OCP
    file: str = ""
    test_time_sec: int = 1800
    freq_hz: float = 10.0
    # 软件自带的 Δ 电位停止条件：保持关闭（由外部判稳接管）
    use_delta_stop: bool = False


@dataclass
class TafelSpec:
    KIND: ClassVar[str] = EXP_TAFEL
    file: str = ""
    init_v: float = -0.5
    final_v: float = 1.5
    scan_mv_s: float = 0.33
    sample_interval_s: float = 0.5
    vs_ocp: bool = True


def step_ladder(init_v: float, final_v: float, delta_v: float,
                max_steps: int = 10) -> List[float]:
    """init→final 之间的中间电位序列（不含两端），最多 max_steps 个。

    按给定 delta 均匀铺；铺不下（中间步超过 10 个）就放宽 delta 等分。
    与 driver5.step_ladder 是同一个实现（5 版先写，这里保持一致）。
    """
    span = float(final_v) - float(init_v)
    if abs(span) < 1e-9 or float(delta_v) <= 0:
        return []
    n_cells = int(abs(span) / float(delta_v) + 0.5)
    n_cells = max(n_cells, 1)
    if n_cells - 1 > max_steps:
        n_cells = max_steps + 1
    step = span / n_cells
    return [round(init_v + step * k, 6) for k in range(1, n_cells)]


@dataclass
class StepSpec:
    """任意恒电位阶梯波(多电位阶跃)。

    控件 id 取自 5 版实测控件表（p131，frmPotSquareWave）；6 版同类窗口
    与 5 版共用一套 id（OCP/Tafel/EIS 三个窗均已证实同源）。
    """
    KIND: ClassVar[str] = EXP_STEP
    file: str = ""
    init_v: float = -0.2
    final_v: float = 0.5
    delta_v: float = 0.05
    # 用户指定：中间电位都不选，初始/终止各保持 2 s，循环 20 个周期
    hold_s: float = 2.0
    freq_hz: float = 10.0
    cycles: int = 20
    use_steps: bool = False                     # False = 中间电位全不勾选
    edits: dict = field(default_factory=dict)   # 兼容旧接口：额外 aid→值


@dataclass
class EisSpec:
    """交流阻抗-频率扫描(电位控制模式) / Nyquist+Bode。

    6 版菜单：测试方法(E) → 交流阻抗 → 频率扫描-电位控制模式(Nyquist, Bode)
    5 版菜单：测试方法(E) → 交流阻抗 → 阻抗~频率扫描(F)
    字段 id 取自 5 版实测；6 版大概率同名（OCP/Tafel 两个窗已证实同名）。
    """
    KIND: ClassVar[str] = EXP_EIS
    file: str = ""
    dc_v: float = 0.0              # 直流电位(V)，相对开路时 0 = 不外加极化
    amp_mv: float = 10.0           # 交流幅值(mV)
    init_freq: float = 100000.0    # 初始频率(Hz)
    final_freq: float = 0.01       # 终止频率(Hz)
    pts_per_decade: float = 10.0   # 点/10倍频
    vs_ocp: bool = True


def _kind_of(name: str, desc: str) -> str:
    blob = (name or "") + " " + (desc or "")
    if "阶梯波" in blob or "阶跃" in blob or "多电位" in blob:
        return EXP_STEP
    if "阻抗" in blob or "频率扫描" in blob or "EIS" in blob.upper():
        return EXP_EIS
    if "Tafel" in blob or "动电位" in blob or "LPR" in blob:
        return EXP_TAFEL
    if "开路电位" in blob or "OCP" in blob:
        return EXP_OCP
    return "other"


def _click_by_id(ui: Studio, root, aid: str) -> bool:
    c = ui.by_id(aid, root)
    if c is None:
        return False
    try:
        c.click_input()
        time.sleep(0.2)
        return True
    except Exception:
        return False


def _checkstate(ui: Studio, root, aid: str):
    """返回复选框勾选状态；控件不存在返回 None。"""
    c = ui.by_id(aid, root)
    if c is None:
        return None
    try:
        return c.get_toggle_state() == 1
    except Exception:
        try:
            return (c.legacy_properties() or {}).get("CheckState") == 1
        except Exception:
            return None


class ParasiteDriver:
    def __init__(self, ui: Optional[Studio] = None, log=None):
        self.ui = ui or Studio()
        self._log = log or (lambda m: None)
        self.channel_title: Optional[str] = None

    def log(self, msg: str) -> None:
        self._log(msg)

    # ---------- 通道 ----------
    def find_channel(self) -> Optional[str]:
        for c in self.ui.descendants():
            try:
                if c.element_info.control_type == "Window":
                    t = c.window_text() or ""
                    if t.startswith("通道") and "型号" in t:
                        self.channel_title = t
                        return t
            except Exception:
                continue
        return None

    def ensure_channel(self) -> bool:
        """确保有通道窗口；没有就点「工作通道 → 通道 1」。"""
        if self.find_channel():
            return True
        if not self.ui.click_menu("%c", "通道 1"):
            # 演示模式下菜单热键是 Alt+C
            if not self.ui.click_menu("%c", "通道 1"):
                return False
        for _ in range(20):
            if self.find_channel():
                time.sleep(0.4)
                return True
            time.sleep(0.25)
        return False

    def activate(self) -> bool:
        """让通道窗口成为活动 MDI 子窗口（否则第一次点工具栏会被吞掉）。"""
        t = self.find_channel()
        if not t:
            return False
        for c in self.ui.descendants():
            try:
                if c.element_info.control_type == "Window" and (c.window_text() or "") == t:
                    c.click_input()
                    time.sleep(0.3)
                    return True
            except Exception:
                continue
        return False

    # ---------- 序列 ----------
    def seq_clear(self) -> bool:
        if not self.activate():
            return False
        ok = self.ui.click_toolbar("seq", "清空", wait=0.8)
        self._dismiss_any("clear")
        return ok

    def rows_desc(self) -> List[str]:
        out = []
        for r in self.ui.rows():
            out.append(" | ".join(r))
        return out

    def read_sequence(self) -> List[dict]:
        """读现有序列（不改结构，符合"寄生不扰动"原则）。

        返回 [{index, name, desc, file, kind}]，kind ∈ OCP/Tafel/Step/other。
        """
        out = []
        for i, r in enumerate(self.ui.rows()):
            name = r[1] if len(r) > 1 else ""
            desc = r[2] if len(r) > 2 else ""
            file = r[3] if len(r) > 3 else ""
            out.append({
                "index": i,
                "name": name.strip(),
                "desc": desc.strip(),
                "file": file.strip(),
                "kind": _kind_of(name, desc),
            })
        return out

    def sequence_plan(self) -> List[str]:
        return ["%d. [%s] %s" % (r["index"] + 1, r["kind"], r["file"]) for r in self.read_sequence()]

    def configure_row(self, index: int, spec) -> bool:
        """双击第 index 行打开它的参数窗，按 spec 填好并确定。"""
        if not self.activate():
            self.log("激活通道窗口失败")
            return False
        self.ui.clear_modals(3)
        panel = self.ui.open_row_panel(index)
        if panel is None:
            self.log("双击第 %d 行没打开参数窗" % (index + 1))
            return False
        time.sleep(0.4)
        title = panel.window_text() or ""
        try:
            return self._fill_panel(panel, spec)
        finally:
            # 参数窗若还开着就关掉，避免挡住后续点击
            w = self.ui.window_titled(title) if title else None
            if w is not None:
                self.ui.press_cancel(w)
                time.sleep(0.4)

    def _fill_panel(self, panel, spec) -> bool:
        kind = getattr(spec, "KIND", None)
        if kind == EXP_OCP:
            ok = self.fill_ocp_panel(panel, spec)
        elif kind == EXP_TAFEL:
            ok = self.fill_tafel_panel(panel, spec)
        elif kind == EXP_STEP:
            ok = self.fill_step_panel(panel, spec)
        elif kind == EXP_EIS:
            ok = self.fill_eis_panel(panel, spec)
        else:
            self.log("不认识的实验类型：%r" % kind)
            return False
        return ok and self._confirm_with_prompt(panel)

    def _click_prompt(self, w, labels) -> bool:
        """模态提示框上的按钮：优先 UIA invoke，退回坐标点击；点完确认消失。"""
        for label in labels:
            b = self.ui.button(label, w)
            if b is None:
                continue
            for act in ("invoke", "click_input"):
                try:
                    getattr(b, act)()
                except Exception:
                    continue
                time.sleep(0.9)
                if self.ui.window_titled("提示") is None:
                    return True
        return False

    def _confirm_with_prompt(self, panel) -> bool:
        """点参数窗的确定；若弹出参数校验「提示」就点「是(Y)」继续。

        实测 Tafel 设了过高采样频率（如 50 mV/s + 0.01 s）会弹：
        「采样频率过高，建议降低采样频率或增加电位间隔，是否继续修改？」
        """
        ok = self.ui.press_ok(panel)
        time.sleep(0.9)
        for _ in range(5):
            r = self.ui.close_win32_modal(prefer=("是(Y)", "是", "确定"))
            if r is None:
                break
            self.log("参数校验对话框：[%s] %s -> 点了 %s" % r)
            if r[1] and "请输入正确" in r[1]:
                # 值本身非法，点确定没用，直接放弃
                self.log("值校验失败，放弃本次配置")
                return False
        closed = self.ui.window_titled(panel.window_text() or "") is None
        self.log("参数窗已关闭=%s" % closed)
        return closed

    def _dismiss_any(self, tag: str = "") -> None:
        kw = self.ui.any_blocking_dialog()
        if kw:
            self.log("出现对话框[%s]，尝试确认关闭" % kw)
            if not self.ui.dismiss_duplicate_prompt("overwrite"):
                for label in ("确定", "是(Y)", "是"):
                    b = self.ui.button(label)
                    if b is not None:
                        b.click_input()
                        time.sleep(0.6)
                        break

    # ---------- 添加实验 ----------
    def _combo_value(self, combo) -> str:
        try:
            return (combo.legacy_properties() or {}).get("Value", "") or ""
        except Exception:
            return ""

    @staticmethod
    def _exp_popups():
        """可见的自绘下拉浮层（顶层 WindowsForms10.Window.20808 窗）。"""
        import win32gui
        found = []

        def cb(h, _):
            try:
                if win32gui.IsWindowVisible(h) and "20808" in win32gui.GetClassName(h):
                    r = win32gui.GetWindowRect(h)
                    if (r[2] - r[0]) > 150 and (r[3] - r[1]) > 60:
                        found.append((h, r))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, None)
        return found

    def _pick_item_by_uia(self, dlg, key: str) -> bool:
        """在 cboExp 浮层树里选中名为 key 的条目（2026-11-06 重写）。

        旧版用「32px 行距盲点」——probe_seed6f/6g/6h 截图+UIA 实证推翻：
          * 浮层是树形列表（常用/稳态极化/暂态极化/…分组），行距 23px；
          * 条目只能点 UIA BoundingRectangle 的真实矩形（点行缝/外围无效，
            首次点击常常只夺焦点，要点第二次）；
          * 滚轮对这棵自绘树无效，滚动要拖它右侧滚动条；
          * 列表项文本带后缀（任意恒电位阶梯波(多电位阶跃)），匹配用
            精确或前缀（startswith 天然排除「特征频率扫描…」这类变体）。
        """
        from pywinauto import Desktop

        combo = None
        for c in dlg.descendants():
            try:
                if c.element_info.automation_id == "cboExp":
                    combo = c
                    break
            except Exception:
                continue
        if combo is None:
            self.log("找不到 cboExp 下拉")
            return False

        def read_val():
            try:
                return combo.legacy_properties().get("Value", "") or ""
            except Exception:
                return ""

        # 初值已经是目标（LastSelectExp 记忆）就直接成功
        if key in read_val():
            self.log("实验类型本就是 %s" % key)
            return True

        try:
            dlg.set_focus()
        except Exception:
            pass
        time.sleep(0.4)
        ps = []
        for _ in range(2):
            try:
                combo.click_input()
            except Exception as e:
                self.log("展开浮层异常：%s" % e)
            time.sleep(0.9)
            ps = self._exp_popups()
            if ps:
                break
        if not ps:
            self.log("浮层没展开")
            return False

        def click(x, y):
            import win32api
            import win32con
            win32api.SetCursorPos((int(x), int(y)))
            time.sleep(0.2)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.6)

        found_rect = None
        wheels = 0
        while wheels < 10 and found_rect is None:
            h, pr = self._exp_popups()[0]
            pop_win = Desktop(backend="uia").window(handle=h)
            for c in pop_win.descendants():
                try:
                    if c.element_info.control_type != "TreeItem":
                        continue
                    t = (c.window_text() or "").strip()
                    if not (t == key or t.startswith(key)):
                        continue
                    r = c.rectangle()
                    if r.width() > 20 and r.height() > 5:
                        found_rect = (r.left, r.top, r.right, r.bottom)
                        break
                except Exception:
                    continue
            if found_rect is None:
                # 拖浮层右侧滚动条（滚轮无效）；找不到滚动条就盲拖右缘
                sb_x = pr[2] - 8
                top_y, bot_y = pr[1] + 16, pr[3] - 16
                import win32api
                import win32con
                mid = (top_y + bot_y) // 2
                win32api.SetCursorPos((sb_x, mid))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.15)
                step_y = 60 if wheels % 2 == 0 else 120
                for yy in range(mid, bot_y, step_y):
                    win32api.SetCursorPos((sb_x, yy))
                    time.sleep(0.03)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.5)
                wheels += 1
        if found_rect is None:
            self.log("浮层里没找到 %s" % key)
            return False

        x = (found_rect[0] + found_rect[2]) // 2
        y = (found_rect[1] + found_rect[3]) // 2
        self.log("点击条目 %s @(%d,%d)" % (key, x, y))
        click(x, y)
        time.sleep(0.8)
        if key not in read_val():
            # 首次点击常只夺焦点；若还不行，UIA 矩形可能已随树重排而漂移
            # （虚拟化列表）——ESC 收浮层、重开、重新找矩形再点一轮
            # （verify_add_experiment 实测：第二轮才命中的情况真实存在）
            for retry in range(2):
                self.log("  选择未生效（值=%r），重开浮层重试第 %d 轮" % (read_val(), retry + 1))
                try:
                    from pywinauto.keyboard import send_keys as _sk
                    _sk("{ESC}")
                except Exception:
                    pass
                time.sleep(0.4)
                try:
                    combo.click_input()
                except Exception:
                    pass
                time.sleep(0.9)
                if not self._exp_popups():
                    continue
                h2, pr2 = self._exp_popups()[0]
                pop2 = Desktop(backend="uia").window(handle=h2)
                rect2 = None
                for c in pop2.descendants():
                    try:
                        if c.element_info.control_type != "TreeItem":
                            continue
                        t = (c.window_text() or "").strip()
                        if not (t == key or t.startswith(key)):
                            continue
                        r = c.rectangle()
                        if r.width() > 20 and r.height() > 5:
                            rect2 = (r.left, r.top, r.right, r.bottom)
                            break
                    except Exception:
                        continue
                if rect2 is None:
                    continue
                click((rect2[0] + rect2[2]) // 2, (rect2[1] + rect2[3]) // 2)
                time.sleep(0.8)
                if key in read_val():
                    break
        if key not in read_val():
            self.log("点击后值=%r，选择失败" % read_val())
            return False
        if self._exp_popups():
            # 收浮层：点对话框标题栏（浮层下拉在 combo 下方，不盖标题栏）
            dr = dlg.rectangle()
            click(dr.left + dr.width() // 2 - 120, dr.top + 10)
            time.sleep(0.6)
            if key not in read_val():
                self.log("收浮层后选择丢失（%r）" % read_val())
                return False
        self.log("实验类型已切到 %s" % key)
        return True

    @staticmethod
    def _dropdown_open() -> bool:
        """下拉浮层是否真的展开了（纯自绘窗口，只能按类名+尺寸找）。"""
        import win32gui
        found = []

        def cb(h, acc):
            try:
                if not win32gui.IsWindowVisible(h):
                    return True
                cls = win32gui.GetClassName(h)
                if "WindowsForms10.Window.20808" not in cls:
                    return True
                r = win32gui.GetWindowRect(h)
                if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 100:
                    acc.append(h)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, found)
        return bool(found)

    def pick_experiment(self, dlg, kind: str) -> bool:
        """（v2）把「添加」对话框的实验类型切到 kind。

        旧版 32px 盲点实现已废弃（浮层实为 23px 树形列表，见
        _pick_item_by_uia 的实证注释）；本方法保留旧签名做兼容入口。
        """
        return self._pick_item_by_uia(dlg, EXP_COMBO_TEXT[kind])

    def add_experiment(self, kind: str) -> Optional[object]:
        """点「添加」→ 切实验类型 → 确定 → 返回弹出的参数窗（还没填参数）。"""
        if not self.activate():
            self.log("激活通道窗口失败")
            return None
        self.ui.click_toolbar("seq", "添加", wait=1.6)
        time.sleep(0.6)

        dlg = self.ui.window_titled("添加")
        if dlg is None:
            self.log("没等到「添加」对话框")
            return None

        for c in dlg.descendants():
            try:
                ei = c.element_info
                if ei.control_type == "RadioButton" and "测量方法" in (c.window_text() or ""):
                    c.click_input()
                    time.sleep(0.25)
                    break
            except Exception:
                continue

        # v2：_pick_item_by_uia 内部完成 选条目→收浮层→值校验
        if not self._pick_item_by_uia(dlg, EXP_COMBO_TEXT[kind]):
            self.log("切换实验类型失败：%s" % EXP_COMBO_TEXT[kind])
            self.ui.press_cancel(dlg)
            return None

        ok = self.ui.by_id("buttonOK", dlg)
        if ok is None:
            ok = self.ui.button("确定", dlg)
        if ok is None:
            self.log("「添加」对话框没找到确定按钮")
            return None
        try:
            ok.click_input()
        except Exception as e:
            self.log("点确定异常：%s" % e)
        time.sleep(1.6)
        if self.ui.window_titled("添加") is not None:
            self.log("「添加」对话框没关闭，重试点确定")
            self.ui.press_ok(dlg)
            time.sleep(1.4)

        panel = None
        for kw in (EXP_COMBO_TEXT[kind], "开路电位", "动电位", "阶梯波"):
            panel = self.ui.window_titled(kw)
            if panel is not None:
                break
        if panel is None:
            self.log("没等到 %s 参数窗" % kind)
        return panel

    # ---------- OCP ----------
    def fill_ocp_panel(self, panel, spec: OcpSpec) -> bool:
        """在已打开的 OCP 参数窗里填参数。"""
        # set_edit 返回值必须累积：框非空不代表写入的是新值
        # （set_edit 失败时框里还是旧值，"框非空"会冒充成功——
        # 2026-11-06 代码审查 P2，对齐 driver5 的 ok &= 写法）
        ok = True
        ok &= self.ui.set_edit("Control_FileName_Text", spec.file, panel)
        ok &= self.ui.set_edit("Ocp_Param_Text", str(int(spec.test_time_sec)), panel)
        # 采样频率（先切到频率单选，否则值框 disabled）
        _click_by_id(self.ui, panel, "FrqControl_Frq_Radio")
        ok &= self.ui.set_edit("FrqControl_Frq_Text", _fmt_num(spec.freq_hz), panel)
        if _checkstate(self.ui, panel, "chkStopByDeltaE"):
            _click_by_id(self.ui, panel, "chkStopByDeltaE")
        elif not spec.use_delta_stop:
            pass
        got = self.ui.get_edit("Ocp_Param_Text", panel)
        fgot = self.ui.get_edit("Control_FileName_Text", panel)
        self.log("OCP 参数填写 文件=%r 回读时间=%r" % (fgot, got))
        return bool(ok)

    def add_ocp(self, spec: OcpSpec) -> bool:
        panel = self.add_experiment(EXP_OCP)
        if panel is None:
            return False
        return self.fill_ocp_panel(panel, spec)

    # ---------- Tafel ----------
    def fill_tafel_panel(self, panel, spec: TafelSpec) -> bool:
        # 同 fill_ocp_panel：必须累积 set_edit 返回值（2026-11-06 代码审查 P2）
        ok = True
        ok &= self.ui.set_edit("Control_FileName_Text", spec.file, panel)
        ok &= self.ui.set_edit("PotDynamic_InitialPot_txt", _fmt_num(spec.init_v), panel)
        ok &= self.ui.set_edit("PotDynamic_FinalPot_txt", _fmt_num(spec.final_v), panel)
        ok &= self.ui.set_edit("PotDynamic_ScanRate_txt", _fmt_num(spec.scan_mv_s), panel)
        # 采样间隔优先（默认就是选中的）
        _click_by_id(self.ui, panel, "SampleInterval_radio")
        ok &= self.ui.set_edit("SampleInterval_txt", _fmt_num(spec.sample_interval_s), panel)
        fgot = self.ui.get_edit("Control_FileName_Text", panel)
        iv = self.ui.get_edit("PotDynamic_InitialPot_txt", panel)
        fv = self.ui.get_edit("PotDynamic_FinalPot_txt", panel)
        sr = self.ui.get_edit("PotDynamic_ScanRate_txt", panel)
        self.log("Tafel 参数填写 文件=%r Init=%r Final=%r Scan=%r" % (fgot, iv, fv, sr))
        return bool(ok)

    def add_tafel(self, spec: TafelSpec) -> bool:
        panel = self.add_experiment(EXP_TAFEL)
        if panel is None:
            return False
        return self.fill_tafel_panel(panel, spec)

    # ---------- 阶梯波（任意恒电位阶梯波 frmPotSquareWave）----------
    def _select_combo_containing(self, panel, aid: str, want: str,
                                 max_tries: int = 6) -> bool:
        """在下拉里选中值包含 want 的项：键盘导航+读回校验，不怕项序。"""
        c = self.ui.by_id(aid, panel)
        if c is None:
            self.log("  缺下拉 %s" % aid)
            return False
        try:
            cur = c.legacy_properties().get("Value") or ""
        except Exception:
            cur = ""
        if want in str(cur):
            return True
        from pywinauto import keyboard as _kb
        for k in ("{HOME}", "{END}", "{DOWN}", "{DOWN}", "{DOWN}", "{UP}"):
            try:
                c.click_input()
                time.sleep(0.4)
                _kb.send_keys(k)
                time.sleep(0.3)
                _kb.send_keys("{ENTER}")
                time.sleep(0.4)
                cur = c.legacy_properties().get("Value") or ""
            except Exception as e:
                self.log("  下拉 %s 导航失败：%s" % (aid, e))
                return False
            if want in str(cur):
                return True
        self.log("  下拉 %s 里找不到含 %r 的项（当前 %r）" % (aid, want, cur))
        return False

    def fill_step_panel(self, panel, spec: "StepSpec") -> bool:
        """填「任意恒电位阶梯波」参数。

        结构：初始电位(持续时间) → 中间电位1..N(各带持续时间/启用勾选)
        → 终止电位(持续时间)，循环 cycles 圈。时间单位固定 s，
        极化电位基准选「相对开路」（与 Tafel 的 vs OCP 一致）。
        """
        ui = self.ui
        # use_steps=False（默认）时中间电位全部不勾选，只在初始/终止之间跳
        steps = step_ladder(spec.init_v, spec.final_v, spec.delta_v) \
            if getattr(spec, "use_steps", False) else []
        ok = ui.set_edit("Control_FileName_Text", spec.file, panel)
        self._select_combo_containing(panel, "PotSquare_TimeUnit_cbo", "s")
        self._select_combo_containing(panel, "Vs_Combo", "开路")
        for aid, val in (("PotSquare_InitialE_txt", "%.4f" % spec.init_v),
                         ("PotSquare_InitTime_txt", "%g" % spec.hold_s),
                         ("PotSquare_FinalE_txt", "%.4f" % spec.final_v),
                         ("PotSquare_FinalTime_txt", "%g" % spec.hold_s)):
            ok &= bool(ui.set_edit(aid, val, panel))
        for i in range(1, 11):
            en_id = "PotSquare_Step%d_chb" % i
            e_id = "PotSquare_Step%d_txt" % i
            t_id = "PotSquare_Step%dTime_txt" % i
            want_on = i <= len(steps)
            chb = ui.by_id(en_id, panel)
            if chb is not None:
                try:
                    on = chb.get_toggle_state() == 1
                    if on != want_on:
                        chb.click_input()
                        time.sleep(0.2)
                except Exception:
                    pass
            if want_on:
                if ui.by_id(e_id, panel) is not None:
                    ok &= bool(ui.set_edit(e_id, "%.4f" % steps[i - 1], panel))
                if ui.by_id(t_id, panel) is not None:
                    ok &= bool(ui.set_edit(t_id, "%g" % spec.hold_s, panel))
        ok &= bool(ui.set_edit("PotSquare_Cycles_txt", str(int(spec.cycles)), panel))
        _click_by_id(ui, panel, "FrqControl_Frq_Radio")
        ok &= bool(ui.set_edit("FrqControl_Frq_Text", _fmt_num(spec.freq_hz), panel))
        for aid, val in getattr(spec, "edits", {}).items():
            ui.set_edit(aid, _fmt_num(val), panel)
        fgot = ui.get_edit("Control_FileName_Text", panel)
        self.log("阶梯波参数填写 文件=%r %g→%g V 中间%d步 每步%gs"
                 % (fgot, spec.init_v, spec.final_v, len(steps), spec.hold_s))
        return bool(fgot) and ok

    # ---------- 交流阻抗（频率扫描-电位控制模式）----------
    def fill_eis_panel(self, panel, spec: "EisSpec") -> bool:
        # 同 fill_ocp_panel：必须累积 set_edit 返回值（2026-11-06 代码审查 P2）
        ok = True
        ok &= self.ui.set_edit("Control_FileName_Text", spec.file, panel)
        for aid, val in (("EISVSfrq_SineBias_Text", spec.dc_v),
                         ("EISVSfrq_SineAmp_Text", spec.amp_mv),
                         ("EISVSfrq_InitFre_Text", spec.init_freq),
                         ("EISVSfrq_FinalFre_Text", spec.final_freq),
                         ("EISVSfrq_TenTwice_Text", spec.pts_per_decade)):
            ok &= self.ui.set_edit(aid, _fmt_num(val), panel)
        fgot = self.ui.get_edit("Control_FileName_Text", panel)
        rb = {}
        for aid in ("EISVSfrq_SineBias_Text", "EISVSfrq_SineAmp_Text",
                    "EISVSfrq_InitFre_Text", "EISVSfrq_FinalFre_Text",
                    "EISVSfrq_TenTwice_Text"):
            try:
                rb[aid] = self.ui.get_edit(aid, panel)
            except Exception:
                rb[aid] = None
        self.log("阻抗参数填写 文件=%r 回读=%r" % (fgot, rb))
        return bool(ok)

    def add_eis(self, spec: "EisSpec") -> bool:
        panel = self.add_experiment(EXP_EIS)
        if panel is None:
            return False
        return self.fill_eis_panel(panel, spec)

    # ---------- 启动 / 停止 ----------
    def set_cell_area(self, row_index: int, area_cm2: float,
                      density: Optional[float] = 7.93,
                      temperature: Optional[float] = 25.0) -> bool:
        """通过任意实验参数窗的「电解池」入口设置试样面积（cm²）。

        电解池参数是全局的；设完点确定保存，再取消参数窗本身以不改实验参数。
        材料密度（Elec_Elec_Density_Text）统一设 7.93 —— 用户 2026-11-04
        明确「所有的测试项目中的材料密度都是 7.93」；density=None 表示不动它。
        """
        if not self.activate():
            return False
        self.ui.clear_modals(2)
        panel = self.ui.open_row_panel(row_index)
        if panel is None:
            self.log("set_cell_area: 打不开参数窗")
            return False
        try:
            btn = self.ui.by_id("Btn_Cell", panel)
            if btn is None:
                self.log("set_cell_area: 找不到电解池按钮")
                return False
            btn.click_input()
            time.sleep(1.6)
            cell = None
            for t, c in self.ui.panels():
                if ("电极" in t) or ("电解池" in t):
                    cell = c
            if cell is None:
                self.log("set_cell_area: 电解池窗没出现")
                return False
            old = self.ui.get_edit("Elec_Elec_Area_Text", cell)
            ok = self.ui.set_edit("Elec_Elec_Area_Text", ("%g" % float(area_cm2)), cell)
            self.log("试样面积 %s -> %s (ok=%s)" % (old, area_cm2, ok))
            # 溶液温度（用户 2026-11-04 写死）
            if temperature is not None:
                t_old = self.ui.get_edit("Elec_Cell_Temp_Text", cell)
                t_ok = self.ui.set_edit("Elec_Cell_Temp_Text",
                                        ("%g" % float(temperature)), cell)
                self.log("溶液温度 %s -> %s (ok=%s)" % (t_old, temperature, t_ok))
            # 材料密度统一 7.93（用户 2026-11-04：所有测试项目都是 7.93）
            if density is not None:
                d_old = self.ui.get_edit("Elec_Elec_Density_Text", cell)
                d_ok = self.ui.set_edit("Elec_Elec_Density_Text",
                                        ("%g" % float(density)), cell)
                self.log("材料密度 %s -> %s (ok=%s)" % (d_old, density, d_ok))
            self.ui.press_ok(cell)
            time.sleep(0.8)
            self.ui.clear_modals(2)
            return ok
        finally:
            try:
                self.ui.press_cancel(panel)
            except Exception:
                pass
            time.sleep(0.6)
            self.ui.clear_modals(2)

    def start(self, timeout: float = 8.0) -> bool:
        if not self.activate():
            return False
        self.ui.click_toolbar("seq", "开始", wait=1.0)
        # 处理"文件重复"提示
        end = time.time() + timeout
        while time.time() < end:
            if self.ui.dismiss_duplicate_prompt("overwrite"):
                self.log("已自动处理「文件重复」提示（覆盖）")
                return True
            kw = self.ui.any_blocking_dialog()
            if kw and kw != "提示":
                self.log("启动时出现对话框：%s" % kw)
                for label in ("确定", "是"):
                    b = self.ui.button(label)
                    if b is not None:
                        b.click_input()
                        time.sleep(0.6)
                        break
                return False
            time.sleep(0.3)
        return True

    def stop_current(self) -> bool:
        """点数据窗口工具栏「停止」：中止当前实验，序列自动进入下一项。"""
        ok = self.ui.click_toolbar("data", "停止", wait=0.8)
        self.log("点停止 ok=%s" % ok)
        return ok

    def abort_sequence(self) -> bool:
        """彻底停：序列工具栏的停止。"""
        ok = self.ui.click_toolbar("seq", "停止", wait=0.8)
        self.log("点序列停止 ok=%s" % ok)
        return ok


def _fmt_num(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.6f" % v).rstrip("0").rstrip(".")
