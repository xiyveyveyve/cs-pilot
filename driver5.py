# -*- coding: utf-8 -*-
"""driver5.py —— CS Studio5（5.6.1202.2）的寄生式驱动。

与 6 版（driver.py）的差异，全部来自实测：

| 项目            | CS Studio6                     | CS Studio5                          |
|-----------------|--------------------------------|-------------------------------------|
| 主窗口          | 全屏 1930x1030                 | 小窗 838x664，类名 .8.app...        |
| 多实验序列      | 工作通道→通道1（frmMultiExp）  | **没有序列**，一次开一个实验窗      |
| 演示模式        | 系统设置→进入演示模式          | 同左（前提：先关掉启动时的“用户设置”模态框）|
| 端口/窗口重名   | 唯一                           | **同名窗口多个**，必须用 handle 定位|
| 菜单            | UIA submenu() 可用             | **无 submenu()**；子项预先注册、展开后 rect 才有值；点主菜单常不展开，**Alt+字母更可靠** |
| 工具栏按钮      | 无文本，只能按索引             | **有 window_text**                  |
| 参数窗          | automation_id=frmOCP           | 同左（**控件 id 大部分相同**）      |
| 确定/取消/帮助  | btnOK / btnCancel / btnHelp    | **Ocp_Ok_Btn / Ocp_Cancel_Btn / Ocp_Help_Btn** |
| 终止条件        | chkStopByE/chkStopByDeltaE     | **Ocp_Stop_Check / chkStop2**       |
| 数据文件        | .txt，运行中可 tail            | **.cor，运行期间独占锁（不可读）**  |
| 运行中数据源    | watch.CorFileTail              | **uiprobe.UiSampler（读界面）**     |
| 文件首行        | CSStudioFile,ID_XXX,<base64>   | **CORRW ASCII / CorrTest...SN... / ID_XXX** |
| 实验接续        | 序列自动接续                   | **无，必须由脚本逐个开实验**        |

因此 5 版的流程是：
    open_ocp() → fill_ocp() → ok() → UiSampler 判稳 → stop() → 关闭
    → open_tafel() → fill_tafel() → ok() → 等结束 → 关闭
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

CLS5 = "WindowsForms10.Window.8.app.0.13965fa_r6_ad1"
EXE5 = r"D:\sci\CS Studio5\CS Studio5\CorrTest.CSStudio.exe"

# 5 版参数窗按钮 id（实测；注意动电位是 OK 大写、OCP 是 Ok 大小写混排）
BTN_OK = {"ocp": "Ocp_Ok_Btn", "tafel": "PotDynamic_OK_btn",
          "eis": "EISVSfrq_OK", "step": "PotSquare_Ok_Btn"}
BTN_CANCEL = {"ocp": "Ocp_Cancel_Btn", "tafel": "PotDynamic_Cancel_btn",
              "step": "PotSquare_Cancel_Btn"}


def msg_click(c):
    """点击控件（主桌面真实鼠标）。

    ★ 2026-11-09 更正：754ea01 的「消息点击」是空实现（c.click() 失败后
    递归调用自己），且命名桌面（CreateDesktop）下 SendInput/keybd_event/
    PostMessage 全部被系统拒绝（GetForegroundWindow()=0），即虚拟桌面隔离
    路线不可行。本函数恢复为主桌面 click_input + 坐标兜底。
    """
    try:
        c.click_input()
        return True
    except Exception:
        pass
    # 兜底：按 rect 中心发真实鼠标事件（主桌面可用）
    try:
        import win32api
        import win32con

        r = c.rectangle()
        if r.right - r.left <= 2 or r.bottom - r.top <= 2:
            return False
        cx = (r.left + r.right) // 2
        cy = (r.top + r.bottom) // 2
        win32api.SetCursorPos((cx, cy))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def esc_keys(s: str) -> str:
    return "".join("{%s}" % ch if ch in "+^%~(){}[]" else ch for ch in str(s))


def _f(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _is_run_title(t: str) -> bool:
    """判定窗口标题是不是『实验运行窗口』而不是『参数窗』。

    运行窗口形如 `开路电位 <2mA>  D:\\...\\xxx.cor`，必带量程 `<2mA>` 和文件路径；
    参数窗只有 `开路电位` / `动电位扫描` 这样的纯名字。用这个区分，否则
    find_run_hwnd 会把刚弹出的参数窗也当成"实验已启动"。
    """
    if not t or "CS Studio" in t:
        return False
    return ("<" in t and "mA" in t) or ("\\" in t) or ("/" in t)


def _stop_via_runwin(hwnd) -> bool:
    """在运行窗口里点它自己的「停止」按钮，让实验真正停下来。

    只关窗口是不行的：CS Studio5 的运行窗被 WM_CLOSE 掉之后，工作站里的
    实验仍在继续采集，只是界面看不到了，接着就会把下一个实验顶掉。
    """
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(handle=hwnd)
        w = app.window(handle=hwnd)
    except Exception:
        return False
    return _stop_via_runwin_w(w, hwnd)


def _stop_via_runwin_w(w, hwnd) -> bool:
    """在运行窗 w 里点「停止」并应答确认框。返回是否可以安全关窗。

    True = 点到了停止并应答确认框（或停止键已禁用 = 实验已自行结束）；
    False = 没找到停止键 / 点击未生效 → 保留窗口，绝不关窗（关窗≠实验停）。
    """
    disabled = False
    clicked = False
    try:
        for tb in w.descendants(control_type="ToolBar"):
            for b in tb.descendants(control_type="Button"):
                try:
                    if (b.window_text() or "").strip() != "停止":
                        continue
                    if not b.is_enabled():
                        disabled = True
                        continue
                    if msg_click(b):
                        clicked = True
                except Exception:
                    continue
                if clicked:
                    break
            if clicked:
                break
    except Exception:
        return False
    if not clicked:
        return disabled
    time.sleep(0.5)
    try:
        import win32process
        pid = int(win32process.GetWindowThreadProcessId(hwnd)[1])
    except Exception:
        pid = 0
    try:
        n = clear_modals(limit=2, prefer=("是(Y)", "是", "确定"), pid=pid or None)
        if not n and pid:
            answer_confirm_uia(pid)
    except Exception:
        pass
    return True


def find_run_hwnd(keywords=("开路电位", "动电位", "恒电位", "阶梯波", "阻抗", "频率扫描"), exclude=(), expect=None):
    """用 win32 枚举找实验运行窗口的 hwnd（它不在 Desktop().windows() 里）。

    exclude: 要跳过的 hwnd（启动前就存在的旧窗口），避免抓到上一轮残留。
    expect : 标题里必须包含的片段（通常是刚写入的文件名）。这是最可靠的判据 ——
             实测真机上「启动瞬间旧窗口还没关干净」时，只靠 exclude 会抓错窗口，
             导致监视到别人的数据、误判实验结束。
    """
    try:
        import win32gui
    except ImportError:
        return None
    found = []

    def cb(h, _):
        try:
            if h in exclude:
                return True
            if not win32gui.IsWindowVisible(h):
                return True
            t = win32gui.GetWindowText(h) or ""
        except Exception:
            return True
        if not _is_run_title(t):
            return True
        if expect and expect not in t:
            return True
        if any(k in t for k in keywords):
            found.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return found[-1] if found else None


def all_run_hwnds(keywords=("开路电位", "动电位", "恒电位", "阶梯波", "阻抗", "频率扫描")):
    """列出当前所有实验运行窗口的 hwnd。"""
    try:
        import win32gui
    except ImportError:
        return []
    found = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            t = win32gui.GetWindowText(h) or ""
        except Exception:
            return True
        if _is_run_title(t) and any(k in t for k in keywords):
            found.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return found


# ---------------- 模态提示框（#32770）----------------
# CS Studio5 的提示框和 6 版一样是 Win32 #32770，UIA 树里抓不到。
# 实测「是否覆盖当前文件?」的按钮是 Button '是(&Y)' id=6 / '否(&N)' id=7。
_ID_ALIAS = {6: ("是(Y)", "是", "覆盖", "确定"), 7: ("否(N)", "否"), 1: ("确定", "OK"), 2: ("取消",)}


def _norm(s: str) -> str:
    return (s or "").replace("&", "").replace("（", "(").replace("）", ")").strip()


def modal_dialogs(pid=None):
    """枚举可见 #32770 模态框。pid 给定时只保留该进程的对话框。

    多实例并存时各台 CS5 都有自己的确认框，不过滤 pid 会点掉别台的框、
    自己的框却留着没应答 → 自己的实验停不下来。pid=None 保持旧行为。
    """
    try:
        import win32gui
    except ImportError:
        return []
    if pid:
        import win32process
    out = []

    def cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770":
                if pid and win32process.GetWindowThreadProcessId(h)[1] != pid:
                    return True
                out.append(h)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return out


def modal_text(h) -> str:
    try:
        import win32gui
    except ImportError:
        return ""
    txt = []

    def cb(c, _):
        try:
            if win32gui.GetClassName(c) == "Static":
                t = win32gui.GetWindowText(c)
                if t:
                    txt.append(t)
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(h, cb, None)
    return " / ".join(txt)


def modal_buttons(h):
    try:
        import win32gui
    except ImportError:
        return []
    out = []

    def cb(c, _):
        try:
            if win32gui.GetClassName(c) == "Button":
                out.append((win32gui.GetDlgCtrlID(c), _norm(win32gui.GetWindowText(c)), c))
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(h, cb, None)
    return out


def click_modal(h, prefer=("是(Y)", "是", "覆盖", "确定", "OK")) -> str:
    """点模态框的按钮，返回被点的文字；失败返回空。"""
    import win32gui

    btns = modal_buttons(h)
    prefer_n = [_norm(p) for p in prefer]
    # 「另存为」对话框：「保存(S)」按钮 id=1，id 兜底会把它当「确定」误点 →
    # 以错误名字落盘。只允许点「取消」，且绝不走 id 兜底。
    try:
        title = win32gui.GetWindowText(h) or ""
    except Exception:
        title = ""
    if "另存为" in title or "另存为" in modal_text(h):
        for bid, txt, hwnd in btns:
            if bid == 2 or txt == "取消":
                win32gui.SendMessage(hwnd, 0x00F5, 0, 0)
                return txt
        return ""
    # 1) 按文字
    for want in prefer_n:
        for bid, txt, hwnd in btns:
            if txt == want:
                win32gui.SendMessage(hwnd, 0x00F5, 0, 0)  # BM_CLICK
                return txt
    # 2) 按控件 id 兜底
    for bid, txt, hwnd in btns:
        for alias in _ID_ALIAS.get(bid, ()):
            if _norm(alias) in prefer_n:
                win32gui.SendMessage(hwnd, 0x00F5, 0, 0)
                return txt
    return ""


def answer_confirm_uia(pid: int, prefer=("是(Y)", "是", "确定", "OK")) -> str:
    """UIA 兜底应答确认框（返回被点的按钮文字）。

    背景：2026-11-12 真机 1 号实测确认——CS5 点「停止」后会弹确认框，
    点「是」才真的停；而 clear_modals 只认 Win32 的 #32770 标准对话框，
    .NET WinForms 自绘的确认框类名是 WindowsForms10.* 、按钮也不是 "Button"，
    抓不到 → 实验继续跑、数据文件一直在写。这里按进程 pid 枚举窗口，
    用 UIA 找「是(Y)/是/确定」按钮点掉。
    """
    try:
        import win32gui
        import win32process
        from pywinauto import Application
    except ImportError:
        return ""

    targets = []

    def cb(h, _):
        try:
            if not win32gui.IsWindowVisible(h):
                return True
            _t, p = win32process.GetWindowThreadProcessId(h)
            if p != pid:
                return True
            title = win32gui.GetWindowText(h) or ""
            # 只认对话框：主窗/运行窗工具栏里也有「关闭」「停止」，
            # 2026-11-12 真机实测误点过主窗的「关闭」→ 这里必须排除
            if "CS Studio" in title or ".cor" in title:
                return True
            targets.append(h)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        return ""

    for h in targets:
        try:
            app = Application(backend="uia").connect(handle=h, timeout=2)
            w = app.window(handle=h)
            for b in w.descendants(control_type="Button"):
                try:
                    t = (b.window_text() or "").strip()
                    if t in prefer:
                        b.click_input()
                        return t
                except Exception:
                    continue
        except Exception:
            continue
    return ""


def clear_modals(limit=6, prefer=("是(Y)", "是", "覆盖", "确定", "OK"), pid=None) -> int:
    """把所有可见 #32770 模态框按 prefer 点掉。返回处理个数。

    pid: 只处理该进程的对话框（多实例隔离）；None = 不过滤（旧行为）。
    """
    import win32gui

    n = 0
    for _ in range(limit):
        found = False
        for h in modal_dialogs(pid=pid):
            txt = modal_text(h)
            got = click_modal(h, prefer)
            if got or txt:
                found = True
                n += 1
        if not found:
            break
        time.sleep(0.6)
    return n


class Studio5:
    def __init__(self, log=None, sn: str = "", hwnd: int = 0):
        self.log = log or (lambda *a: None)
        self.sn = sn                      # ★ 多实例并存：按序列号锁定本机窗口
        self.hwnd_hint = hwnd             # ★ 更硬：fleet 按 pid 定位的实例句柄
        self.app = None
        self.main = None
        self.hwnd = None

    # ---------------- 生命周期 ----------------
    def _pid(self) -> int:
        """本实例进程 pid（UIA 兜底应答确认框时按 pid 过滤窗口）。"""
        try:
            import win32process
            return win32process.GetWindowThreadProcessId(self.hwnd)[1]
        except Exception:
            return 0

    def find_main(self) -> bool:
        """找主窗口（判据：descendants 里同时有 menuStrip 和 toolStrip）。

        注意：主窗口被最小化时 GetWindowRect 返回 (-32000,-32000,...)，
        pywinauto 的 Desktop.windows() 会漏掉它；实测真机场景软件常被最小化。
        所以先用 win32 按类名枚举所有顶层窗口，最小化的先 SW_RESTORE，再走 UIA 判据。

        ★ hwnd_hint（fleet 按 pid 定位）优先：4 实例并存时枚举会抓错别人的窗口。
        """
        if self.hwnd_hint:
            h = self.hwnd_hint
            try:
                import win32gui
                r = win32gui.GetWindowRect(h)
                if r[0] <= -30000 or r[1] <= -30000:
                    win32gui.ShowWindow(h, 9)       # SW_RESTORE
                    time.sleep(0.8)
                app = Application(backend="uia").connect(handle=h, timeout=5)
                ww = app.window(handle=h)
                self.app, self.main, self.hwnd = app, ww, h
                try:
                    ww.set_focus()
                except Exception:
                    pass
                time.sleep(0.7)
                self.log("按 hwnd 锁定实例：%s" % h)
                return True
            except Exception:
                self.log("hwnd %s 失效，回退枚举" % h)
                self.hwnd_hint = 0
        hwnds = []
        try:
            import win32gui

            def _cb(h, acc):
                try:
                    # 标题预过滤：4 实例并存时（CS5/CS6 各自多开），同代 WinForms
                    # 类名可能撞车——没有 "CS Studio5" 标题的窗口绝不候选
                    # （2026-11-07 审查：find_main 曾可能抓到 CS Studio6）
                    t = win32gui.GetWindowText(h)
                    if "CS Studio5" not in t:
                        return True
                    if self.sn and self.sn not in t:
                        return True       # ★ 多实例：只认标题含本机 SN 的窗口
                    if win32gui.GetClassName(h) == CLS5 and win32gui.IsWindowVisible(h):
                        acc.append(h)
                except Exception:
                    pass

            win32gui.EnumWindows(_cb, hwnds)
        except Exception as e:
            self.log("win32 枚举窗口失败: %s" % e)

        if not hwnds:
            try:
                d = Desktop(backend="uia")
                for w in d.windows():
                    try:
                        wt = w.window_text() or ""
                        if (w.class_name() == CLS5 and "CS Studio5" in wt
                                and (not self.sn or self.sn in wt)):
                            hwnds.append(w.handle)
                    except Exception:
                        pass
            except Exception as e:
                self.log("枚举窗口失败: %s" % e)
                return False

        for h in hwnds:
            try:
                try:
                    import win32gui
                    r = win32gui.GetWindowRect(h)
                    if r[0] <= -30000 or r[1] <= -30000:
                        self.log("主窗口处于最小化状态，正在还原…")
                        win32gui.ShowWindow(h, 9)   # SW_RESTORE
                        time.sleep(0.8)
                except Exception:
                    pass

                app = Application(backend="uia").connect(handle=h, timeout=5)
                ww = app.window(handle=h)
                ids = set()
                for c in ww.descendants():
                    try:
                        ids.add(c.automation_id())
                    except Exception:
                        pass
                if "menuStrip" in ids and "toolStrip" in ids:
                    self.app, self.main, self.hwnd = app, ww, h
                    # 刚从最小化还原时窗口还没真正到前台，点菜单会被吞掉。
                    try:
                        ww.set_focus()
                    except Exception:
                        pass
                    time.sleep(0.7)
                    return True
            except Exception:
                continue
        return False

    def launch(self, wait=25.0) -> bool:
        if self.find_main():
            self.log("CS Studio5 已在运行（hwnd=%s）" % self.hwnd)
            return True
        if not os.path.exists(EXE5):
            self.log("找不到 5 版程序: %s" % EXE5)
            return False
        self.log("启动 CS Studio5 …")
        Application(backend="uia").start(EXE5)
        end = time.time() + wait
        while time.time() < end:
            if self.find_main():
                self.log("已连上（hwnd=%s）" % self.hwnd)
                return True
            time.sleep(1.0)
        return False

    def title(self) -> str:
        try:
            return self.main.window_text() if self.main else ""
        except Exception:
            return ""

    def is_demo(self) -> bool:
        return "演示模式" in self.title()

    def close_user_settings(self) -> int:
        """5 版启动/操作后常弹『用户设置』模态框，会挡住菜单点击。

        ⚠️ 这个框是 owned window，`Desktop(backend="uia").windows()` 列不出来
        （实测 0 个命中，导致菜单一直点不开）。必须用 win32 EnumWindows 按标题
        拿到 hwnd，再 Application.connect(handle=h) 精确定位后点『退出』(btnCancel)。

        ⚠️ 4 实例并存（2026-11-09 四机实证）：EnumWindows 是**全桌面**枚举，
        每台 runner 都会看到别人实例的同名框，抢着点 → 由于被遮挡的窗口点不准，
        结果是「关闭了 2 个/3 个」越关越多、自己的框反而关不掉、菜单永远展不开。
        所以这里必须按本实例 pid 过滤，关之前再把它顶到前台。
        """
        n = 0
        want_pid = 0
        try:
            import win32process as _wp
            if self.hwnd_hint:
                want_pid = _wp.GetWindowThreadProcessId(self.hwnd_hint)[1]
        except Exception:
            want_pid = 0
        hwnds = []
        try:
            import win32gui as _wg

            def _cb(h, acc):
                try:
                    if not _wg.IsWindowVisible(h):
                        return True
                    if _wg.GetWindowText(h) != "用户设置":
                        return True
                    if want_pid:
                        try:
                            import win32process as _wp2
                            if _wp2.GetWindowThreadProcessId(h)[1] != want_pid:
                                return True
                        except Exception:
                            pass
                    acc.append(h)
                except Exception:
                    pass
                return True

            _wg.EnumWindows(_cb, hwnds)
        except Exception as e:
            self.log("  枚举『用户设置』失败: %s" % e)
            return 0

        for h in hwnds:
            try:
                # 先顶到前台：被遮挡时 click_input 的鼠标事件落在别的窗口上
                try:
                    import win32gui as _wg2
                    _wg2.ShowWindow(h, 5)
                    _wg2.BringWindowToTop(h)
                    _wg2.SetForegroundWindow(h)
                    time.sleep(0.3)
                except Exception:
                    pass
                app = Application(backend="uia").connect(handle=h)
                w = app.window(handle=h)
                clicked = False
                for aid in ("btnCancel", "btnOk"):
                    try:
                        b = w.child_window(auto_id=aid)
                        if b.exists(timeout=0.5):
                            msg_click(b)
                            clicked = True
                            break
                    except Exception:
                        pass
                if not clicked:
                    for b in w.descendants(control_type="Button"):
                        try:
                            if b.window_text() in ("退出", "取消"):
                                msg_click(b)
                                clicked = True
                                break
                        except Exception:
                            pass
                if clicked:
                    n += 1
                    time.sleep(0.5)
            except Exception as e:
                self.log("  关闭『用户设置』hwnd=%s 失败: %s" % (h, e))
        if n:
            self.log("关闭了 %d 个『用户设置』框" % n)
        return n

    def enter_demo(self) -> bool:
        if self.is_demo():
            return True
        self.close_user_settings()
        if not self.find_main():
            return False
        self.log("进入演示模式 …")
        self.click_main_menu("系统设置(S)")
        time.sleep(0.8)
        for name in ("进入演示模式", "退出演示模式"):
            if self.click_menu_item(name):
                time.sleep(2.0)
                if self.find_main():
                    self.log("演示模式: %r" % self.title())
                    return self.is_demo()
        return False

    # ---------------- 菜单 ----------------
    def exit_demo(self) -> bool:
        """退出演示模式（连接丢失后 app 会落 demo——demo 下通讯设置不可达）。"""
        if not self.is_demo():
            return True
        self.log("退出演示模式 …")
        self.close_user_settings()
        if not self.find_main():
            return False
        self.click_main_menu("系统设置(S)")
        time.sleep(0.8)
        if self.click_menu_item("退出演示模式"):
            time.sleep(2.0)
            if self.find_main():
                self.log("退出后: %r" % self.title()[:60])
                return not self.is_demo()
        return False

    def _close_comset_dialog(self) -> bool:
        """关闭残留的「通讯设置」窗（点取消），防止模态挡住后续菜单操作。"""
        try:
            d = self._find_comset_dialog(timeout=1.0)
            if d is None:
                return False
            cancel = None
            for c in d.descendants():
                try:
                    if (c.element_info.automation_id or "") in ("Btn_Cancel", "btn_Cancel"):
                        cancel = c
                        break
                except Exception:
                    continue
            if cancel is not None:
                msg_click(cancel)
            else:
                d.type_keys("{ESC}")
            time.sleep(0.5)
            self.log("关闭了残留的「通讯设置」窗")
            return True
        except Exception:
            return False

    def _find_comset_dialog(self, timeout: float = 0.0):
        end = time.time() + timeout
        while True:
            try:
                if not self.main:
                    self.find_main()
                for c in self.main.descendants():
                    try:
                        if ((c.element_info.automation_id or "") == "frmcomProperty"
                                and c.is_visible()):
                            return c
                    except Exception:
                        continue
            except Exception:
                pass
            if time.time() >= end:
                return None
            time.sleep(0.5)

    def connect_lan(self, port: str, wait: float = 40.0) -> bool:
        """网口手动连接：系统设置(S)→通讯设置→网口→手动→选 port→确定。

        多实例并存时广播发现分不清设备归属（实例会连错别人的 sim）——
        手动指定端口是唯一确定性配对（2026-11-08 四机冒烟：JK-P/Q 连错
        sim → SN 等待超时 → 熔断）。
        """
        import studio_ui as _SU
        self.exit_demo()                         # ★ demo 下通讯设置不可达，先退出
        if not self.main and not self.find_main():
            return False
        try:
            if port in (self.main.window_text() or ""):
                return True                      # 已连着就免连
        except Exception:
            pass
        # ★ 键盘路径（命名桌面鼠标 ACCESS DENIED 实证；keybd_event 可用）：
        #   Alt+S 展开 → DOWN×3 到「通讯设置」（子项序：打印/系统设置/用户/通讯）→ ENTER
        from pywinauto.keyboard import send_keys as _sk
        dlg = None
        for attempt in range(4):
            try:
                self.main.set_focus()
            except Exception:
                pass
            _sk("{ESC}")
            time.sleep(0.4)
            _sk("%s")                      # Alt+S
            time.sleep(0.9)
            _sk("{DOWN}{DOWN}{DOWN}{ENTER}")
            time.sleep(1.4)
            dlg = self._find_comset_dialog()
            if dlg is not None:
                break
        if dlg is None:
            self.log("通讯设置：键盘路径 4 次尝试都没打开")
            return False

        def by_aid(aid):
            for c in dlg.descendants():
                try:
                    if c.element_info.automation_id == aid:
                        return c
                except Exception:
                    continue
            return None

        eth, user = by_aid("btnEthernet"), by_aid("rbtUser")
        pc, okb = by_aid("Com_Com_Com_Combox"), by_aid("btn_Ok")
        if not (eth and user and pc and okb):
            self.log("通讯设置控件不全")
            return False
        msg_click(eth)
        time.sleep(0.5)
        msg_click(user)
        time.sleep(0.5)
        try:
            if not pc.is_enabled():
                self.log("IP 下拉仍禁用")
                return False
        except Exception:
            pass
        if not _SU.navigate_combo(pc, port.split(":")[-1], max_try=25):
            self.log("选端口 %s 失败" % port)
            return False
        msg_click(okb)
        end = time.time() + wait
        while time.time() < end:
            time.sleep(2)
            try:
                t = self.main.window_text() or ""
                if self.sn and self.sn in t and port in t:
                    self.log("网口已连接：%s" % t[:60])
                    return True
            except Exception:
                continue
        self.log("网口连接 %s 超时" % port)
        return False

    def connect_com(self, com: str, baud: int = 115200, wait: float = 45.0,
                    tries: int = 3, gap: float = 8.0) -> bool:
        """真机串口连接（外层重试）：菜单路径整段重来，间隔 gap 秒。

        2026-11-11 多实例实证：4 个 CS Studio 同时启动时，后启动实例的
        自动扫描窗口期会瞬时握住别人的口，先连的报「设备被另一实例占用」
        ——但 pyserial 复核口并没有被占。占用提示多数是启动期冲突，重试
        即可。「已连着别的口」也不再是硬冲突：CS5 会按共享 SysConfig.ini
        的 ComName 在启动时自动重连（2026-11-11 real4 错位实证——全新实例
        8s 内自己连上了 ini 里记的口），所以"连着别的口"时要**换口**：
        继续走通讯设置窗流程重选目标口即可。若目标口真被别人握住，
        _connect_com_once 会连不上（标题不变）→ 重试耗尽自然报错。
        """
        if not self.main and not self.find_main():
            return False
        try:
            t = self.main.window_text() or ""
            if ("in %s" % com) in t:
                return True                      # 已连着目标口
            import re as _re
            m0 = _re.search(r"in (COM\d+)", t)
            if m0 and m0.group(1) != com:
                self.log("⚠ 实例已连 %s（ini 自动重连所致），换连 %s"
                         % (m0.group(1), com))
            if "演示" in t:
                self.exit_demo()
        except Exception:
            pass
        for attempt in range(tries):
            if self._connect_com_once(com, baud, wait):
                return True
            if attempt < tries - 1:
                self.log("串口连接第 %d 次失败，%g s 后重来（占用提示多为启动期扫描冲突）"
                         % (attempt + 1, gap))
                time.sleep(gap)
                if not self.main and not self.find_main():
                    return False
        return False

    def _connect_com_once(self, com: str, baud: int, wait: float) -> bool:
        """单次连接：系统设置(S)→通讯设置→USB→手动→选端口+波特率→确定。

        2026-11-11 真机实证（CS350 @ COM10 115200）：连上后主窗标题出
        【型号：CS350 in COM10】,序列号:CS3501501006。两个下拉的 aid 与
        标签交叉——以 Value 实证为准：Com_Com_Baute_Combox=波特率
        （Value=115200），Com_Com_Com_Combox=端口（默认选中 COM10）。
        """
        import studio_ui as _SU
        from pywinauto.keyboard import send_keys as _sk
        dlg = None
        for attempt in range(3):
            # 「用户设置」模态框会挡住菜单 invoke（2026-11-11 换口实验实证：
            # 框在右上角常驻，系统设置菜单 invoke 报 COMError -2147220992），
            # 每轮尝试前都清一次；残留的「通讯设置」窗同理（上一轮失败后
            # 窗没关，模态挡着菜单点不动）。
            try:
                self.close_user_settings()
            except Exception:
                pass
            self._close_comset_dialog()
            items = self.menu_items()
            tgt = [c for txt, r, c in items if "系统设置" in txt]
            if tgt:
                try:
                    tgt[0].iface_invoke.invoke()
                except Exception:
                    pass
            time.sleep(1.0)
            hit = None
            for c in self.main.descendants(control_type="MenuItem"):
                try:
                    r = c.rectangle()
                    t2 = (c.window_text() or "").strip()
                    if "通讯" in t2 and (r.left or r.top) and r.top > 400:
                        hit = c
                        break
                except Exception:
                    continue
            if hit is not None:
                msg_click(hit)
                time.sleep(1.4)
                dlg = self._find_comset_dialog(timeout=4.0)
            if dlg is not None:
                break
            try:
                _sk("{ESC}")
            except Exception:
                pass
            time.sleep(0.5)
        if dlg is None:
            self.log("通讯设置窗打不开（真机 %s）" % com)
            return False

        def by_aid(aid):
            for c in dlg.descendants():
                try:
                    if c.element_info.automation_id == aid:
                        return c
                except Exception:
                    continue
            return None

        # ★ Socket 态实例窗初开是「网口」模式：没有波特率/串口下拉
        #   （real6 实证，控件只有 btnUsb/btnEthernet/btn_Ok/Btn_Cancel/
        #   rbtUser/rbtAuto/IP下拉）。先点 USB 让窗体重绘出串口控件，
        #   再重新枚举（重绘后原 UIA 元素全部失效）。
        usb, okb = by_aid("btnUsb"), by_aid("btn_Ok")
        if not (usb and okb):
            self.log("通讯设置控件不全（真机 %s）" % com)
            self._close_comset_dialog()
            return False
        msg_click(usb)
        time.sleep(0.8)
        dlg = self._find_comset_dialog(timeout=4.0) or dlg
        user = by_aid("rbtUser")
        baud_cb = by_aid("Com_Com_Baute_Combox")   # 波特率下拉（USB 模式才有）
        port_cb = by_aid("Com_Com_Com_Combox")     # 端口下拉（USB 模式=串口）
        okb = by_aid("btn_Ok")
        if not (user and port_cb and baud_cb and okb):
            self.log("通讯设置控件不全（USB 切换后，真机 %s）" % com)
            self._close_comset_dialog()
            return False
        msg_click(user)
        time.sleep(0.6)
        if not _SU.navigate_combo(port_cb, com, max_try=15):
            cur = ""
            try:
                cur = str(port_cb.legacy_properties().get("Value") or "")
            except Exception:
                pass
            self.log("端口下拉没选到 %s（当前值 %r）——按当前值继续，由标题校验判定" % (com, cur))
        if baud:
            _SU.navigate_combo(baud_cb, str(baud), max_try=15)
        msg_click(okb)
        end = time.time() + wait
        while time.time() < end:
            time.sleep(2)
            try:
                t = self.main.window_text() or ""
            except Exception:
                continue
            if ("in %s" % com) in t:
                self.log("串口已连接：%s" % t[:60])
                return True
            if ("in COM" in t) and ("in %s" % com) not in t:
                self.log("连到了别的口：%s（想要 %s）" % (t[:60], com))
                return False
        self.log("串口连接 %s 超时" % com)
        return False

    def menu_items(self, only_visible=True):
        out = []
        try:
            for c in self.main.descendants(control_type="MenuItem"):
                try:
                    r = c.rectangle()
                    if only_visible and not (r.left or r.top):
                        continue
                    out.append(((c.window_text() or "").strip(), r, c))
                except Exception:
                    continue
        except Exception:
            pass
        return out


    def close_stale_panels(self, keep=None) -> int:
        """关掉残留的参数窗/运行窗，避免它们被当成目标窗（实测踩过）。

        keep 里放当前要保留的 hwnd。
        """
        keep = keep or ()
        closed = 0
        try:
            import win32con
            import win32gui

            def _walk(h, _):
                nonlocal closed
                try:
                    cn = win32gui.GetClassName(h)
                    t = win32gui.GetWindowText(h)
                    if cn != CLS5 or h in keep:
                        return True
                    if "演示模式" in t or "CS Studio5" in t:
                        return True
                    if not (t.strip()):
                        return True
                    if "<" in t and "mA" in t:
                        # 运行窗不在此处强关：没先停止就把窗关了，正是文档记录的
                        # 「窗口没了实验还在跑」事故路径（2026-11-07 审查 P2）。
                        # 停止由 _finish_run/cleanup_run_windows 的正规流程负责。
                        return True
                    if "图形显示" in t or "参数设置" in t \
                            or t.startswith(("开路电位", "动电位", "阻抗", "恒电位", "阶梯波",
                                             "任意恒电位")):
                        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                        closed += 1
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_walk, None)
        except Exception:
            pass
        if closed:
            time.sleep(0.8)
        return closed

    def _has_expanded_children(self) -> bool:
        """是否已有菜单项展开（rect 有效且不在菜单栏那一行）。"""
        try:
            for txt, r, c in self.menu_items():
                if r.top > 200 and (r.right - r.left) > 10:
                    return True
        except Exception:
            pass
        return False

    def click_main_menu(self, name: str) -> bool:
        """点主菜单项。点不开时退回 Alt+字母。"""
        self.close_user_settings()
        for txt, r, c in self.menu_items():
            if txt == name:
                self.main.set_focus()
                time.sleep(0.3)
                try:
                    msg_click(c)
                    time.sleep(0.7)
                except Exception:
                    pass
                # 检查是否真的展开了：子项 rect 必须从 0 变成有效值
                if self._has_expanded_children():
                    return True
                break
        # 兜底：Alt+字母
        m = {"文件(F)": "f", "系统设置(S)": "s", "工作单元(C)": "c",
             "测试方法(E)": "e", "数据分析(T)": "t", "窗口(W)": "w", "帮助(H)": "h"}
        key = m.get(name)
        if key:
            self.main.set_focus()
            time.sleep(0.3)
            send_keys("%" + key)
            time.sleep(0.9)
            # 2026-11-06 代码审查 P3：Alt 助记键在菜单项不存在时会被系统
            # 静默吞掉，无条件 return True 会让调用方误以为已展开
            # （对齐 studio_ui.open_menu 的修法：验证子项 rect 是否有效）。
            return bool(self._has_expanded_children())
        return False

    def click_menu_item(self, name: str) -> bool:
        """点已展开的菜单项。

        5 版菜单项全部预注册，未展开时 rect=(0,0,0,0)。只点 rect 有效的，
        否则点击落点跑到 (0,0)，什么都没发生。
        """
        cands = []
        for txt, r, c in self.menu_items():
            if txt != name:
                continue
            valid = (r.right - r.left) > 10 and (r.bottom - r.top) > 6 and r.top > 0
            cands.append((valid, r, c))
        # 优先点「已展开」的那个
        cands.sort(key=lambda x: (not x[0], x[1].top))
        for valid, r, c in cands:
            if not valid:
                continue
            try:
                self.main.set_focus()
                time.sleep(0.2)
                msg_click(c)
                time.sleep(0.9)
                return True
            except Exception as e:
                self.log("点击 %r 失败: %s" % (name, e))
                continue
        self.log("菜单项 %r 当前未展开（rect 无效），跳过" % name)
        return False

    # ---------------- 参数窗 ----------------
    def find_panel(self, auto_id: str):
        try:
            for c in self.main.descendants(control_type="Window"):
                try:
                    if c.automation_id() == auto_id:
                        r = c.rectangle()
                        if r.right - r.left > 150:
                            return c
                except Exception:
                    continue
        except Exception:
            pass
        return None

    #: 主菜单对应的 Alt 助记键（实测比纯鼠标点稳定得多）
    MAIN_ALT = {
        "文件(F)": "%f", "系统设置(S)": "%s", "工作单元(C)": "%c",
        "测试方法(E)": "%e", "数据分析(T)": "%t", "窗口(W)": "%w",
        "帮助(H)": "%h",
    }

    def open_experiment(self, path, auto_id, tries=3):
        """按菜单路径打开实验参数窗。path 形如 ("测试方法(E)","稳态极化(S)","开路电位(O)")。

        实测：5 版的菜单用纯鼠标点经常不展开（子项 rect 保持 0），
        而 Alt+助记键几乎必成。所以一级菜单优先用键盘展开，再往下点。
        """
        from pywinauto.keyboard import send_keys as _sk
        for attempt in range(tries):
            # 关键：模态框挡着时主菜单点了也不会展开。典型是 #32770
            # 「提示：该方法还没有完成，是否关闭？」（是(Y)/否(N)）
            n_modal = clear_modals(limit=3, prefer=("是(Y)", "是", "关闭", "确定", "否(N)", "否", "OK"), pid=self._pid())
            if n_modal:
                self.log("清掉 %d 个模态框" % n_modal)
            n_stale = self.close_stale_panels()
            if n_stale:
                self.log("关掉 %d 个残留窗口" % n_stale)
            self.close_user_settings()
            try:
                self.main.set_focus()
            except Exception:
                pass
            time.sleep(0.35)
            for i, name in enumerate(path):
                if i == 0:
                    # 一级菜单用鼠标点（Alt+助记键实测反而展不开二级）
                    self.click_main_menu(name)
                    time.sleep(0.7)
                else:
                    self.click_menu_item(name)
                    time.sleep(0.6)
            time.sleep(1.2)
            panel = self.find_panel(auto_id)
            if panel is not None:
                return panel
            # 退路：按标题找，但只找与本次目标匹配的那一个
            # （曾因按 "阻抗频率扫描" 兜底，把上一个实验的残留窗当成动电位窗）
            want = ""
            if auto_id == "frmEISVSfrq":
                want = "阻抗频率扫描"
            elif auto_id == "frmPotDynamic":
                want = "动电位扫描"
            elif auto_id == "frmOCP":
                want = "开路电位"
            if want:
                cand = self.find_panel_by_title(want, timeout=1.0)
                if cand is not None:
                    self.log("按标题找到参数窗：%r" % want)
                    return cand
            self.log("打不开 %s（第 %d 次）" % (auto_id, attempt + 1))
            time.sleep(1.2)
        return None

    def by_ids(self, panel):
        out = {}
        try:
            for c in panel.descendants():
                try:
                    aid = c.automation_id()
                    if aid and aid not in out:
                        out[aid] = c
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def set_edit(self, c, value: str) -> bool:
        """给 Edit 写值。

        实测：`type_keys("^a")` 偶发 Ctrl 没生效，`^a` 被当字面字符打出 'a'，
        于是 "0.01" 变成 "a0.01"。所以先 `^a` 再 `{DEL}` 显式清空，
        不符时退化为「逐个退格删干净再重新输入」。
        """
        aid = "?"
        try:
            aid = c.automation_id()
            c.set_focus()
            time.sleep(0.1)

            def _clear_and_type(backspaces: int = 0) -> None:
                c.type_keys("^a")
                time.sleep(0.05)
                c.type_keys("{DEL}")
                time.sleep(0.05)
                for _ in range(backspaces):
                    c.type_keys("{BACKSPACE}")
                c.type_keys(esc_keys(value), with_spaces=True, pause=0.02)
                time.sleep(0.15)

            _clear_and_type()
            got = c.get_value()
            if self._edit_value_equal(got, value):
                return True

            for _ in range(2):
                cur = c.get_value() or ""
                n = max(len(cur), len(value)) + 2
                _clear_and_type(backspaces=n)
                got = c.get_value()
                if self._edit_value_equal(got, value):
                    return True

            self.log("  %s 写入 %r 回读 %r 不符" % (aid, value, got))
            return False
        except Exception as e:
            self.log("  %s 写入失败: %s" % (aid, e))
            return False

    @staticmethod
    def _edit_value_equal(got, want) -> bool:
        """回读等价判断：字符串全等，或数值等价。

        数值框会被软件重新格式化（-0.5000 → -0.5、2.0000 → 2）：
        只做字符串全等会把已成功的写入误报失败（2026-11-06 代码审查 P2，
        与 studio_ui.set_edit 的数值等价放行对齐）。
        """
        if got is None:
            return False
        g, w = str(got).strip(), str(want).strip()
        if g == w:
            return True
        if g and w:
            try:
                return abs(float(g) - float(w)) < 1e-9
            except (TypeError, ValueError):
                pass
        return False

    # ---------------- OCP ----------------
    def open_ocp(self):
        return self.open_experiment(("测试方法(E)", "稳态极化(S)", "开路电位(O)"), "frmOCP")

    def fill_ocp(self, panel, out_path: str, seconds: float, freq_hz: float = 10.0) -> bool:
        ids = self.by_ids(panel)
        ok = True
        if "Control_FileName_Text" in ids:
            ok &= self.set_edit(ids["Control_FileName_Text"], out_path)
        else:
            self.log("  缺 Control_FileName_Text")
            ok = False
        # 测量时间统一用「秒」（用户 2026-11-04：各版本统一 1800 秒）
        if "Ocp_Param_Combo" in ids:
            try:
                cur = ids["Ocp_Param_Combo"].legacy_properties().get("Value")
            except Exception:
                cur = None
            if cur != "秒":
                try:
                    msg_click(ids["Ocp_Param_Combo"])
                    time.sleep(0.4)
                    send_keys("{UP}")      # 分 -> 秒 往上
                    time.sleep(0.3)
                    send_keys("{ENTER}")
                    time.sleep(0.3)
                except Exception as e:
                    self.log("  切单位失败: %s" % e)
                try:
                    cur2 = ids["Ocp_Param_Combo"].legacy_properties().get("Value")
                except Exception:
                    cur2 = None
                if cur2 != "秒":
                    self.log("  单位切换后仍非『秒』：%r → 参数写入失败" % cur2)
                    ok = False
        if "Ocp_Param_Text" in ids:
            ok &= self.set_edit(ids["Ocp_Param_Text"], ("%g" % seconds))
        if "FrqControl_Frq_Radio" in ids:
            try:
                msg_click(ids["FrqControl_Frq_Radio"])
                time.sleep(0.2)
            except Exception:
                pass
        if "FrqControl_Frq_Text" in ids:
            ok &= self.set_edit(ids["FrqControl_Frq_Text"], ("%g" % freq_hz))
        return ok

    # ---------------- 动电位扫描 ----------------
    def open_tafel(self):
        return self.open_experiment(
            ("测试方法(E)", "稳态极化(S)", "动电位扫描(D)"), "frmPotDynamic")

    def fill_tafel(self, panel, out_path: str, init_v: float, final_v: float,
                   scan_mv_s: float = 0.5, interval_s: float = 0.5,
                   stop_ma: Optional[float] = None) -> bool:
        """填动电位扫描参数。

        stop_ma: 扫描停止的阳极电流阈值（mA，**绝对电流，不乘面积**）。None 表示不动软件设置。
                 5 版默认 `PotDynamic_ScanStop_chk` 勾选、Max +4.5 / Min -4.5 mA。
                 界面实测（2026-11-15）：两栏标签「当电流(mA)>」「或电流(mA)<」，
                 单位就是 mA 绝对电流。下限固定写 -2.00（2 mA 量程），只让阳极阈值生效。
        """
        ids = self.by_ids(panel)
        ok = True
        if "Control_FileName_Text" in ids:
            ok &= self.set_edit(ids["Control_FileName_Text"], out_path)
        else:
            self.log("  缺 Control_FileName_Text")
            ok = False
        if "PotDynamic_InitialPot_txt" in ids:
            ok &= self.set_edit(ids["PotDynamic_InitialPot_txt"], "%.4f" % init_v)
        if "PotDynamic_FinalPot_txt" in ids:
            ok &= self.set_edit(ids["PotDynamic_FinalPot_txt"], "%.4f" % final_v)
        if "PotDynamic_ScanRate_txt" in ids:
            ok &= self.set_edit(ids["PotDynamic_ScanRate_txt"], "%g" % scan_mv_s)
        # 采样：用「电位间隔(mV)」而不是采样频率，与 6 版保持一致
        if "SampleInterval_radio" in ids:
            try:
                msg_click(ids["SampleInterval_radio"])
                time.sleep(0.2)
            except Exception:
                pass
        if "SampleInterval_txt" in ids:
            ok &= self.set_edit(ids["SampleInterval_txt"], "%g" % interval_s)
        if stop_ma is not None:
            # 扫描停止开关是必需控件：缺失/点击失败/回读未勾选 = 软件电流停止
            # 未启用。5 版已删脚本侧电流判停，此时将完全没有电流停止，必须
            # 拒绝开跑（审查 #30，M4 的 CS5 孪生）。
            chk = ids.get("PotDynamic_ScanStop_chk")
            if chk is None:
                self.log("  缺 PotDynamic_ScanStop_chk → 无法启用软件电流停止，中止")
                ok = False
            else:
                try:
                    for _ in range(2):
                        if chk.get_toggle_state():
                            break
                        msg_click(chk)
                        time.sleep(0.2)
                    if not chk.get_toggle_state():
                        self.log("  扫描停止开关回读仍未勾选 → 中止（软件电流停止未启用）")
                        ok = False
                except Exception as e:
                    self.log("  扫描停止开关处理失败：%s → 中止" % e)
                    ok = False
            # 停止电流必须写入并回读核验：残留旧阈值会把扫描提前截断
            # （2026-11-14 真机：MaxCurrent 残留 0.1 mA → 动电位 t=2000 s 被截）
            # 界面实测（2026-11-15 演示模式 dump）：两栏是 **绝对电流 mA**，
            # 「当电流(mA)> X」或「或电流(mA)< Y」满足任一即停，不乘面积。
            # 下限固定 -2.00（= 2 mA 量程，等价于不在量程内提前停；超量程软件自己停），
            # 只让阳极方向的 stop_ma 生效。
            pair = (("PotDynamic_MaxCurrent_txt", "%.2f" % abs(stop_ma)),
                    ("PotDynamic_MinCurrent_txt", "-2.00"))
            for aid, val in pair:
                if aid not in ids:
                    self.log("  缺 %s → 停止电流无法写入，中止（防残留阈值截断扫描）" % aid)
                    ok = False
                    continue
                ok &= self.set_edit(ids[aid], val)
            if ok:
                time.sleep(0.3)
                for aid, val in pair:
                    try:
                        got = ids[aid].get_value()
                    except Exception:
                        got = None
                    if not self._edit_value_equal(got, val):
                        self.log("  %s 回读 %r ≠ %r → 重写" % (aid, got, val))
                        self.set_edit(ids[aid], val)
                        try:
                            got = ids[aid].get_value()
                        except Exception:
                            got = None
                        if not self._edit_value_equal(got, val):
                            self.log("  %s 重写后仍 %r ≠ %r → 中止（防残留阈值截断扫描）"
                                     % (aid, got, val))
                            ok = False
                if ok:
                    try:
                        self.log("  软件侧停止电流：%s / %s mA" % (
                            ids[pair[0][0]].get_value(), ids[pair[1][0]].get_value()))
                    except Exception:
                        pass
        return ok

    # ---------------- 阶梯波（任意恒电位阶梯波 frmPotSquareWave）----------------
    def open_step(self, tries: int = 3):
        """打开「任意恒电位阶梯波」参数窗。

        5 版菜单：测试方法(E) → 暂态极化(T) → 任意恒电位阶梯波(多电位阶跃)。
        叶子项的确切助记括号各版本可能不同，所以末级按「包含」模糊匹配
        （p131 实测通过）；窗口 id frmPotSquareWave 从实测控件表取得。
        """
        for attempt in range(tries):
            clear_modals(limit=3, prefer=("是(Y)", "是", "关闭", "确定", "否(N)", "否", "OK"), pid=self._pid())
            self.close_stale_panels()
            self.close_user_settings()
            try:
                self.main.set_focus()
            except Exception:
                pass
            time.sleep(0.35)
            if not self.click_main_menu("测试方法(E)"):
                self.log("展开测试方法失败（第 %d 次）" % (attempt + 1))
                continue
            time.sleep(0.7)
            if not self.click_menu_item("暂态极化(T)"):
                self.log("展开暂态极化失败（第 %d 次）" % (attempt + 1))
                send_keys("{ESC}")
                continue
            time.sleep(0.8)
            target = None
            for c in self.main.descendants():
                try:
                    ei = c.element_info
                    if ei.control_type != "MenuItem":
                        continue
                    r = ei.rectangle
                    if ("任意恒电位阶梯波" in (c.window_text() or "")
                            and r.bottom > 60 and r.top > 60):
                        target = c
                        break
                except Exception:
                    continue
            if target is None:
                self.log("子菜单里没找到阶梯波项（第 %d 次）" % (attempt + 1))
                send_keys("{ESC}")
                continue
            try:
                msg_click(target)
            except Exception:
                try:
                    target.invoke()
                except Exception as e:
                    self.log("点阶梯波菜单失败：%s" % e)
                    send_keys("{ESC}")
                    continue
            time.sleep(2.0)
            panel = self.find_panel("frmPotSquareWave")
            if panel is None:
                panel = self.find_panel_by_title("任意恒电位阶梯波", timeout=1.0)
            if panel is not None:
                return panel
            self.log("菜单点了但参数窗没出现（第 %d 次）" % (attempt + 1))
        return None

    @staticmethod
    def step_ladder(init_v: float, final_v: float, delta_v: float,
                    max_steps: int = 10) -> List[float]:
        """init→final 之间的中间电位序列（不含两端），最多 max_steps 个。

        按给定 delta 均匀铺；中间步超过 10 个就放宽 delta 等分。
        例：-0.2→0.5，delta=0.05 → n_cells=14 > 11 → 放宽为 11 格
        ×0.0636，中间 10 步（示例按实现修正，2026-11-07 审查）。
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

    def _select_combo_containing(self, cbo, want: str, max_tries: int = 6,
                                 exact: bool = False) -> bool:
        """在下拉里选中值包含 want 的项：反复 键盘导航+读回校验，不怕项序。

        exact=True 按全等匹配——短 want（如 TimeUnit 的 "s"）用包含匹配
        会命中 "ms"（2026-11-07 审查 P2）。"""
        def _hit(cur):
            cur = str(cur)
            return cur == want if exact else want in cur
        try:
            cur = cbo.legacy_properties().get("Value") or ""
        except Exception:
            cur = ""
        if _hit(cur):
            return True
        keys = ["{HOME}", "{END}", "{DOWN}", "{DOWN}", "{DOWN}", "{UP}"]
        for k in keys:
            try:
                msg_click(cbo)
                time.sleep(0.4)
                send_keys(k)
                time.sleep(0.3)
                send_keys("{ENTER}")
                time.sleep(0.4)
            except Exception as e:
                self.log("  下拉导航失败：%s" % e)
                return False
            try:
                cur = cbo.legacy_properties().get("Value") or ""
            except Exception:
                cur = ""
            if _hit(cur):
                return True
        self.log("  下拉里找不到含 %r 的项（当前 %r）" % (want, cur))
        return False

    def fill_step(self, panel, out_path: str, init_v: float, final_v: float,
                  delta_v: float = 0.05, hold_s: float = 2.0,
                  freq_hz: float = 10.0, cycles: int = 20,
                  use_steps: bool = False) -> bool:
        """填「任意恒电位阶梯波」参数（frmPotSquareWave 控件表来自 p131 实测）。

        结构：初始电位(持续时间) → 中间电位1..N(各带持续时间/启用勾选)
        → 终止电位(持续时间)，循环 cycles 圈。

        use_steps=False（默认，按用户指定）时**中间电位全部不勾选**，
        只在初始/终止两个电位之间来回跳，每步 hold_s 秒，循环 cycles 圈。
        """
        ids = self.by_ids(panel)
        ok = True

        def put(aid, val):
            nonlocal ok
            if aid in ids:
                ok &= self.set_edit(ids[aid], val)
            else:
                self.log("  缺 %s" % aid)
                ok = False

        put("Control_FileName_Text", out_path)
        # 时间单位固定为 s。exact：包含匹配会命中 "ms"（2026-11-07 审查 P2）
        if "PotSquare_TimeUnit_cbo" in ids:
            ok &= self._select_combo_containing(ids["PotSquare_TimeUnit_cbo"], "s",
                                                exact=True)
        # 极化电位基准：相对开路（与 Tafel 的 vs OCP 一致；窗里默认是「相对参比」）
        if "Vs_Combo" in ids:
            ok &= self._select_combo_containing(ids["Vs_Combo"], "开路")
        put("PotSquare_InitialE_txt", "%.4f" % init_v)
        put("PotSquare_InitTime_txt", "%g" % hold_s)
        put("PotSquare_FinalE_txt", "%.4f" % final_v)
        put("PotSquare_FinalTime_txt", "%g" % hold_s)
        steps = self.step_ladder(init_v, final_v, delta_v) if use_steps else []
        for i in range(1, 11):
            en_id = "PotSquare_Step%d_chb" % i
            e_id = "PotSquare_Step%d_txt" % i
            t_id = "PotSquare_Step%dTime_txt" % i
            want_on = i <= len(steps)
            if en_id in ids:
                try:
                    on = ids[en_id].get_toggle_state() == 1
                    if on != want_on:
                        msg_click(ids[en_id])
                        time.sleep(0.2)
                except Exception:
                    pass
            if want_on:
                if e_id in ids:
                    ok &= self.set_edit(ids[e_id], "%.4f" % steps[i - 1])
                if t_id in ids:
                    ok &= self.set_edit(ids[t_id], "%g" % hold_s)
        put("PotSquare_Cycles_txt", str(int(cycles)))
        # 采样：切到「采样频率」单选，填 Hz（与 OCP 同一套控件 id）
        if "FrqControl_Frq_Radio" in ids:
            try:
                msg_click(ids["FrqControl_Frq_Radio"])
                time.sleep(0.2)
            except Exception:
                pass
        if "FrqControl_Frq_Text" in ids:
            ok &= self.set_edit(ids["FrqControl_Frq_Text"], "%g" % freq_hz)
        self.log("阶梯波参数：%g → %g V，%s，每步 %g s，循环 %d 圈"
                 % (init_v, final_v,
                    ("中间 %d 步" % len(steps)) if steps else "中间不选",
                    hold_s, cycles))
        return ok

    # ---------------- EIS（阻抗频率扫描）----------------
    # 名称对照：
    #   6 版「交流阻抗 → 频率扫描-电位控制模式(Nyquist, Bode)」
    #   5 版「交流阻抗 → 阻抗~频率扫描(F)」
    # 两者是同一个实验：电位固定在直流电位（默认相对开路），扫频率。
    # find_panel_by_title 统一实现在文件后部（带运行窗排除 + before/timeout）；
    # 2026-11-06 代码审查 P1：本类曾有两处同名定义，后一处（无运行窗过滤）
    # 覆盖了前一处，导致运行窗被误当参数窗的事故复活，现只保留一份。

    def open_eis(self):
        """打开阻抗频率扫描参数窗。"""
        pnl = self.open_experiment(
            ("测试方法(E)", "交流阻抗(I)", "阻抗~频率扫描(F)"), "frmEISVSfrq")
        if pnl is not None:
            return pnl
        # automation_id 未采集时的退路：按标题找刚弹出的窗
        for _ in range(8):
            time.sleep(0.5)
            c = self.find_panel_by_title("阻抗频率扫描")
            if c is not None:
                return c
        return None

    def fill_eis(self, panel, out_path: str, dc_v: float = 0.0,
                 amp_mv: float = 10.0, init_freq: float = 100000.0,
                 final_freq: float = 0.01, pts_per_decade: float = 10.0,
                 vs_ocp: bool = True) -> bool:
        """填阻抗频率扫描参数。

        dc_v="直流电位(V)"，vs_ocp=True 时是相对开路（0 表示不外加极化）。
        amp_mv="交流幅值(mV)"。init_freq/final_freq="初始/终止频率(Hz)"。
        pts_per_decade="点/10倍频"。
        注意：软件里这几个字段的 element_info.name 互相错位，必须按 id 认。
        """
        ids = self.by_ids(panel)
        ok = True
        if "Control_FileName_Text" in ids:
            ok &= self.set_edit(ids["Control_FileName_Text"], out_path)
        else:
            self.log("  缺 Control_FileName_Text")
            ok = False
        # 电位基准：相对开路 / 相对参比
        want = "相对开路" if vs_ocp else "相对参比"
        if "Vs_Combo" in ids:
            # 改用带回读重试的选择器：旧版单向 {DOWN}/{UP} 切一次、结果只写
            # 日志不校验——项序不符时静默用错基准，EIS 结果系统性偏差
            # （2026-11-07 审查 P2）
            if not self._select_combo_containing(ids["Vs_Combo"], want):
                self.log("  电位基准切 %r 失败 → 参数写入失败" % want)
                ok = False
        for aid, val, fmt in (
            ("EISVSfrq_SineBias_Text", dc_v, "%g"),
            ("EISVSfrq_SineAmp_Text", amp_mv, "%g"),
            ("EISVSfrq_InitFre_Text", init_freq, "%g"),
            ("EISVSfrq_FinalFre_Text", final_freq, "%g"),
            ("EISVSfrq_TenTwice_Text", pts_per_decade, "%g"),
        ):
            if aid in ids:
                ok &= self.set_edit(ids[aid], fmt % val)
            else:
                self.log("  缺 %s" % aid)
                ok = False
        return ok

    def eis_readback(self, panel):
        """回读 EIS 参数窗当前值，供日志核对。"""
        ids = self.by_ids(panel)
        out = {}
        for aid in ("Control_FileName_Text", "EISVSfrq_SineBias_Text",
                    "EISVSfrq_SineAmp_Text", "EISVSfrq_InitFre_Text",
                    "EISVSfrq_FinalFre_Text", "EISVSfrq_TenTwice_Text"):
            c = ids.get(aid)
            if c is None:
                continue
            try:
                out[aid] = c.get_value()
            except Exception:
                try:
                    out[aid] = c.legacy_properties().get("Value")
                except Exception:
                    out[aid] = None
        if "Vs_Combo" in ids:
            try:
                out["Vs_Combo"] = ids["Vs_Combo"].legacy_properties().get("Value")
            except Exception:
                pass
        return out

    def find_panel_by_title(self, title_kw: str, before=None, timeout: float = 0.0):
        """在主窗 UIA 树里按标题关键字找可见参数窗（全类唯一实现）。

        必须排除「运行窗口」：实验跑起来后窗口标题是
        `开路电位 <2mA>  D:\\...\\xxx.cor`，也含「开路电位」字样，
        按关键字会把运行窗当成参数窗（实测踩过，导致缺 Control_FileName_Text）。
        before 传入「点之前已有的标题集合」时，只认新出现的那个，避免抓到残留窗。
        timeout>0 时轮询等待窗口出现；0（旧签名）只查一次立即返回。
        """
        t0 = time.time()
        while True:
            cand = []
            try:
                for c in self.main.descendants(control_type="Window"):
                    try:
                        t = (c.window_text() or "").strip()
                        if "<mA" in t or (os.sep in t) or ("/" in t):
                            continue      # 运行窗口（带量程和文件路径），不是参数窗
                        r = c.rectangle()
                        if title_kw in t and 100 < (r.right - r.left) < 1300 \
                                and (r.bottom - r.top) > 120:
                            if before is None or t not in before:
                                cand.append((t, c))
                    except Exception:
                        pass
            except Exception:
                pass
            if cand:
                return cand[-1][1]
            if time.time() - t0 >= timeout:
                return None
            time.sleep(0.4)

    def _panel_titles(self):
        out = set()
        try:
            for c in self.main.descendants(control_type="Window"):
                try:
                    t = c.window_text() or ""
                    if t:
                        out.add(t)
                except Exception:
                    pass
        except Exception:
            pass
        return out

    def set_cell_area(self, panel, area_cm2: float,
                      density: Optional[float] = 7.93,
                      temperature: Optional[float] = 25.0) -> bool:
        """在实验参数窗里点『电极/电解池』图标（Btn_Cell），改电极面积后确定。

        ⚠️ 面积是每个实验各自存的（旧会话需求：「每个测试项目的面积设置是单独的」），
        所以 OCP / 阻抗 / 动电位三个阶段都要各设一次。
        ⚠️ 电解池窗里 Elec_Elec_Equiv_Text 的 name 被错标成「电极面积(cm²)」，
        真正的面积是 Elec_Elec_Area_Text，只能按 id 认。
        ⚠️ 材料密度 Elec_Elec_Density_Text 在 5 版出厂是 7.8，用户指出应为 7.93
        （6 版默认就是 7.93）；density=None 表示不动它。
        """
        ids = self.by_ids(panel)
        btn = ids.get("Btn_Cell")
        if btn is None:
            self.log("  参数窗里没有 Btn_Cell，无法设面积")
            return False
        before = self._panel_titles()
        try:
            msg_click(btn)
        except Exception as e:
            self.log("  点 Btn_Cell 失败: %s" % e)
            return False
        time.sleep(1.2)
        cell = self.find_panel_by_title("电解池", before=before, timeout=6.0)
        if cell is None:
            cell = self.find_panel_by_title("电极与", before=None, timeout=2.0)
        if cell is None:
            self.log("  没找到电解池参数窗")
            return False
        try:
            self.log("  电解池窗：%r" % cell.window_text())
        except Exception:
            pass

        cids = self.by_ids(cell)
        area_ctl = cids.get("Elec_Elec_Area_Text")
        if area_ctl is None:
            self.log("  缺 Elec_Elec_Area_Text")
            self._cancel_cell(cell)
            return False
        try:
            old = area_ctl.get_value()
        except Exception:
            old = None
        ok = self.set_edit(area_ctl, "%g" % area_cm2)
        try:
            new = area_ctl.get_value()
        except Exception:
            new = None
        self.log("  电极面积: %r -> %r (目标 %g) %s" % (old, new, area_cm2, "OK" if ok else "失败"))
        if not ok:
            self._cancel_cell(cell)
            return False

        # 材料密度：5 版出厂默认 7.8，实测值应为 7.93（碳钢/不锈钢），
        # 用户 2026-11-04 指出「阻抗的材料密度错了，是 7.93」。
        dens_ctl = cids.get("Elec_Elec_Density_Text")
        if dens_ctl is not None and density is not None:
            try:
                d_old = dens_ctl.get_value()
            except Exception:
                d_old = None
            d_ok = self.set_edit(dens_ctl, "%g" % density)
            try:
                d_new = dens_ctl.get_value()
            except Exception:
                d_new = None
            self.log("  材料密度: %r -> %r (目标 %g) %s"
                     % (d_old, d_new, density, "OK" if d_ok else "失败"))

        # 溶液温度（用户 2026-11-04：写死；通气/搅拌/转速保持关闭不动）
        temp_ctl = cids.get("Elec_Cell_Temp_Text")
        if temp_ctl is not None and temperature is not None:
            try:
                t_old = temp_ctl.get_value()
            except Exception:
                t_old = None
            t_ok = self.set_edit(temp_ctl, "%g" % temperature)
            try:
                t_new = temp_ctl.get_value()
            except Exception:
                t_new = None
            self.log("  溶液温度: %r -> %r (目标 %g) %s"
                     % (t_old, t_new, temperature, "OK" if t_ok else "失败"))

        # 参比电极是下拉选择（不能直接输入），用户要求 Ag/AgCl(饱和KCl)
        ref_ctl = cids.get("Elec_Page_Combo")
        if ref_ctl is not None:
            try:
                r_cur = ref_ctl.legacy_properties().get("Value")
            except Exception:
                r_cur = None
            self.log("  参比电极: %r（如需修改请手动在软件里选）" % (r_cur,))

        btn_ok = cids.get("Elec_Btn_OK")
        if btn_ok is None:
            self.log("  缺 Elec_Btn_OK")
            return False
        try:
            msg_click(btn_ok)
            time.sleep(1.0)
        except Exception as e:
            self.log("  点电解池确定失败: %s" % e)
            return False
        return True

    def _cancel_cell(self, cell):
        try:
            ids = self.by_ids(cell)
            b = ids.get("Elec_Btn_Cancel")
            if b is not None:
                msg_click(b)
                time.sleep(0.6)
        except Exception:
            pass

    def press_ok(self, panel, kind: str = "auto") -> bool:
        # kind="auto" 时按参数窗标题推断，避免在动电位窗里去找 Ocp_Ok_Btn
        if kind == "auto":
            try:
                t = panel.window_text()
            except Exception:
                t = ""
            if "动电位" in t or "Tafel" in t:
                kind = "tafel"
            elif "阻抗" in t or "频率扫描" in t:
                kind = "eis"
            elif "阶梯波" in t or "阶跃" in t:
                kind = "step"
            else:
                kind = "ocp"
        ids = self.by_ids(panel)
        aid = BTN_OK.get(kind)
        btn = ids.get(aid) if aid else None
        if btn is None:
            for cand in ("确定", "OK"):
                try:
                    btn = panel.child_window(title=cand, control_type="Button")
                    if btn.exists(timeout=0.5):
                        break
                    btn = None
                except Exception:
                    btn = None
        if btn is None:
            self.log("  找不到确定按钮")
            return False
        try:
            msg_click(btn)
            time.sleep(1.5)
            return True
        except Exception as e:
            self.log("  点确定失败: %s" % e)
            return False

    # ---------------- 运行窗口 ----------------
    def start_experiment(self, panel, kind: str = "auto",
                         wait: float = 8.0) -> bool:
        """点确定启动实验，自动处理「波形表指令失败」错误框。

        返回是否成功（运行窗出现）。不重试：2026-11-07 审查 P3 证实重试循环
        是死代码，且重开参数窗会重置参数（默认参数开跑=真机事故）；旧签名里的
        `retries` 形参自那时起就是死参数（C2.2 移除，调用方一并清理），
        重试语义=调用方重新走一遍开窗流程。
        实机实测：CS120 偶发 `发送波形表指令失败,请稍候重试`，
        关掉错误框后重试通常成功。
        """
        import win32con
        import win32gui

        pre = set(all_run_hwnds())
        # 单次尝试（2026-11-07 审查 P3：原 for-retry 循环是死代码——第一次
        # 失败必然走"窗口已关/参数被重置"分支直接 return，retries 永不生效；
        # 重开参数窗参数会被重置，带默认参数开跑是真机事故，故不重试）
        ok = self.press_ok(panel, kind=kind)
        self.log("  点确定：%s" % ok)
        t_end = time.time() + wait
        pid = self._pid()
        while time.time() < t_end:
            time.sleep(0.6)
            # 只应答本实例的模态框：不带 pid 会点掉别台仪器/应用的弹窗
            # （审查 #2 的漏网处，审查 #31）；pid 取不到时不自动应答。
            mods = modal_dialogs(pid=pid) if pid else []
            for h in mods:
                txt = modal_text(h) or ""
                self.log("  模态框：%s" % txt[:70])
                click_modal(h, prefer=("确定", "是(Y)", "是", "关闭", "否(N)"))
                time.sleep(0.6)
            h = find_run_hwnd(exclude=pre, expect=None)
            if h:
                self.log("  运行窗出现：hwnd=%s" % h)
                return True
        self.log("  %g s 内未见运行窗" % wait)
        return False

    def activate(self) -> bool:
        """把本实例窗口弹到前台（4 实例共存时，每次交互前必做）。

        主桌面 4 实例并存时窗口互相遮挡：被挡住的窗口 click_input 会点到
        别人身上（前台窗口才是输入目标）。所以拿 UI 锁后先无条件置顶前台。
        """
        import win32con
        import win32gui
        hwnd = getattr(self, "hwnd", None)
        if not hwnd:
            return False
        try:
            r = win32gui.GetWindowRect(hwnd)
            if r[0] <= -30000 or r[1] <= -30000:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.4)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False

    def ensure_main_visible(self) -> bool:
        """主窗被最小化时还原它。

        WinForms 主窗最小化后 GetWindowRect 返回 (-32000,-32000,...)，
        它 own 的实验运行窗也会 IsWindowVisible=0，导致 UIA 读不到任何数值。
        """
        import win32con
        import win32gui

        # 2026-11-06 代码审查 P2：原引用不存在的 _main_hwnd/self.win，
        # hwnd 恒 None → 本方法恒 return False，最小化恢复完全失效。
        # 真实属性是 __init__ 里存的 self.hwnd。
        hwnd = getattr(self, "hwnd", None)
        if not hwnd:
            return False
        try:
            r = win32gui.GetWindowRect(hwnd)
            if r[0] <= -30000 or r[1] <= -30000:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)
                win32gui.BringWindowToTop(hwnd)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(0.4)
                return True
        except Exception:
            pass
        return False

    def ensure_run_window_visible(self, rw) -> bool:
        """运行窗跑到屏幕外时拉回屏幕内（只挪位置、不改可见性）。

        2026-11-12 真机 2 号（CS120 一号）实测：多实例并发时 CS5 把运行窗
        排在主窗左边，rect=(-31,97,640,571) 整个落在屏幕外——用户看不到
        页面，msg_click 的坐标点击也全部落空（按钮 enabled、UIA rect 正常，
        但真实鼠标点在屏幕外）。这里用 SetWindowPos 且**不加 SWP_SHOWWINDOW**：
        1 号实测对隐藏窗做 ShowWindow/SW_RESTORE 会让 runner 误判
        「运行窗口消失」，所以隐藏态交给文件心跳兜底，这里只管位置。
        """
        try:
            import win32api
            import win32con
            import win32gui
            h = rw.handle
            l, t, r, b = win32gui.GetWindowRect(h)
            sw = win32api.GetSystemMetrics(0)
            sh = win32api.GetSystemMetrics(1)
            w = max(320, r - l)
            hh = max(240, b - t)
            # 完全/大部分越界才算（±40 容差；最小化时 GetWindowRect 的 -32000 也算越界）
            if l >= -40 and t >= -40 and r <= sw + 40 and b <= sh + 40:
                return False
            x = max(0, min(l, sw - w))
            y = max(0, min(t, sh - hh))
            win32gui.SetWindowPos(h, win32con.HWND_TOP, x, y, w, hh,
                                  win32con.SWP_NOACTIVATE)
            self.log("  运行窗跑到屏幕外 (l=%d t=%d r=%d b=%d) → 拉回 (%d,%d)"
                     % (l, t, r, b, x, y))
            return True
        except Exception as e:
            self.log("  运行窗归位失败：%s" % e)
            return False

    def find_run_window(self, timeout=12.0,
                        keywords=("开路电位", "动电位", "恒电位", "阶梯波", "阻抗", "频率扫描"),
                        exclude=(), expect=None):
        """找实验运行窗口。

        注意：CS Studio5 的实验窗口是 **owned window**（主窗拥有），
        `Desktop(backend="uia").windows()` **列不出来**，必须用 win32 EnumWindows
        拿 hwnd，再 connect(handle=...) 取 UIA wrapper。

        exclude 传「启动前就存在的 hwnd」，避免抓到上一轮残留窗口（否则读数会
        一直停在上一次的终点时间）。
        expect  传本次期望的文件名片段，标题必须包含它 —— 真机上启动瞬间旧窗口
        可能还没关干净，只靠 exclude 会抓错（实测抓到过昨天的文件窗口）。
        """
        end = time.time() + timeout
        while time.time() < end:
            # 实验启动时常弹「是否覆盖当前文件?」，必须先点掉，否则不会跑
            n = clear_modals(limit=2, prefer=("是(Y)", "是", "覆盖", "确定"), pid=self._pid())
            if n:
                self.log("  已处理 %d 个提示框（覆盖/确定）" % n)
            h = find_run_hwnd(keywords, exclude=exclude, expect=expect)
            if h:
                try:
                    app = Application(backend="uia").connect(handle=h, timeout=5)
                    w = app.window(handle=h)
                    if w.window_text():
                        self.ensure_run_window_visible(w)
                        return w
                except Exception:
                    pass
            time.sleep(0.6)
        return None

    def stop_run(self, runwin=None, tries: int = 5) -> bool:
        """停掉正在跑的实验：点运行窗「停止」键，**循环确认真的停下**。

        2026-11-12 真机 1 号（CS350, CS 5 版）实测：单点一次「停止」返回 True，
        但 40 s 内数据文件仍在增长 —— 与 6 版 2026-11-09「连点 11 次都不停」
        同源。所以这里改成：每轮 = 点「停止」+ 记录并清掉弹出的确认框，
        最多 tries 轮；是否真停由调用方（wait_endexp 的文件心跳）裁决。

        实测补记（2026-11-12 演示模式抓 UIA 树）：CS5 运行窗的停止键虽然
        画的是红色 STOP 图标，但 UIA name 是完整的「停止」——运行窗共 24 个
        Button，顺序为 按分类顺序/按字母顺序/属性页/打开/…/停止(7)/暂停(8)/
        重新测试(9)/反向(10)/极化关闭(11)/…/关闭(23)，window_text() 匹配有效；
        点一次后数据文件即冻结（2516 B 18 s 不增长）。所以真机停不下来的症结
        不在「点不到按钮」，而在「点完停止后的确认框应答」——见
        clear_modals(prefer 不含「关闭」) 与 answer_confirm_uia（只扫对话框）。

        2026-11-14 补记：实验自然结束后「停止」键是禁用态——不是停不下来，
        而是没什么可停。此时直接返回 True 交调用方文件心跳裁决，不再空转
        重试、更不走关窗兜底（真机曾因此每次切换白烧 ~90 s）。
        """
        w = runwin or self.find_run_window(timeout=1.0)
        if w is None:
            return False
        clicked = False
        for _i in range(tries):
            hit = False
            disabled_stop = False
            for b in w.descendants(control_type="Button"):
                try:
                    if (b.window_text() or "").strip() != "停止":
                        continue
                    if not b.is_enabled():
                        disabled_stop = True
                        continue
                    if msg_click(b):
                        hit = clicked = True
                    else:
                        self.log("  「停止」键点击未生效（msg_click False）")
                    break
                except Exception:
                    continue
            if not hit and disabled_stop:
                self.log("  「停止」键禁用 → 实验可能已自行结束，交文件心跳裁决")
                return True
            if not hit:
                # 2026-11-14 真机实测：阻抗频率扫描扫完后的收尾运行窗里没有
                # 文字「停止」的 Button（OCP/动电位运行窗有）→ 报「点停止 False」。
                # 兜底按 automation_id/name 含 stop 找图标键；仍找不到只打印
                # 按钮清单（不做盲点：误点「重新测试」会重启实验更糟）。
                btns = []
                try:
                    btns = [b for b in w.descendants(control_type="Button")
                            if b.is_visible()]
                    self.log("  运行窗无「停止」键，按钮 %d 个：%s" % (
                        len(btns), [(b.window_text() or "·") for b in btns][:24]))
                except Exception:
                    pass
                for b in btns:
                    try:
                        aid = (b.element_info.automation_id or "").lower()
                        nm = (b.window_text() or "").lower()
                        if not ("stop" in aid or "stop" in nm):
                            continue
                        if not b.is_enabled():
                            continue
                        if msg_click(b):
                            hit = clicked = True
                            self.log("  停止（图标键 aid=%s）" % aid)
                        break
                    except Exception:
                        continue
                if not hit:
                    break
            # 点完立即处理确认框（CS5 某些阶段会弹「测试还没有完成，是否立即停止?」）
            try:
                for _h in modal_dialogs():
                    self.log("  停止后弹框：%s" % (modal_text(_h) or "?"))
            except Exception:
                pass
            try:
                n = clear_modals(limit=2, prefer=("是(Y)", "是", "确定"), pid=self._pid())
                if n:
                    self.log("  停止后应答 %d 个确认框" % n)
                else:
                    got = answer_confirm_uia(self._pid())
                    if got:
                        self.log("  停止后应答确认框「%s」（UIA 兜底）" % got)
            except Exception:
                pass
            time.sleep(1.5)
        return clicked

    def close_run(self, runwin=None) -> bool:
        w = runwin or self.find_run_window(timeout=1.0)
        if w is None:
            return False
        for b in w.descendants(control_type="Button"):
            try:
                if b.window_text() == "关闭":
                    msg_click(b)
                    time.sleep(0.8)
                    return True
            except Exception:
                continue
        return False

    def polarization_off(self, runwin=None) -> bool:
        """点运行窗工具栏的「极化关闭」，把极化回路断开。

        实测必要性：OCP 结束后立刻开 EIS，设备状态没复位，EIS 一个点都采不到
        （.z60 只有表头）。断开极化相当于把回路置回空闲。
        """
        w = runwin or self.find_run_window(timeout=1.0)
        if w is None:
            return False
        try:
            for tb in w.descendants(control_type="ToolBar"):
                try:
                    n = tb.button_count()
                except Exception:
                    continue
                for i in range(n):
                    try:
                        if (tb.button(i).window_text() or "").strip() == "极化关闭":
                            msg_click(tb.button(i))
                            self.log("  已点「极化关闭」")
                            return True
                    except Exception:
                        continue
        except Exception as e:
            self.log("  极化关闭异常：%s" % e)
        return False

    def close_temp_curve(self) -> int:
        """关掉「显示温度曲线」悬浮窗（CS5 每开一个测试都会弹一个）。

        用户 2026-11-09：5 版每一个测试的时候都会打开这东西，删掉。
        它是纯温度显示窗（T/°C vs Time/s），**没有实验本体**——直接
        WM_CLOSE 即可，不需要像 cleanup_run_windows 那样先点窗内停止。
        只动本进程的窗口：4 实例并存时不会关到别人的（同 cleanup 的
        pid 门禁；拿不到自身 pid 宁可不关）。
        """
        try:
            import win32gui
            import win32con
            import win32process
        except ImportError:
            return 0
        base = getattr(self, "hwnd", None) or getattr(self, "hwnd_hint", 0)
        try:
            if not base:
                base = self.main.handle
        except Exception:
            base = 0
        if not base:
            return 0
        _tid, pid = win32process.GetWindowThreadProcessId(base)
        if not pid:
            return 0
        n = 0

        def cb(h, _):
            nonlocal n
            try:
                _t, wp = win32process.GetWindowThreadProcessId(h)
                if int(wp) != int(pid):
                    return True
                t = win32gui.GetWindowText(h) or ""
                if "显示温度曲线" in t and win32gui.IsWindowVisible(h):
                    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                    n += 1
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, None)
        if n:
            self.log("  关闭 %d 个「显示温度曲线」窗" % n)
        return n

    def cleanup_run_windows(self, keep=()) -> int:
        """把残留的实验运行窗（图形显示/波形图）关掉，主窗绝不碰。

        只动**本软件进程**的窗口：本机可能同时开着 CS Studio5 和 CS Studio6，
        全局 EnumWindows 会把另一个软件正在跑的实验窗口也关掉（实测踩过，
        对方的实验还在跑但界面窗口没了）。
        """
        try:
            import win32gui
            import win32con
            import win32process
        except ImportError:
            return 0
        pids = set()
        try:
            base = getattr(self, "hwnd", None) or self.main.handle
            _tid, pid = win32process.GetWindowThreadProcessId(base)
            if pid:
                pids.add(int(pid))
        except Exception:
            pass
        if not pids:
            # 拿不到自身 pid：宁可不关任何窗口，也绝不能退化成"关全系统
            # 所有运行窗"（会把并开的 CS Studio6 的实验窗也关掉，2026-11-07 审查 P2）
            self.log("  cleanup_run_windows：拿不到自身进程 pid，跳过清理")
            return 0
        n = 0

        def cb(h, _):
            nonlocal n
            try:
                if h in keep:
                    return True
                if pids:
                    _tid, pid = win32process.GetWindowThreadProcessId(h)
                    if int(pid) not in pids:
                        return True
                t = win32gui.GetWindowText(h) or ""
                if not t or "CS Studio" in t:
                    return True
                if (("图形显示" in t or "波形图" in t or _is_run_title(t))
                        and win32gui.IsWindowVisible(h)):
                    # 先让实验真正停下来，再关窗口。
                    # 直接 WM_CLOSE 只是把界面窗口关掉，工作站里的实验会继续跑
                    # （实测：5 版窗口关了、实验还在采集，把下一个实验顶掉）。
                    stopped = False
                    for _try in range(2):
                        try:
                            if _stop_via_runwin(h):
                                stopped = True
                                break
                        except Exception:
                            pass
                        time.sleep(0.8)
                    if not stopped:
                        # 停止没点成功：宁可留着窗口（下次还能从它上面点停止），
                        # 也不能把「实验还在跑」的唯一界面证据关掉。
                        self.log("  ⚠️ 停不下来，保留窗口待排查：%r" % t[:48])
                        return True
                    time.sleep(1.5)
                    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                    n += 1
            except Exception:
                pass
            return True

        win32gui.EnumWindows(cb, None)
        if n:
            self.log("  关掉 %d 个残留实验窗口" % n)
        return n

    # ---------------- 状态 ----------------
    def run_status(self, runwin) -> str:
        """从状态栏读『采样频率(Hz):10,测量时间(s):180』这类文本。"""
        try:
            for c in runwin.descendants(control_type="Text"):
                try:
                    t = (c.window_text() or "").strip()
                    if "采样频率" in t or "测量时间" in t:
                        return t
                except Exception:
                    continue
        except Exception:
            pass
        return ""
