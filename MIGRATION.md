# 重构迁移说明（MIGRATION）

> **状态（2026-11-12 21:20）：本记录所述重构已全部并入主线**（`D:\deepseek\cspilot-parasite`）。
> 主线当前基线 `18805e4` + 本批改动；副本目录仅作历史留档，不再维护。
> **2026-11-14 更新**：终止/接续修复批直接落地原库（见文末）；副本并入核验完成，
> 原库为唯一工作库（用户批准），旧「原库只读」约束作废。

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
- ~~原库 `D:\deepseek\cspilot-parasite` 只读~~（2026-11-14 用户批准原库为唯一工作库，此条作废）；
  对外行为/CLI/文件产物保持兼容；
  每步以 11 套离线测试全绿为验收线；3 个弹窗截图测试中 test_fleet_gui 已于 C2.5 跑通（两图落 logs/）。
- **关窗≠实验停**：停止必须先点「停止」键并等数据文件心跳确认真停，才允许关窗/开下一项。

## 2026-11-14 终止/接续修复批（原库直改，用户按编号批准 1→4）

背景：11-14 真机（进口老AC-18V、国产 钝化 26V 等）切换测试项时终止不停：
CS5 停止空转、CS6 硬开下一项 COMError（-2147220991）。

- **修复1（runner5）**：`_RUN_PATH_RE` 允许空格——11-11 起命名空格分隔，
  旧 `[^\s]` 写法从真实标题抠不出路径 → `wait_endexp` 文件心跳判据整个失效；
  新增 `_data_file_for`，正常/强制收尾两轮都把数据文件全路径显式传给 `wait_endexp`。
  回归 `test_wait_endexp_path.py` 13 项（含 3 条 11-14 真实标题）。
- **修复2（driver5.stop_run）**：「停止」键禁用 = 实验已自行结束 → 返回 True
  交文件心跳裁决，不再 6 轮空转；图标兜底只认 aid/name 含 stop 且启用的键；
  msg_click 未生效记日志。回归 `test_stop_run_cs5.py` 7 项。
- **修复3（CS6 红线）**：① `_settle_after_stop` 返回 bool，菜单栏 60s 未恢复可用
  → OCP/阻抗/测试项三处闸门一律 `_fail` 停止自动接续（交人工）；
  ② OCP 数据停滞 7.5s 须过 `_menu_idle` 交叉验证——菜单仍禁用不判「自行结束」；
  ③ `studio_ui.close_win32_modal` 对「另存为」只点「取消」不点「保存」
  （保存=IDOK 被「确定」别名命中 → 循环弹框、菜单栏 60s 不恢复的真因）。
  回归 `test_cs6_settle_gate.py` 17 项。
- `test_judge_count.py` 假环境收尾打桩对齐新契约（闸门行为由 settle_gate 覆盖）。

验收：**全套离线 24 项全绿**——18 个 test_*（含新增 37 项回归）+ selftest_runner/
runner5/cs5 + testbed（simdevice 57/57、协议 27/27、 faults 14/14）。
真机验证待下次真机跑：CS6 日志应出现菜单交叉验证/另存为取消；CS5 应无停止空转。

### 副本并入核验（2026-11-14）
桌面副本 `CS-Pilot-GUI重构_20261112` 全量 162 文件比对：137 与原库相同；
17 处差异均为原库更新（含本批修复）；副本独有 8 文件仅运行时心跳/截图/.bak_rename2。
**无代码需回流**。副本 README/MIGRATION 已标「已并入主线、仅作历史留档」（未删除）。

## 2026-11-14 整体代码审查修复批（发现 1-26，用户批准「按顺序修补」）

背景：终止修复批之后对全库做整体审查，得 26 条已验证问题，按编号 1→26 顺序修复，
每批配离线回归；编号即审查发现编号，不重排。

### 修复 1-5（CS5 驱动层 P0）——回归 test_review_cs5.py 23 项
1. `driver5.fill_tafel` 停止电流：Max/MinCurrent 成对写入 + 回读校验，不一致重写、
   重写仍不一致 → 中止开跑（t=2000s 截断真因：.cor 残留 0.1mA 阈值）。
2. 模态框按进程过滤：`modal_dialogs/clear_modals` 增 pid 参数，4 处调用接
   `pid=self._pid()`，防多实例串窗误点；`_stop_via_runwin` 拆出
   `_stop_via_runwin_w`：停止键禁用=已自行结束，点击后按 pid 清弹窗 + UIA 兜底。
3. 「另存为」防护：只点「取消」/ID 2，永不走 id 兜底（保存=ID 1 会被「确定」别名命中）。
4. `runner5.build_filenames5` 查重覆盖 .cor/.z60/.txt 三扩展名（.z60 撞名不再触发覆盖框）。
5. CS5 停止确认弹窗兼容 .NET WinForms（`answer_confirm_uia` 兜底）。

### 修复 6-10（CS5 流程层）——回归 test_review_cs5_flow.py 18 项
6. `wait_endexp` 默认 quiet 3→8s；`_finish_run` 阻抗按 120s quiet/135s 轮超时/3 轮
   （低频点 ~100s 才写一次，旧阈值把「没 flush」当「已结束」）。
7. `_do_mon_test` 死代码 `files.get("tafel")` → `_data_file_for("动电位")`。
8. `_safe_finish` 60s 拿不到 UI 锁 → 不做界面收尾、交上层（不再无锁裸操作）。
9. `fill_ocp` 时间单位回读非「秒」→ 中止；`fill_eis` Vs_Combo 选择失败 → 中止。
10. `gui.py` CS5 分支把停止电流密度换算成 mA 填 `tafel_stop_ma`（A/cm²→mA 乘面积×1000）。

### 修复 11-18（CS6）——回归 test_review_cs6.py 26 项
11. `_data_paths()` 按真实存在枚举 .txt/.cor/.z60（阻抗 .z60 心跳不再盲）。
12. `close_run_windows` 顶层 owned 运行窗先点停止，停不下来保留窗（关窗≠实验停）。
13. `_finish` 拿不到 UI 锁不做界面收尾并停止自动接续；判停分支不再锁外裸 stop。
14. `is_running` 键数守卫（15-20 键才认数据工具栏）；`_toolbar` 双候选键数不符 → None。
15. `_do_stop_eis` 无条件 settle（is_running 启发式有假阴性）。
16. `_settle_after_stop` 60s 数据文件仍在长 → False（不再「按已停止处理」）。
17. `force_stop` 异常不再谎报已停。
18. `ocp_fixed` 固定时长模式不重试 OCP。

### 修复 19-26（多机/数据层）——回归 test_review_fleet_data.py 54 项
19. `fleet.stop_all` 先向所有活 runner 广播 CTRL_BREAK 再统一等待（共享 300s 截止）；
    `supervise_round` 在 stopping 期间冻结复活（旧代码边停边拉起先退出的机器）。
20. `stop_machine` 收尾等待 90→300s（多轮停止重试+菜单恢复 90s 不够）。
21. `watch.finished_quiet` 阈值自适应：max(quiet, 相邻样本间隔中位数×3)；
    runner6 两处静默判停叠加 `_menu_idle()` 交叉验证。
22. 一键清场顺序红线：先 `fleet.stop_all()`（runner 优雅收尾）→ 杀残留 runner →
    再杀 CSStudio（旧顺序先杀软件，活着的 runner 会继续注入/重连/重启实验）。
23. `stabilizer.feed` 遇 t 回退 → reset 重积累（文件覆盖重建后旧代码静默丢光新点）。
24. `ui_lock` 可重入计数（内层 release 不再提前放掉外层的锁）；
    `graceful_exit` 信号处理器只置旗标，主循环 `consume_abort` 在两次 tick 之间
    执行 abort（防 UI 重入）；9 个入口 14 处循环全部接线（fake_runner 自带处理器除外）。
25. `fleet_gui.refresh` 异常防护：任何异常不打断 2s 重排，看板显示错误。
26. OCP 到点全程无数据 → 走 S_STOP_OCP 停止收尾后报错，拒绝以 0V 基准接续；
    `watch` 增 read_errors/bad_lines 计数，runner6 三个监视点累计异常大声告警。

验收（2026-11-14）：**全套离线 24 套全绿、0 FAIL**——22 个根目录 test_*
（含四份审查回归 23+18+26+54=121 项）+ testbed faults 14/14、协议全部通过；
逐套日志在 `_auto/accept_1114/`。真机验证待下次真机跑：急停应并行收尾且不复活、
清场后无 runner 残留注入、慢 flush 体系不再被静默阈值截断。

### 2026-11-15 动电位停止改由软件自带（用户指令）

- 删除 `runner5._do_mon_test` 里的脚本侧电流密度判停（原来连续 2 个新点
  `|i|/面积 ≥ 1e-3 A/cm²` 就 `_safe_finish`）。
- 改为完全依赖软件自带「扫描停止电流」：`PotDynamic_ScanStop_chk` +
  `PotDynamic_MaxCurrent_txt` / `PotDynamic_MinCurrent_txt`，各入口按
  **面积×1 mA（= 1×10⁻³ A/cm²）** 写入——`runner5_live.py:138`、`gui.py:466`、
  `runner5_resume_after_ocp.py:68`，本次补 `runner5_resume_tafel.py`；
  `driver5.fill_tafel(stop_ma=...)` 成对写入 + 回读核验（不一致重写，仍不符中止）。
- 脚本只负责「等它停」：运行窗消失 / 数据 20 s 不更新 / 文件心跳静止 / 阶段超时。
- `test_i_hit_new_points_r5.py` 改为守护测试（3 项）：电流再大、新点再多，
  runner5 也不自己判停。
- 6 版（CS350M）动电位参数窗没有「扫描停止电流」控件，`runner6.py:1113-1130`
  按文件第 2 列 A/cm² 的判停保留（连续 2 个新点 ≥1e-3）。

