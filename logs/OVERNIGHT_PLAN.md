# OVERNIGHT PLAN — CS-Pilot 夜间自动化（2026-11-11 23:10 → 11-12 09:00）

> 本文件是今晚所有自动化轮次的**唯一任务权威**。PROGRESS.md 与本文件冲突时，以本文件为准。
> 每轮唤醒的 agent：先读本文 → 执行「当前项」→ 完成后勾选清单 → 更新「当前项」与「本轮日志」→ 结束本轮。

---

## 0. 裁定（先读，防被旧结论带偏）

- PROGRESS.md「2026-11-10 · ★★ 决定性发现：…CS5 = blocked」节已于 2026-11-11 深夜标注 superseded：
  其变体失败清单系 `ack74 silent` 硬编码 + `0a_echo` sub 索引两 bug 所致假阴性。
  **当前事实 = CS5 无 UI 全链 S1–S7 已贯通 + CORRW ASCII 落盘**（PROGRESS.md「12:5x」节、
  Obsidian `12_纯代码线_dsh接管与CS5全链贯通.md`）。
- 若发现 PROGRESS.md 又出现陈旧的 blocked/失败论调追加（疑似旧看护任务复活），以本文件裁定纠正之，勿重复劳动。

---

## 1. 红线（每轮必须遵守）

1. **绝不触碰真机 COM 口**（COM16/COM10/COM7/COM6/COM4/5/11/12）——真机端到端需用户在场授权，今晚不做。
2. `D:\deepseek\cspilot-parasite`、`D:\deepseek\CSDirect`、`D:\sci\MDI Jade 9` **只读**，一个字节都不改。
3. 纯代码线的改动只写 `C:\Users\xiyve\Desktop\CS-Pilot-纯代码\`；GUI 重构产物只写桌面新文件夹（见 C 阶段）。
4. TCP 一律 31001+ 高位端口；离线测试只用模拟器。
5. 不创建/修改其他自动化任务；只在满足 §7 停止条件时调用 CronPauseSelf。
6. 每完成一个阶段按 §5 要求写 Obsidian；每完成一项勾选本清单并更新 §6「当前项」。

---

## 2. 当前状态（2026-11-11 23:10 建档）

- 基线：`tests/run_all.py` 23:04 实跑 **5/5 ALL-OK**（sim selftest 57/57、t2_all4 83.6s、t3_policy 35.9s、双机并行 79.3s）。
- CS5 S1–S7 全链已通（11-10 接管轮）；**真机端到端 = 唯一剩余大项（blocked，等用户授权，今晚不碰）**。
- Obsidian 已补档：00 号（入口指针）、10 号（补记）、12 号（接管轮全记录）、PROGRESS.md 订正注记、巡检记录订正行。
- 环境干净：无 CS Studio/模拟器残留进程；旧 zcode 看护自动化已禁用。

---

## 3. 阶段 A — 纯代码线离线收尾（按序执行）

- [x] **A1** `docs/02_CS5阶段结论.md`：CS5 阶段总结（已打通部分 / 待实机核对部分 / 已知公式冲突
      volt=(raw24−2^23)/2^23×10 vs 00 号 §3.6 的 (2^23−raw24)/2^23×9.8）。✅ 2026-11-11 23:40 完成
      素材：PROGRESS.md 12:5x 节、logs/run_nostream|run_wdnow|run_file.txt、t_cs5wati.txt、t_cs5start.txt、t_cs5srb.log。
- [x] **A2** 0x85 参数帧 13B 逐字段语义表（写进 02 文档）：素材 = logs/auto53_53le_32200.out、sim_32307.out、
      tests/probe/t_cs5parse2.txt（BaseParams.GetDoubleChannelSampleBytes 128B 静态反汇编）、CommandPackage 静态模板；
      逐字段（cmd/族码 0x63/sub/data[0..12]/SUM）标注已知值与推测，**推测必须标「未证实」**。
      ✅ 2026-11-11 23:50 完成（02 文档 §十：0x52 双通道帧逐字段 + 0x85 63 0A 表 + 配套帧 + SUM 含 AA 规则验算）
- [x] **A3** S6 长跑压测：`python -I tools/run_cs5.py --variant 53le --probe steps --no-stream` 连跑 ≥10 轮
      （logs/s6_soak_20261112.txt 逐轮记录），统计 S4/S6 偶发 False 率；若 ≥1 次失败且能定位规律
      （如 ClearData 时机/推流竞态），修 tools/run_cs5.py 并复测；修完必须重跑 tests/run_all.py 保持 5/5。
      ✅ 2026-11-12 00:2x 完成：**10/10 全绿**（wati7+0a_echo+echo74+--no-stream，每轮 15.6-15.9s，
      S4 False=0、S6 False/HANG=0）——修复已彻底稳定，无需改码，无需重跑 run_all。
- [ ] **A4** CS6 稳定性加固：tests/run_all.py 连跑 3 轮全绿（logs/run_all_x3_20261112.log）；
      任何 flaky 先修再计入。
- [x] **A5**（可选，A1–A4 全绿且时间充裕才做）UI 原生线①：写探针 dump frmOCP「确定」click 处理器 IL，
      找「确定后实验不真启动」的静默校验分支；**只做静态调查+写结论，夜间不启动软件本体 GUI（不弹窗）**。
      ✅ 2026-11-12 00:4x 完成（探针 tests/probe/t_cs6ocp.cs → logs/t_cs6ocp.txt）：
      **CorrForm 层全部 4B 桩**（确定处理器 frmOCP.XcJVANUspPb、BaseParamFrm.CheckParam/CheckFrq/
      SaveParams/IsCheckState/IsValidated 全是 00 00 00 2A；控件字段名全乱码）——静态到此为止；
      但方法名清单已把「确定后实验不真启动」嫌疑收敛到 **BaseParamFrm 校验链
      （StartButtonClick → CheckParam/CheckFrq 静默失败 → SaveParams）**；
      下一步只能运行时探针（CS6 壳 JIT 层 hook，反射拿不到真身）或 UI 线下次联调加日志。
- [x] **A6** 阶段收尾：PROGRESS.md + 巡检记录.md 写阶段小结 → 按 §5 写 Obsidian → 进入阶段 B。
      ✅ 2026-11-12 00:5x 完成。**阶段 A 全绿收官**（A0 5/5 基线、A1 文档修订、A2 帧字段表、
      A3 压测 10/10、A4 三连 3×5/5、A5 静态调查出结论）。

---

## 4. 阶段 B — GUI 线审计（只读）→ 阶段 C — 重构副本

### B 审计（产出 = `C:\Users\xiyve\Desktop\CS-Pilot-GUI线审计报告_20261112.md`）

- [x] **B1** 全量清点（已知底子，按需复核）：`D:\deepseek\cspilot-parasite` 顶层 ~100 个 .py **平铺 26268 行、
      无包结构**；三代驱动并存（driver.py 939 / driver5.py 1980 / driver_direct.py 1052）；
      三代 runner（runner.py 705 / runner5.py 1125 / runner6.py 1115 + runner5_live/runner6_live/runner5_resume_tafel）；
      40+ 个 probe_*.py 一次性脚本与生产代码混放；testbed/simdevice.py 2385 行；
      machines.json / machines_real.json / *.bak 配置散乱；git 提交链 F5→F9→主桌面方案；
      UI 层 studio_ui.py 982 + gui.py 688 + fleet_gui.py 393。
      ✅ 2026-11-12 00:5x 完成：import 图实测（生产核心/入口/40 探针 STANDALONE/测试四分类），
      结论已写入报告 §1（C:\Users\xiyve\Desktop\CS-Pilot-GUI线审计报告_20261112.md）——
      平铺无包 + 三代并存 + 40 探针混放 + 配置双轨 = 「乱与不统一」四大根源。
- [x] **B2** 逐文件精读（按价值排序：runner5/6 → driver5/driver_direct → studio_ui →
      watch/stabilizer/ui_lock/sync_barrier → gui.py/fleet*/monitor* → run_sample/who_is_who →
      testbed → 其余 probe/selftest 一览即可）。
      ✅ 2026-11-12 04:4x 完成（10 轮精读，报告 §2.1–§2.10）：核心 13 文件全量/定向精读、
      重复矩阵坐实（4 处实现 ×6 职责）、P1×3（runner5 property 赋值崩溃、runner5 判停漏修、
      复制粘贴演化）+ P2 ~15 条 + 行为资产清单。测试 11 套全离线化健康；testbed 工程化最好。
- [x] **B3** 问题清单分级 ✅ 05:1x：P0=0；P1 真缺陷×2（runner5 property 崩溃、判停漏修）+ P1 结构×3（复制粘贴演化矩阵、v1 legacy、上帝类）；P2 ~20；P3 清单；行为资产 15 项。
- [x] **B4** 报告定稿 ✅ 05:1x：选型 (a) 整体复制分层重构；目标结构 core/ui/drivers/runners/entries/config/tools/archive；执行序 C2.1–C2.4（4–5 轮）；明确不做边界 4 条；风险 5 条。
- [x] **B5** 报告完成 → 按 §5 写 Obsidian ✅ 05:2x（14 号已建，审计报告完成节落库）。

### C 重构副本（桌面新文件夹 `C:\Users\xiyve\Desktop\CS-Pilot-GUI重构_20261112\`）

> [!important] ★ 硬性前置（用户 2026-11-11 23:35 指令）
> **C 阶段任何一步（含 C1 复制）都必须等 B1–B5 全部勾选、精读完成、且优化报告文件已落盘之后才能开始。**
> 宁可 C 阶段推迟/缩水，不许带着没读完的代码动刀。

- [x] **C1** 按 B4 报告选型：(a) 整体复制后逐步重构（排除 .git、__pycache__），或 (b) 按模块重组拼装；
      默认 (a)，稳妥。✅ 2026-11-12 05:4x 完成：robocopy 137 文件（.py 95 两侧一致）→
      `Desktop\CS-Pilot-GUI重构_20261112`；副本离线基线 **10/11 套全绿**
      （test_naming 4 项失败=原库就有的陈旧测试：11-11 命名改空格、测试停在连字符旧规格，
      与原库逐字节 diff 证实——列入 C2.4 修复）。跳过夜间不弹窗的 3 个截图类测试（test_gui_shot/
      test_monitor_shot/test_fleet_gui），C3 阶段白天补跑。
- [x] **C2** 执行优化（保守优先）✅ 2026-11-12 07:4x（C2.1–C2.4 全部交付，明细见 MIGRATION.md）：
      C2.1 archive 44 脚本+骨架；C2.2 修复三件+回归锁；C2.3 缩水包（SU-5 结构化心跳+微修+P3）；
      C2.4 test_naming 对齐 11-11 空格口径（6/6 PASS）+ README 重写。
      **缩水声明**：ui 五件套统一/BaseRunner/生产分层/配置 loader/gui 单代化未执行
      （时间窗不足，半吊子大一统比不做更乱），设计留档报告 §4.2 作后续路线。
- [x] **C3** 测试 ✅ 2026-11-12 08:2x：**13/13 全绿**（CLI 11 套含新增回归 + selftest 57 + protocol 27）
      + 3 个截图测试白天补跑：gui_shot/monitor_shot PNG 目检 PASS；fleet_gui 测试 30 分钟无产出挂起后自行退出（无截图），诚实记为**未完成**——test_fleet.py（编排逻辑）6/6 已覆盖，GUI 截图验收列白天人工清单。
- [x] **C4** 完成 → 按 §5 写 Obsidian ✅ 08:2x（14 号 C 阶段节 + 00 号早更新节落库）。

---

## 5. Obsidian 记录要求（用户明确要求：每阶段完成后记录到 obs）

- vault：`D:\杂物间\xiyve的obsidian\未完成项目记录\deepseek-harness\cs-pilot\`
- **阶段 A 开始时**创建 `13_纯代码线_1112夜自动化执行记录.md`（frontmatter 仿 10/12 号），
  A 期间每项完成追加小节；**A 全部完成 = 写「阶段 A 小结」节**。
- **阶段 B 报告完成** → 创建 `14_GUI线审计与重构_执行记录.md`，写「审计报告完成」节（报告路径 + 要点摘要）。
- **阶段 C 完成** → 在 14 号追加「重构副本完成」节（做了什么 + 测试结果 + 文件夹路径）。
- **09:00 收尾** → 在 `00_项目恢复入口.md` 追加「2026-11-12 早更新」节（夜班总结果 + 下一步），
  并在 13/14 号写收尾节。

---

## 6. 当前项指针（每轮唤醒后由 agent 更新）

- **当前项：全部完成**（最终摘要已预写于 §7 上方；09:10 轮：确认 → CronPauseSelf，无其他动作）
  - 2026-11-12 04:1x | cron 第10轮 | B2 进展：gui/fleet/monitor 家族——gui v2 worker/queue 模式+关窗拦截
    = 行为资产；G-1 三 runner 隐式鸭子接口契约不一致（P2）；**F-1 fleet 的 CreateDesktop 路径已证伪
    未删（~80 行死路径）**、F-2 双编排哲学并存（fleet sim vs run_sample 真机，无共同抽象）
    | 下轮 testbed/测试抽样 → B3 分级 → B4 方案
  - 2026-11-12 04:4x | cron 第11轮 | B2 收尾完成：testbed（simdevice 双协议模拟器=纯代码线资产，健康）
    + 测试 11 套全离线化（多为审查修复的回归锁）——**runner6 判停修复有回归测试、runner5 同源 bug
    没修没测**（漂移案例实锤）；probe_*×40 归档候选 | 下轮 B3 分级 + B4 方案 + B5 落盘
  - 2026-11-12 05:2x | cron 第12轮 | **B 阶段收官**：B3 分级（P0=0/P1 真缺陷×2/P1 结构×3/P2 ~20/P3 清单）
    + B4 定稿（选型 (a)、目标结构、C2.1–C2.4 执行序、边界 4 条、风险 5 条）+ B5 落盘
    （报告全文 + Obsidian 14 号）。**C 阶段硬门禁已满足，下轮起 C1 复制 → C2.1 分层**
  - 2026-11-12 05:4x | cron 第13轮 | C1 完成：robocopy 137 文件（95 .py 两侧一致）→ 副本离线基线
    **10/11 套全绿**；test_naming 4 失败 = 原库陈旧测试（11-11 命名改空格未同步测试，逐字节 diff 证实）
    列入 C2.4；3 个弹窗截图测试夜间跳过、C3 白天补 | 下轮 C2.1 分层
  - 2026-11-12 06:1x | cron 第14轮 | C2.1 完成：44 脚本归档（38 加路径引导头）、根 .py 87→43、
    八目录骨架就位、MIGRATION.md 落盘；**范围微调：生产文件分层并入 C2.3**（平移必破 import，
    零逻辑改动的分层只能做到归档层）；测试与归档前逐项一致、唯一失败仍是原库陈旧 test_naming
    | 下轮 C2.2 修 bug 三件
  - 2026-11-12 06:4x | cron 第15轮 | C2.2 完成：三件修复落地 + test_i_hit_new_points_r5.py 回归锁
    （3 用例 PASS）；driver5 签名清理 + 5 调用方对齐；全套回归与基线一致 | 下轮 C2.3 共享层统一
  - 2026-11-12 07:1x | cron 第16轮 | C2.3 **缩水执行**（诚实决策：剩余 ~2h 做不完大一统，
    半吊子重构比不做更乱）：SU-5 结构化 stopping 字段（两 live 写入方+屏障双路径回退，
    行为等价 4/4）+ 6-1/6-3 微修 + P3 整理；**BaseRunner/ui 五件套/生产分层未执行**，
    设计留档报告 §4.2 作为后续路线 | 下轮 C2.4
  - 2026-11-12 07:4x | cron 第17轮 | C2.4 完成：test_naming 对齐空格口径（6/6 PASS，
    **副本 11/11 套全绿**）+ README 重写；config loader/gui 单代化诚实缩减未做
    | 下轮 C3 验收 + C4 Obsidian 收尾
  - 2026-11-12 08:2x | cron 第18轮 | C3 完成：**13/13 全绿**（CLI 11 套 + selftest 57 + protocol 27）；
    截图目检 gui 主窗/三机看板 PASS（文件名预览已见空格新口径）；fleet_gui 后台运行中；
    C4 完成：Obsidian 14 号 C 阶段节 + 00 号早更新节落库 | 下轮收 fleet_gui → 09:00 收尾自停
  - 2026-11-12 08:5x | cron 第19轮 | fleet_gui 测试 30 分钟挂起后自行退出（无截图）——诚实记为
    未完成（test_fleet.py 6/6 已覆盖编排逻辑），白天人工排查；**最终摘要已预写**（§7 上方），
    09:10 轮仅确认+CronPauseSelf | 夜班实质完成
  - 2026-11-12 03:4x | cron 第9轮 | B2 进展：支撑层全量精读——**stabilizer.py = 全库质量标杆**（两阶段
    +ASTM 快照，零复制）、watch.py 实际 162 行（B1 误估已修正）、ui_lock/sync_barrier 干净；
    SU-5 魔法字符串匹配（P2）；run_sample/who_is_who = 最新演化模板（以标题为准不信配置）
    | 下轮 gui/fleet/monitor 家族
- 本轮日志：
  - 2026-11-11 23:10 | 建档 | 基线 5/5 ALL-OK；旧看护自动化已禁用；计划书建立 | 从 A1 开始
  - 2026-11-11 23:40 | 交互会话 | A1 完成：`docs/02_CS5阶段结论.md` 落盘（已打通/待实机/公式冲突/壳边界/资产，
    预留 §8 给 A2 填 0x85 字段表）；PROGRESS.md+巡检记录已同步 | 下一轮从 A2 开始
  - 2026-11-11 23:50 | cron 首轮 | A2 完成：02 文档 §十 = 0x85 63 0A 逐字段表 + S4 帧2（0x52 07 D2 00 03）
    逐字段推断（dataLength 分支 5/7→9/11、GetDoubleSingleSampleBytes 4B 桩）+ SUM 含 AA 规则验算 + 配套帧表；
    Obsidian 13 号创建（A1+A2 纪要） | 下一轮从 A3（S6 十轮压测）开始
  - 2026-11-12 00:2x | cron 第2轮 | A3 完成：S6 压测 **10/10 全绿**（S4 False=0、S6 False=0，每轮 15.6-15.9s），
    修复彻底稳定无需改码；A4 三连回归已后台启动（logs/run_all_x3_20261112.log）| 下一轮收 A4 结果 → A5 判断
  - 2026-11-12 00:4x | cron 第2轮续（后台通知触发）| A4 完成：**3×(5/5 ALL-OK)**（各 ~3.3 分钟）；
    A5 完成：CorrForm 层全 4B 桩实锤，UI 原生线嫌疑收敛到 BaseParamFrm 校验链（运行时才能破，本轮静态止步）；
    A6 阶段 A 小结写入 PROGRESS/巡检/Obsidian 13 号 | **阶段 A 收官，下轮进 B1（GUI 审计清点）**
  - 2026-11-12 00:5x | cron 第3轮 | B1 完成：import 图四分类（生产核心 13 模块 / 入口 ~15 / 一次性探针 40 /
    测试 10），四大根源初判写入报告 §1 | 下轮进 B2（runner5.py 精读起）
  - 2026-11-12 01:1x | cron 第4轮 | B2 进展：runner5.py 精读完毕写入报告 §2.1——**P1 真缺陷 1 个**
    （L349 对只读 property 赋值必抛 AttributeError）+ 结构性重复 2 处（四段式 open/fill/start ~300 行
    同构、停滞判停逻辑 4 份且阈值口径不一致）+ P2×5 | 下轮 runner6.py 对照
  - 2026-11-12 01:4x | cron 第5轮 | B2 进展：runner6.py 精读 + 与 runner5 对照——**逐字复制 2 组方法**、
    停滞判停第 5 份、RunConfig ~20 字段重复；**新 P1：runner5 电流密度判停按 tick 计数**（runner6 已修
    runner5 漏修，同源 bug 跨文件不一致）；语义差异仅 3 处（数据源/收尾步数/控件 id）→ 共享骨架+策略注入
    方向确定，写入报告 §2.2 | 下轮 driver5.py
  - 2026-11-12 02:1x | cron 第6轮 | B2 进展：driver5.py 结构图全量+定向精读——**start_experiment 的 retries
    是死参数**（API 语义撒谎）、by_aid 内嵌重复 ×2、PostMessage 与 click_input 两套注入模型并存、
    模态框疑似两套实现（待 studio_ui 定级）；头部 5/6 差异表=重构版本差异配置表资产 | 下轮 driver_direct+driver
  - 2026-11-12 02:4x | cron 第7轮 | B2 进展：driver.py+driver_direct.py 对照——**gui.py 三代 runner 全部
    可选（v1 序列路径可达但非主线，死代码判定保守）**；set_cell_area 三份实现（P1）、step_ladder/
    _select_combo_containing 两份、driver.py ~700 行序列逻辑 legacy-alive；DirectDriver.stop 三级优先级
    （17 键校验防 CSAnalysis 误触）= 行为资产 | 下轮 studio_ui.py
  - 2026-11-12 03:1x | cron 第8轮 | B2 进展：studio_ui.py 精读——**重复矩阵收口：同一职责最多 4 处实现**
    （模态框 4 处坐实 P1、下拉 2 套、电解池 3 份、编辑框 4 份、点确定 4 份）；Studio 上帝类 890 行；
    工具栏 rect.top 绝对坐标魔法数（分辨率敏感）；B4 核心动作确定 = studio_ui 升级全版本共享基础层
    | 下轮支撑层四件套
- 遗留问题：
  - 0x85 的 data[4..14] 分块规则与 sub(0x0A/0x09) 语义未证实——真机联调按 §六-3 实录即可闭环，不阻塞。

---

## ★★ 最终摘要（2026-11-12 08:5x 预写；09:10 轮确认后 CronPauseSelf）

**夜班总结果（23:10 → 08:5x，18 轮唤醒，全部按 OVERNIGHT_PLAN 执行）**：

| 阶段 | 交付 |
|---|---|
| A 纯代码线 | CS5 结论文档全面修订（docs/02，stale blocked 裁定落档）；0x85/S4 帧族字段表（SUM 含 AA 规则六帧验算）；S6 压测 **10/10**；CS6 三连 **3×(5/5)**；UI 原生线静态调查（CorrForm 全 4B 桩实锤，嫌疑收敛 BaseParamFrm 校验链）。**纯代码线离线部分收官** |
| B GUI 审计 | 10 轮精读 13 文件：复制粘贴矩阵（同职责最多 4 处实现）+ P1×5（含 runner5 两处真缺陷）+ P2 ~20 + 行为资产 15 项；报告 `Desktop\CS-Pilot-GUI线审计报告_20261112.md` |
| C 重构副本 | `Desktop\CS-Pilot-GUI重构_20261112\`：归档 44 脚本、修复 3 真 bug（property 崩溃/判停漏修/retries 死参数）、SU-5 结构化心跳（行为等价 4/4）、test_naming 对齐口径、README 重写；**验收 13/13 全绿 + gui/monitor 截图目检 PASS**；未执行项（ui 统一/BaseRunner/分层/config loader/gui 单代化）诚实留档报告 §4.2 |
| Obsidian | 12 号（接管轮补档）+ 13 号（A 阶段）+ 14 号（B/C 阶段）+ 00 号三轮更新；PROGRESS/巡检/裁定同步 |

**唯一剩余大项不变：真机端到端（等用户在场授权）**。
**fleet_gui 截图测试挂起未出图**（test_fleet.py 6/6 已覆盖编排逻辑）——白天人工排查，不阻塞验收。
**09:10 轮动作：确认本摘要 → CronPauseSelf。**

## 7. 停止条件

- 本地时间 **>= 2026-11-12 09:00**：完成收尾（§5 最后一条 + 本文件写「最终摘要」）→ 调用 CronPauseSelf。
- 若连续 3 轮完全无可推进项（全部 blocked）：可提前 CronPauseSelf，并在 Obsidian 13/14 号说明原因。
- 其余情况一律干到 09:00，不提前停。
