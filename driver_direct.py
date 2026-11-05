# -*- coding: utf-8 -*-
"""6 版（CS Studio6）「直开窗口」流程的驱动层。

与 `driver.ParasiteDriver` 的区别：**不碰序列**。
用主工具栏按钮直接弹出某个实验的参数窗，填完点「确定」立刻开跑，
跑完用同一个思路开下一个实验。完全绕开了「添加」对话框里那个
按使用历史漂移的自绘下拉（cboExp）。

实测（演示模式）：
    主工具栏 [1] → 开路电位测量(OCP)                  automation_id 与序列双击开的一样
    主工具栏 [3] → 动电位扫描(Tafel,LPR)
    主工具栏 [5] → 频率扫描-电位控制模式(Nyquist, Bode)
点「确定」后**立即开跑**，序列内容不变。

注意：按钮索引会随窗口状态变化，所以每次先按「所开窗口的标题」确认，
索引只作为首选值，不匹配时按 1..13 逐个试。
"""
import re
import time
from typing import Optional, Tuple

import win32con
import win32gui
from pywinauto import mouse
from pywinauto.keyboard import send_keys

import studio_ui as S

# 运行窗标题判据（2026-11-06 整理，配合 test_run_title.py 的实测样例）：
#   6 版运行窗是 MDI 子窗，标题 "[通道1]-开路电位测量(OCP) <数据文件> [2mA]"
#   （演示模式无 [量程] 段）；通道窗本身是 "通道1【型号：…】"（无 "-"），
#   绝不能混。另有两类独立图形窗："波形图"、"图形显示"。
RUN_TITLE_RE = re.compile(
    r"^\[通道\d+\]-"          # MDI 运行子窗前缀
    r"|^\[通道\d+\] "         # 变体：空格分隔
    r"|波形图|图形显示"
)


def is_run_title(title: str) -> bool:
    """判断窗口标题是不是一个实验运行窗（绝不把通道窗/主窗算进来）。"""
    t = (title or "").strip()
    if not t or "CS Studio" in t:
        return False
    return bool(RUN_TITLE_RE.search(t))


# 主工具栏按钮索引（实测值）
DIRECT_BTN = {"ocp": 1, "tafel": 3, "eis": 5, "step": 11}

# 「测试方法(E)」菜单路径：一级菜单 → 二级菜单 → 三级菜单项
# 6 版在「工作通道」菜单消失之后，这条路径仍然可用（实测 2026-11-05）
MENU_PATH = {
    "ocp":   ("测试方法(E)", "稳态极化", "开路电位测量(OCP)"),
    "tafel": ("测试方法(E)", "稳态极化", "动电位扫描(Tafel,LPR)"),
    "eis":   ("测试方法(E)", "交流阻抗", "频率扫描-电位控制模式"),
    # 菜单项显示名不带快捷键后缀（写成「任意恒电位阶梯波(A)」会匹配不上）
    "step":  ("测试方法(E)", "暂态极化", "任意恒电位阶梯波"),
}

# 一级菜单的 Alt 快捷键
MAIN_ALT = {"测试方法(E)": "%e", "系统设置(S)": "%s", "工作通道(C)": "%c"}

# 打开后应当出现的窗口标题关键字
DIRECT_TITLE = {
    "ocp": "开路电位测量(OCP)",
    "tafel": "动电位扫描(Tafel,LPR)",
    "eis": "频率扫描-电位控制模式",
    "step": "任意恒电位阶梯波",
}

# 参数窗的 automation_id（与序列模式相同）
PARAM_ID = {"ocp": "frmOCP", "tafel": "frmPotDynamic", "eis": "frmEISVSfrq",
            "step": "frmPotSquareWave"}


def _log_noop(*a):
    pass


class DirectDriver:
    """直开窗口模式的驱动。复用 Studio（UIA 封装）+ ParasiteDriver 的面积设置等。"""

    def __init__(self, ui, base, log=print):
        self.ui = ui
        self.base = base          # driver.ParasiteDriver，提供 set_edit / configure_row 等
        self.log = log
        self._tb = None
        self.last_error = None    # "no_device" / None，供上层区分"打不开"的原因

    # ---------- 基础 ----------
    def get_toolbar(self, retries: int = 6):
        """取主工具栏。不缓存：实验启停后 UIA 元素会失效，且主窗会重排。"""
        for attempt in range(retries):
            self._tb = None
            try:
                if self.ui.main is None or not self.ui.main.exists():
                    self.ui.acquire(3.0)
            except Exception:
                pass
            for c in self.ui.descendants():
                try:
                    if c.element_info.automation_id == "toolStrip":
                        self._tb = c
                        return c
                except Exception:
                    pass
            time.sleep(0.8)
        return None

    def is_running(self) -> bool:
        """是否正在跑实验。先走启发式，再用数据工具栏「停止」键的可用性
        排掉「运行窗残留（实验已停但窗口还开着）」的假阳性。"""
        if not self._is_running_heuristic():
            return False
        try:
            tb = self.ui._toolbar("data")
            if tb is not None:
                btns = self.ui._tb_buttons(tb)
                if btns:
                    return bool(btns[0].is_enabled())   # DATA_BTN 停止=0
        except Exception:
            pass
        return True

    def _is_running_heuristic(self) -> bool:
        # ① 主窗标题：实验开着时会被拼成
        #    "CS Studio6  演示模式 - [[通道1]-开路电位测量(OCP) <文件> [量程]]"
        #    注意必须用双括号 " - [["：通道本身的标题 "- [通道1【型号…】]"
        #    也含 " - ["，用单括号会把「没在跑」误判成「在跑」（实测踩坑）
        try:
            t0 = self.ui.title or ""
            if " - [[" in t0 and "通道" in t0:
                return True
        except Exception:
            pass
        # ② UIA：独立的运行窗（标题判据统一走 is_run_title）
        try:
            for t, _c in self.ui.panels():
                if is_run_title(t):
                    return True
        except Exception:
            pass
        # ②b MDI 子窗（6 版无通道窗时唯一可用的判据）
        if self.mdi_run_windows():
            return True
        # ② 窗口列表（5 版那种独立窗）
        if self.run_windows():
            return True
        # ③ 文件还在长
        try:
            for p, _sz, _mt in self._file_marks:
                import os
                if (os.path.exists(p) and os.path.getsize(p) > _sz + 32
                        and time.time() - os.path.getmtime(p) < 5.0):
                    return True
        except Exception:
            pass
        return False

    def _own_pids(self):
        """本软件（当前连接的那个 CS Studio 实例）的进程号集合。

        必须按 PID 过滤：本机可能同时开着 CS Studio5 和 CS Studio6，
        全局 EnumWindows 会把另一个软件的运行窗也算进来，
        一旦去"关运行窗"就会把对方正在跑的实验窗口关掉（实测踩过）。
        """
        pids = set()
        try:
            import win32process
            h = getattr(self.ui, "hwnd", None) or self.ui.main.handle
            _tid, pid = win32process.GetWindowThreadProcessId(h)
            if pid:
                pids.add(int(pid))
        except Exception:
            pass
        return pids

    def run_windows(self):
        hits = []
        pids = self._own_pids()

        def cb(h, _):
            try:
                if not win32gui.IsWindowVisible(h):
                    return True
                if pids:
                    import win32process
                    _tid, pid = win32process.GetWindowThreadProcessId(h)
                    if int(pid) not in pids:      # 不是本软件的窗口，一律跳过
                        return True
                t = win32gui.GetWindowText(h)
                if is_run_title(t):
                    hits.append((h, t))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, None)
        return hits

    def stop(self, tries: int = 4) -> bool:
        """停掉正在跑的实验，循环确认真的停下。

        注意：**没有通道窗时绝不能碰 data 工具栏** —— 那时 toolbars() 里那条
        "data" 实际指向主工具栏，一旦按索引点就会误触「CS Analysis」（外部程序），
        表现就是"一直弹数据分析软件"。
        """
        has_channel = False
        try:
            has_channel = self.base.channel_title is not None
        except Exception:
            has_channel = False
        for i in range(tries):
            if not self.is_running():
                return True
            if has_channel:
                try:
                    if self.ui.click_toolbar("data", "停止"):
                        time.sleep(1.2)
                        continue
                except Exception:
                    pass
            if has_channel:
                tb = self.get_toolbar(retries=3)
                if tb is not None:
                    # 逐个试、每试一个都查状态——原来"点一个就 break"会卡在
                    # 禁用键上，永远轮不到真正的停止键。
                    # 只试 7(开始)/8(停止)：9 是 CS Analysis 外部程序，不能乱点
                    for idx in (7, 8):
                        if not self.is_running():
                            break
                        try:
                            tb.button(idx).click_input()
                        except Exception:
                            continue
                        time.sleep(1.2)
                    self.ui.clear_modals(2)
            # 没有通道窗时**绝不点主工具栏**：6 版无通道时按钮索引整体位移，
            # 按索引点会落到「CS Analysis」（外部数据分析程序），
            # 表现就是"一直弹数据分析软件"。这种情况下只能靠关运行窗来中止。
            time.sleep(0.8)
        self.close_run_windows()
        return not self.is_running()

    def _mdi_run_windows(self):
        """6 版运行窗是 MDI 子窗：EnumWindows 抓不到，panels() 的尺寸过滤
        又会漏掉最大化的（~1450px 宽 > 1300 上限）——这里直接按标题特征查。"""
        out = []
        try:
            for c in self.ui.descendants():
                try:
                    if c.element_info.control_type != "Window":
                        continue
                    t = c.window_text() or ""
                    if "[通道" in t and ("<" in t or "mA" in t):
                        out.append(c)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def close_run_windows(self) -> int:
        """关掉实验运行窗。

        6 版的运行窗是 **MDI 子窗口**，win32 EnumWindows 枚举不到，
        只能通过 UIA 在主窗的 descendants 里找 control_type=Window。
        标题必须过 is_run_title()：旧版"标题非空就关"会把通道窗
        「通道1【型号：…】」也关掉（probe_rehearsal6 实测踩坑：
        通道窗一关，点「开始」就没有序列可跑了）。
        """
        import win32gui as _w

        n = 0
        # 1) UIA 里的 MDI 子窗
        try:
            for w in self.ui.main.descendants(control_type="Window"):
                try:
                    t = w.window_text() or ""
                except Exception:
                    continue
                if not is_run_title(t):
                    continue
                try:
                    w.close()
                    n += 1
                    time.sleep(0.6)
                    self.log("  关掉 MDI 运行窗：%s" % t[:56])
                except Exception:
                    pass
        except Exception:
            pass
        # 2) 顶层 owned 运行窗（演示模式的波形图等）
        for h in self.run_windows():
            try:
                t = _w.GetWindowText(h)
            except Exception:
                continue
            if "CS Studio" in t:
                continue
            try:
                _w.PostMessage(h, 0x0010, 0, 0)   # WM_CLOSE
                n += 1
                time.sleep(0.4)
            except Exception:
                pass
        return n

    def close_panels(self, keep=()) -> int:
        """关掉残留的参数窗（标题命中实验名但不是主窗/运行窗）。"""
        n = 0
        for t, c in list(self.ui.panels()):
            if any(k in t for k in keep):
                continue
            if any(k in t for k in ("开路电位测量", "动电位扫描", "频率扫描",
                                    "循环伏安", "恒电位极化", "添加",
                                    "一键通道控制")):
                try:
                    self.ui.press_cancel(c)
                    n += 1
                except Exception:
                    pass
        if n:
            time.sleep(0.5)
        return n

    def close_blockers(self) -> int:
        """关掉启动/操作时弹的「用户设置」「通讯配置向导」等挡路窗。"""
        n = 0
        for t, c in list(self.ui.panels()):
            if any(k in t for k in ("用户设置", "通讯配置向导", "快速实验定制",
                                    "提示", "警告", "错误")):
                try:
                    self.ui.press_cancel(c)
                    n += 1
                except Exception:
                    pass
        if n:
            self.log("关掉 %d 个挡路窗" % n)
            time.sleep(0.6)
        self.ui.clear_modals()
        return n

    def prepare(self) -> bool:
        """开窗前清场：停实验、关运行窗、关残留参数窗、清模态框。"""
        self.close_blockers()
        if self.is_running():
            self.log("检测到实验在跑，先停止")
            self.stop()
        self.close_run_windows()
        self.close_panels()
        self.ui.clear_modals()
        return True

    # ---------- 打开参数窗 ----------
    def _clear_before_open(self):
        """开窗前的统一清场。"""
        try:
            self.base.activate()
        except Exception:
            pass
        try:
            self.ui.main.set_focus()      # 主工具栏/菜单都在主窗上，必须让主窗在前台
            time.sleep(0.4)
        except Exception:
            pass
        self.ui.clear_modals()
        if self.is_running():
            self.log("开窗前先停掉在跑的实验")
            self.stop()
        self.close_run_windows()
        self.close_panels()
        self.close_blockers()

    def _ensure_menu_mode(self) -> None:
        """演示模式下 6 版会把「测试方法(E)」整条菜单换成「工作通道(C)」。

        probe_menu6b 实测（2026-11-05）：
            非演示：系统设置(S) / 测试方法(E) / 组合方法(B) / 窗口(W) / 帮助(H)
            演示中：系统设置(S) / 工作通道(C) / 组合方法(B) / 窗口(W) / 帮助(H)
        即演示模式**根本没有实验入口**（5 版不是这样，5 版演示模式能跑实验并出 .cor）。
        所以开窗前必须确认不在演示模式。
        """
        try:
            if not self.ui.is_demo:
                return
            self.log("当前是演示模式（6 版演示模式没有「测试方法(E)」菜单），先退出演示模式")
            self.close_blockers()
            if self.ui.click_menu("%s", "退出演示模式"):
                time.sleep(1.8)
                self.ui.clear_modals()
            self.log("退出后主窗：%r" % (self.ui.title,))
        except Exception as e:
            self.log("退出演示模式出错：%s" % e)

    def open_by_menu(self, kind: str) -> Optional[object]:
        """走「测试方法(E)」菜单开实验参数窗。

        6 版实测（2026-11-05，probe_menu6b / probe_step6）：
          测试方法(E) → 稳态极化 → 开路电位测量(OCP) / 动电位扫描(Tafel,LPR)
          测试方法(E) → 交流阻抗 → 频率扫描-电位控制模式(Nyquist, Bode)
          测试方法(E) → 暂态极化 → 任意恒电位阶梯波(多电位阶跃)   ← 菜单文字带后缀
        注意「暂态极化」「稳态极化」「交流阻抗」这三个二级项**不带**快捷键后缀。

        无设备时的行为（已实测）：菜单能一路点到三级，但点下去会弹
        「通讯配置向导-第一步」，配不上设备就放弃开窗。这不是本驱动的 bug，
        上层应据此报"需要设备"而不是傻重试。
        """
        self._ensure_menu_mode()
        path = MENU_PATH.get(kind)
        if not path:
            self.log("未知实验类型：%s" % kind)
            return None
        main_menu, sub_menu, item = path
        want = DIRECT_TITLE.get(kind, item)

        def _snap():
            return set(p.window_text() for p in
                       self.ui.main.descendants(control_type="Window"))

        def _find_new(before):
            for p in self.ui.main.descendants(control_type="Window"):
                t = p.window_text()
                if t and t not in before and want in t:
                    return p
            return None

        fail_kind = None      # "no_device" / "no_response"
        miss = 0
        for attempt in range(1, 3):
            self._clear_before_open()
            before = _snap()
            try:
                # ① 展开一级菜单
                self.ui.force_foreground()
                time.sleep(0.3)
                alt = MAIN_ALT.get(main_menu)
                if alt:
                    opened = self.ui.open_menu(alt)
                else:
                    opened = self.ui.click_menu(main_menu.split("(")[0], None)
                if not opened:
                    self.log("菜单栏里没有「%s」（演示模式下 6 版会隐藏这一项）" % main_menu)
                    return None
                time.sleep(0.6)

                # ② 悬停二级菜单项展开子菜单（点 rect 中心，不能溢出到相邻区域）
                subs = [m for m in self.ui.main.descendants(control_type="MenuItem")
                        if (m.window_text() or "").strip() == sub_menu]
                if not subs:
                    # 二级项可能带「(T)」这类后缀，退一步按前缀匹配
                    subs = [m for m in self.ui.main.descendants(control_type="MenuItem")
                            if (m.window_text() or "").strip().startswith(sub_menu)]
                if not subs:
                    self.log("菜单里找不到「%s」（第 %d 次）" % (sub_menu, attempt))
                    continue
                r = subs[0].rectangle()
                if not r.width():
                    self.log("「%s」未展开（第 %d 次）" % (sub_menu, attempt))
                    continue
                mouse.move(coords=(r.left + 15, r.top + r.height() // 2))
                time.sleep(1.6)

                # ③ 点三级菜单项：hover 后必须立刻点（一停顿菜单就收起）
                # 菜单项名可能带后缀（如「频率扫描-电位控制模式(Nyquist, Bode)」），
                # 所以先精确匹配，再退回包含匹配。
                its = [m for m in self.ui.main.descendants(control_type="MenuItem")
                       if (m.window_text() or "").strip() == item]
                if not its:
                    its = [m for m in self.ui.main.descendants(control_type="MenuItem")
                           if item and item in (m.window_text() or "")]
                if not its:
                    self.log("子菜单里找不到「%s」（第 %d 次）" % (item, attempt))
                    continue
                rr = its[0].rectangle()
                if not rr.width():
                    self.log("「%s」不可见（第 %d 次）" % (item, attempt))
                    continue
                pt = (rr.left + 15, rr.top + rr.height() // 2)
                mouse.move(coords=pt)
                mouse.click(coords=pt)
                time.sleep(2.2)

                pnl = _find_new(before)
                if pnl is not None:
                    self.log("已打开「%s」（菜单路径）" % want)
                    return pnl
                # 被「通讯配置向导」拦住 = 没有设备。重试三次也没用，直接如实上报。
                wiz = [t for t, _c in self.ui.panels() if "通讯配置向导" in t]
                if wiz:
                    self.log("被「%s」拦住：软件没找到设备，拒绝打开「%s」参数窗"
                             % (wiz[0], want))
                    self.log("  → 6 版无设备时点任何实验都会先要求配通讯，配不上就放弃开窗")
                    self.last_error = "no_device"
                    self.close_blockers()
                    return None
                self.log("点了「%s」但没出现参数窗（第 %d 次）" % (item, attempt))
                miss += 1
                if miss >= 2:
                    # 点了两次都既不弹参数窗也不弹向导 = 软件静默忽略（典型是无设备且
                    # 已处于「设备未连接」态）。再重试只是白等，如实上报。
                    self.log("菜单点得动但软件没响应：判定为无设备/未连接，停止重试")
                    fail_kind = "no_response"
                    break
            except Exception as e:
                self.log("菜单路径出错（第 %d 次）：%s" % (attempt, e))
        if fail_kind and not self.last_error:
            self.last_error = fail_kind
        return None

    def open(self, kind: str) -> Optional[object]:
        """打开 kind 的参数窗并返回 wrapper；失败返回 None。

        优先走「测试方法(E)」菜单（6 版通道窗丢失后仍可用），
        菜单失败再回退到主工具栏按钮。
        """
        self.last_error = None
        pnl = self.open_by_menu(kind)
        if pnl is not None:
            return pnl
        if self.last_error in ("no_device", "no_response"):
            # 明确不是控件定位问题：不要再去点工具栏瞎试，
            # 那只会又弹一遍通讯配置向导并留下残留窗口。
            self.log("没有设备/软件未响应，放弃打开「%s」的参数窗" % kind)
            return None
        self.log("菜单路径失败，回退主工具栏按钮")
        return self._open_by_toolbar(kind)

    # ---- 演示模式专用路径（无设备自检用） ----

    def _main_child(self, substr, types=("Window", "Pane", "Custom")):
        """在主窗子树里找名字含 substr 的窗式控件。

        「用户设置」「添加」「提示」和各参数窗都不是顶层窗口
        （EnumWindows 看不见），而是主窗内部的 child 窗。
        """
        try:
            for c in self.ui.main.descendants():
                ei = c.element_info
                t = (ei.name or "").strip()
                if substr in t and ei.control_type in types:
                    return c
        except Exception:
            pass
        return None

    def _combo_channel_rows(self, chan) -> int:
        """数通道窗待运行列表的条目数（ListItem 且名字为纯数字）。"""
        n = 0
        try:
            for c in chan.descendants(control_type="ListItem"):
                t = (c.window_text() or "").strip()
                if t.isdigit():
                    n += 1
        except Exception:
            pass
        return n

    def _clear_combo_channel(self, tb, chan) -> bool:
        """清空通道队列。**慎用**：实测清空后“+”添加会永久报「输入错误」
        （软件约束），只有确认不再需要通过本路径打开参数窗时才允许清空。

        逐轮：选中第一行 → 点工具栏垃圾桶（btn[6]，无确认框直接删）。
        """
        def _toolbar():
            try:
                for c in chan.descendants(control_type="ToolBar"):
                    if (c.element_info.automation_id or "") == "toolStrip1":
                        return list(c.descendants(control_type="Button"))
            except Exception:
                pass
            return None

        def _rows():
            try:
                return [c for c in chan.descendants(control_type="ListItem")
                        if (c.window_text() or "").strip().isdigit()]
            except Exception:
                return []

        for _ in range(15):
            rows = _rows()
            if not rows:
                return True
            try:
                rows[0].click_input()           # 选中第一行
                time.sleep(0.3)
                btns = _toolbar()
                if not btns or len(btns) < 7:
                    return False
                btns[6].click_input()           # 垃圾桶=删除选中行（无确认框，实测）
            except Exception:
                return False
            time.sleep(0.6)
            for w in ("确认", "提示", "输入错误"):   # 打地鼠（保险）
                box = self._main_child(w)
                if box is None:
                    continue
                try:
                    for c in box.descendants(control_type="Button"):
                        t = (c.window_text() or "").strip()
                        if t in ("是(Y)", "是", "确定", "OK", "Yes"):
                            c.click_input()
                            break
                except Exception:
                    pass
                time.sleep(0.4)
        return self._combo_channel_rows(chan) == 0

    def _dismiss_dialog(self, title, texts=("是(Y)", "是", "确定", "OK", "Yes")):
        """关掉主窗内名为 title 的模态提示框（点 texts 里的按钮，或第一个按钮）。"""
        box = self._main_child(title)
        if box is None:
            return False
        try:
            btns = list(box.descendants(control_type="Button"))
            for c in btns:
                t = (c.window_text() or "").strip()
                if t in texts:
                    c.click_input()
                    return True
            if btns:
                btns[0].click_input()
                return True
        except Exception:
            pass
        return False

    def open_by_combo_demo(self, kind: str = "step") -> Optional[object]:
        """无设备路径：演示模式 → 组合方法(B) → 组合测试 → 「添加」新条目 → 参数窗。

        2026-11-06 v2：改走 driver.ParasiteDriver.add_experiment（序列工具栏
        「添加」+ UIA 条目矩形机制）。旧实现自己点通道窗工具栏按钮：
        btns[2] 其实是「开始」（误开跑事故），btns[4] 才是添加——现在
        统一收敛到一条验证过的添加路径，不再自己维护第二套。
        前提：已进演示模式且有通道窗（演示模式下工作通道(C)菜单存在）。
        """
        if not self.ui.click_menu("%b", "组合测试"):
            self.log("「组合方法(B)→组合测试」点不开")
            return None
        time.sleep(2.5)
        chan = None
        try:
            for c in self.ui.main.descendants(control_type="Window"):
                if "通道" in (c.window_text() or ""):
                    chan = c
                    break
        except Exception:
            pass
        if chan is None:
            self.log("没找到通道窗")
            return None
        rows = self._combo_channel_rows(chan)
        if rows == 0:
            self.log("通道队列为空：走「添加」新建条目")
        try:
            self.base.activate()
        except Exception:
            pass
        return self.base.add_experiment(kind)

    def _open_by_toolbar(self, kind: str) -> Optional[object]:
        """用主工具栏按钮开参数窗（老路线，按钮索引会因是否建通道而变）。"""
        tb = self.get_toolbar()
        if tb is None:
            self.log("找不到主工具栏")
            return None
        want = DIRECT_TITLE[kind]
        self._clear_before_open()
        tb = self.get_toolbar()      # 清场后重新取，避免 stale element
        if tb is None:
            self.log("找不到主工具栏")
            return None

        order = [DIRECT_BTN[kind]] + [i for i in range(1, 14) if i != DIRECT_BTN[kind]]
        for idx in order:
            try:
                tb.button(idx).click_input()
            except Exception as e:
                self.log("  toolbar[%d] 点不动：%s" % (idx, e))
                tb = self.get_toolbar()
                if tb is None:
                    return None
                continue
            time.sleep(2.0)
            self.ui.clear_modals()
            if idx == order[0]:
                self.log("  toolbar[%d] 点后可见窗：%r" % (
                    idx, [t for t, _ in self.ui.panels()][:6]))

            # 命中标题？
            hit = None
            for t, c in self.ui.panels():
                if want in t:
                    hit = c
                    break
            if hit is None:
                # 试下一个按钮前先收拾干净
                self.close_panels()
                self.ui.clear_modals()
                continue

            # 确认 automation_id 对得上（防止开成别的实验的参数窗）
            ids = set()
            for d in hit.descendants():
                try:
                    a = d.element_info.automation_id
                    if a:
                        ids.add(a)
                except Exception:
                    pass
            self.log("已打开「%s」（toolbar[%d]，%d 个控件）" % (want, idx, len(ids)))
            return hit
        self.log("打不开「%s」的参数窗" % want)
        return None

    # ---------- 填参数 ----------
    @staticmethod
    def _num_eq(a, b) -> bool:
        try:
            return abs(float(str(a).strip()) - float(str(b).strip())) < 1e-9
        except Exception:
            return False

    def _set_cell_num(self, aid: str, value: str, cell) -> bool:
        """写数值框：字符串回读不一致时按数值比较（软件会把 2.0000 规范成 2）。"""
        if self.ui.set_edit(aid, value, cell):
            return True
        got = self.ui.get_edit(aid, cell)
        if got is not None and self._num_eq(got, value):
            self.log("  %s 回读格式不同但数值正确（got=%r）" % (aid, got))
            return True
        self.log("  %s 写入失败（回读 %r）" % (aid, got))
        return False

    def set_cell(self, panel, area_cm2=None, density=7.93, temperature=25.0) -> bool:
        """点参数窗里的「电解池」按钮，写面积/密度/温度。"""
        btn = self.base._by_id(panel, "Btn_Cell") if hasattr(self.base, "_by_id") else None
        if btn is None:
            for d in panel.descendants():
                try:
                    if d.element_info.automation_id == "Btn_Cell":
                        btn = d
                        break
                except Exception:
                    pass
        if btn is None:
            self.log("找不到电解池按钮 Btn_Cell")
            return False
        try:
            btn.click_input()
        except Exception as e:
            self.log("点电解池失败：%s" % e)
            return False
        time.sleep(1.5)

        cell = None
        for t, c in self.ui.panels():
            if "电极与池" in t or "电解池" in t or "电极" in t:
                cell = c
                break
        if cell is None:
            self.log("电解池参数窗没出现")
            return False

        ok_all = True
        if area_cm2 is not None:
            g = self._set_cell_num("Elec_Elec_Area_Text", "%.4f" % float(area_cm2), cell)
            self.log("  电极面积 → %s" % ("OK" if g else "失败"))
            ok_all = ok_all and bool(g)
        if density is not None:
            g = self._set_cell_num("Elec_Elec_Density_Text", "%.2f" % float(density), cell)
            self.log("  材料密度 → %s" % ("OK" if g else "失败"))
        if temperature is not None:
            g = self._set_cell_num("Elec_Cell_Temp_Text", "%.1f" % float(temperature), cell)
            self.log("  溶液温度 → %s" % ("OK" if g else "失败"))

        self.ui.press_ok(cell)
        time.sleep(1.0)
        self.ui.clear_modals()
        return ok_all

    def mark_files(self, paths) -> None:
        """记录实验前的文件尺寸，供 is_running() 判断数据是否在长。"""
        import os
        self._file_marks = []
        for p in paths:
            try:
                self._file_marks.append((p, os.path.getsize(p) if os.path.exists(p) else 0,
                                         os.path.getmtime(p) if os.path.exists(p) else 0.0))
            except Exception:
                self._file_marks.append((p, 0, 0.0))

    def mdi_run_windows(self):
        """6 版的实验是 MDI 子窗（标题形如 `[通道1]-开路电位测量(OCP) <文件>`）。

        无通道窗时主窗标题不会变、panels() 里也只有一个隐藏的窗口，
        所以 is_running()/press_ok() 必须额外认这类 MDI 子窗。
        标题判据统一走 is_run_title()（test_run_title.py 有实测样例）。
        """
        hits = []
        try:
            for w in self.ui.main.descendants(control_type="Window"):
                t = w.window_text() or ""
                if not is_run_title(t):
                    continue
                # 关掉之后 UIA 树里还会残留不可见的元素，必须过滤，
                # 否则 is_running() 永远为 True、停止逻辑会一直空转。
                try:
                    if not w.is_visible():
                        continue
                except Exception:
                    pass
                hits.append((w, t))
        except Exception:
            pass
        return hits

    def press_ok(self, panel, dup_policy: str = "overwrite") -> bool:
        """点参数窗的「确定」——直开模式下这会立刻开始实验。

        dup_policy：数据文件重复提示框的选择策略（A4 定型，2026-11-06）
            overwrite → 点「覆盖」（自动化默认：拿全新数据）
            extend    → 点「扩展」（沿用旧文件继续写）
            cancel    → 点「取消」
        """
        self.ui.press_ok(panel)
        time.sleep(2.5)
        prefer = {
            "overwrite": ("覆盖", "是(Y)", "是", "确定"),
            "extend": ("扩展", "是(Y)", "是", "确定"),
            "cancel": ("取消", "否(N)"),
        }.get(dup_policy, ("覆盖", "是(Y)", "是", "确定"))
        # 「文件重复」之类的提示
        for _ in range(4):
            r = self.ui.close_win32_modal(prefer=prefer)
            if r is None:
                break
            self.log("处理提示框：%s / %s → %s" % r)
            time.sleep(0.6)
        # 6 版无通道窗时主窗标题不变，只能靠 MDI 子窗判断
        if not self.is_running() and self.mdi_run_windows():
            self.log("检测到 MDI 运行子窗")
            return True
        ok = self.is_running()
        if not ok:
            # 留现场：主窗标题 + 可见窗清单 + 截图
            try:
                self.log("启动未生效现场：主窗=%r 可见窗=%r MDI=%r" % (
                    self.ui.title, [t for t, _ in self.ui.panels()][:8],
                    [t for _w, t in self.mdi_run_windows()][:4]))
                self.ui.snapshot(r"D:\deepseek\_probe\press_ok_fail.png")
            except Exception:
                pass
        return ok
