# -*- coding: utf-8 -*-
"""probe_dump6.py —— 侦察 6 版界面：进演示模式菜单长什么样、有哪些项。

只读侦察：启动软件 → 打印主窗标题 / 系统设置菜单项 → 退出。
不点任何会改参数的按钮。
"""

import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import studio_ui as S

EXE6 = r"D:\sci\MDI Jade 9\CorrTest.CSStudio.exe"
OUT = r"D:\deepseek\_probe\dump6_recon.log"

_lines = []


def log(m):
    print(m, flush=True)
    _lines.append(str(m))


def main():
    log("启动 6 版：%s" % EXE6)
    p = subprocess.Popen([EXE6])
    ui = S.Studio(log=log)
    if not ui.acquire(30):
        log("!! 30 s 没找到主窗")
        return 2
    log("主窗：%r" % (ui.title,))
    log("演示模式：%s" % ui.is_demo)

    time.sleep(1.0)
    ui.force_foreground()
    try:
        n = ui.clear_modals(limit=4)
        log("关闭模态框：%r" % (n,))
    except Exception as e:
        log("关模态出错：%s" % e)

    # 看系统设置菜单
    for hk, name in (("%s", "系统设置(S)"), ("%e", "测试方法(E)")):
        try:
            ok = ui.open_menu(hk)
            log("")
            log("=== 打开菜单 %s（%s）→ %s ===" % (name, hk, ok))
            if not ok:
                continue
            time.sleep(0.4)
            items = ui.menu_items()
            log("共 %d 项" % len(items))
            for it in items:
                try:
                    t, c, r = it
                    aid = getattr(c.element_info, "automation_id", "") or ""
                    acc = getattr(c.element_info, "accelerator_key", "") or ""
                    log("   %-42r aid=%-26r key=%-8r rect=%s" % (t, aid, acc, r))
                except Exception as e:
                    log("   <读不到：%r：%s>" % (it, e))
            # 收起菜单
            ui.open_menu(hk)
        except Exception as e:
            log("菜单 %s 出错：%s" % (name, e))

    time.sleep(0.5)
    log("")
    log("侦察完成，关闭软件")
    try:
        p.terminate()
        p.wait(timeout=10)
    except Exception as e:
        log("关软件出错：%s" % e)
    return 0


if __name__ == "__main__":
    rc = main()
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
    except Exception:
        pass
    sys.exit(rc)
