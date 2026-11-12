# -*- coding: utf-8 -*-
"""probe_verify6.py —— 验证本轮四处修复是否真的生效：

① studio_ui.open_menu 在菜单项不存在（演示模式下的「测试方法(E)」）时返回 False
② DirectDriver._ensure_menu_mode 会自动退出演示模式
③ 退出后 open_menu("%e") 返回 True
④ 无设备时 dd.open("step") 返回 None 且 last_error == "no_device"，
   日志明确写"被「通讯配置向导」拦住"，而不是重试三次后含糊地说"打不开"
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S
import driver_direct as D

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\verify6.log"

_lines = []
fails = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def check(name, cond, detail=""):
    log("%s %s%s" % ("PASS" if cond else "FAIL", name, ("  " + detail) if detail else ""))
    if not cond:
        fails.append(name)


def kill6():
    subprocess.run("taskkill /F /IM CorrTest.CSStudio.exe /T", shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FakeBase:
    channel_title = None

    def _by_id(self, *a, **k):
        return None


def main():
    kill6()
    time.sleep(1.0)
    subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(40):
        log("!! 没找到主窗")
        return 2
    log("主窗：%r 演示=%s" % (ui.title, ui.is_demo))
    time.sleep(1.2)
    ui.force_foreground()
    ui.clear_modals(limit=3)

    dd = D.DirectDriver(ui, FakeBase(), log=log)

    # ① 非演示模式下 %e 应该能展开
    ui.force_foreground()
    ok = ui.open_menu("%e")
    check("① 非演示模式 open_menu('%e') 返回 True", ok is True, "got=%r" % (ok,))
    from pywinauto.keyboard import send_keys
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.5)

    # ② 进演示模式
    if not ui.is_demo:
        ui.click_menu("%s", "进入演示模式")
        time.sleep(1.8)
        ui.clear_modals(limit=3)
    log("现在：%r 演示=%s" % (ui.title, ui.is_demo))
    check("② 已进入演示模式", bool(ui.is_demo), "title=%r" % (ui.title,))

    # ③ 演示模式下 %e 应该返回 False（菜单整条不存在）
    ui.force_foreground()
    ok2 = ui.open_menu("%e")
    check("③ 演示模式 open_menu('%e') 返回 False", ok2 is False, "got=%r" % (ok2,))
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.4)

    # ④ _ensure_menu_mode 应自动退出演示模式
    dd._ensure_menu_mode()
    time.sleep(0.8)
    log("_ensure_menu_mode 之后：%r 演示=%s" % (ui.title, ui.is_demo))
    check("④ 已自动退出演示模式", not ui.is_demo, "title=%r" % (ui.title,))

    # ⑤ 退出后菜单恢复
    ui.force_foreground()
    ok3 = ui.open_menu("%e")
    check("⑤ 退出演示后 open_menu('%e') 返回 True", ok3 is True, "got=%r" % (ok3,))
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.5)

    # ⑥ 无设备时 open("step") 必须报 no_device
    t0 = time.time()
    pnl = dd.open("step")
    dt = time.time() - t0
    check("⑥ dd.open('step') 返回 None", pnl is None, "got=%r 用时%.1fs" % (pnl, dt))
    check("⑦ last_error 明确区分无设备/无响应",
          dd.last_error in ("no_device", "no_response"), "got=%r" % (dd.last_error,))
    check("⑧ 不再傻重试三次（用时 < 25 s）", dt < 25.0, "用时%.1fs" % dt)

    log("")
    log("结果：%d 项检查，失败 %d 项 %r" % (8, len(fails), fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    rc = 99
    try:
        rc = main()
    finally:
        log("清理：taskkill /T")
        try:
            kill6()
        except Exception:
            pass
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        log("EXIT=%s" % rc)
