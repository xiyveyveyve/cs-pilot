# 重构迁移说明（MIGRATION）

> **状态（2026-11-12 21:20）：本记录所述重构已全部并入主线**（`D:\deepseek\cspilot-parasite`）。
> 主线当前基线 `18805e4` + 本批改动；副本目录仅作历史留档，不再维护。

基线：`D:\deepseek\cspilot-parasite` **工作区快照**（HEAD `929b523`，2026-11-10 17:49；另含 11-11 真机联调未提交改动 528 行）。该批改动已于 2026-11-12 提交为 `18805e4`，故本副本内容等价于 `18805e4` + C1/C2.1/C2.2/C2.5 改动。
审计报告：`C:\Users\xiyve\Desktop\CS-Pilot-GUI线审计报告_20261112.md`。
权威计划：`C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\OVERNIGHT_PLAN.md` §4（B4 定案）。

## 已完成

### C1（05:4x）整体复制
137 文件 → 本目录（排除 .git/__pycache__）。副本离线基线 10/11 套绿；
test_naming 4 项失败为**原库陈旧测试**（11-11 命名口径改空格分隔，测试未同步——diff 证实），
列入 C2.4 修复。

### C2.1（06:1x）archive 归档 + 骨架就位
- `archive/`：44 个一次性脚本（probe_*×40、verify_*×2、monitor_only、bench_6v、sniff_startup、
  plot_jkf、position_windows、resume_tafel）——互不引用、无测试引用；38 个 import 仓库模块的
  已加 2 行路径引导头（archive 内可直接 `python archive/<脚本>.py` 运行）。
- 根目录 .py 87 → 43。
- 骨架目录 `core/ ui/ drivers/ runners/ entries/ config/ tools/ docs/` 就位（空）。
- 测试与归档前完全一致（唯一失败仍是陈旧 test_naming）→ **零逻辑改动达成**。

### C2.2（06:4x）bug 修复三件 ✅ 已完成
① runner5.py:349 对只读 property 赋值 —— 修复为**删掉该行**（`running` 无 setter，
   且上一行 `set_state(S_ERROR)` 后 property 本就返回 False）；
② runner5 电流密度判停按 tick 计数 → 对齐 runner6 的 `_i_last_t` 以新点计数修法 + 补回归测试
   `test_i_hit_new_points_r5.py`（3 用例）；
③ driver5.start_experiment 的 `retries` 死参数清理（签名与 5 个调用方对齐）。

### C2.3（2026-11-12 07:1x）——**缩水执行：低风险清理包**（诚实记录）
已做：
- SU-5：sync_barrier 支持结构化 stopping 字段（runner5_live/runner6_live 写心跳时自带，
  语义与旧文案规则等价，旧心跳自动回退文案匹配）——行为等价性验证 4/4 PASS。
- 6-1：runner6 死导入删除；6-3：runner6 两处无意义 hasattr 清理。
- P3：多通道模式重做方案.md → docs/；machines_real.json.bak_pre_rename 删除
  （原库同文件仍在磁盘，已加入 .gitignore，不进版本库）。
未做（★ 时间窗口不足，半吊子大一统比不做更乱——设计留档见审计报告 §4.2，作为后续路线）：
- ui/ 五件套统一（4 处模态框/4 处编辑框/2 套下拉的合并——涉及 CS5 全局窗 vs CS6 pid 域
  语义差异，需真机联调护航）
- runners/base.py 的 BaseRunner/StallWatcher 提取（runner5/6 时序常数不同，需逐行为等价验证）
- 生产文件正式分层进 core/ui/drivers/runners/entries（平移必破 import，需与上述统一同批）

### C2.4（2026-11-12 07:4x）——test_naming 修正 + README 重写（诚实缩减）
已做：
- test_naming.py 对齐 2026-11-11 空格口径（docstring 注明变更史）→ **6/6 PASS，副本 11/11 套全绿**。
- README.md 重写（快速上手/目录/版本差异/测试清单/改动摘要/红线）。
未做（并入后续路线，与 C2.3 未执行项同批）：
- config/machines.py 统一 loader（machines.json 双轨仍靠文件名区分）
- gui 单代化（v1 序列选项移除——涉及用户工作流变更，需用户裁定）

### C2.5（2026-11-12 11:2x）——副本路径自洽 + 四通道按型号命名（人工复核后补修）
背景：C1 是"整体复制"，漏改了复制残留的绝对路径 → 副本"能读不能跑多机"。
- runner5_live.py:62 / runner6_live.py:62：`HB_DIR` 由 `r"D:\deepseek\cspilot-parasite\_auto\hb"`
  改为相对 `__file__` 的 `_auto/hb`（与 sync_barrier.py:24 / fleet.py:30 口径一致）。
  原状态：runner 心跳写进原库，而 fleet_gui 与同步屏障读副本 → **多机看板全灰、停止屏障失效**。
- 启动检测.bat:3：`cd /d "D:\deepseek\cspilot-parasite"` → `cd /d "%~dp0"`（原来双击跑的是原库）。
- testbed/fake_runner.py:16,27、stop_tafel_visible.py:8：同样由绝对路径改相对。
- test_fleet_gui.py：① 急停确认框打桩（无人值守自动点「是」）；② 删掉废行 `g._log = g._log`
  （FleetGUI 无 `_log` 属性 → Tkinter 回调抛 AttributeError → 后续 `root.after` 不再调度
  = 2026-11-12 08:5x「挂起 30 分钟、无 PNG」的**真因**）；③ 配置/截图路径改到副本内。
- 验证：test_fleet_gui 通过（全部停止 = True，两图落 logs/）；test_fleet 6/6、
  test_close_run_windows PASS、test_status_report 25/25、testbed selftest 57/57、
  test_protocol 27/27；心跳实测落在副本 `_auto/hb/模拟A.json`。
- 配置：machines_real.json / machines.json 四通道改为 CS350M、CS350、CS120一号、CS120二号
  （一二号按序列号小者为一号），顺序按型号聚拢，lock 名按通道序重排，sim 端口 30001–30004 同步。

## 红线
- 原库 `D:\deepseek\cspilot-parasite` 只读；对外行为/CLI/文件产物保持兼容；
  每步以 11 套离线测试全绿为验收线；3 个弹窗截图测试中 test_fleet_gui 已于 C2.5 跑通（两图落 logs/）。
