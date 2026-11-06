# CS-Pilot 方案3 自动任务状态（10 小时窗口 · 2026-11-07 00:05 起）

> 本文件是本轮自动任务的**唯一进度真相源**。巡检 cron 每 10 分钟读它。
> 开始时间：2026-11-07 00:05 ｜ 窗口截止：**2026-11-07 10:05**（超过即收尾）
> 项目：`D:\deepseek\cspilot-parasite`（git 仓库，本轮基线快照 e9ae88f，6 套测试全 PASS）
> 文档区：`D:\杂物间\xiyve的obsidian\未完成项目记录\deepseek-harness\cs-pilot\`
> 目标：推进方案3（纯代码无头装配）剩余缺口——RX 收包入库、GetUID 应答、三实验下发实测、模拟器正式化、全链回归、文档。

## 安全红线（每个代理每轮必须遵守）

1. 串口：只允许虚拟对 **CNCA0/CNCB0（别名 COM90）** 与 **CNCA1/CNCB1（别名 COM91）**。
   **绝不打开 COM16/COM10/COM6/COM4/COM5/COM11/COM12（真实设备/蓝牙）——真机实验必须用户在场授权。**
2. 绝不启动 CS Studio GUI（CorrStudio/CorrTest 进程）；绝不写入 `D:\sci\MDI Jade 9` 安装目录（DLL 只允许 LoadFrom 读）。
3. 绝不删除任何 `.cor/.txt` 实测数据；临时探针放 `D:\deepseek\_tmp\`，日志放 `D:\deepseek\_probe\`。
4. taskkill 只允许针对本任务自己的残留进程（命令行含 cspilot-parasite / sim_probe / simdevice / probe_ / testbed 的 python/powershell），先用命令行匹配确认再杀，绝不 kill 其他进程。
5. PowerShell 5.1 脚本含中文必须存 UTF-8 with BOM；长脚本用 Write 工具写文件再执行，不用 heredoc（截断坑）。
6. 每个里程碑 git commit（仅本仓库，绝不 push）；不动既有 6 套测试的语义，任何改动后重跑保证全 PASS。
7. 枚举一律按名解析（坑 41），绝不写死数字。

## 端口所有权（并行不冲突）

| 资源 | 归属 |
|---|---|
| CNCA0/CNCB0 + 别名 COM90 | **Agent B**（RX 收包入库） |
| CNCA1/CNCB1 + 别名 COM91 | **Agent C**（三实验下发实测） |
| 不占串口（离线自测） | **Agent A**（simdevice v2） |
| Phase 2 整合 | 串行使用两对（先用 COM90 后 COM91） |

## 工作流看板（Phase 1）

| 工作流 | 心跳文件 | 状态 |
|---|---|---|
| A · 模拟器 v2：testbed/simdevice.py（全命令解析+应答+数据推送+离线 --selftest） | _auto/AGENT_A.md | ✅ 完成（commit 317b272） |
| B · .NET RX 收包入库（0x68 → PointCount 涨 + GetUID 应答消费） | _auto/AGENT_B.md | ✅ 完成（实测修正：入库命令码是 0x60 非 0x68；probe_rx_final 两连跑 RX-ALL-OK） |
| C · 三实验 SendMethodBytes 实测（Tafel/EIS/阶梯波：帧捕获+逐字段解码表） | _auto/AGENT_C.md | ✅ 完成（commit 212ebc8） |
| **Phase 2 整合**（四实验全链回归 + test_protocol.py + 既有 6 套全绿） | _auto/AGENT_INT.md | ✅ 完成（02:20；probe_e2e 四实验 VERDICT: E2E-ALL-OK，test_protocol 27 项+selftest 57 项+既有 6 套全 PASS） |
| **Phase 3 收尾**（独立审查修 bug → 08 号文档 + 00/README/03 清单更新 → ALL-DONE） | _auto/AGENT_DOC.md | ✅ 完成（独立审查 P1/P2/P3 全落地 commit d98dd01，8 套测试全 PASS；08 号执行记录 + 00/README/03 三处更新；ALL-DONE 见文末） |

心跳协议：代理开始时在 AGENT_X.md 写 `START <时间> <一句目标>`；每完成一步追加 `[<时间>] <一句话>`；结束写 `DONE <时间>`，并把上表状态改为 ✅（附结论 2-3 句）。断线判据：心跳最后时间戳距今 > 30 分钟且状态非 ✅。

**并发规则（重要）**：本环境后台代理并发上限为 **2**。同一时刻最多 2 个工作流在跑。排队（⏸）的工作流在任一在跑工作流变为 ✅ 后**立即重启**（主会话或巡检执行；重启前先把它标 🔄 再启动，避免双重启动）。排队引起的重启不计入「断线重启 ≤3 次」的限额；只有因心跳超时被重启的才计数。

## Phase 2 计划（Phase 1 全 ✅ 后启动，心跳 _auto/AGENT_INT.md）

整合代理（串口串行：先 COM90 后 COM91）：
1. simdevice.py 接管 CNCB0：全链路回归 = 四实验 SendMethodBytes → TX 帧 → sim 应答 → RX 入库 PointCount 涨 → SysStop，一条龙脚本 testbed/probe_e2e.ps1。
2. 固化 testbed/test_protocol.py 协议级回归（无串口可跑的解析断言为主 + 可选 --com 冒烟开关）。
3. 全仓 6 套既有测试 + 新测试全 PASS；发现问题即修（提交注明）。

## Phase 3 计划（Phase 2 后启动，心跳 _auto/AGENT_DOC.md）

1. 独立审查子代理：审查本轮全部新代码（P1/P2/P3 分级），P1/P2 修复落地并回归测试。
2. 文档：写 `08_纯代码测试床_全链回归.md`（cs-pilot 文档目录）；更新 00 恢复入口 §2026-11-06、仓库 README；若 B 产生新协议语义，更新 03 清单 RX 章节。
3. 最终 git commit + 在本文件写 ALL-DONE + 总结一段。

## 关键事实速查（给新代理的起跑线）

- 工作配方（顺序敏感，范本 testbed/probe_testbed9.ps1）：LoadFrom DLL（D:\sci\MDI Jade 9）→ `SerialConnect.Open("COM90")` → `conn.CheckPackReceiveThread()` → `new BaseContext()` → `ctx.SetConnect(conn)`；**绝不调 ctx.InitCom（会自建 SockectConnect 覆盖连接）**；`ctx.ThisExp=<Experiment 按名解析>`；`ctx.BaseParam=<参数对象>`；**参数对象反挂 ctx（属性 baseContext/BaseContext/context/Context 逐个试，缺它 SendMethodBytes NullRef）** → `new ExpComSendClass(ctx)` → `ctx.set_ExpComSend(send)` → `send.SendMethodBytes(params)`。
- 参数类：CSStudio6.CorrData.dll 的 MethodParams 命名空间（OcpParams/PotDynamicParams/**EISVSfrqParams**/PotSquareParams，无参构造 + GetSaveString/InitByString；「EisParams」不存在，C 反射实测修正）；四窗默认值实测 `D:\deepseek\_probe\dump6_all\defaults_*.json`。
- 协议：帧 = `55 AA | LEN_H LEN_L | CMD | DATA… | SUM`，SUM = 累加和 sum(buf[0..len-2])&0xFF（不是 CRC16）；无载荷命令 LEN=6；float32 小端（实测样本 `55 AA 00 0A 60 CD 7B 0E BE 7D` → −0.139 V）。详见文档区 03_反编译API清单.md。
- 现模拟器：**正式资产 `testbed/simdevice.py`（Agent A 完成，--selftest 41/41）**；前身临时版在 `D:\deepseek\_probe\vp-channel\simdevice.py`（`_tmp/sim_probe2.py` 只是探针脚本）；sim 日志样例 `D:\deepseek\_probe\testbed_sim*.log`。OCP 批量帧实测 126B=30 点 float32（文档 29 点系误记）。
- 命令面反射归档：`D:\deepseek\_probe\sendtest.txt`（ExpComSendClass 40+ 方法，含 SendEisSetup/SendDevSetup/GetOcpValue）。
- .NET 桥：pythonnet 未装，用 PowerShell 5.1 反射（范本仓库根 csdotnet.ps1）；程序集 .NET Framework 4.5.2；ilspycmd 已装（部分程序集方法体被 stub 化——静态结论必须运行期验证）。
- 07 号执行记录（§6 测试床全貌）在文档区；上一轮自动任务状态 `_auto/AUTO_STATE.md`（已完成，只读参考）。

## 各工作流结论区

（各代理 DONE 时在此追加）

### A 结论
testbed/simdevice.py 落地（自包含单文件，commit 317b272）：累加和编解码+坏帧拒绝计数、30 个命令名全表分发（未知命令 NAck 0xFF+原命令号）、0x51(OCP)/0x54(动电位·Tafel 同构)/0x45/0x40 参数解码、0x68 批量推流、JSONL 帧日志；`python testbed/simdevice.py --selftest` 41/41 全绿 EXIT=0，全程离线不 import pyserial、代码内硬拒绝真实设备口。关键实测修正：OCP 批量帧=126B/30 点 float32（真机帧 55 AA 00 7E 60…F6 SUM 复核，文档「29 点」系 LEN=0x7A 帧误记），FinalE+OCP=0.895371；默认 --points 30 与真机同构，--points 1 为旧版单点兼容模式。待校对：EIS/阶梯波帧布局（Agent C 实捕 frames_eis.txt/frames_step.txt 落地后校对推测解码器）、0x45/0x40 载荷语义、0xFF NAck 为模拟器自定约定。

### B 结论
**RX 收包入库 + GetUID 全部打通**：`testbed/probe_rx_final.ps1` 两连跑 `VERDICT: RX-ALL-OK`——模拟器推流后 PointCount 0→105（10Hz 无缺帧）、`DataItem` 三 List+ChargeValues+Indexs 同步涨、VolteValues 实值 −0.1389~−0.1411 V（换算库内已完成）、GetUID 返回 `CS350M24030650`。日志 `D:\deepseek\_probe\testbed_rx_final.log`。

**推翻/修正 03 清单的三个结论（Phase 3 文档代理请据此更新）**：
1. **入库命令码是 0x60 CSDataE / 0x61 CSDataI / 0x62 CSDataEI，不是 0x68**——0x68 CSDataOCP 在本版 `BaseContext.PackReceive` 分发表里不存在（运行期 Console 实测输出「未识别数据包类型：68」），与 A 的真机 126B/0x60 批量帧结论互证；真实 OCP 流=0x60。
2. **★ 无头装配的激活开关：`ctx.ExpMethodState = SysRuning`（公开 setter）**——CSStart 的 ack 走 `SendReturnBoolBytes` 同步队列（出队即丢）到不了 ctx，State 永远停在 SysStop，ctx.PackReceive 收到数据帧也不入库；手动置 SysRuning 后立刻入库+PointCount 自增。StartSample 是首个数据帧到达后的输出标志（自动变 true），不是前置条件。
3. **`IDataItem` 落数据方法真名是 `Add(ulong nIndex, double time, double volt, double curr, double charge)`**（03 清单的「MAdd」系误记，接口里根本没这个名字）；直调一次五个集合全 +1；PointCount 由 ctx 在 PackReceive 数据处理时自增，与 List 数独立。

**接线/机理事实**：`ctx.SetConnect(conn)` 会**自动**把 `conn.OnPackReceive` 挂到 `ctx.PackReceive`（Target=ctx 运行期验证），无需手动接线；接收双线程=`SerialConnect.Open` 自启 DataReceivedThread（读+校验和解析入队）+`CheckPackReceiveThread` 启动 PackReceivedThread（每 5ms 出队分发，OnPackReceive=null 时静默丢包）。**GetUID 机理=SendReturnPackage 双出队**（bool 消费 1 包 + payload 再消费 1 包）：空闲单应答必超时返回 ""（.NET 侧固有 quirk，真机+真软件同构存在），**必须在数据流中调用**（积包自然补 bool 位），返回 payload 的 hex 字符串、ASCII 解码即 SN。

**交付物**：`testbed/probe_rx_final.ps1`（一条龙验收，RX-OK×2 判据）、`testbed/rxprobe_helper.cs`（Add-Type 强类型委托接线+Console 捕获+合成帧注入+IDataItem 直调工具）、`testbed/sim_rx.py`（B 端 0x60 单点推流模拟器，SimDevice 子类）、`testbed/probe_rx1~4.ps1`（探索过程存档）。

**遗留**：① 批量 0x60 帧（126B/30 点，A 的 simdevice 默认布局）入库未单独验证（单点 10B 帧已证，Phase 2 顺手验）；② 0x71 CellYWGet 处理器在 DevInfo 量程表为空时抛索引越界（被分发线程 per-pack 捕获，不影响数据流）；③ EIS 入库路径未测（待 C 实捕帧）；④ B 进程已清、CNCA0/CNCB0 已让出。

### C 结论
**三实验 SendMethodBytes 实测全部打通**（commit 212ebc8；探针 `testbed/probe_send3.ps1`，帧表 `testbed/frames_tafel.txt / frames_eis.txt / frames_step.txt`，可复现生成器 `testbed/build_frames_c.py`，原始 JSONL `D:\deepseek\_probe\testbed_simC.jsonl`）。串口链 = COM91 别名（新脚本 `testbed/make_alias.py` 参数化造 COM91→\Device\com0com11=CNCA1）→ simdevice.py live @ CNCB1；冒烟 0x14 往返全对。

1. **Tafel/PotDynamicParams（ctx.ThisExp=ID_PotDynamic）**：方法帧=0x54 CSPotDynamic LEN=34，DATA=28B=7×f32 `[量程5.0][InitE+OCP][Mid1+OCP][Mid2+OCP][FinalE+OCP][ScanRate V/s][Frq]`，与 00 文档 3.5 真机样本逐字段吻合；Mid 槽未启用填 InitE、启用填 MidEOne/MidETwo（变体实测）；Frq=参数对象 get_Frq() 原值拷贝（GUI 规则 mV/s×2；对象内 IsFrq=true→SampleFrq×BaseFreqRate、false→BaseFreqRate/SampleInter，**无公共 setter**，InitByString 显式报「Frq 未实现 Set 过程」——纯代码路径改不了 Frq，只能借 SampleFrq/SampleInter 间接定）。
2. **EIS/EISVSfrqParams（ID_EISVSFRQ；类名是 EISVSfrqParams，状态文件旧写的 EisParams 不存在）**：**主下载路径就是 SendMethodBytes**，发 4 帧 0x45+0x40+0x41 ScanStart(45B)+0x70(31B 新命令)；**前提 ctx.BaseParam 必须挂参数对象，否则 EISVSfrqParams.SendMethodParams() 内部 NullRef**（OCP/Tafel/阶梯波不需要，EIS 独有——配方已补强）。`send.SendEisSetup(prm,false)` 单独调用只发 0x41 一帧（返回 True），是运行中重配路径**不是**主下载。0x41 DATA=39B：`[01][FFFFFFFF][Init_Fre f32][SineAmp f32][FFFFFF01][Integral_Time i32][Integral_Period i32][延迟标志 u8(=!IsAutoDelayTime)][DelayTime u16LE][11B 零]`；0x70 DATA=25B：`[Init_Fre f32][Final_Fre f32][SineBias f32][常量0.01][4×TenTwice f32][PrePolTime i32][MeasurementSpeedMode u8]`（均为差分实测）。TestPoints/Mode/ParamsType/ADS_EN/ADS_Fre/Filter_Fre/AttenualSet/Range_*/Filter_*/DevGain 在两帧中均未出现（CS350M 非 360 路径，待真机核对）。
3. **阶梯波/PotSquareParams（ID_AnyPotStatic）**：方法帧=**0x56 新命令**，LEN=114，DATA=108B：`[量程5.0][Initial_E+OCP][InitialTime 秒][(Step_k+OCP)(Time_k 秒)]×10[Final_E+OCP][FinalTime 秒][Cycles i32 LE @+100][Frq]`。**ms 陷阱实锤：TimeUnit=1 时对象 ms 值一律 ×0.001 成秒落帧**（2ms→0.002、50ms→0.05、100ms→0.1）；**Cycles 是 int32 不是 float**；未启用的 Step_k 仍发对象当前值、Time_k=0。模拟器回 NAck 不影响发送（SendMethodBytes 照样 True——发送不等待应答）。
4. **公共前缀**：每次 SendMethodBytes 先发 0x45 CSOutput（DATA=5B：u16BE 100+3 零，全实验恒定）+ 0x40 DevSetup（32B，DATA=26B，各实验因 DevParam 差异有少量字节不同），再发方法帧；SysStart→0x30、SysStop→0x32。
5. **给 Agent A（simdevice v2 校对）**：0x70 与 0x56 未收录（现回 NAck），解码器可按上述布局实现；0x41 已在 ACK_ECHO；真机 OCP 批量帧走 0x60（与 B 结论互证）。
6. **待验证项**：0x45 u16BE=100 语义、0x40 26B 逐字段、0x70 的 0.01 常量与 4×TenTwice 换算、EIS 未落帧字段（真机 360 路径？）、Frq 在真 GUI 会话的精确来源（真机样本 0.66=mV/s×2，与对象 getter 规则不符，GUI 内部另有写入路径）。

### Phase 2 结论（整合代理，2026-11-07 02:20）

**交付物三件（全部 commit）**：`testbed/simdevice.py` 升级（2adc629）、`testbed/test_protocol.py`（364b881）、`testbed/probe_e2e.ps1`（69fef67）。

1. **simdevice.py 对齐实测真相**：数据流默认 **0x60 CSDataE 批量帧**（--points 30 = 真机 126B 同构；`--cmd68` 保留旧命令码仅作协议对照）；新增 **0x56 阶梯波**（DATA=108B，ms 陷阱 ×0.001 落帧、Cycles int32@+100、未启用 Step_k 发对象当前值）、**0x70 CSEisSetup**（DATA=25B，Init/Final_Fre、SineBias、常量 0.01、4×TenTwice、PrePolTime、SpeedMode）、**0x41 ScanStart**（DATA=39B，Integral/延迟标志/DelayTime u16LE）三个专用解码器 + `potsquare_frame`/`eis_scan_start`/`eis_setup_frame` 三个构造器（与 C 实捕帧**逐字节一致**，selftest 断言背书）；0x45/0x40 前缀标注升级（0x45 全实验恒定 u16BE=100+3 零为 SendMethodBytes 前导帧、0x40 恒 32B 随实验 DevParam 少量差异）。step/eis 模式推 0x62 (E,i)。`--selftest` 41→**57 项全绿**（原 41 项语义对齐无退化，全程离线）。
2. **test_protocol.py 协议级回归 27 项**：P 组编解码/坏帧拒绝、T/E/S 组四实验 golden 帧（**直接解析 frames_*.txt RAW 段为唯一真相源**）+ O 组真机样本 + R 组离线分发对话（四方法帧全识别零 NAck）；`--com` 冒烟开关默认关闭。无串口可跑。
3. **probe_e2e.ps1 四实验一条龙 E2E，两连跑 `VERDICT: E2E-ALL-OK`**（日志 `D:\deepseek\_probe\testbed_e2e.log`，sim 帧日志 `D:\deepseek\_probe\testbed_e2e_sim.jsonl`）：
   - **OCP** PointCount +113/+127、五集合齐涨——**★ B 遗留① 已证：126B/30 点批量 0x60 帧整帧入库**（PointCount 每 3s 一帧精确 +30，10s 窗 +90，SysStop 冲刷 +23；若逐点入库最多 +3）
   - **Tafel** +107、**Step** +106——0x54/0x56 方法帧下发→sim 识别→0x62 数据流→ctx 入库全链
   - **EIS** +105 **EIS-OK**——**B 遗留③ 部分打通**：ctx 在 ID_EISVSFRQ 下同样接受 0x62 (E,i) 入五集合；EIS 专用数据形状（EisDatas 保持 0）仍待真机核对
   - **遗留**：GetUID 在批量流（3s/帧稀疏包）3 重试未消费（双出队 quirk，B 已证单点 10Hz 流可用）；E2E 判为 WARN 不阻断
   - **无害现象**：SysStart/SysStop 的 ACK（0x30/0x32）时序撞入 ctx.PackReceive 时打「未识别数据包类型：30/32」（与 B 记录的 0x68 同机理，不影响数据流与判定）
4. **全量测试 8 项全 PASS**：既有 6 套（14+6+全部+6+全部+9 项）+ test_protocol 27 项 + simdevice selftest 57 项，EXIT 全 0。**本轮零修改既有代码**。运行注记：test_stab_2phase/test_stab_snap/test_runner5_finish 必须按脚本头约定的 `python test_xxx.py` 跑——`python -I` 隔离模式不注入脚本目录致 import 失败，是运行方式非代码问题。
5. **给 Phase 3 文档代理**：03 清单 RX 章节可再补——「批量 0x60 帧整帧入库已实测（每帧 PointCount+30）」「0x30/0x32 ACK 撞 ctx 分发线程打未识别日志属正常」「EIS 实验 ctx 接受 0x62 形状数据入五集合」。


## 巡检日志

- 2026-11-07 00:05 任务创建：基线 e9ae88f 提交（11-06 上午改动 + 6 套测试全 PASS），Phase 1 三代理后台启动，cron 每 10 分钟巡检建立。
- 2026-11-07 00:10 修正：Agent C 启动失败（用户并发限制 exceeded）→ 改为 ⏸ 排队，A/B 正常在跑；状态文件入库 cc988fa。
- 2026-11-07 00:26 Agent A 完成（simdevice.py，selftest 41/41，commit 317b272，两处文档误记修正）→ 并发槽空出，C 标 🔄 重启。
- 2026-11-07 01:03 Phase 1 全 ✅（C 于 01:00 完成 commit 212ebc8，期间过滤器误拦一次、SendMessage 续跑解决）→ 主会话点火 Phase 2 整合代理。
- 2026-11-07 02:25 Phase 2 全 ✅（4 commits：simdevice 0x60 化+三解码器 2adc629 / test_protocol 27 项 364b881 / probe_e2e 四实验闭环 69fef67；既有代码零修改）→ 主会话点火 Phase 3 收尾代理。
- 2026-11-07 03:0x Phase 3 收尾完成（审查修复 d98dd01 + 文档 README 2b17d63；08 号/00 号/03 号三处文档更新）→ **ALL-DONE**。

## Phase 3 结论（收尾代理，2026-11-07）

**1 · 独立审查**（本轮全部新代码逐文件通读，git diff e9ae88f 核实既有文件零改动）：
- **P1 ×1**：`testbed/sim_rx.py` 依赖仓库外归档临时版（`_probe/vp-channel`）+ `CSDirect` 的
  cspilot.proto，与正式 simdevice「已归档不再依赖」声明矛盾且新环境必挂；且模式名
  potdynamic 与正式 simdevice 的 potdyn 不一致 → 改为只依赖同目录正式资产。
- **P2 ×1**：`test_protocol.py` T2 的 Frq 断言自比较空转（判据假阳性）→ 改实断言
  （正值有限；golden 默认对照 RUN Frq=2.0 证明无统一 rate×2 换算，勿写死）。
- **P3 ×8 全清**：C10 测试标题 0x68 旧写、未用 HOST_CMDS、JSONL 落盘双线程无锁、
  ReadOcp 锁外取 rng 值、0x51 采样率无夹紧、rxprobe_helper 两处过时注释（MAdd→Add、
  CaptureConsole 无镜像）、probe_e2e EIS minDelta 死配置+头注释夸大 GetUID 判据、
  probe_rx_final 基线 PointCount 未实测即打印。
- 修复 commit **d98dd01**；修完重跑全量 8 项测试全 PASS（6 既有套件 14+6+6+snap+9+close +
  test_protocol 27 + selftest 57，EXIT 全 0）。

**2 · 文档**：
- **新建** `08_纯代码测试床_全链回归.md`：四代理分工、无头装配最终配方（★SysRuning 激活开关
  + EIS 必须 BaseParam 两关键坑）、E2E 四实验结果表、8 套测试资产清单、审查表、真机在环清单。
- **更新** `00_项目恢复入口.md`：frontmatter updated=2026-11-07、顶部 important 块指向 08 号、
  §3.4 的 0x68 行与「116B/29 点」行按「划线注明不删原条目」规则加实证修正注记、
  新增「2026-11-07 更新」小节（★下一步=真机端到端）。
- **更新** 仓库 README.md（commit 2b17d63）：testbed 模块小节+配方+0x68 修正注记。
- **更新** `03_反编译API清单.md`：§1.1 SetConnect 自动接线 / §1.2 ExpMethodState 激活开关 /
  §2.1 Frq getter 规则+EISVSfrqParams 类名+PotSquareParams 注记 / §3.1 MAdd→Add 划线修正 /
  §5 例证 / §6.3 数据命令码+入库分发表+GetUID 双出队 / 新增 §10.10 运行期实证修正汇总表（11 条）。

**3 · 提交链（本轮全程）**：e9ae88f（基线）→ 317b272（A simdevice）→ e4e4daa/19bb7c8（B RX）→
212ebc8（C 帧表）→ 2adc629/364b881/69fef67/6a68a4c（Phase 2）→ d98dd01（Phase 3 审查修复）→
2b17d63（README）。文档区三文件不入 git。

---

# ★ ALL-DONE（2026-11-07 03:0x · 方案3 自动任务全窗口收官）

**成果**：纯代码（无 GUI 无真机）路线从 07 号的「TX 通、RX 未通」推进到**四实验全链闭环**——
无头装配（LoadFrom→SerialConnect→BaseContext→ExpComSendClass，★ExpMethodState=SysRuning 激活
开关、EIS 必须挂 BaseParam）→ SendMethodBytes 下发（0x45+0x40 前缀 + 0x51/0x54/0x56/0x41+0x70
方法帧，golden 帧表逐字段解码）→ simdevice 应答与推流（0x60 批量 30 点/0x62 单点）→ ctx 收包
入库（PointCount+五集合，批量帧整帧 +30 实证）→ SysStop；probe_e2e 四实验 `E2E-ALL-OK` 两连跑。
**测试资产 8 套全 PASS**（6 既有套件 + test_protocol 27 项 + selftest 57 项）。运行期实证推翻/
修正 11 条旧结论（入库码 0x60 非 0x68、IDataItem 真名 Add、GetUID 双出队 quirk、Frq getter
规则、EISVSfrqParams 类名等），全部回写文档（03 §10.10 / 00 §3.4 注记 / 08 号）。
**遗留**：EIS 专用数据形状、0x45/0x40/0x70 待定字段、0x56 真名、GetUID 批量流 quirk、
0x71 量程表越界——全部归入真机在环清单（08 号第八节）。
**下一步 = 真机端到端**（CS350M@COM16，必须用户在场授权；联调顺序建议：单点 10Hz 流打通
GetUID → OCP 批量流 → Tafel/阶梯波 → EIS 形状 → dup_policy/vs-OCP 语义确认）。
提交链：e9ae88f → 317b272 → e4e4daa → 212ebc8 → 2adc629 → 364b881 → 69fef67 → 6a68a4c →
d98dd01 → 2b17d63。
