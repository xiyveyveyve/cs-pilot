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
| A · 模拟器 v2：testbed/simdevice.py（全命令解析+应答+数据推送+离线 --selftest） | _auto/AGENT_A.md | 🔄 进行中 |
| B · .NET RX 收包入库（0x68 → PointCount 涨 + GetUID 应答消费） | _auto/AGENT_B.md | 🔄 进行中 |
| C · 三实验 SendMethodBytes 实测（Tafel/EIS/阶梯波：帧捕获+逐字段解码表） | _auto/AGENT_C.md | 🔄 进行中 |

心跳协议：代理开始时在 AGENT_X.md 写 `START <时间> <一句目标>`；每完成一步追加 `[<时间>] <一句话>`；结束写 `DONE <时间>`，并把上表状态改为 ✅（附结论 2-3 句）。断线判据：心跳最后时间戳距今 > 30 分钟且状态非 ✅。

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
- 参数类：CSStudio6.CorrData.dll 的 MethodParams 命名空间（OcpParams/PotDynamicParams/EisParams/PotSquareParams，无参构造 + GetSaveString/InitByString）；四窗默认值实测 `D:\deepseek\_probe\dump6_all\defaults_*.json`。
- 协议：帧 = `55 AA | LEN_H LEN_L | CMD | DATA… | SUM`，SUM = 累加和 sum(buf[0..len-2])&0xFF（不是 CRC16）；无载荷命令 LEN=6；float32 小端（实测样本 `55 AA 00 0A 60 CD 7B 0E BE 7D` → −0.139 V）。详见文档区 03_反编译API清单.md。
- 现模拟器：`D:\deepseek\_tmp\sim_probe2.py`（B 端 CNCB0 @115200，已解析 0x45/0x40/0x51/OCP 参数/0x30/0x32）；sim 日志样例 `D:\deepseek\_probe\testbed_sim*.log`。
- 命令面反射归档：`D:\deepseek\_probe\sendtest.txt`（ExpComSendClass 40+ 方法，含 SendEisSetup/SendDevSetup/GetOcpValue）。
- .NET 桥：pythonnet 未装，用 PowerShell 5.1 反射（范本仓库根 csdotnet.ps1）；程序集 .NET Framework 4.5.2；ilspycmd 已装（部分程序集方法体被 stub 化——静态结论必须运行期验证）。
- 07 号执行记录（§6 测试床全貌）在文档区；上一轮自动任务状态 `_auto/AUTO_STATE.md`（已完成，只读参考）。

## 各工作流结论区

（各代理 DONE 时在此追加）

### A 结论
（待填）

### B 结论
（待填）

### C 结论
（待填）

## 巡检日志

- 2026-11-07 00:05 任务创建：基线 e9ae88f 提交（11-06 上午改动 + 6 套测试全 PASS），Phase 1 三代理后台启动，cron 每 10 分钟巡检建立。
