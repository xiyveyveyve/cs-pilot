# -*- coding: utf-8 -*-
"""CS Studio6 UIA 封装（寄生式驱动的基础层）。

设计原则
--------
1. 只"操作界面"，不改软件配置文件、不改注册表、不碰软件内部数据。
2. CS Studio6 的所有模态对话框（实验参数窗、添加窗、提示框）都不是独立顶层
   窗口，而是挂在主窗口的 UIA 树里 —— 所以一律从主窗口 descendants 里找。
3. 工具栏按钮没有文本/automation_id，只能靠位置区分；同一窗口里可能同时存在
   两个 toolStrip1（序列工具栏 y≈131、数据窗口工具栏 y≈356），用 rect.top 分辨。
"""
from __future__ import annotations

import time
from typing import Callable, Iterable, List, Optional

from pywinauto import Desktop, mouse
from pywinauto.keyboard import send_keys
from typing import Tuple

MAIN_TITLE_RE = r".*CS Studio6.*"

# ---- 已知 automaton_id（实测得来，见 _probe/p9, p10, p15）----
ID_LIST = "listViewTest"          # 序列窗口的实验列表
ID_SEQ_TOOLBAR = "toolStrip1"     # 注意：数据窗口也有同名 toolbar
ID_MDI = "frmMultiExp"            # 通道窗口容器

# 序列工具栏按钮顺序（实测 14 个，用 tooltip 校验过）
SEQ_BTN = {
    "加载方案": 0, "保存方案": 1, "开始": 2, "停止": 3, "添加": 4,
    "修改": 5, "移除": 6, "清空": 7, "复制": 8, "粘贴": 9,
    "上移": 10, "下移": 11, "定时任务": 12, "批量修改文件路径": 13,
}
# 数据窗口（图形窗口）工具栏按钮顺序（实测 17 个）
DATA_BTN = {
    "停止": 0, "暂停": 1, "保存测量数据": 2, "反向": 3, "极化关闭": 4,
    "打印": 5, "图形复制": 6, "自适应显示": 7, "数据读点": 8, "坐标格线": 9,
    "显示标记": 10, "图形设置": 11, "是否显示参数": 12,
    "测试完成后自动打开数据": 13, "测量参数": 14, "帮助": 15,
}

SEQ_TOOLBAR_MAX_TOP = 250     # 序列工具栏在 MDI 子窗口顶部；数据工具栏在下半部
DATA_TOOLBAR_MIN_TOP = 300


_KEYSPECIAL = {
    "+": "{+}", "^": "{^}", "%": "{%}", "~": "{~}",
    "(": "{(}", ")": "{)}", "{": "{{}", "}": "{}}",
    "[": "{[}", "]": "{]}",
}


def esc_keys(text: str) -> str:
    """把 pywinauto.keyboard 认为特殊的字符转义成 {x} 形式。"""
    return "".join(_KEYSPECIAL.get(ch, ch) for ch in str(text))


class Studio:
    """CS Studio6 主窗口包装。"""

    def __init__(self, timeout: float = 5.0, log=None):
        self.d = Desktop(backend="uia")
        self.main = None
        self.log = log or (lambda m: None)   # set_edit 回读不一致等告警的出口
        self.acquire(timeout)

    # ---------- 基础 ----------
    def acquire(self, timeout: float = 5.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            for w in self.d.windows():
                try:
                    if "CS Studio6" in (w.window_text() or ""):
                        self.main = w
                        return True
                except Exception:
                    continue
            time.sleep(0.3)
        return False

    @property
    def title(self) -> str:
        return self.main.window_text() if self.main else ""

    @property
    def is_demo(self) -> bool:
        return "演示模式" in self.title

    # ---------- 查找 ----------
    def descendants(self) -> Iterable:
        if not self.main:
            return []
        try:
            return self.main.descendants()
        except Exception:
            return []

    def by_id(self, auto_id: str, root=None):
        # root 可能是已关闭窗口的 stale 引用：descendants() 抛 COMError
        # 时按"没找到"处理，返回 None 而不是让调用方炸出
        # （2026-11-06 代码审查 P3）。
        try:
            src = root.descendants() if root is not None else self.descendants()
        except Exception:
            return None
        for c in src:
            try:
                if c.element_info.automation_id == auto_id:
                    return c
            except Exception:
                continue
        return None

    def by_ids(self, auto_id: str) -> List:
        out = []
        for c in self.descendants():
            try:
                if c.element_info.automation_id == auto_id:
                    out.append(c)
            except Exception:
                continue
        return out

    def button(self, text: str, root=None) -> Optional[object]:
        """按可见文本找按钮（参数窗的确定/取消/覆盖等）。"""
        # 与 by_id 同理：stale root 的 descendants() 异常按"没找到"处理
        try:
            src = root.descendants() if root is not None else self.descendants()
        except Exception:
            return None
        for c in src:
            try:
                ei = c.element_info
                if ei.control_type == "Button" and (c.window_text() or "").strip() == text:
                    if c.rectangle().width() > 0:
                        return c
            except Exception:
                continue
        return None

    def button_prefix(self, prefix: str) -> Optional[object]:
        for c in self.descendants():
            try:
                ei = c.element_info
                t = (c.window_text() or "").strip()
                if ei.control_type == "Button" and t.startswith(prefix) and c.rectangle().width() > 0:
                    return c
            except Exception:
                continue
        return None

    def edit(self, auto_id: str, root=None):
        return self.by_id(auto_id, root)

    def force_foreground(self, tries: int = 3) -> bool:
        """把 CS Studio 主窗口硬拽到前台（UIA set_focus 有时会被系统拒）。"""
        import win32gui, win32con
        h = None
        try:
            h = self.main.handle
        except Exception:
            return False
        for _ in range(tries):
            try:
                if win32gui.IsIconic(h):
                    win32gui.ShowWindow(h, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(h)
                win32gui.SetForegroundWindow(h)
            except Exception:
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOW)
                except Exception:
                    pass
            time.sleep(0.25)
            try:
                if win32gui.GetForegroundWindow() == h:
                    break
            except Exception:
                pass
        try:
            self.main.set_focus()
        except Exception:
            pass
        time.sleep(0.2)
        return True

    def panels(self) -> List[Tuple[str, object]]:
        """所有**可见**的对话框/参数窗 [(title, wrapper)]，按 UIA 顺序（新开的通常在后）。"""
        res = []
        for c in self.descendants():
            try:
                ei = c.element_info
                if ei.control_type != "Window":
                    continue
                t = c.window_text() or ""
                r = c.rectangle()
                if not (100 < r.width() < 1300 and 60 < r.height() < 900):
                    continue
                try:
                    if not c.is_visible():
                        continue
                except Exception:
                    pass
                res.append((t, c))
            except Exception:
                continue
        return res

    def window_titled(self, keyword: str) -> Optional[object]:
        """参数窗 / 提示框等（在 main 的 UIA 树里），只认可见窗口，取最后一个。"""
        hit = None
        for t, c in self.panels():
            if keyword in t:
                hit = c
        return hit

    def has_dialog(self, keyword: str) -> bool:
        return self.window_titled(keyword) is not None

    # ---------- 工具栏 ----------
    def toolbars(self):
        """返回 [(top, rect, wrapper)]，按 top 排序。"""
        res = []
        for tb in self.by_ids(ID_SEQ_TOOLBAR):
            try:
                r = tb.rectangle()
                res.append((r.top, r, tb))
            except Exception:
                continue
        res.sort(key=lambda x: x[0])
        return res

    def _toolbar(self, kind: str):
        cands = [(top, rect, tb) for top, rect, tb in self.toolbars()
                 if len(self._tb_buttons(tb)) >= 10]
        if kind == "seq":
            for top, rect, tb in cands:
                if top < SEQ_TOOLBAR_MAX_TOP:
                    return tb
            return None
        # data：两个 toolStrip1 里位置更靠下的那个是数据工具栏。
        # 旧绝对坐标阈值（DATA_TOOLBAR_MIN_TOP=300）在 MDI 子窗停靠屏幕
        # 顶部时失效——数据工具栏整个落在 y<300，找不到「停止」（实测踩坑）。
        if len(cands) >= 2:
            return max(cands, key=lambda x: x[0])[2]
        return None

    @staticmethod
    def _tb_buttons(tb) -> List:
        out = []
        for c in tb.descendants():
            try:
                if c.element_info.control_type == "Button":
                    out.append(c)
            except Exception:
                continue
        return out

    def click_toolbar(self, kind: str, name: str, wait: float = 0.4) -> bool:
        """kind: 'seq' | 'data'；name 见 SEQ_BTN / DATA_BTN。"""
        table = SEQ_BTN if kind == "seq" else DATA_BTN
        if name not in table:
            raise KeyError("unknown toolbar button: %s" % name)
        tb = self._toolbar(kind)
        if tb is None:
            return False
        btns = self._tb_buttons(tb)
        idx = table[name]
        if idx >= len(btns):
            return False
        b = btns[idx]
        try:
            b.click_input()
        except Exception:
            r = b.rectangle()
            mouse.click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
        time.sleep(wait)
        return True

    def toolbar_enabled(self, kind: str, name: str) -> bool:
        table = SEQ_BTN if kind == "seq" else DATA_BTN
        tb = self._toolbar(kind)
        if tb is None:
            return False
        btns = self._tb_buttons(tb)
        idx = table[name]
        if idx >= len(btns):
            return False
        try:
            return btns[idx].is_enabled()
        except Exception:
            return False

    # ---------- 菜单 ----------
    def _visible_menu_count(self) -> int:
        """当前有实际位置（=已展开可见）的 MenuItem 数量。"""
        n = 0
        for c in self.descendants():
            try:
                if c.element_info.control_type != "MenuItem":
                    continue
                r = c.rectangle()
                if r.width() > 0 and r.height() > 0:
                    n += 1
            except Exception:
                continue
        return n

    def open_menu(self, hotkey: str, wait: float = 0.7) -> bool:
        """用 Alt+字母 展开顶级菜单（.NET 自绘 MenuStrip 必须这样）。

        返回**是否真的展开了**：菜单项不存在时 Alt 键被系统静默吞掉，
        旧实现无条件 return True，上层就会把"根本没有这一项"误当成
        "展开了但找不到子项"——6 版演示模式里「测试方法(E)」整条菜单消失，
        就是这么被误判成"找不到『暂态极化』"的（probe_menu6b 实测）。
        """
        try:
            self.main.set_focus()
        except Exception:
            pass
        time.sleep(0.2)
        before = self._visible_menu_count()
        try:
            send_keys(hotkey)
        except Exception:
            return False
        time.sleep(wait)
        if self._visible_menu_count() > before:
            return True
        # 本来就展开着时，再按一次会收起：ESC 收掉后重来一次
        try:
            send_keys("{ESC}")
        except Exception:
            return False
        time.sleep(0.25)
        before2 = self._visible_menu_count()
        try:
            send_keys(hotkey)
        except Exception:
            return False
        time.sleep(wait)
        return self._visible_menu_count() > before2

    def menu_items(self, only_visible: bool = True) -> List:
        out = []
        for c in self.descendants():
            try:
                ei = c.element_info
                if ei.control_type != "MenuItem":
                    continue
                r = c.rectangle()
                if only_visible and r.top <= 0:
                    continue
                out.append(((c.window_text() or "").strip(), c, r))
            except Exception:
                continue
        return out

    def click_menu(self, hotkey: str, text: str) -> bool:
        if not self.open_menu(hotkey):
            return False
        for t, c, r in self.menu_items():
            if t == text:
                c.click_input()
                time.sleep(0.5)
                return True
        send_keys("{ESC}")
        return False

    @staticmethod
    def _is_focused_window(c) -> bool:
        """控件所在的顶层窗口是否就是当前前台窗口。

        GUI 宿主（Tk 等同进程窗口）在前台时，UIA set_focus 会被系统
        静默吞掉，随后的 type_keys 全落到别的窗口——必须校验。
        """
        try:
            import win32gui
            fg = win32gui.GetForegroundWindow()
            h = c.handle
            while True:
                p = win32gui.GetParent(h)
                if not p:
                    break
                h = p
            return fg == h
        except Exception:
            return True

    # ---------- 表单写入 ----------
    def set_edit(self, auto_id: str, value: str, root=None) -> bool:
        r"""稳妥地给文本框赋值，并回读校验。

        CS Studio6 的 WinForms TextBox **不实现 UIA ValuePattern**
        （set_edit_text/set_text 均抛 COMError -2147220992），只能用键盘。
        而 pywinauto 的 set_focus + type_keys 对含反斜杠的路径是安全的
        （实测 `D:\deepseek\_probe\row1-OCP.txt` 逐字符正确回读），
        全局 send_keys 则会串字符，所以这里一律走控件级 type_keys。
        """
        c = self.edit(auto_id, root)
        if c is None:
            return False
        val = str(value)
        for attempt in (1, 2):
            try:
                c.set_focus()
                time.sleep(0.06)
                if not self._is_focused_window(c):
                    # 焦点没真过去（GUI 宿主持前台等场景）：真鼠标点一下输入框
                    c.click_input()
                    time.sleep(0.15)
                c.type_keys("^a")
                time.sleep(0.06)
                c.type_keys(esc_keys(val), with_spaces=True, pause=0.01)
                time.sleep(0.18)
            except Exception as e:
                # 写入动作本身抛错（焦点丢失/控件消失）不能静默：
                # 上层只拿到 False 时无从排查（2026-11-06 代码审查 P3）
                self.log("set_edit 写入异常(第%d次) auto_id=%s: %s"
                         % (attempt, auto_id, e))
                return False
            got = None
            try:
                got = c.get_value()
            except Exception:
                pass
            if got is not None and str(got).strip() == val.strip():
                return True
            # 数值框会被软件重新格式化（2.0000 → 2、0.50 → 0.5）：
            # 字符串不等但数值相等就算写入成功（审查 P2-12；以前只做字符串
            # 全等，导致已成功的写入被报失败，上层误判填参失败）
            if got is not None and val.strip() and str(got).strip():
                try:
                    if abs(float(str(got).strip()) - float(val.strip())) < 1e-9:
                        return True
                except (TypeError, ValueError):
                    pass
            self.log("set_edit 回读不一致(第%d次) auto_id=%s want=%r got=%r"
                     % (attempt, auto_id, val, got))
        return False

    def get_edit(self, auto_id: str, root=None) -> Optional[str]:
        c = self.edit(auto_id, root)
        if c is None:
            return None
        try:
            return c.get_value()
        except Exception:
            return None

    def press_ok(self, root=None) -> bool:
        b = self.by_id("btnOK", root)
        if b is None:
            b = self.button("确定", root)
        if b is None:
            return False
        b.click_input()
        time.sleep(0.6)
        return True

    def press_cancel(self, root=None) -> bool:
        b = self.by_id("btnCancel", root)
        if b is None:
            b = self.button("取消", root)
        if b is None:
            return False
        b.click_input()
        time.sleep(0.5)
        return True

    # ---------- 对话框兜底 ----------
    def dismiss_duplicate_prompt(self, policy: str = "overwrite") -> bool:
        """处理「本次测量数据文件存在重复」提示框。policy: overwrite|extend|cancel"""
        w = self.window_titled("提示")
        if w is None:
            return False
        names = {"overwrite": ("覆盖", "覆蓋"), "extend": ("扩展", "擴展"), "cancel": ("取消",)}
        for pfx in names.get(policy, ("覆盖",)):
            b = self.button_prefix(pfx)
            if b is not None:
                b.click_input()
                time.sleep(0.8)
                return True
        return False

    def any_blocking_dialog(self) -> Optional[str]:
        for kw in ("提示", "警告", "错误", "失败", "确认"):
            w = self.window_titled(kw)
            if w is not None:
                return kw
        return None

    # ---------- 序列 ----------
    def rows(self) -> List[List[str]]:
        lv = self.by_id(ID_LIST)
        if lv is None:
            return []
        out = []
        for it in lv.descendants():
            try:
                if it.element_info.control_type != "ListItem":
                    continue
                texts = [d.window_text() for d in it.descendants()
                         if d.element_info.control_type == "Text"]
                if texts:
                    out.append(texts)
            except Exception:
                continue
        return out

    def row_rect(self, index: int):
        lv = self.by_id(ID_LIST)
        if lv is None:
            return None
        items = [it for it in lv.descendants() if it.element_info.control_type == "ListItem"]
        if index >= len(items):
            return None
        return items[index].rectangle()

    def open_row(self, index: int) -> bool:
        """双击某行打开它的参数窗。"""
        lv = self.by_id(ID_LIST)
        if lv is None:
            return False
        items = [it for it in lv.descendants() if it.element_info.control_type == "ListItem"]
        if index >= len(items):
            return False
        self.force_foreground()
        items[index].double_click_input()
        time.sleep(1.2)
        return True

    def open_row_panel(self, index: int, keywords=("开路电位", "动电位", "阶梯波", "恒电位", "阶跃")):
        """双击某行，返回弹出的参数窗 wrapper（找不到返回 None）。"""
        before = {t for t, _ in self.panels()}
        if not self.open_row(index):
            return None
        for _ in range(15):
            for t, c in self.panels():
                if t not in before and any(k in t for k in keywords):
                    self.log("打开参数窗：[%s]" % t)
                    return c
            time.sleep(0.3)
        # 退路：任何可见的参数窗
        for t, c in self.panels():
            if any(k in t for k in keywords):
                self.log("打开参数窗(退路)：[%s]" % t)
                return c
        return None

    def select_row(self, index: int) -> bool:
        r = self.row_rect(index)
        if r is None:
            return False
        mouse.click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
        time.sleep(0.3)
        return True

    # ---------- win32 模态对话框（#32770）----------
    @staticmethod
    def win32_modal_dialogs(pid=None):
        """枚举可见的 #32770 对话框 —— CS Studio 的模态提示/错误框都是这类。

        传 pid 时只返回该进程的对话框：全局枚举会把其他软件的确认框也算进来，
        误点别的程序的弹窗是真实风险（2026-11-06 代码审查 P2，同库
        driver_direct._own_pids / driver5.cleanup_run_windows 均已按 PID 过滤）。
        """
        import win32gui
        res = []

        def cb(h, acc):
            try:
                if not win32gui.IsWindowVisible(h):
                    return True
                cls = win32gui.GetClassName(h)
                t = win32gui.GetWindowText(h)
                if cls == "#32770" and t:
                    if pid is not None:
                        _, wpid = win32gui.GetWindowThreadProcessId(h)
                        if wpid != pid:
                            return True
                    acc.append((h, t, win32gui.GetWindowRect(h)))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, res)
        return res

    def _main_pid(self):
        """主窗进程 PID；取不到返回 None（退回全局行为）。"""
        import win32gui
        try:
            if self.main is not None:
                _, pid = win32gui.GetWindowThreadProcessId(self.main.handle)
                return pid
        except Exception:
            pass
        return None

    @staticmethod
    def dialog_text(hwnd: int) -> str:
        """读 #32770 里的 Static 正文，用于日志留证。"""
        import win32gui
        out = []

        def cb(ch, acc):
            try:
                if win32gui.GetClassName(ch) == "Static":
                    t = win32gui.GetWindowText(ch)
                    if t:
                        acc.append(t)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, cb, out)
        except Exception:
            pass
        return " / ".join(out)

    @staticmethod
    def _norm_btn(t: str) -> str:
        """把「是(&Y)」归一化成「是(Y)」，去掉助记符 & 与全角括号。"""
        t = (t or "").replace("&", "").replace("（", "(").replace("）", ")")
        return t.strip()

    def close_win32_modal(self, prefer=("确定", "是(Y)", "是", "OK", "关闭", "否(N)")):
        """关掉一个 win32 模态框；返回 (标题, 正文, 点的按钮) 或 None。"""
        import win32gui, win32con
        dlgs = self.win32_modal_dialogs(pid=self._main_pid())
        if not dlgs:
            return None
        h, title, _r = dlgs[0]
        body = self.dialog_text(h)
        kids = []
        try:
            win32gui.EnumChildWindows(h, lambda ch, acc: (acc.append(ch), True)[1], kids)
        except Exception:
            kids = []
        # 按钮 ID -> 默认文本（CS Studio 的 WinForms 按钮常带 & 助记符）
        ID_ALIAS = {6: ("是(Y)", "是"), 7: ("否(N)", "否"), 1: ("确定", "OK"), 2: ("取消",)}

        def btn_alias_norm(cid):
            # 按钮文本别名归一化后集合；want 必须出现在这里才算"按别名匹配"，
            # 否则任何标准按钮都会因为 txt 恒在自己的 alias 里而命中恒真
            # （2026-11-06 代码审查 P1：旧判断 txt in alias 让 prefer 顺序失效，
            # 「是否继续修改？」框可能被点成「否(N)」）。
            return {self._norm_btn(a) for a in ID_ALIAS.get(cid, ())}

        picked = None
        for want in prefer:
            target = self._norm_btn(want)
            for ch in kids:
                try:
                    if "BUTTON" not in win32gui.GetClassName(ch).upper():
                        continue
                    txt = self._norm_btn(win32gui.GetWindowText(ch))
                    cid = win32gui.GetDlgCtrlID(ch)
                    if txt == target or target in txt or target in btn_alias_norm(cid):
                        win32gui.SendMessage(ch, win32con.BM_CLICK, 0, 0)
                        picked = txt or want
                        break
                except Exception:
                    continue
            if picked:
                break
        if picked is None:
            # 退路：want 与按钮 ID 的默认别名匹配才点（6=是 1=确定）
            for want in prefer:
                target = self._norm_btn(want)
                for ch in kids:
                    try:
                        if "BUTTON" not in win32gui.GetClassName(ch).upper():
                            continue
                        cid = win32gui.GetDlgCtrlID(ch)
                        if target in btn_alias_norm(cid):
                            win32gui.SendMessage(ch, win32con.BM_CLICK, 0, 0)
                            picked = self._norm_btn(win32gui.GetWindowText(ch)) or want
                            break
                    except Exception:
                        continue
                if picked:
                    break
        if picked is None:
            try:
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                picked = "<WM_CLOSE>"
            except Exception:
                picked = "<failed>"
        time.sleep(0.9)
        return (title, body, picked)

    def clear_modals(self, limit: int = 6):
        """清掉所有挡路的模态框，返回处理记录。"""
        done = []
        for _ in range(limit):
            r = self.close_win32_modal()
            if r is None:
                break
            done.append(r)
            try:
                self.log("关闭模态框：%s / %s / 按钮=%s" % r)
            except Exception:
                pass
        return done

    # ---------- 状态 ----------
    def status_texts(self) -> List[str]:
        out = []
        for c in self.descendants():
            try:
                if c.element_info.automation_id == "statusStrip1":
                    for cc in c.descendants():
                        t = (cc.window_text() or "").strip()
                        if t and t not in ("手柄",):
                            out.append(t)
            except Exception:
                continue
        return out

    def snapshot(self, path: str) -> bool:
        try:
            self.main.set_focus()
            time.sleep(0.2)
            self.main.capture_as_image().save(path)
            return True
        except Exception:
            return False


def ensure_foreground(studio: Studio) -> None:
    try:
        studio.main.set_focus()
        time.sleep(0.2)
    except Exception:
        pass
