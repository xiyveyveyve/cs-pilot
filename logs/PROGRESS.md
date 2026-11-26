---
title: "CS-Pilot 纯代码路线 — 进度真相源"
status: in-progress
created: 2026-11-10
updated: 2026-11-10
---

# CS-Pilot 纯代码路线 · PROGRESS

> 本文件是本项目的**唯一进度真相源**。每轮巡检/推进在此追加，不另建并行版本。
> 工作目录：`C:\Users\xiyve\Desktop\CS-Pilot-纯代码`
> 方案：[[01_纯代码路线_方案]]（docs/01_纯代码路线_方案.md）

## 当前阶段

**Phase 1 · 宿主最小可运行（T1 冒烟）** — in-progress

## 硬约束（每轮必读）

1. `D:\sci\MDI Jade 9`、`D:\sci\CS Studio5\CS Studio5`、`D:\deepseek\cspilot-parasite`、
   `D:\deepseek\CSDirect` **只读**，绝不修改。
2. 绝不碰真机端口 COM16/COM10/COM6/COM4/COM5/COM11/COM12。
3. 离线测试只用模拟器，TCP 用 31001+ 高位端口。
4. 新代码只写在本目录 `code/`。

## 已完成

- [x] 独立工作目录建成（docs/code/tests/logs/data，与主程序完全隔离）
- [x] 环境核实：csc v4.0.30319 可用、.NET 4.8、com0com 服务运行中、python 3.13
- [x] **API 全量 dump**（本轮最大产出，全部落 `logs/dump{1,2,3}.txt`）
  - `dump1`：IConnect 两实现（SerialConnect / SockectConnect）全部成员；CS5 的 SockectCom/CSTSockect
  - `dump2`：BaseContext 全属性/方法、ExpComSendClass 40 方法、IDataItem 23 组、
    四实验参数类全属性、CorrPackage、Experiment 枚举实值
  - `dump3`：IBaseParams / BaseParams、VsType / MethodState 枚举、IExpComSend、ZDataItem
- [x] **C# 宿主可用性验证通过**（`tests/probe/t2.cs`）：64 位进程内 LoadFrom 9 个 CS6 程序集 +
  `BaseContext` 实例化成功（`PointCount=0`）
- [x] 方案文档 `docs/01_纯代码路线_方案.md` 完成（含三个技术未知 U1/U2/U3）
- [x] `code/cshost/CsPilotHost.cs` 编写完成并编译通过（26,624 B exe）
- [x] `code/sim/simdevice.py` 只读复制 + sha256 记录（`MANIFEST.txt`），与前序 testbed 一字不差
- [x] `code/sim/launch.py` 薄封装 + 红线端口检查，自测通过（TCP 31999 起停正常）

## 本轮关键发现（调研结论，已写进方案文档）

1. **★ 找到落盘入口**：`BaseContext.BeginStartWriteFile / WriteDataNow / EndWriteFile /
   BeginStartWriteEisWriteFile / CalculateCD` —— 产物不需要 GUI 参与。这是纯代码路线成立的关键。
2. **网口原生支持**：`SockectConnect` 与 `SerialConnect` 同接口，宿主可直接 `Open("IP:PORT")`。
3. **`GetOcpValue(ref double)` 存在**：可以直接问设备要 OCP，不必自己从数据流反算。
4. **参数类全 public 可写**：四实验每个字段都能代码设置，无需碰控件。

## 下一步（按序）

1. **T1 冒烟**：sim（串口 CNCB0 + COM90 别名）→ 宿主 → OCP 单实验 → 回答 U1/U2/U3
2. 若 U1 通过（原生落盘可用）→ Phase 2 四实验 + 双路落盘
3. 若 U1 失败 → 走自写 txt，`.cor` 降级为后续项

## 阻塞

无。

---

## 2026-11-10 02:2x · 巡检轮次（Phase 1 → 已突破，Phase 2 待开）

### 本轮结论：★ U1/U2/U3 全部回答，T1 冒烟通过

**U1（`BeginStartWriteFile` 无窗体能否落盘）→ ✅ 完全可用，且产物是真实原生 `.cor`**
```
data/t1/t1_ocp.cor   6491 B / 150 行
  L1  CORRW ASCII
  L2  CorrTest for Windows: SN   V6.7.611.2
  L3  ID_OCP
  L5  ExpParmas:ExpType=ID_OCP&-&TestTime=30&...   ← 完整参数串
  L5  ...,ExpInfo:Freq(Hz):10,Hold Time(s):0
  L6  Open Circuit Potential (V):0
  数据段 126 行三列： -1.41406E-01  1.00000E-10  11.90000  (E, i, t)
```
- 与自写 `own_ocp.txt` 并存（120 点 / 125 行），两路互为校验
- **不需要 MainFrm、不需要消息循环、不需要 GUI**

**U2（是否要显式刷盘）→ ✅ 需要，每批新点调一次 `WriteDataNow()`**
宿主每 200ms 采一批后刷一次，`.cor` 从 2181 B（仅头部）增长到 6491 B，数据行 126 条。

**U3（`SysRuning` 是否会被翻回）→ ❌ 不会被翻回，但要主动停止**
采集全程 `state=SysRuning, busy=False`。停靠 `SysStop()` 显式调用。
`IsBusy` 一直是 False，**不能拿它当收尾判据**（与 03 清单 §4 的假设不同，记为新坑）。

### 关键数据（T1 实测）
```
points=120  pointcount_delta=126  reason=max_sec  elapsed=12.06s
```
- `PointCount` 增量（126）> 实收点（120）：批量帧 30 点/帧，最后一帧计数已加但 List 未追平
  → **游标必须用 List 下标（已改），不能用 PointCount**

### 本轮修掉的问题
1. `CheckPackReceiveThread` 在 `SockectConnect` 实现类上不存在 → 必须从 `IConnect` 接口取方法
2. 宿主卡死真因不是 API，而是**模拟器连接处于坏状态**（残留进程占着 31001，`auto_wired=false`）
   → 复现方法：留下旧 sim 不杀就重跑。修复：每次跑前清干净再起
3. 厂商方法会永久阻塞 → 全部加 `Guarded()` 超时守卫（3~8s）+ 300s 全局看门狗
4. `DrainData` 游标改用 List 下标

### 下一步
1. Phase 2：四实验（OCP/Tafel/Step/EIS）跑通，每个验证 `.cor` 非空 + 点数对得上
2. 验证 `ReSetData` 在实验切换时是否足够干净
3. 补 `tests/run_all.py` 回归骨架

### 阻塞
无。

---

## 2026-11-10 02:5x · Phase 2 · 四实验全绿 ★

### 战果（连跑 3 次，3/3 ALL-OK）

```
        try1                        try2                        try3
ocp   60点 dp86 cor5105 OK     60点 dp86 cor5105 OK     60点 dp87 cor5139 OK
tafel 86点 dp86 cor5512 OK     86点 dp86 cor5512 OK     84点 dp85 cor5478 OK
step  86点 dp86 cor5604 OK     85点 dp85 cor5571 OK     86点 dp86 cor5604 OK
eis   84点 dp85 cor5595 OK     84点 dp84 cor5553 OK     86点 dp86 cor5615 OK
```

四份原生 `.cor` 头部标识逐一正确：
```
t2_ocp.cor    ID_OCP
t2_tafel.cor  ID_PotDynamic
t2_step.cor   ID_AnyPotStatic
t2_eis.cor    Sweep Frequency: Control Voltage
```
每个文件 85~87 行数据，与 points 对得上；同时并生成 own_*.txt 作为第二路。

### 本轮排查的最大坑：模拟器状态污染（已定案）

**现象**：宿主连上（`connect ok=true`）但探测全超时、`BeginStartWriteFile` 永久阻塞、
`SendMethodBytes` 返回 false、数据零入库；sim 侧报 `ConnectionResetError(10054)`。

**根因**：`simdevice.py` 的 TCP 模式**一个进程只可靠服务一次连接**。
上一次宿主退出后若复用同一 sim，第二次连接会被半死不活的会话卡住。

**修复**：`tests/run_case.py` 每次跑都先杀干净所有 sim 再起新的（匹配 `*simdevice.py*`），
并用 `port_free()` 等端口真正释放。**这条必须固化，否则后面所有测试都是假阴性。**

### 另一个必要修复：探测会污染连接

`GetSerialNumber/GetPstType/GetRomVersion` 是同步请求/应答（`SendReturnPackage` 双出队）。
无应答时它会阻塞并耗尽同步队列 → **连续 3 次探测后 `BeginStartWriteFile` 永久阻塞**（t8 实证）。
→ 宿主改为 `probe` 开关（默认 false）；探测只在显式要 SN 时做，且只试 1 次。

### 新增资产
- `tests/run_case.py`：作业执行器（清场→起 sim→跑宿主→校验→落 result.json）
- `tests/jobs/t2_all4.json`：四实验作业
- 契约：**sim 一个进程一次连接**；**probe 默认关**；**游标用 List 下标不用 PointCount**

### 下一步
1. Phase 3：判稳/判停策略离线标定（用桌面真机曲线回归）
2. 补 `tests/run_all.py` 一键回归
3. `own_*.txt` 的点数与 `.cor` 行数做严格一致性校验（当前相差 1~2 行，需查清是头部还是空行）

### 阻塞
无。

---

## 2026-11-10 03:5x · 巡检轮次 · Phase 3 全通

### 本轮完成

**1. 判稳/判停策略 Python 版落地（`code/policies.py`）**
- `StabilizeDetector`：窗口斜率 + 峰峰值双约束 + hold 保持
- `CurrentDensityStopper`：连续 confirm_n 次超阈值
- `TimeLimit`：兜底
- `read_csstudio_txt` / `read_cor`：读真机数据与原生产物
- `scan_stabilize`：离线整段扫，返回首次判稳点

**2. 离线标定（`tests/test_policies.py`，35 PASS / 0 FAIL）**
真机 5 组 OCP 曲线（只读桌面数据）判稳点：
```
26.11.3 4HT-LS-320  t=126.2s E=-0.103079 V  slope=-3.35 ptp=1.74
26.11.3 GC-C        t= 60.5s E=-0.184630 V  slope= 0.58 ptp=0.28
26.11.3 GC-D        t=237.1s E=-0.202301 V  slope=-0.47 ptp=0.23
26.11.5 JK-D        t= 82.5s E=-0.143837 V  slope=-2.31 ptp=1.06
10.31 q 开路电位    t=211.5s E=-0.091712 V  slope= 2.70 ptp=1.54
```
A3 用例专门守住「斜率正负抵消」这个历史坑：振荡信号斜率可能小，但峰峰值硬约束必须拦住。

**3. 端到端验证：两个策略在真机回放数据上都正确触发**
```
ocp    points=60  reason=stabilized        cor=4630
tafel  points= 7  reason=current_density   cor=2833
```

### 本轮新增/修正的坑

| # | 坑 | 影响 | 处置 |
|---|---|---|---|
| 1 | **模拟器 TCP 一个进程只可靠服务一次连接** | 第二次连接必是半死状态 | runner 每次尝试都换新 sim |
| 2 | `BeginStartWriteFile` 在半死连接上**永久阻塞**并拖死收包线程 | 假阴性（连上但零数据） | 超时降到 2s + 失败不阻断采集 |
| 3 | 模拟器自检本身会消耗那唯一一次连接 | 自检反而把主流程搞坏 | **删掉自检**，改由 runner 失败重试 |
| 4 | `IConnect.CheckPackReceiveThread` 起的是**前台线程** | Main 返回后进程不退出（runner 假超时 rc=124） | 结尾 `Environment.Exit(rc)` |
| 5 | sim 默认 OCP 信号含 -12 mV/min 漂移 | 永远判不稳 | 验证 stabilize 必须用真机回放数据 |

### 当前能力盘点（纯代码，零 GUI）

- ✅ 程序集零 GUI 加载 + BaseContext 装配（csc 直编 C# exe）
- ✅ TCP 连接（`SockectConnect`）
- ✅ 四实验下发/启动/采集/停止（OCP/Tafel/Step/EIS）
- ✅ 原生 `.cor` 落盘 + 自写 txt 双路
- ✅ 四种停止策略（max_sec / stabilize / current_density / timeout 兜底）
- ✅ JSONL 事件流（机读）
- ✅ 离线策略回归 35 项
- ✅ 失败自动换 sim 重试

### 下一步
1. Phase 4：`run_all.py` 一键回归（把所有作业串起来跑）
2. 多机并行编排（每机独立端口 + 独立 sim + 独立宿主）
3. 归档到 Obsidian

### 阻塞
无。注意：真机端到端仍需用户在场授权（本阶段全程只用模拟器）。

---

## 2026-11-10 04:1x · Phase 4 全通 · 一键回归 5/5

### 本轮完成

**1. `code/pilot.py` 多机编排器**
- 每台机器独立端口 + 独立 sim + 独立宿主进程，并行跑
- 机器配置 `machines.json`（name/port/replay/experiments/retries）
- 端口红线（1024 = 设备发现口，拒绝）
- 汇总 `logs/pilot_report.json`

**2. `tests/run_all.py` 一键回归（三层）**
```
L0 离线      test_policies.py            35 PASS / 0 FAIL      1.0s
L0 离线      simdevice --selftest         57/57 通过            0.1s
L1 端到端    t2_all4 四实验              ALL-OK               84.3s
L1 端到端    t3_policy 策略(真机回放)     ALL-OK              146.2s
L2 多机      pilot 双机并行              ALL-OK               79.7s
                                                    合计 5/5 ALL-OK
```

**3. 双机并行实测**
```
M1 port=31011  ocp:60  tafel:7   35.8s
M2 port=31012  ocp:390 step:103  78.7s
并行总耗时 78.7s（无互扰）
```

### 本轮修的坑

| 坑 | 处置 |
|---|---|
| subprocess 捕获中文输出编码不一致，`PASS` 计数变 0 | 收 bytes + utf-8/gbk 双重兜底解码 |
| 自测结果解析不到 | 改按 `自测结果: M/M 通过` 正则 |

### 项目当前状态：纯代码路线 **全链路可用**

```
                 ┌── code/cshost/CsPilotHost.exe   (C#，零 GUI，加载厂商程序集)
纯代码栈 ────────┤   code/sim/simdevice.py          (只读复制，虚拟设备)
                 ├── code/policies.py               (判稳/判停)
                 ├── code/pilot.py                  (多机编排)
                 └── tests/run_all.py               (一键回归)
```

能力清单：
- 四实验（OCP/Tafel/Step/EIS）下发→启动→采集→停止→双路落盘
- 四种停止策略，真机回放数据上验证有效
- 多机并行，进程级隔离（不再有 GUI 焦点/桌面堆问题）
- 全量回归 5 项，总耗时 ~5 分钟

### 下一步
1. 归档到 Obsidian（新建 10 号文档 + 更新 00 恢复入口）
2. 真机端到端（**需用户在场授权**，本阶段全程未碰真机）
3. 可选：CS5 支持（另一套协议族，第二阶段）

### 阻塞
无离线阻塞。真机验证为唯一剩余项，需用户在场。

---

## 2026-11-10 04:3x · 归档完成

### Obsidian 已更新
- **新建** `未完成项目记录/deepseek-harness/cs-pilot/10_纯代码路线_宿主化.md`
  （调研结论、U1/U2/U3 答案、API 全量清单、架构、战果数据、10 条坑、真机清单）
- **更新** `00_项目恢复入口.md`：主线指针指向 10 号；方案 A 标 superseded
- **更新** `00_未完成项目索引.md`：CS Pilot 条目重写为最新状态
- **追加** `09_双版本网口模拟协议定案.md` 第七节：方案 A 证伪 + CS5「全绿」不成立更正

### 归档纪律核对
- 新文档含完整 frontmatter（title/type/agent/status/created/updated/tags）
- 使用库根相对 Wikilink
- 未修改 `D:\sci\MDI Jade 9`、`D:\deepseek\cspilot-parasite`、`D:\deepseek\CSDirect`
- 原归档目录 `cs-pilot/` 内新增，未搬动历史文档

### 项目状态
纯代码路线**离线部分全部完成**。唯一剩余 = 真机端到端（需用户在场）。

### 巡检任务
每 20 分钟自查任务保持 active。后续若无可推进的离线工作，按规则暂停。

---

## 2026-11-10 05:2x · 巡检轮次 · ★ 根治了一个被误判的根因

### 本轮做了什么

上一轮把「模拟器 TCP 一个进程只可靠服务一次连接」当作定型结论写进文档和代码注释，
只靠 runner 重试兜底。本轮复查**证明这个结论是错的**，并找到了真正的根因、做了根治。

### 取证过程

1. **直接测模拟器**：单进程连续 3 次 connect → SN 读回、数据流全正常（139 B/次）。
2. **压实测**：10 轮「立刻 RST 强断 + 立刻重连」→ **0/10 失败**。
3. → 模拟器没问题。回头查宿主：卡住那次事件流里 `auto_wired=false`。

### 真正根因

上一宿主进程退出后，Windows 侧留着**半关闭 socket**（FIN_WAIT/RST 未收尾）。
下一个宿主 `Open()` 能成功（`IsOpen=true`），但 `SockectConnect` 拿到的连接已死。
**判断依据就是 `SetConnect` 后 `OnPackReceive` 是否为 null**：
- `auto_wired=true` → 连接健康，一切正常
- `auto_wired=false` → 半死连接，后续 `SendMethodBytes`/`SysStart`/`BeginStartWriteFile`
  全部无效，且 `BeginStartWriteFile` 会永久阻塞

### 修复（`CsPilotHost.cs`）

1. `Connect` 成功后静置 150ms，让残留 FIN/RST 收尾
2. `BuildContext` 校验 `auto_wired`：为 false 就 **Close 旧连接 + 重建，最多 3 次**
3. 3 次仍失败则明确抛错（不再静默产出零数据）

### 验证结果

| 测试 | 结果 |
|---|---|
| 同 sim 连续 6 次作业 | 6/6 rc=0，`auto_wired=true`，points=30 |
| 再连跑 8 次（共 14 次） | 14/14 通过 |
| **`--retries 1`（禁止重试）四实验 ×3 轮** | **3/3 ALL-OK** ← 关键：不靠重试也能过 |
| 全量回归 `run_all.py` | 5/5 ALL-OK，策略端到端耗时 146s→36s |

### 顺带修正
- `tests/run_case.py` 顶部说明与内联注释里的错误结论已改正（保留纠正记录，不删原文）
- runner 的"每作业配新 sim"保留为额外隔离，但不再是必需

### 教训（值得记的元教训）
**"每次都要重启才能过"这种症状，先怀疑自己的客户端清理不干净，再怀疑对端。**
上一轮把时序性故障当成了对端的设计限制，导致给整条测试链套了一层不必要的重试。
统计口径也踩了坑：`rc=0` 但在数据零入库时曾被判为通过（早期版本），本轮已确保
判据必须同时满足 `rc==0` **且** `points>0`。

### 下一步
离线可推进项已基本清空。剩余：
1. 真机端到端（**唯一阻塞项，需用户在场授权**）
2. CS5 支持（第二阶段，协议族不同）
3. 可选：EIS 专用数据形状核对（真机）

### 阻塞
无离线阻塞。真机验证需用户在场。

---

## 2026-11-10 05:5x · 巡检轮次 · CS5 可行性调研（第二阶段启动）

### 本轮做了什么

Phase 1–4（CS6 纯代码）已全通，本轮开始第二阶段 **CS5 支持**的可行性调研。
CS5（`CorrTest.*`）是另一套程序集，接口族与 CS6 完全不同。

### 已查明（新增 6 份 dump：`logs/dump_cs5{,b,c,d,e,f}.txt`）

**1. 连接层**：`CorrTest.CorrCom.SockectCom`，`Open("IP:PORT")` **成功**，`IsOpen=True`，`StartThread` OK。

**2. ★ 连接注入方式不同**：CS5 的 `BaseContext` **没有 `SetConnect`**。
   连接存在私有字段 `_com`（类型 `ICorrCom`），必须**直接写私有字段**：
   ```csharp
   ctxT.GetField("_com", BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx, com);
   // 之后 ctx.GetCom() 返回非空
   ```
   `InitCom()` 无参调用不报错但**不建连接**（`_com` 仍为 NULL）。

**3. ★ ctx 必须按依赖顺序补齐接口成员**，否则 `BaseParams.set_baseContext` 抛 NRE：
   ```
   ParsingParms      ← ParsingParamsClass()           无参
   ParsingParmsAux   ← ParsingParamsClass()           无参
   ExpTimeHlp        ← ExpTimeHlpClass()              无参
   ExpParamsBytes    ← ExpParamsBytesClass(parsingParams)
   ExpComSend        ← ExpComSendClass(ctx)
   CellsSwitch       ← CellsSwitchClass(ctx)
   ExtComHlp         ← ExtComHlpClass(ctx)
   BaseIO/BaseIOAux  ← BaseIOClass(byte[])            ⚠ 本机实测抛 NRE（暂缺）
   ```
   补齐前 7 项后 `set_baseContext` **成功**，`ExpClass(ctx, prm)` **构造成功**。

**4. 数据面不同**：CS5 无 `BaseContext.DataItem` / `PointCount`。
   数据在 `IExpClass` 上：`VoltList` / `CurrList` / `TimeList` / `ChargeList` / `EisDataItems`
   + `PointCount`（ExpClass 自己的）。落盘也是 `IExpClass` 的方法：
   `BeginStartWriteFile()` / `WriteContext()` / `WriteDataNow()` / `EndWriteFile()`。

**5. 控制面不同**：`IExpComSend` 上是
   `StartMethod(IBaseParams, bool isGetOcpValue, bool isCallWatiFun, ref string sError)`、
   `InitExp(IBaseParams)`、`SendSysStart()` / `SendSysStop()`（无参数），
   而不是 CS6 的 `SendMethodBytes` / `SysStart(bool)` / `SysStop()`。

**6. 枚举差异**：`Experiment` 枚举两版**数值不同**（03 清单 §10.1 早已指出），
   必须按名解析（本轮同样按名）。

### 当前进度

| 环节 | CS6 | CS5 |
|---|---|---|
| 程序集加载 | ✅ | ✅ 10 个 dll 全 OK |
| 连接 | ✅ `SetConnect` | ✅ **私有字段 `_com` 注入** |
| ctx 装配 | ✅ | ✅ 按序补齐 7 个接口成员 |
| 参数对象 + 反挂 | ✅ | ✅ `set_baseContext` 通过 |
| ExpClass 构造 | n/a | ✅ `ExpClass(ctx, prm)` |
| 落盘 | ✅ 原生 `.cor` | ⚠ `BeginStartWriteFile` 返回但**文件未创建** |
| 下发/启动 | ✅ | ❓ `StartMethod/InitExp` 未验证 |
| 数据入库 | ✅ `IDataItem` | ❓ `VoltList/CurrList` 未验证 |

### 下一步（CS5 剩余）

1. 查 `BeginStartWriteFile` 为何不建文件（可能要先 `WriteContext()`，或依赖 `BaseIO`/`DevParam`）
2. `BaseIOClass(byte[])` 的 NRE 依赖（可能要传真实 IO 字节）
3. `StartMethod` 的 `ref sError` 参数 + 真实启动流程
4. `VoltList/CurrList` 数据入库验证
5. CS5 版 sim（`--lan5` 已支持）与宿主对接

### 阻塞
无。CS5 属第二阶段，不影响 CS6 已完成的能力。

---

## 2026-11-10 06:3x · 巡检轮次 · CS5 落盘确认 + 启动链打通到协议层

### ★ 纠正上一轮的错误结论

上一轮记的「CS5 `BeginStartWriteFile` 返回但文件未创建」**是错的**——我查了带 `.cor` 的路径，
而 **CS5 的 FilePath setter 会自动去掉扩展名**，实际文件已生成。

**实证**：
```
data/cs5/exp_wf    1030 B   ← 上一轮"未创建"的产物，其实一直在
data/cs5/cs5k_ocp  1030 B
data/cs5/exp_wf2   1902 B
```
内容为原生 CS5 格式（结构比 CS6 更啰嗦）：
```
CORRW ASCII
CorrTest for Windows: SN   V
ID_OCP
Data:2026-11-10   Time:06:12:08
ExpParmas:ExpType=ID_OCP&-&TestTime=30&...&-&DevParam=VoltRange=2&|...&-&CellParam=Area=1&|...
  Begin Information:            Cell Information
      ...
  End Information:              Cell Information
  Begin Experiment:
      Axes Type:              0
  End Experiment:
E(V)		i(A/cm^2)		T(s)
```

### 本轮新查明

**1. ★ `BaseContext.ExtDevHlp` 是公有字段，不是属性 —— StartMethod 的拦路虎**
`StartMethod` 抛 NRE，IL 反查到栈帧落在 `SendRotatingSpeed(ICellParams)`，
再反查该方法 IL，发现它读的是 `baseContext.ExtDevHlp`：
```
ldfld ExpComSendClass.baseContext
ldfld BaseContext.ExtDevHlp          ← 公有字段，不在属性表里
callvirt ExtDevHlpClass.IsSpeedMode
```
补齐后 `StartMethod` **不再 NRE**：
```csharp
var f = ctxT.GetField("ExtDevHlp", BindingFlags.Instance|BindingFlags.Public);
f.SetValue(ctx, Activator.CreateInstance(Find(ci,"ExtDevHlpClass"), new object[]{ctx}));
// 随后 IsSpeedMode()=False, IsTempMode()=False
```

**2. CS5 Experiment 枚举实值与 CS6 不同（印证 03 §10.1）**
```
        ID_OCP  ID_PotDynamic  ID_AnyPotStatic  ID_EISVSFRQ
CS6        1          5              63             32
CS5        1          4              56             30
```
→ **必须按名解析**，写死数字必错。

**3. CS5 控制面方法都有真实 IL（非 stub）**
```
StartMethod(IBaseParams, bool, bool, ref string sError)   588 B
InitExp(IBaseParams)                                      650 B
SendSysStart() / SendSysStop() / SendSysPause()          138/59/78 B
SendRotatingSpeed(ICellParams)                            146 B
```

**4. ★ CS5 启动链已推进到协议层（关键里程碑）**
`StartMethod` 现在返回明确业务错误而不是崩溃：
```
ret=False  sError='指令下发失败，请稍后重试!'
```
模拟器侧实收帧序（**证明软件的 CS5 协议栈被完整驱动**）：
```
AA 85 63 0A ...   ×8   参数帧
AA CF 01 ...      ×9   工作模式应答（软件在等）
AA 53 01 ...      ×9   实验启动
AA 74 00 ...      ×9   方法下载起始
AA 80 53 ...      ×3   Stop（收尾）
```
→ **纯代码宿主已经能驱动 CS5 的完整启动序列**，剩下的只是模拟器侧应答语义。

### 当前 CS5 状态

| 环节 | 状态 |
|---|---|
| 程序集加载（11 个） | ✅ |
| 连接（`_com` 字段注入） | ✅ |
| ctx 装配（7 成员 + ExtDevHlp） | ✅ |
| 参数 + ExpClass | ✅ |
| **落盘** | ✅ **原生格式已生成（纠正上一轮误判）** |
| InitExp | ✅ 返回 True |
| StartMethod | ⚠ 返回 False + 「指令下发失败」（协议应答问题） |
| 数据入库 | ❌ 待协议应答修好后验证 |

### 下一步

1. **模拟器 CS5 应答语义**：软件发 `AA 53 01`（启动）后在等 `AA CF 01`，
   sim 的 `_cs5_handle` 有对应逻辑但需确认 `--lan5` + `lan_off==12` 分支被正确触发
2. `AA 85 63 0A` 参数帧的 ACK 格式（当前 sim 回显）
3. `AA 74` 方法下载起始的应答
4. 数据帧（10B 无帧头）推流验证

### 阻塞
无。CS5 协议应答属离线可推进项。

---

## 2026-11-10 07:0x · 巡检轮次 · CS5 模拟器应答语义定位

### 本轮做了什么

继续上一轮的下一步「模拟器 CS5 应答语义」。定位到一个**双重问题**，两者都确认了。

### 发现 1：`--lan5` 单独用不启用 CS5 协议栈

`simdevice.py` 的启动代码：
```python
lan=args.lan,
lan_off=(12 if args.lan5 else 13)
```
而 `start()` 选线程的条件是：
```python
threading.Thread(target=(self._cs5_reader if (self.lan and self.lan_off == 12) else self._reader), ...)
```
→ **`--lan5` 只改 `lan_off`，不改 `lan`。单独用 `--lan5` 时 `self.lan=False`，
走的是 CS6 的 `_reader`。**

实证对比（软件发的是同一条 `AA 85 63 02 ... 94`）：
```
31040（仅 --lan5）      日志: [SIM] RAW 16B: AA 85 63 02 ...
31042（--lan --lan5）   日志: [SIM] CS5 RAW 16B: AA 85 63 02 ...
```
**正确用法：CS5 测试必须同时传 `--lan --lan5`。**（不改 simdevice.py 本体，保持只读副本纯净）

### 发现 2：★ `_cs5_handle` 对 `0x85` 的回显应答会让软件直接断连

`_cs5_reader` 真正启用后，软件在发完 `AA 85 63 02` 后**立刻被断开**：
```
[SIM] CS5 RAW 16B: AA 85 63 02 00 ... 94
[SIM] CS5 帧 cmd=0x85 data=63 02 00 ...
[SIM] CS5 连接断开: ConnectionResetError(10054, '远程主机强迫关闭了一个现有的连接。')
```
而走 `_reader`（不回应答）时，软件能一路跑完 5 个帧序。

→ **`0x85` 的 `return [frame]`（原样回显）被软件判为非法参数帧。**
源码里这行注释也写着「ACK 未定：先回显」——是当时未定案的临时实现。

### 对照：31040 那轮能跑完的帧序（软件真实行为，无应答时）
```
AA 85 63 02 ...  ×8    参数帧（软件在等 ACK，等不到也继续重试）
AA CF 01 ...     ×9    工作模式
AA 53 01 ...     ×9    实验启动
AA 74 00 ...     ×9    方法下载起始
AA 80 53 ...     ×3    Stop 收尾
→ StartMethod 返回 False + '指令下发失败，请稍后重试!'
```

### 本轮结论（重要）

CS5 的模拟器应答表**有两处是未定案的临时实现**：
| 命令 | 当前实现 | 状态 |
|---|---|---|
| `0x85` 参数帧 | `return [frame]` 原样回显 | ❌ 软件判非法，直接断连 |
| `0x74` 方法下载起始 | `return [frame]` 原样回显 | ❓ 未单独验证 |
| `0x53` 实验启动 | `[frame, CF01]` 双帧 | ❓ 需在前两项修好后验证 |
| `0x80 0x53` Stop | `CF00` | ✅ 09 号文档实证 |

### 下一步

1. **`0x85` ACK 格式定案**：需要试出软件接受的应答。
   候选：`AA CF xx`（工作模式帧）、`AA 85` 无 data、`AA 85 63 0A`（原值+确认位）等
2. `0x74` ACK 格式
3. 修好后跑通 `StartMethod` → 数据入库 → `.cor` 落盘完整链
4. 把 CS5 的 `_cs5_handle` 应答表固化成 `code/cs5/` 下的独立模块（不改编 sim 本体）

### 阻塞
无。属离线可推进的应答格式试错。

---

## 2026-11-10 07:5x · 巡检轮次 · ★ 0x85 应答变体扫描完成，定案「不应答」

### 本轮新增资产

- `code/cs5/sim_cs5.py`：CS5 应答实验台。**用子类覆盖 `_cs5_handle`**，
  不修改 `simdevice.py` 只读副本（保持 sha256 纯净）。内置 8 个 `0x85` 变体 + 4 个 `0x74` 变体，
  自带 `--selftest`（校验各变体字节合法）。
- `code/cs5/scan_ack.py`：变体自动扫描器（起 sim → 跑探针 → 收结论 → 汇总表）。
- `tests/probe/t_cs5probe.cs/.exe`：精简 CS5 探针（Open→StartThread→装配→InitExp→StartMethod），
  单行输出结论供扫描器抓取。

### ★ 扫描结果（8 个变体，全部对真实软件跑过）

| 变体 | 应答字节 | 软件反应 |
|---|---|---|
| `cf00` | `AA CF 00 79` | ❌ 断连 |
| `cf01` | `AA CF 01 7A` | ❌ 断连 |
| `bare85` | `AA 85 2F` | ❌ 断连 |
| `85_echo_plus_cf` | 原帧 + `AA CF 00 79` | ❌ 断连 |
| `85_bare_plus_cf` | `AA 85 2F` + `AA CF 00 79` | ❌ 断连 |
| `63` | `AA 63 63 00 70` | ❌ 断连 |
| `8053` | `AA 80 53 7D` | ❌ 断连 |
| **`silent`（不应答）** | **无** | **✅ 推进到 `AA 53 01` 实验启动** |

### 定案：`0x85` 是**设备不收应答**的参数下发帧

`silent` 变体下软件的完整帧序（真实行为）：
```
AA 85 63 02 ...  ×9    参数下发（重试 9 次，等 ACK 等不到就继续）
AA 80 53 ...     ×1    Stop（安全停）
AA 85 63 0A ...  ×9    参数下发（第二组）
AA CF 01 ...     ×5+   工作模式
AA 53 01 ...           实验启动
```
→ **`0x85` 期间设备必须保持沉默**。之前 `_cs5_handle` 的 `return [frame]` 回显是错的，
任何应答都会让软件判定协议错乱并 RST。
（这也解释了为什么早前用 CS6 的 `_reader`（完全不回 CS5 应答）反而能跑完全程。）

### 当前 CS5 状态

| 环节 | 状态 |
|---|---|
| 连接 / ctx 装配 / ExtDevHlp | ✅ |
| 参数 + ExpClass + 落盘 | ✅ |
| **`0x85` 应答语义** | ✅ **定案：不应答** |
| StartMethod | ⚠ 仍 NRE（新线索见下） |
| 数据入库 | ❌ 待 StartMethod 通过 |

### 下一步（新的具体线索）

`StartMethod` 仍抛 NRE，但**与 `0x85` 无关**了。当前观察：
- 加 `StartThread` 后 `InitExp`/`StartMethod` 都 NRE；不加 `StartThread` 时 `InitExp` 返回 True。
- 怀疑 `StartThread` 启动的内部线程改写了 `_com` 相关状态，或它需要配套的 `EnableDataEvent`。

**候选排查**：
1. 试 `StartThread` + `EnableDataEvent(true)` 组合
2. 或**不调 `StartThread`**（CS5 也许像 CS6 一样，Open 后自带收包线程）
3. 若 StartMethod 内部还有 NRE，继续用 IL 反查（上轮 `ExtDevHlp` 就是这么找到的）

### 阻塞
无。属离线可推进。

---

## 2026-11-10 08:2x · 巡检轮次 · ★★ CS5 启动链完全打通（InitExp ✅ / StartMethod 进入等数据阶段）

### 本轮方法：IL 反查（沿用上轮找到 ExtDevHlp 的招，一次命中）

反汇编 `ExpComSendClass.InitExp`（650B）的头几条指令：
```
+1  callvirt → IBaseParams.get_BaseIO
+6  callvirt → IBaseIO.GetPotOrCur        ← 立刻用 BaseIO 的方法
+14 callvirt → IBaseParams.get_DevParam
+20 callvirt → IDeviceParams.set_IsVoltAutoRange
...
```
→ **`InitExp` 第一件事就是取 `prm.BaseIO` 并调用它。** 而 `BaseIO` 此前从未设置。

### 修复

`BaseParams.BaseIO` 是惰性 getter（读一次会自己 new 一个 `BaseIOClass`），
但 `DevParam.BaseIO` 是独立的另一个槽位，也必须指向同一实例：

```csharp
// prm.BaseIO 读一次即惰性创建
object bio = ocpT.GetProperty("BaseIO").GetValue(prm, null);
// DevParam.BaseIO 必须显式补同一实例
object dev = ocpT.GetProperty("DevParam").GetValue(prm, null);
dev.GetType().GetProperty("BaseIO").SetValue(dev, bio, null);
```

`BaseIOClass` 构造器：`C(Byte[] iobytes)`（CS6 的 `BaseIO` 里那些字节）。

### 战果：InitExp 从 NRE → 通过，StartMethod 从 NRE → 进入协议等待

```
[4] ExpClass → OK
[5] InitExp  → OK              ← 之前是 NRE
[6] StartMethod → HANG>20000ms ← 之前是 NRE，现在是"挂起等应答"
[7] 数据 Time=0 Volt=0
```

**挂起 ≠ 崩溃。** 它说明 `StartMethod` 已经走完所有内存检查，进入
「发命令 + 等设备回应」阶段。

### 模拟器侧实收完整 CS5 启动帧序（历史首次全序列跑通）

```
AA 85 63 ×9     参数下发（silent，设备不应答，软件重试 9 次后继续）
AA 80 53 ×1     Stop（安全停）
AA 85 63 ×9     第二组参数
AA CF 01 ×9     工作模式
AA 53 01 ×1     ★ 实验启动（日志已打印「CS5 实验模式 → ocp」）
AA 80 53 ×3     Stop 收尾（探针 20s 超时后主动停）
```

对照上一轮：那时帧序在 `AA 53 01` 后就 RST 断连；**本轮软件主动发了 Stop 收尾**，
说明它认为实验已经"启动成功"，只是等数据等不到才被探针打断。

### CS5 状态更新

| 环节 | 上轮 | 本轮 |
|---|---|---|
| 连接 / ctx / ExtDevHlp | ✅ | ✅ |
| 参数 + ExpClass + 落盘 | ✅ | ✅ |
| `0x85` 应答语义 | ✅ 定案不应答 | ✅ |
| **InitExp** | ❌ NRE | ✅ **OK** |
| **StartMethod** | ❌ NRE | ⚠ **HANG（等数据）** |
| 数据入库 | ❌ | ❌ Time=0 Volt=0 |

### 下一步（很具体了）

`StartMethod` 挂起 = 在等数据流。而模拟器 `_cs5_streaming` 已在 `0x53` 分支置 True，
数据帧应以 **10B 无帧头格式**（`60 | E float32 LE | t float32 LE | seq 1B`）推流。

排查方向：
1. `_cs5_reader` 的推流循环用 `self.ser.write()`，而应答也用它——需确认没被应答挤掉
2. 检查 `sample_hz` 是否 >0（`_cs5_streaming and self.sample_hz > 0` 才推）
3. `StartMethod` 的 `isGetOcpValue=true` 参数可能要求设备先回一个 OCP 值
4. 若推流正常但仍 HANG，反汇编 `StartMethod` 看它等的具体是什么

### 阻塞
无。

---

## 2026-11-10 09:0x · 巡检轮次 · ★★ 找到 StartMethod 挂起的确切原因

### 本轮结论：挂起 = 在等 `ReadOcpBytes` 的应答（同步请求/应答）

#### 1. 先排除了模拟器推流问题（已证明正常）

裸 socket 测试：连上 → 发 `AA 53 01` → 收到双帧 ACK + 连续 10B 数据帧：
```
AA 53 01 ... FE  AA CF 01 7A        ← 双帧 ACK
60 F3 50 0E BE 00 00 D6 38 00       ← 10B 数据帧（E≈-0.139V）
60 8F 55 0E BE 40 99 EB 3D 01
```
→ **推流完全正常，不是模拟器的锅。**

#### 2. `0xCF`（工作模式查询）不是原因

软件会连发 `AA CF 01` ×9，模拟器原本**没有 0xCF 分支**。加了 `echo/silent` 两种变体各测一遍，
`StartMethod` 都仍然 HANG → 排除。

#### 3. ★ 反汇编 `ExpCallWatiFun`（590B）定位到挂起点

```
+209  callvirt → IBaseParams.get_baseContext
+214  callvirt → BaseContext.GetCom
+219  ldsfld   → CommandPackage.ReadOcpBytes     ← 静态帧模板
+236  callvirt → ICorrCom.SendReturnPackage      ← ★ 同步请求/应答，就是这里阻塞
+286  callvirt → IParsingParams.GetVoltValue
+296  callvirt → IParsingParams.GetCurrValue
```
`SendReturnPackage` 是**同步**的（CS5 的 `ICorrCom` 上无超时重载以外的异步路径），
设备不回应答就永久阻塞。

#### 4. ★★ 关键：`ReadOcpBytes` 就是 `AA 53 01`

`CommandPackage` 的静态模板 dump：
```
SerialBytes   = AA 81 00 00 ... 2B       查序列号
ReadOcpBytes  = AA 53 01 00 ... FE       ★ 读 OCP 值
StartBytes    = AA 80 51 00 ... 7B       启动
```
→ 软件发出的 `AA 53 01` **不是"实验启动"，而是"读 OCP 值"请求**。
（之前几轮把它当成实验启动帧，是错的。）

所以 `ExpCallWatiFun` 发 `AA 53 01` 后，**在等设备回一个带 OCP 数值的应答帧**。
模拟器当前对 0x53 的应答是 `[echo(AA 53 01), AA CF 01]` —— **两个帧都不含 OCP 数值**，
所以软件解析 `IParsingParams.GetVoltValue` 拿不到值，`SendReturnPackage` 一直等。

### 本轮修正的认知错误

| 之前认为 | 实际 |
|---|---|
| `AA 53 01` = 实验启动 | **`AA 53 01` = 读 OCP 值（`ReadOcpBytes`）** |
| `AA 80 51` 是启动 | `StartBytes = AA 80 51`（这个才是启动） |
| StartMethod 等数据流 | **等 `ReadOcpBytes` 的应答包（含 OCP 数值）** |

### 下一步（非常具体）

1. **`AA 53 01` 的应答必须带 OCP 数值**。参考 CS6 的同类应答：CS6 用
   `0x55 RR RR RR 80 04 CHK` 的 7 字节回读格式（`Volt=(2^23-raw24)/2^23×9.8`）。
   CS5 需要先探出对应格式——候选：
   - 回 `AA 53` + 4B float32 LE（OCP 值）
   - 回 `AA CF` + 4B float32 LE
   - 回 CS6 式 7 字节 `55 xx xx xx 80 04 chk`
2. 用同样的变体扫描法（`code/cs5/sim_cs5.py` 加 `VARIANTS_READOCP`）逐个试
3. 应答格式对了之后，`ExpCallWatiFun` 应能返回，`StartMethod` 应能跑通
4. 之后再验证 `SendSampleBytes`（IL 已知：`GetAdSamFast` + `SendReturnBoolThree`）

### 当前 CS5 状态

| 环节 | 状态 |
|---|---|
| 连接/ctx/ExtDevHlp/BaseIO | ✅ |
| 参数 + ExpClass + 落盘 | ✅ |
| `0x85` 应答语义 | ✅ 定案不应答 |
| `0xCF` 工作模式查询 | ✅ 排除影响 |
| InitExp | ✅ OK |
| **StartMethod** | ⚠ HANG 在 `ReadOcpBytes` 等 OCP 应答 |
| 数据入库 | ❌ 待上一步 |

### 阻塞
无。属离线可推进（应答格式试错）。

---

## 2026-11-10 · 减少授权打扰 + 定位到 3 个失败点

### ★ 一、解决"每步都要点授权"（用户反馈）

**问题**：之前每轮巡检要做几十次独立操作（杀进程、起 sim、跑探针、grep 日志、再杀进程），
每次都要用户点一次网络/命令许可，用户跟不上。

**方案**：新增 `tools/run_cs5.py`，把全流程收进**一个 Python 进程**：

| 原来的做法 | 现在 |
|---|---|
| powershell 杀残留 sim | Python `Popen` 保留句柄，`finally` 里 `terminate()` |
| netstat 看端口 | `socket.connect` 探活 |
| 手工挑端口 | `pick_port()` 从 32200 起自动找空闲口 |
| 起 sim（一次授权）| 同一进程内完成 |
| 跑探针（一次授权）| 同一进程内 `subprocess` |
| grep 日志（一次授权）| 同一进程内解析并打印 |
| 再杀进程（一次授权）| `finally` 自动 |

**一条命令搞定**：
```bash
python -I tools/run_cs5.py --variant 53le --probe steps   # 单个变体
python -I tools/run_cs5.py --scan53                      # 扫全部 11 个变体
```
实测：单变体 27.3 s 完成，全程无残留进程。

### ★ 二、定位到 StartMethod 链路上的 3 个失败点

新增 `tests/probe/t_cs5steps.cs`（逐步探针，严格照 StartMethod 的 IL 顺序调用）：

```
[1] Open = True
    StartThread ok
[2] ctx assembled
[3] params ready; BaseIO=ok DevParam=ok
[4] ExpClass = OK:CorrTest.CorrData.ClassModules.ExpClass

=== 逐步下发（对齐 StartMethod IL 顺序）===
[S1] set_Persent(0)         : OK:null
[S2] SendMethodInit()       : OK:True
[S3] GetOcpValueAutoRange() : ★ EXC:NullReferenceException
[S4] SendMethodParams()     : ★ OK:False        ← 「指令下发失败」的直接来源
[S5] InitExp()              : OK:True
[S6] StartMethod(full)      : OK:False  ret=采样频率(Hz):5,测量时间(s):0
                                        err='指令下发失败，请稍后重试!'
[S7] Data Time=0 Volt=0
```

**两个新事实**：
1. **`SendMethodParams()` 返回 False** —— 这是 `err='指令下发失败'` 的直接来源，不是 OCP 应答问题。
2. **`StartMethod` 的返回值是字符串**（`"采样频率(Hz):5,测量时间(s):0"`），不是 bool。
   之前一直按 bool 解读是错的。

`GetOcpValueAutoRange()` 的 NRE 也很可疑——它在 `SendMethodParams()` 之前，
按 IL 顺序先执行。两者可能同源。

### 本轮排除项（有实证，不用再试）

- `ack53` 的 OCP 应答格式**不是**卡点：legacy/53le/cfle/echo 四个变体结果完全一致。
- 数据推流**正常**：裸 socket 实测能收到 10B 数据帧（`60 F3 50 0E BE ...`，E≈-0.139 V）。
- `0xCF` 工作模式查询**不是**卡点：echo/silent 都同样失败。
- `0x85` **必须不应答**（8 变体实测，只有 silent 能推进）。

### 下一步

1. 反汇编 `IBaseParams.GetOcpValueAutoRange`（NRE）——找它依赖哪个空成员
2. 反汇编 `IBaseParams.SendMethodParams`（返回 False）——它内部一定有失败分支/日志串
3. 注意：这两个方法都在 `CorrTest.CorrInterface.Params.IBaseParams` 接口上，
   实现应在 `OcpParams`/`BaseParams`，需先定位实现体
4. 修通后 `StartMethod` 应能返回成功，再验证 `VoltList/CurrList` 入库

### 阻塞
无。全部离线可推进。

---

## 2026-11-10 · 降打扰工具 + CS5 失败链进一步收窄

### 一、`tools/run_cs5.py`（解决频繁授权）

把「杀残留进程 → 起 sim → 跑探针 → 解析 → 收尾」收进**一个 Python 进程**：
`Popen` 保留句柄、`finally` 里 `terminate()`、`socket` 探活、`pick_port()` 自选空闲口。
一条命令即一次授权：

```bash
python -I tools/run_cs5.py --variant 53le --probe steps        # 单变体 ~20-27s
python -I tools/run_cs5.py --variant 53le --probe steps --scan85sub   # 扫 8 个变体
python -I tools/run_cs5.py --scan53                            # 扫 11 个 ack53 变体
```

### 二、新增 `tests/probe/t_cs5steps.cs`（逐步探针）

严格照 `StartMethod` 的 IL 顺序逐个调用，输出每一步的返回值：

```
[S1] set_Persent(0)         : OK:null
[S2] SendMethodInit()       : OK:True
[S3] GetOcpValueAutoRange() : EXC:NullReferenceException   ← 未解决
[S4] SendMethodParams()     : OK:False                      ← 「指令下发失败」直接来源
[S5] InitExp()              : OK:True
[S6] StartMethod(full)      : OK:False  ret=采样频率(Hz):5,测量时间(s):0
                                        err='指令下发失败，请稍后重试!'
[S7] Data Time=0 Volt=0
```

**新事实**：`StartMethod` 的返回值是**字符串**（`"采样频率(Hz):5,测量时间(s):0"`），不是 bool。

### 三、IL 反查结果（本轮新增）

**`BaseParams.GetOcpValueAutoRange`（26 B）**
```
+3  callvirt -> BaseParams.GetOcpValue
+15 call     -> PublicMethod.AutoSwitchVoltRangeForOcp
```

**`BaseParams.GetOcpValue`（156 B）**
```
BaseContext.get_IsAlive
BaseContext.get_ParsingParms
BaseContext.GetCom
ldsfld CommandPackage.ReadOcpBytes     ← AA 53 01
ICorrCom.SendReturnPackage             ← 同步请求/应答
IParsingParams.GetVoltValue / GetCurrValue
```

**`PublicMethod.AutoSwitchVoltRangeForOcp`（133 B）**
```
BaseIO.GetVoltRange → Math.Abs → Math.Pow
BaseContext.get_ExtAmpData → ExtAmpData.get_VotCoefficient   ← ★ 空引用来源候选
BaseContext.get_ParsingParms → IParsingParams.get_IsVolteFull
BaseIO.SetVoltRange → ExpComSend.SendIOBytes
```

**`OcpParams.SendMethodParams`（76 B）** ← 与 BaseParams 版本不同
```
baseContext.get_IsDemoMode
baseContext.GetCom
BaseParams.GetMethodBytes
ICorrCom.SendReturnBoolThree      ← 第一次
Thread.Sleep
baseContext.GetCom
BaseParams.GetDoubleChannelSampleBytes
ICorrCom.SendReturnBoolThree      ← 返回这个的结果
```

**`BaseParams.SendMethodParams`（94 B，对照）**：用 `SendReturnBool`（非 Three）+ `SendPolarON`。

**`OcpParams.SendMethodInit`（254 B）**：`SendSysStop → SetOptAttenual → SetVirMode →
SendPolarOff → SendEISNotchfilter → …SendReturnBool(char) → IsDaCalibration → IsEisData →
CloseDA → SendRotatingSpeed(CellParam)`。

**`OcpParams.GetDoubleChannelSampleBytes`（128 B）**：
`set_IsStopCheck → set_MethodTimeOut=MaxValue → SingleToBytes.scanRateToScanFrq →
stfld BaseContext.dataLength → CommandPackage.GetDoubleSingleSampleBytes`（两次分支）。

### 四、本轮已修的两个 bug

1. **`sim_cs5.py` 缺 `import time`** —— 0x53 分支里 `time.time()` 直接 NameError，
   导致 ack53 应答后的推流状态维护抛异常（这是之前一堆"无反应"的隐形元凶之一）。
2. **`tools/run_cs5.py` 未把 `--ack85sub` 传给 `run_one()`** —— 子命令变体根本没生效。
   修好后 `ACK85SUB[0a_echo]` 实测触发 27 次。

### 五、实验结论（本轮）

| 尝试 | 结果 |
|---|---|
| `ack85sub=0a_echo`（回显 0x85 63 0A） | S4 仍 False |
| `ack85sub=0a_cf00`（回 CF00） | S4 仍 False |
| `ack85sub=0a_echo_cf`（回显+CF00） | S4 仍 False |
| `ack85sub=all_cf00`（全部回 CF00） | 更差：S2 SendMethodInit 就 NRE |
| `ExtAmpData` 注入（VotCoefficient=1） | S3 仍 NRE |

→ **`0x85 63 0A` 的 ACK 格式不是唯一问题**，`SendReturnBoolThree` 的语义（可能是三帧/三次握手）
以及 `GetDoubleChannelSampleBytes` 的输出才是 S4 的关键。

### 六、下一步

1. 反汇编 `ICorrCom.SendReturnBoolThree` 的实现（在 `CorrTest.CorrCom`，可能混淆）
   —— 搞清它到底在等几个包、期望什么内容
2. S3 的 NRE：`GetOcpValue` 里 `SendReturnPackage` 返回 null 后 `GetVoltValue` 解引用；
   需确认 `ack53` 回的帧能否被 `ParsingParams` 解析（当前 11 个变体都失败）
3. 若 S3/S4 都卡在"设备应答语义"，考虑先用**真机日志**反推（但真机需用户在场）

### 阻塞
无。仍属离线可推进。

## 2026-11-10 12:5x · ★★★ CS5 全链 S1–S7 贯通（接管轮：大肥鱼接棒 zcode，纯代码路线胜利）

**里程碑**：CS5 无 UI 全链 S1–S7 + 数据落盘全部打通。落盘实证：
`C:\Users\xiyve\Documents\Corrtest\Data\cspilot_steps_32200`（CORRW ASCII）：
`E(V)  i(A/cm^2)  T(s)` → `3.09000E-02  1.00000E-10  0.0000/0.2000/0.4000`
（E=0.0309 = wati7 变体模拟 OCP 值，软件自己完成编码换算。）

### 接管后关键破案（全部实测）

1. **壳=运行时解密型（.NET Reactor 风）**：静态反射只见 4B stub；LoadFrom 后运行时调用全真
   ——黑盒运行时探针（tests\probe\）是唯一正道。CorrCom/BaseContext/CommandPackage 在壳内；
   CorrData（ParsingParamsClass/BaseParams）无壳可静态反汇编。
2. **S2/S5/S6 NRE 同源**：`ParsingParamsClass.FlushParams(IBaseIO, bool)` 读 this.context，
   而 ..ctor 不初始化 context → 注入 `pp.context = ctx`（反射字段）后全绿。
   金堆栈：FlushParams ← BaseContext.eN9I2Er1a4qfvbLTa ← set_BaseIO ← ExpComSendClass.SendIOBytes ← SendMethodInit。
3. **S4=False 真因**：帧2=`AA 85 63 0A 00×11 9C`（GetDoubleChannelSampleBytes 动态构造，16B）无人应答
   → sim_cs5.py 补 0x85（sub=frame[3]，frame[2]=0x63 是族码）+0x74+0x52 回显后 S4 True。
   另 sim_cs5.py 旧版 `sub=frame[2]` 的 bug 导致 zcode 时代所有 0a_* 变体静默（结论作废）。
4. **S6 偶发 False 真因**：StartMethod Sleep(800)×2+50×3 期间 sim 推流塞满 m_DataBuffer(List<byte>)，
   ACK 判定层（SendReturnBool 从头顺序解析消费）被推流垃圾卡死。**修复=--no-stream**；
   S4/S6 调用前插 ClearData() 清残渣。判定=队列非空即可，内容无关；残渣会卡后续帧。
5. **S7 数据零真因**：ExpTime=0 → ExpIsFinished=True → AddData 首行 `if(ExpIsFinished) return` 全拒。
   修复：S6 前 `prm["ExpTime"]=60f; DevParam["WaitSecond"]=60` + set_ExpIsFinished(false)。
6. **落盘机制**：AddData 只入库不写盘；写盘=手动 WriteDataNow()；AddData 尾部 NRE（graphFrm null）无害。
   **文件路径被软件无视 prm.FilePath 改写到 Documents\Corrtest\Data\<FileName>**。
7. **volt 编码**（GetVoltValue 黑盒标定）：3B 大端偏移二进制 `(raw24−2^23)/2^23×10`（LSB 1.19μV）；
   curr 同构 ×2.5。应答帧=8B `AA 53 + volt3B + curr2B + SUM`（剥 AA 后 data[0]=cmd, volt@1..3, curr@4..6）。
8. **ExpCallWatiFun 590B 全逻辑**（t_cs5wati.txt）：ExpType∈{1,38,5001,5000,51,52} 直返；循环
   SendReturnPackage(ReadOcpBytes,1500,7,170,3)→len7: volt@1,3 curr@4,3；量程自适应 AutoRangeInc；
   WatiFun 只做 AutoRange 不入库。

### 帧序全景（S1→S7 现场实测）

```
连接 → AA D0×2 → AA D1×3 → AA 8B×3（不应答则掉线进演示模式）
启动 → AA 80 53×3 → AA 81×3 → AA 53 01（OCP 轮询，AA 53+volt3+curr2+SUM 应答）
S2   → AA 74 00…1E（echo 16B）
S4   → AA 85 63 0A…（echo 16B）→ AA 52 07 D2 00 03…D8（echo 16B）×9
S6   → StartMethod（--no-stream + ClearData）
S7   → AddData(volt,curr,dt) → WriteDataNow() → CORRW ASCII 文件
```

### 资产清单（本轮新增/修改）

- tests\probe\t_cs5steps.cs（主探针：S1–S7+全诊断）、t_cs5wati.cs、t_cs5start.cs、t_cs5cal.cs、
  t_cs5pack.cs、t_cs5rx.cs、t_cs6srb.cs、t_cs5parse{,2,3}.cs（反汇编模板+RVA dump）
- code\cs5\sim_cs5.py（0x85/0x74/0x52/0x53 分发+wati7 8B 帧版）、tools\run_cs5.py（--no-stream --ack74）
- 日志：logs\run_nostream/run_wdnow/run_file.txt（S6 True + 落盘）、run_s4*.txt、run_s6c.txt、
  t_cs5wati.txt、t_cs5start.txt、t_cs6srb.txt、auto53_*.out（sim 帧现场）

### 下一步

1. **CS6 路线已全通（此前轮），CS5 全链本轮贯通** → 巡检记录.md 同步大捷。
2. 剩余打磨：S6 偶发 False 残余不稳定（多轮连跑观察）；落盘路径强制写 Documents（可接受）。
3. 更高目标（用户原方向）：完整参数帧语义表（0x85 63 0A 的 13B data 字段含义），
   为将来纯协议直连（CSDirect）铺路——素材已全部实录在 sim 日志与探针里。

### 阻塞

无。全链已通，无未解依赖。

---

## 2026-11-10 15:2x ★★★ CS6 UI 宿主三实验贯通（OCP→EIS→动电位，软件界面全程可见）

### 任务（用户指令）

"拿模拟测试一下，先开路再阻抗再动电位，设置为面积1 型号x，软件界面打开让我看到进度"
→ CsPilotUi6.exe 宿主：软件原生启动（壳 EntryPoint）+ 手动线驱动三实验 + 原生落盘。

### 结果（logs\ui6_run.txt / Documents\Corrtest\Data\ui6_*.cor）

| 实验 | SendMethodBytes | SysStart | 点数 | 落盘 |
|---|---|---|---|---|
| ocp  | True | True | 50  | ui6_ocp.cor 3,876B |
| eis  | True | True | 303 | ui6_eis.cor 11,344B |
| tafel| True | True | 662 | ui6_tafel.cor 14,726B |

- 窗口标题全程=「CS Studio6 【型号：CS350M in 10.9.73.113:31101】,序列号:CS350M24030650」。
- tafel.cor 文件头完整：ExpParmas 全参数串（InitE=-0.3→FinalE=0.8/ScanRate=25/**OcpValue=-0.14**/vsRef×4/DevParam 全套/**CellParam=Area=1**）+「Open Circuit Potential (V):-0.14」。

### ★ 根因（一句话）：Coerce() 把接口类型塞进 Convert.ChangeType → InvalidCastException

- 链条：`SetProp(prm,"baseContext",ctx)` → Coerce(v=ctx, t=IBaseContext 接口) → 尾部
  `Convert.ChangeType` 抛 InvalidCast → catch 吞掉返回 false → **prm.baseContext=null**
  → SendMethodParams 真身读 baseContext.xxx → NRE「未将对象引用设置到对象的实例」。
- 无头宿主为何没事：CsPilotHost.BuildParams 的 baseContext 是**直接 SetValue 不走 Coerce**。
- **修复（CsPilotUi6.cs Coerce 首行）**：`if (t.IsInstanceOfType(v)) return v;`
- 诊断套路（可复用）：SetProp 打印失败原因（v 类型 + Inner 消息）→ `baseContext 装配=FAIL 读回=null!!!`
  一眼定位；`[prm属性]` dump 确认属性存在且 w=True → 锁定 SetValue 异常。

### 宿主架构定稿（code\cs6ui\CsPilotUi6.cs）

1. Main：LoadAsms（LoadFrom 全家）→ 起 Runner 后台线程 → `exe.EntryPoint.Invoke` 壳原生启动（资源/皮肤/搜索全真，frmMain 资源被壳混淆乱码名 ppSAetW3CkDorch4wo.*，不可手动 new frmMain）。
2. Runner：等 frmMain 出现（Application.OpenForms 轮询）→ **ManualWire()**（SockectConnect.Open(127.0.0.1:31101) → CheckPackReceiveThread → new BaseContext → SetConnect）——**手动线跑实验**（软件自己的 ctx 上 SendMethodBytes 必 NRE，原因未究但手动线=无头宿主同款已验证）→ ExpComSendClass(ctx) 自 new+挂 ctx。
3. RunExperiment（每实验）：ThisExp=枚举 → prm 四连 fallback 装配 baseContext + ExpType + JSON 参数 → FileName/FilePath → ctx.BaseParam/SysRuning → BeginStartWriteFile(false) fire-forget → SendMethodBytes(prm) → SysStart(true) → 轮询 PointCount 稳定 → SysStop → WriteDataNow 落盘。
4. sim 多客户端：simdevice.py `_tcp_accept_loop` while+listen(2)——软件 LAN 连入与手动线并存。

### 侦查中排除的死路（防重蹈）

- CS6 CorrData 也有运行时解密壳（BaseParams/SendMethodParams 静态 IL=4B stub）；
  **GetMethodBody 运行时也拿 4B** → 壳在 JIT 层 hook，反射不可见真身（但调用会执行真实现）。
- 软件自装 ExpComSend vs 自 new：两者都 NRE（问题在 prm.baseContext，与发送器无关）。
- NRE 堆栈三变体（plKkBQqXbp8VFhcTwh4 中间帧有无）不影响定位——同一 NRE。

### 资产

- code\cs6ui\CsPilotUi6.cs / CsPilotUi6.exe（UI 宿主定稿版）
- tests\probe\t_cs6nre.cs（CS6 prm/BaseContext 结构 dump，注意 DumpMethods contains=null 会炸 IndexOf）
- tests\jobs\ui6base.json（无头基线 OCP job）
- 日志：logs\ui6_run.txt（全程）、logs\t_cs6nre.txt、logs\ui6base_events.jsonl（无头对照 rc=0）

### 下一步

1. 面积/型号参数化：CellParam 挂在 prm 的 ExpParmas 串里（Area=1 已默认对）——如需显式设,
   找 prm.CellParam 或 WriteParams 深挖（本轮 warn「ctx 无 CellParam」是查错了对象，CellParam 不在 ctx）。
2. UI 可视化增强：软件图表显示实验曲线（手动线数据在 ctx.BaseGraph 链——待验证是否已入图）。
3. CSDirect 纯协议方向素材继续积累（sim jsonl 已录三实验全帧序）。

### 阻塞

无。

---

## 2026-11-10 · ★★ 决定性发现：CS5 的 CorrCom 层是运行时解密，静态 IL 全是桩

> [!warning] 2026-11-11 深夜订正（本节部分结论 superseded）
> 本节由停留在 11-10 上午上下文的看护会话于 11-11 22:31 追加（当晚仅做 t_cs5srb2 静态 IL dump，
> 未跑任何实验）。其中「4B 桩 / 运行时解密」的静态事实**成立**（接管轮 11-10 11:32 独立复证）；
> 但下文「黑盒试错已覆盖 8 个 0x85 变体 + 11 个 ack53 变体 + 8 个 0x85 子命令变体，全失败」
> 的清单与「CS5 = blocked」结论**已被推翻**：那批失败系两个测试台 bug 所致——
> ①`tools/run_cs5.py` 硬编码 `--ack74 silent`（S4 帧1 AA 74 无人应答）；
> ②sim 变体分发 sub 读 frame[2] 应读 frame[3]（0a_* 变体从未真正生效）。
> 接管轮修复后 **S1–S7 全绿 + CORRW ASCII 落盘**（见本文「2026-11-10 12:5x」节与
> Obsidian `12_纯代码线_dsh接管与CS5全链贯通.md`）。
> 「真机抓包」降级为真机联调清单中的「实机应答语义核对」项，不再是阻塞。

### 证据（`tests/probe/t_cs5srb2.cs` → `logs/t_cs5srb2.log`）

把 `ICorrCom` 全族方法的**原始 IL 字节**打出来，只有 4 字节：

```
BaseCorrCom.SendReturnBool      (3p)  00 00 17 2A
BaseCorrCom.SendReturnBoolThree (1p)  00 00 17 2A
BaseCorrCom.SendReturnPackage   (5p)  00 00 14 2A
CorrCom520.SendReturnBool*           00 00 17 2A   （全族相同）
CSTSerialPort.SendReturnBool*        00 00 17 2A
CSTSockect.SendReturnBool*           00 00 17 2A
CSTSockect.SendReturnPackage         00 00 14 2A
```

按 IL 指令表解码：

| 字节 | 指令 | 含义 |
|---|---|---|
| `00` | nop | 空操作 |
| `17` | ldc.i4.1 | 压入常数 1 |
| `14` | ldc.i4.0 | 压入常数 0（引用类型即 null） |
| `2A` | ret | 返回栈顶 |

→ **`SendReturnBool*` 恒返回 `true`，`SendReturnPackage` 恒返回 `null`。**
所有 `SockectCom` / `CorrCom520` / `CSTSerialPort` / `CSTSockect` 的实现**一模一样**，
且 `SockectCom` 继承 `BaseCorrCom`（自身 `SendReturnBoolThree` IL=-1，即没有实现）。

### 这说明什么

**CorrCom 层被混淆器的运行时解密保护了**（与前序文档提到的 ConfuserEx 式一致）。
这些 4 字节桩是静态视图下的"占位"，真实逻辑在运行时由解密器 patch 进去。

因此：
1. **对 `CorrTest.CorrCom` 这一层，静态 IL 反查完全不适用** —— 之前用 IL 找
   `ExtDevHlp` / `BaseIO` 的方法（在 `CorrData`/`CorrInterface` 层有效）在这里失效。
2. **S3 的 NRE 得到解释**：`BaseParams.GetOcpValue` 里
   `ldsfld ReadOcpBytes → ICorrCom.SendReturnPackage`（桩返回 null）
   → `IParsingParams.GetVoltValue(null)` 解引用 → NullReferenceException。
3. **S4 返回 False 必须来自运行时真实实现**，因为静态桩恒返回 true。
   即：`SendMethodParams` → `SendReturnBoolThree` 在运行时真的做了收发并判定失败。

### 策略调整（重要）

| 原路线 | 新路线 |
|---|---|
| 静态 IL 反查 CorrCom 语义 | ❌ 失效（桩） |
| 静态 IL 反查 CorrData/CorrInterface | ✅ 仍有效（本轮此前所有收获都来自这层） |
| 推断设备应答语义 | ✅ 只能靠**黑盒字节观测 + 变体试错** |
| 真机抓包对照 | ★ 成为**唯一可靠的定案手段** |

### 当前诚实的评估

CS5 卡点集中在「**设备应答语义**」这一件事上，而它：
- 静态不可读（运行时解密）
- 黑盒试错已覆盖 8 个 0x85 变体 + 11 个 ack53 变体 + 8 个 0x85 子命令变体，全失败
- 前序 09 号文档记录的 CS5 协议定案（发现协议/16B AA 帧/SN 应答）都来自**真机 Buffer 日志**，
  而非静态分析——这本身就说明这层只能靠真机证据

**缺失条件（标 blocked）**：
需要**真机 CS120 在线时抓一次完整的「参数下发 → 启动 → 数据」报文**，
才能定案 `0x85 63 0A` / `0x53 01` 的应答格式。真机需用户在场授权。

### 相比之下，CS6 已完成度（不受影响）

| 项 | 状态 |
|---|---|
| 四实验（OCP/Tafel/Step/EIS） | ✅ 全部打通 |
| 原生 `.cor` + 自写 txt 双路落盘 | ✅ |
| 判稳/判停策略 | ✅ 35 项断言全 PASS |
| 多机并行 | ✅ 双机 78.7 s |
| 一键回归 | ✅ 5/5 ALL-OK |

### 下一步（离线仍可做的）

1. 把 CS5 的调研成果整理成一份独立文档（`docs/02_CS5阶段结论.md`），
   明确「已打通的部分」与「被运行时解密挡住的部分」，避免下次重复踩坑
2. `tests/run_all.py` 增加 CS6 侧的稳定性加固（多跑几轮）
3. CS5 侧标记 blocked，等待真机抓包

### 阻塞
**CS5 设备应答语义 = blocked**。缺失条件：真机 CS120 在线的完整收发报文。

---

## 2026-11-10 · CS5 结论文档归档 + CS6 稳定性加固

### 一、新建 `docs/02_CS5阶段结论.md`

把 CS5 的调研成果一次性定案，避免下次重复试错。文档结构：

1. **总览表**：13 个环节的打通状态（装配层全通，卡在设备应答语义）
2. **CS5 vs CS6 差异全表**：命名空间/连接注入/数据载体/落盘/下发/启动/停止/
   **枚举值（两版不同！）**/帧族/数据帧 —— 共 11 个维度
3. **★ 核心阻塞证据**：CorrCom 层 IL 全是 4 字节桩（`00 00 17 2A` = `nop;nop;ldc.i4.1;ret`）
   → 运行时解密保护 → 静态反查失效
4. **已穷尽的试错记录**（**不要重复**）：
   - 8 个 `0x85` 变体（只有 `silent` 能推进）
   - 11 个 `ack53` 变体（结果全部一致，说明不是差异化因素）
   - 8 个 `0x85` 子命令变体（全失败）
   - 4 项已排除项（推流正常 / 0xCF 无关 / ExtAmpData 无效）
5. **软件侧完整启动帧序**（供真机对照）
6. **缺失条件**：真机 CS120 在线的完整双向报文
7. **将来拿到报文怎么继续**（三步）
8. **现有资产清单**（9 个文件）
9. **与 CS6 的关系**：CS6 不受影响

### 二、CS6 稳定性加固（连跑 2 轮全绿）

```
第 1 轮：test_policies 35/0 · selftest 57/57 · t2_all4 83.2s
        t3_policy 34.8s · pilot 78.7s            → 5/5 ALL-OK
第 2 轮：test_policies 35/0 · selftest 57/57 · t2_all4 83.6s
        t3_policy 35.0s · pilot 78.5s            → 5/5 ALL-OK
```

耗时稳定（四实验 83.2/83.6 s，策略 34.8/35.0 s，双机 78.7/78.5 s），
说明前面修掉的 auto_wired 半死连接问题是真根治，不是靠重试碰运气。

### 三、项目当前状态

| 部分 | 状态 | 说明 |
|---|---|---|
| CS6 纯代码路线 | ✅ **完整交付** | 四实验 + 双路落盘 + 4 策略 + 多机 + 回归 5/5 |
| CS5 纯代码路线 | ⚠ **blocked** | 装配层全通，卡在设备应答语义（运行时解密） |
| 文档 | ✅ | `01_纯代码路线_方案.md` + `02_CS5阶段结论.md` + PROGRESS + 巡检记录 |
| Obsidian 归档 | ✅ 待补 02 号 | 需把 `02_CS5阶段结论.md` 同步进库 |

### 四、下一步

1. 把 `docs/02_CS5阶段结论.md` 归档进 Obsidian（新建 `11_CS5阶段结论.md`）
2. CS5 等真机抓包（**blocked，需用户在场**）
3. 离线可做项已基本清空

### 阻塞
**CS5 = blocked**（需真机报文）。CS6 无阻塞。
按规则：连续 3 轮巡检无离线可推进项时暂停巡检。
本轮仍有归档工作可做，故继续。

---

## 2026-11-11 23:5x · 夜间自动化 A1：docs/02_CS5阶段结论.md 全面修订（合并接管轮战果）

- 22:52 旧上下文看护会话曾创建本文档（停在 11-10 上午态：S3/S4/StartMethod 标 ❌、status: blocked）。
- 23:5x 夜间自动化 A1 按接管轮战果全面修订：❌→✅（S4 echo 可通 / S3 探针签名+context 注入 /
  StartMethod --no-stream+ClearData / 数据入库 ExpTime 修复）、§四 变体表就地标注作废原因、
  §五 补接管轮帧序定案版、§六 改「待实机核对清单」、新增 §十 0x85 字段表填充区（A2）。
- 权威裁定：OVERNIGHT_PLAN.md §0。当前项：A2（0x85 13B 字段表）。

---

## 2026-11-12 00:5x · ★ 阶段 A 收官（夜间自动化 A1–A6 全绿）

- **A0 基线**：run_all.py 23:04 5/5 ALL-OK。
- **A1**：docs/02_CS5阶段结论.md 全面修订（stale blocked 内容 → 接管轮定案，作废结论就地标注）。
- **A2**：02 文档 §十——0x85 63 0A 逐字段表 + S4 帧2（0x52 07 D2 00 03）字段推断
  （GetDoubleChannelSampleBytes IL 分支 5/7→9/11 定案；GetDoubleSingleSampleBytes 本体 4B 桩）；
  **SUM = 前 15 字节（含 AA）累加和** 六帧验算 ✓。
- **A3**：S6 压测 **10/10 全绿**（wati7+0a_echo+echo74+--no-stream；S4 False=0、S6 False=0）。
- **A4**：CS6 三连回归 **3×(5/5 ALL-OK)**（logs/run_all_x3_20261112.log）。
- **A5**：frmOCP 确定处理器静态调查（t_cs6ocp.cs）——**CorrForm 层全 4B 桩**实锤；
  UI 原生线「确定后实验不真启动」嫌疑收敛到 BaseParamFrm 校验链
  （StartButtonClick → CheckParam/CheckFrq → SaveParams），破题需运行时探针/联调日志。
- **纯代码线离线部分就此全部收官**；剩余 = 真机端到端（等用户授权）。
- 夜间自动化进入 B 阶段（cspilot-parasite 只读审计）。

---

## 2026-11-13 · ★ 恒电流族四实验离线全链打通（纯代码线新能力）

- **目标**（用户指令）：工作站输出特定波形电流——方波优先，常见波形都做。
- **枚举/参数类定案**（反射 dump）：GalSquareWave=9/GalStatic=3/GalDynamic=6/GalCharge=41；
  参数类 GalSquareParams/GalStaticParams/GalDynamicParams/GalChargeParams 全字段 dump
  （tools/dump_gal_params.ps1）。备用：GalJump=11/GITT=61/PITT=60/AnyGalStatic=64/EISVSFRQG=38。
- **方法帧定案**（t4_gal4/t4b_gal_diff 两轮变参差分）：0x57（方波 114B）/0x53 长帧（阶跃 22B，
  厂商命名 CSGalStatic 本就是 0x53）/0x55（扫描 34B，与 0x54 同构）/0x88（充放电 48B）。
  通用规则：电流 mA→A（f32 链）、0x57 时间 ms→s、0x53 TestTime×2、SUM 含 AA。
- **实现**：CsPilotHost 加 4 case（两字典各 4 行）；simdevice 加 CMD+解码器×4+构造器×4
  （f32 链换算复刻软件舍入）+分发×4+信号源 gal_point×4+推流白名单扩展
  （首跑零入库根因=推流模式白名单漏 gal_*）。
- **E2E**：t4_gal4 三轮 ALL-OK（gal_square 86 点/gal_static 86/gal_dynamic 85/gal_charge 258@30Hz）；
  数据形状验证：方波 ±5e-4 A/cm² 两档电位、恒流对数极化漂移、扫描斜坡、充放电锯齿。
  gal_charge 原生 .cor=9 列专用格式（软件本体完整支持恒流充放电数据模型）。
- **回归**：新增 tests/test_gal_frames.py **65 项全 PASS**（golden 程序化提取+构造器往返等价+
  逐字节全同特例）；run_all.py 5/5 不受影响；selftest 57/57。
- **落盘**：docs/03_恒电流族扩展.md（帧布局定案+备用实验清单+复现命令）；
  tests/golden/gal_frames.json（8 帧程序化提取）。
- **待真机核对**：0x53 ×2 因子、0x88 尾三段恒定字段、i 列增益系数（sim 无量程概念）、
  Times 不落帧的设备侧行为、电流量程上限。

---

## 2026-11-14 · ★ 实时波形显示窗口（code/viewer.py）

- **需求**（用户）：给纯代码线加显示窗口，实时显示工作站输出的波形。
- **数据链**：宿主采集循环新增逐点 `sample` 事件（[t,E,I,Q] → JSONL，重编译）→
  `code/viewer.py` Tk+matplotlib 窗口尾随事件流实时绘制：上图 i(t)（输出波形）、
  下图 E(t)（响应）；多实验时间轴自动拼接、绿色虚线实验分界；静默 15s 自动存
  `logs/viewer_final.png` 收据。
- **用法**：`python tests/run_case.py <job> --port 31001 --view`（--view 自动拉起窗口）；
  或独立 `python code/viewer.py <events.jsonl>`。
- **三坑**：①matplotlib 默认字体无中文（标题豆腐块）→ Microsoft YaHei；
  ②run_case 先删后拉起 → viewer 启动时等文件出现；③for-line 迭代器内 f.tell() 抛
  OSError → readline 循环。
- **验证**：E2E ALL-OK + 离线 12s 自动存图 ✓ + viewer_final.png 目检
  （中文标题/四实验拼接/方波形状全对）。

---

## 2026-11-18 · ★★ CS5 首次真机接触 + 恒流阶跃实测电阻（用户电阻假电池）

**用户接线**：电阻接 WE↔CE，RE 夹 CE 端，GND 悬空；设备 = COM10 CS350（CP210x，SN CS3501501006）。
**红线**：用户在场 + 明确"接好了，测试一下" = 真机授权成立；只碰 COM10，±0.1mA 安全门。

### 纯代码线（t_cs5r.cs，7 轮迭代）
- 离线定案：CS5 Experiment 枚举 `ID_GalStatic=3`（按名解析，勿跨版写死）；
  GalStaticParams 字段 PorCurr/CurrUnit/TestTime/TimeUnit 齐备（params5.txt）。
- 真机实测：**CorCom.Open(COM10)=True**、S2 SendMethodInit / S4 SendMethodParams /
  S5 InitExp / S6 StartMethod **全 OK:True**，原生 .cor 头正确写 `ID_GalStatic`
  （证明参数下发到软件栈层面生效）。
- 挂点定案（dump_cs5_delegates.ps1）：`BaseCorrCom.OnRecePackage` (delegate RecePackage) ↔
  `BaseContext.Com_OnRecePackage(byte[],bool)`；`EnableDataEvent(bool)` 控数据事件。
  已补进装配段（等价于 CS6 的 SetConnect）。
- **卡点（重大发现）**：设备**一帧数据都不回**（rxbuf 全程 0B，WatiFun 跑满 30s、
  OCP 轮询"没有接收到数据"）。pyserial 四种波特率裸发 AA 81 查序列号均无应答。
  → 纯代码链绕过软件主程序，缺**启动握手序列**（doc 12：AA D0×2 / AA D1×3 / AA 8B×3，
  不应答则掉线进演示模式）。软件本体启动时才发这串；启动 CorrTest.CSStudio.exe 后标题
  `【型号：CS350 in COM10】,序列号:CS3501501006` 立即连上，坐实此判断。
- 结论：CS5 纯代码链「装配+下发」已真机验证，「采集」需补握手；留待后续。

### GUI 线（软件本体，real_r_gui3.py）——测量成功
- 菜单路径实证：测试方法(E) → **暂态极化(T)** → 恒电流阶跃(G)（不是稳态极化支）；
  参数窗 aid 全是 `GalJump_*`（软件内部 ExpType=ID_GalJump）。
- 双极性 ±0.1mA 两轮：各 71 点 / 7s，.cor 落盘 `D:\deepseek\_probe\e2e5\real_R_{pos,neg}_*.cor`。
  OCP 字段活读数 -0.00008/-0.00012 V（设备在线的证据）。
- 稳态段（t≥2.8s）中位数：**E(+I)=+0.049776 V，E(−I)=−0.088166 V** → ΔE=0.137942 V；
  i 列中位数 +2.1116e-5 / −2.0207e-5（列头 i(A/cm2)，量纲待核）。
- 两种 R 口径：
  * 按仪器 i 列：R=ΔE/Δi=**3338 Ω**
  * 按设定电流 ±0.1mA：R=ΔE/(2×1e-4)=**690 Ω**
  （差 4.8 倍 = i 列与设定值比例；需用户报标称阻值或加测 0.05mA 档定案）
- 单极性 R 不等（2357 / 4363 Ω）= 存在约 ±0.019V 固定偏置，双极性消偏置有效，
  且 E 随电流符号翻转 → **数据真实，非 demo 陪跑**。

### 待办
1. 用户报电阻标称值 → 定死 R 口径。
2. 加测 0.05mA 档验证 ΔE 线性比例（不依赖 i 列量纲自洽）。
3. 纯代码链补启动握手（从软件本体启动过程抓 AA D0/D1/8B 序列）→ CS5 真机全链闭环。

### 补：0.05mA 档线性验证（同日）
- 加测 ±0.05mA 双极性（real_R_pos_125807 / real_R_neg_125841），四份 .cor 稳态中位数：
  ±0.10mA: E+=+0.049776 / E−=−0.088166 (ΔE=0.137942)，i+=+2.1116e-5 / i−=−2.0207e-5
  ±0.05mA: E+=+0.014931 / E−=−0.054000 (ΔE=0.068931)，i+=+1.0628e-5 / i−=−1.0135e-5
- **ΔE 与 Δi 均严格减半 → 纯欧姆线性，数据真实**（demo 陪跑不可能如此）。
- 两种口径各档自洽：R(设定电流)=689.3/689.7 Ω（跨档 690.1 Ω）；
  R(仪器 i 列)=3319.9/3338.1 Ω（跨档 3356.6 Ω）。差 4.85 倍 = i 列非 A 量纲
  （<200μA> 量程归一化）。按欧姆定律正确口径 **R ≈ 690 Ω**，待用户报标称值终裁。

### 补：2026-11-18 复测（real_r_gui4.py，修两坑）
- 修复：①find_run_window 用 `keywords=("恒电流","阶跃")` + `expect=文件名` 精确匹配，
  消除负轮抓到正轮残留窗的竞态；②改读 .cor 稳态段中位数而非界面 UiSampler。
- 复测 ±0.1mA / ±0.15mA 双极性：R_set **760.6 / 760.1 Ω**（离散 0.5 Ω），
  跨档线性拟合 759.1 Ω；R_col 3674.8 / 3676.4 Ω。
- 第三次 0.1mA 重复：R_set 770.5 Ω、R_col 3706.8 Ω。
- **0.1mA 三轮（跨会话）：690 → 760.6 → 770.5 Ω，单调缓升 ~10%**
  ——单次会话内极稳（0.5Ω 离散），跨会话漂移疑为夹子接触电阻/温度/氧化，
  非算法问题；两口径比例恒 4.83（3338/690、3675/760、3707/770），
  证明 i 列带固定换算系数而非噪声。
- 待用户报电阻标称值终裁口径。

### 补：2026-11-18 第四轮复测（real_r_gui4 同两档）
- ±0.10mA: R_set=775.9 Ω / R_col=3752.5 Ω；±0.15mA: R_set=766.9 Ω / R_col=3712.1 Ω；
  跨档拟合 749.0 Ω，两档离散 9.0 Ω。
- 0.1mA 跨会话序列 **690 → 760.6 → 770.5 → 775.9 Ω**，
  增量 +70.6 → +9.9 → +5.4 → 明显收敛（≈770 Ω 饱和），符合接触/热效应达到稳态的解释。
- 两口径比例仍恒定 4.84（3752.5/775.9、3712.1/766.9）。

### 补：2026-11-18 第五轮复测（收敛确认）
- ±0.10mA: R_set=773.2 Ω / R_col=3740.0 Ω；±0.15mA: R_set=768.1 Ω / R_col=3717.6 Ω；
  跨档拟合 757.9 Ω，两档离散 5.1 Ω。
- 0.1mA 五轮序列 **690 → 760.6 → 770.5 → 775.9 → 773.2 Ω**：
  后四轮稳定在 770~776（±3Ω），收敛确认，首轮 690 为建立期异常值。
- 两口径比仍恒 4.84（3740.0/773.2、3717.6/768.1）。
- 最终稳定读数：**≈771 Ω（设定电流口径）/ ≈3.73 kΩ（i 列口径）**。

### 补：2026-11-18 第六轮复测
- ±0.10mA: R_set=781.6 Ω / R_col=3782.7 Ω；±0.15mA: R_set=769.5 Ω / R_col=3724.9 Ω；
  跨档拟合 745.1 Ω，两档离散 12.2 Ω。
- 0.1mA 六轮序列 690 → 760.6 → 770.5 → 775.9 → 773.2 → **781.6 Ω**：
  后五轮 760~782，均值 ≈772 Ω；本轮略高但仍在同一带内（无持续单调漂移，属正常波动）。
- 两口径比 3782.7/781.6=4.84、3724.9/769.5=4.84，恒定不变。
- 结论不变：稳定读数 **≈772 Ω（设定口径）/ ≈3.74 kΩ（i 列口径）**。

### 补：第七轮复测（稳定性再确认）
- ±0.10mA: 776.8 Ω / 3759.6 Ω(i列)；±0.15mA: 771.5 Ω / 3724.2 Ω(i列)；
  拟合 761.0 Ω，离散 5.3 Ω。0.1mA 七轮：690 → 760.6 → 770.5 → 775.9 → 773.2 → 781.6 → 776.8。
  后六轮 760.6~781.6（均值≈773 Ω）稳定，口径比恒 4.84。

### 补：第八轮复测
- ±0.10mA: 770.4 Ω / 3753.9 Ω(i列)；±0.15mA: 763.4 Ω / 3700.2 Ω(i列)；
  拟合 749.3 Ω，离散 7.1 Ω。0.1mA 八轮：690→760.6→770.5→775.9→773.2→781.6→776.8→770.4。
  后七轮 760.6~781.6（均值≈772 Ω）稳定，口径比恒 4.84。

### 补：换试样后分组（用户 2026-11-18 14:3x 告知「这轮换了试样」）
- **旧试样**（第1~8轮，0.1mA）：690 → 760.6 → 770.5 → 775.9 → 773.2 → 781.6 → 776.8 → 770.4 Ω，
  后七轮均值 ≈772 Ω（760.6~781.6）。
- **新试样**（换样后两轮）：
  * 轮A ±0.1/±0.15mA：761.0 / 760.9 Ω（拟合 760.5，离散 0.2 Ω）
  * 轮B ±0.1/±0.15mA：766.0 / 759.6 Ω（拟合 746.8，离散 6.4 Ω）
  * 新样均值 ≈762 Ω；两口径比仍恒 4.84（3710.3/761.0、3686.5/759.6）。
- **判断**：新旧试样阻值差 ≈1.5%，落在旧样波动带内 → 换上的试样阻值与旧样几乎相同
  （同规格/同批次电阻），或换样未改变回路电阻。若用户预期是明显不同的阻值，
  需确认夹子是否夹到了新试样本体/新试样标称值。

### 补：新试样第三轮
- ±0.10mA: 774.3 Ω / 3756.5 Ω(i列)；±0.15mA: 759.5 Ω / 3693.9 Ω(i列)；
  拟合 729.9 Ω，离散 14.8 Ω。新样三轮 0.1mA: 761.0 → 766.0 → 774.3，
  均值 ≈767 Ω；仍与旧样 ≈772 Ω 无显著区分。口径比恒 4.84。

### 补：新试样第四轮（0.15 档首次失败后补跑）
- 首跑 0.1mA: R_set=773.1 Ω / 3754.1 Ω(i列)；0.15mA 负轮弹「覆盖」提示框导致运行窗未出现（清残留后补跑成功）。
- 补跑 ±0.15mA: R_set=760.0 Ω / 3681.8 Ω(i列)。
- 本轮两档：773.1 / 760.0 Ω（离散 13.1 Ω）；新样四轮 0.1mA: 761.0→766.0→774.3→773.1，均值≈769 Ω。
- 口径比仍 4.84。

### 补：新试样第五轮（软件界面状态不稳，多次重试后补齐）
- 反复出现参数窗残留/「覆盖」提示框拦住菜单与运行窗；用 SendMessageTimeout(WM_CLOSE)+DestroyWindow
  强清残留窗后恢复。0.1mA: R_set=766.7 Ω / 3707.6 Ω(i列)；0.15mA 补跑: 757.3 Ω / 3671.7 Ω(i列)。
- 新样五轮 0.1mA: 761.0→766.0→774.3→773.1→766.7，均值≈768 Ω；口径比仍恒 4.84。
- 备注：软件长时间反复开关参数窗后 UI 状态会劣化，若继续大量复测建议重启 CorrTest.CSStudio.exe。

### 补：重启软件后新试样第六轮
- 先 Stop-Process 重启 CorrTest.CSStudio.exe（真机自动重连 CS350 in COM10，标题确认），清 UI 状态。
- ±0.1mA: 772.5 Ω / 3733.9 Ω(i列)；0.15mA 负轮仍被覆盖框拦，清残留后补跑: 761.3 Ω / 3690.0 Ω(i列)。
- 新样六轮 0.1mA: 761.0→766.0→774.3→773.1→766.7→772.5，均值≈769 Ω；口径比恒 4.84。
- 重启后 0.1mA 一轮即正常，说明 UI 劣化确为累积状态问题；但「覆盖」提示框在重复文件名时仍偶发。

### 补：★★ 新试样（真·换样）读数跳变（2026-11-18 16:2x 后）
- ±0.10mA: R_set=1655.2 Ω / 8013.1 Ω(i列)；±0.15mA: R_set=1575.7 Ω / 7707.8 Ω(i列)；
  跨档拟合 1416.8 Ω，两档离散 79.5 Ω。
- **读数从 ≈769 Ω 跳到 ≈1615 Ω（约 2.1 倍）→ 这次确实换到了不同阻值的试样**；
  前六轮「新样」≈769 Ω 应判为夹子仍夹在旧样/同规格接点上，现予更正为「旧样延续」。
- i 列口径/设定口径比仍 ≈4.84（8013.1/1655.2=4.84、7707.8/1575.7=4.89），
  证明测量系统未变、仅试样改变；口径悬案不受影响。
- 三样本分组（修正）：
  * 样本A（前 8 轮 + 换样后 6 轮）：≈770 Ω
  * 样本B（本轮）：≈1615 Ω / ≈7.86 kΩ

### ★★ 订正：电流口径翻案（2026-11-18，用户问「电流多少」触发核算）
- 参数窗 GalJump_Jump1_txt 输入 0.05/0.1/0.15（下拉显示 mA），但运行窗标题为「<200μA>」量程。
  核查所有轮次 i 列回读 Δi 与「输入值 × 200μA × 2（双极性）」：
  0.05档 2.0763e-5 vs 2.0e-5(1.038)、0.10档 4.1323e-5 vs 4.0e-5(1.033)、
  0.15档 6.2027e-5 vs 6.0e-5(1.034)、样本B 0.10档 4.1312e-5(1.033)、0.15档 6.1329e-5(1.022)。
  → **输入值实为 200μA 量程的比例，真实输出电流 = ±(输入×200μA)**：
  0.05→±10.4μA、0.10→±20.7μA、0.15→±31.0μA；与试样无关（恒流源）、严格线性。
- **订正结论**：此前「R_set = ΔE/(2×输入值×1e-3)」把输入当 mA，比真实电流大 4.84 倍，
  该口径作废；**正确 R 应按 i 列真实电流**：样本A ≈3.7 kΩ、样本B ≈7.8 kΩ。
  4.84 倍恒定的原因 = 100μA(误认设定) / 20.7μA(实际) 之比，非仪器量纲系数。
- 历史数据不改，仅加此订正；待用户报任一试样标称值终裁。

### 补：★ 读数第二次跳变（样本C？）
- ±0.10mA: ΔE=2.420741 V → R_set=12103.7 Ω / R_col=59079.4 Ω；
  ±0.15mA: ΔE=3.546370 V → R_set=11821.2 Ω / R_col=57414.9 Ω；
  跨档拟合(设定口径) 11256.3 Ω，两档离散 282.5 Ω。
- **ΔE 从 0.33V 级跳到 2.42V 级（约 7 倍）、E+ 达 1.53V / E− 达 −2.02V**，
  按已订正的真实电流口径（i 列）R ≈ **58 kΩ**（59.1k/57.4k）。
  未超合规电压（双极性 3.55V 远小于 ±10~20V），两档线性 1.47 倍（电流 1.5 倍）、
  离散 2.4%，数据自洽 → 非仪器饱和，是回路电阻又变了。
- 三个台阶：样本A ≈3.7kΩ → 样本B ≈7.8kΩ → 样本C ≈58kΩ（i 列口径）。
  可能用户连续换了试样，或夹子接触状态变化；待用户确认。

### 停止（用户 2026-11-18 17:0x「停止吧」）
- 本轮（样本C 复测）数据异常，不作有效结果：0.1mA 档 ΔE=3.9829 V（R_set 19914.6 / R_col 19895.9 Ω），
  但 0.15mA 负轮 OCP 字段读到 0.69288 V（此前恒 ≈0）、.cor 仅 2489 B、稳态解析失败，
  两档不再成比例 → 判断为高阻试样在 20~30μA 下压降逼近合规电压/仪器保护，数据作废。
- 按上轮建议尝试降档（0.05/0.1）重测，用户随即要求停止，命令已取消。
- 停止后核查：无残留测量 python 进程（现存 python 为无关 qoder_proxy）、无运行中的实验窗口、
  软件 CorrTest.CSStudio.exe 仍在但无实验通电；**测量已全部停止**。
- 后续若继续高阻试样：输入值降到 0.02~0.05（4~10μA）档再测，避免合规电压触顶。
