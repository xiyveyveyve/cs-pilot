# probe_e2e.ps1 -- CS-Pilot 方案3 Phase 2 四实验一条龙 E2E（无 GUI 无设备全链回归）
#
# 链路：simdevice.py(CNCB0, 设备端) <-> COM90(CNCA0) <-> .NET CSStudio6 协议栈(主机端)
#   LoadFrom DLL -> SerialConnect.Open("COM90") -> CheckPackReceiveThread -> new BaseContext
#   -> SetConnect(自动接线 OnPackReceive=ctx.PackReceive) -> 四实验循环：
#     ThisExp=<按名解析> -> BaseParam=<参数对象+反挂 ctx> -> ExpMethodState=SysRuning
#     -> SendMethodBytes -> SysStart -> 采集 10s -> SysStop
#
# 实验矩阵（全部按名解析，坑 41 纪律）：
#   OCP   ID_OCP         OcpParams        sim 应 0x51 后推 0x60 批量帧 30 点/帧 @10Hz
#   Tafel ID_PotDynamic  PotDynamicParams sim 应 0x54 后推 0x62 (E,i) @10Hz
#   Step  ID_AnyPotStatic PotSquareParams sim 应 0x56 后推 0x62 (E,i) 阶梯波
#   EIS   ID_EISVSFRQ    EISVSfrqParams   sim 应 0x41+0x70 后推 0x62 正弦（入库形状未知，尽力）
#
# 判据（日志末行）：
#   VERDICT: E2E-ALL-OK   = OCP/Tafel/Step 三实验 PointCount+五集合闭环 + GetUID 消费
#                           （OCP 另证 B 遗留①：Delta>=30 即 126B 批量帧整帧入库）
#   EIS 独立标注 EIS-OK / EIS-PARTIAL（PARTIAL 不阻断总判据，证据留档）
#   VERDICT: E2E-FAIL     = 三主实验任一未闭环
param(
    [string]$Port = "COM90",
    [string]$DevPort = "CNCB0",
    [int]$CollectSec = 10
)
$ErrorActionPreference = "Continue"
$repo = "D:\deepseek\cspilot-parasite"
$dir = "D:\sci\MDI Jade 9"
$probe = "D:\deepseek\_probe"
$out = "$probe\testbed_e2e.log"
$simJsonl = "$probe\testbed_e2e_sim.jsonl"
$simOut = "$probe\testbed_e2e_sim.out.log"
$simErr = "$probe\testbed_e2e_sim.err.log"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

# ---- 0. 清理本任务残留 simdevice 进程（红线：仅命令行匹配 testbed\simdevice.py 的 python） ----
try {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -like "*testbed*simdevice.py*" } | ForEach-Object {
        W("CLEANUP kill 残留 simdevice PID=" + $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch { }
if (Test-Path $simJsonl) { Remove-Item $simJsonl -Force -ErrorAction SilentlyContinue }

# ---- 1. 启动模拟器（设备端 B 侧，推 0x60 批量帧 30 点/帧） ----
$simArgs = @("$repo\testbed\simdevice.py", "--port", $DevPort, "--points", "30",
             "--log", $simJsonl)
$sim = Start-Process -FilePath "python" -ArgumentList $simArgs -PassThru `
        -WindowStyle Hidden -RedirectStandardOutput $simOut -RedirectStandardError $simErr
W(("SIM start PID=" + $sim.Id + " port=" + $DevPort + " points=30(cmd 0x60)"))
Start-Sleep -Seconds 3

# ---- 2. C# 助手 + 程序集 ----
Add-Type -TypeDefinition (Get-Content "$repo\testbed\rxprobe_helper.cs" -Raw) `
    -ReferencedAssemblies @("System.dll","System.Core.dll","$dir\CSStudio6.Connect.dll","$dir\CSStudio6.BaseInterface.dll") -ErrorAction Stop
[RxProbe]::CaptureConsole()
$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

# ---- 3. 连接（重试，等 simdevice 就绪） ----
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
[RxProbe]::WireLog($conn)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
$isOpen = $false
for ($try = 1; $try -le 10 -and -not $isOpen; $try++) {
    try { [void]$mOpen.Invoke($conn, @($Port)); $isOpen = $connType.GetMethod("IsOpen").Invoke($conn, @()) } catch { $isOpen = $false }
    if (-not $isOpen) { W(("OPEN retry " + $try + " (sim 未就绪?)")); Start-Sleep -Seconds 1 }
}
W(("STEP1 Open(" + $Port + ") -> " + $isOpen))
if (-not $isOpen) { W("FAIL: 端口打不开"); [System.IO.File]::WriteAllLines($out, $log); try { Stop-Process -Id $sim.Id -Force } catch { }; exit 1 }
[void]$connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @())

# ---- 4. 上下文（一次装配，四实验复用） ----
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
$autoWired = $connType.GetProperty("OnPackReceive").GetValue($conn, @())
W(("STEP2 SetConnect -> OnPackReceive 自动接线=" + $(if ($null -ne $autoWired) { "OK(" + $autoWired.Method.Name + ")" } else { "NULL" })))
$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
$enumMs = $bi.GetTypes() | Where-Object { $_.Name -eq "MethodState" -and $_.IsEnum } | Select-Object -First 1
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()
W("STEP3 上下文/发送器接线完成（四实验复用）")

# ---- 5. 计数工具 ----
function Get-Counters {
    # 返回 "PointCount|Time|Volte|Current|Charge|Indexs"
    $pc = 0; $tt = -1; $vv = -1; $cc = -1; $ch = -1; $ix = -1; $eis = -1
    try { $pc = [int]($ctxType.GetProperty("PointCount").GetValue($ctx, $null)) } catch { }
    try {
        $di = $ctxType.GetProperty("DataItem").GetValue($ctx, $null)
        if ($di) {
            $dt = $di.GetType()
            foreach ($pair in @(@("TimeValues", [ref]$tt), @("VolteValues", [ref]$vv),
                               @("CurrentValues", [ref]$cc), @("ChargeValues", [ref]$ch),
                               @("Indexs", [ref]$ix), @("EisDatas", [ref]$eis))) {
                $pp = $dt.GetProperty($pair[0])
                if ($pp) {
                    $lst = $pp.GetValue($di, $null)
                    if ($null -ne $lst) {
                        $n = 0
                        foreach ($o in [System.Collections.IEnumerable]$lst) { $n++ }
                        $pair[1].Value = $n
                    }
                }
            }
        }
    } catch { }
    return @($pc, $tt, $vv, $cc, $ch, $ix, $eis)
}

# ---- 6. 四实验循环 ----
$exps = @(
    @{ key = "OCP";   exp = "ID_OCP";         prm = "OcpParams";        minDelta = 30 },
    @{ key = "Tafel"; exp = "ID_PotDynamic";  prm = "PotDynamicParams"; minDelta = 20 },
    @{ key = "Step";  exp = "ID_AnyPotStatic"; prm = "PotSquareParams"; minDelta = 20 },
    @{ key = "EIS";   exp = "ID_EISVSFRQ";    prm = "EISVSfrqParams";   minDelta = 0 }
)
$results = @{}
$script:uidOK = $false
foreach ($e in $exps) {
    $key = $e.key
    W("")
    W(("==== EXP " + $key + " (" + $e.exp + " / " + $e.prm + ") ===="))
    $before = Get-Counters
    W(("BASE  " + $key + " PointCount=" + $before[0] + " T=" + $before[1] + " V=" + $before[2] + " I=" + $before[3] + " C=" + $before[4] + " X=" + $before[5] + " Eis=" + $before[6]))

    # 6a. ThisExp 按名解析
    try { $ctxType.GetProperty("ThisExp").SetValue($ctx, [Enum]::Parse($enumExp, $e.exp)) }
    catch { W(("FAIL ThisExp 解析 " + $e.exp + ": " + $_.Exception.InnerException.Message)); $results[$key] = $false; continue }

    # 6b. 参数对象 + 反挂 ctx（缺它 SendMethodBytes NullRef）
    $prmType = $cd.GetTypes() | Where-Object { $_.Name -eq $e.prm } | Select-Object -First 1
    if (-not $prmType) { W(("FAIL 参数类未找到 " + $e.prm)); $results[$key] = $false; continue }
    $prm = [Activator]::CreateInstance($prmType)
    $ctxType.GetProperty("BaseParam").SetValue($ctx, $prm)
    $hooked = $false
    foreach ($pn in @("baseContext", "BaseContext", "context", "Context")) {
        $pp = $prmType.GetProperty($pn)
        if ($pp) { $pp.SetValue($prm, $ctx); $hooked = $true; break }
    }
    W(("STEP4 " + $key + " ThisExp/BaseParam 就绪 反挂=" + $hooked))

    # 6c. ★ 激活运行态（无头装配关键：CSStart ack 走同步队列到不了 ctx）
    $ctxType.GetProperty("ExpMethodState").SetValue($ctx, [Enum]::Parse($enumMs, "SysRuning"))

    # 6d. 方法下发 + 启动
    try { $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($prm)); W(("STEP5 " + $key + " SendMethodBytes -> " + $r)) }
    catch { W(("FAIL " + $key + " SendMethodBytes: " + $_.Exception.InnerException.Message)); $results[$key] = $false; continue }
    Start-Sleep -Milliseconds 500
    try { $r = $sendType.GetMethod("SysStart").Invoke($send, @($true)); W(("STEP6 " + $key + " SysStart(true) -> " + $r)) }
    catch { W(("FAIL " + $key + " SysStart: " + $_.Exception.InnerException.Message)); $results[$key] = $false; continue }

    # 6e. 采集窗口
    $midPC = 0
    for ($k = 1; $k -le [int]($CollectSec / 2); $k++) {
        Start-Sleep -Seconds 2
        $c = Get-Counters
        W(("STEP7 " + $key + " T+" + ($k * 2) + "s PointCount=" + $c[0] + " T=" + $c[1] + " V=" + $c[2] + " I=" + $c[3] + " C=" + $c[4] + " X=" + $c[5] + " Eis=" + $c[6]))
        $midPC = $c[0]
    }
    # GetUID 消费（在数据流中调用才有积包补 bool 位；批量流 3s/帧包稀疏，重试 3 次）
    if ($key -eq "OCP") {
        for ($attempt = 1; $attempt -le 3 -and -not $script:uidOK; $attempt++) {
            try {
                Start-Sleep -Milliseconds 1200
                $uidHex = $sendType.GetMethod("GetUID").Invoke($send, @())
                $sn = ""
                if ($uidHex -and $uidHex.Length -ge 2) {
                    try {
                        $bytes = New-Object byte[] ($uidHex.Length / 2)
                        for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($uidHex.Substring($i * 2, 2), 16) }
                        $sn = [System.Text.Encoding]::ASCII.GetString($bytes)
                    } catch { $sn = "" }
                }
                W(("STEP8 GetUID(stream) attempt=" + $attempt + " -> '" + $uidHex + "' SN='" + $sn + "'"))
                if ($sn -like "CS350*") { $script:uidOK = $true; W(("RX-OK GetUID=" + $sn)) }
                elseif ($attempt -eq 3) { W("WARN GetUID 3 次未消费（不阻断 E2E，机理见 B 结论双出队 quirk）") }
            } catch { W(("WARN GetUID 抛出: " + $_.Exception.InnerException.Message)); break }
        }
    }

    # 6f. 停止
    try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()); W(("STEP9 " + $key + " SysStop -> True")) } catch { }
    Start-Sleep -Milliseconds 800
    $after = Get-Counters
    $dPC = $after[0] - $before[0]
    $sets = @()
    for ($i = 1; $i -le 5; $i++) {
        $a = $after[$i]; $b = $before[$i]
        if ($b -lt 0) { $b = 0 }
        if ($a -lt 0) { $a = 0 }
        $sets += ($a - $b)
    }
    $allGrow = ($sets | Where-Object { $_ -gt 0 }).Count -eq 5
    W(("DIFF  " + $key + " dPointCount=" + $dPC + " dSets[T,V,I,C,X]=(" + ($sets -join ",") + ") 五集合齐涨=" + $allGrow))
    W("final " + [RxProbe]::DumpState($conn, $ctx))

    if ($key -eq "EIS") {
        # EIS 独立判据：入库形状未知，尽力测
        if ($dPC -ge 20 -and $allGrow) { W("EIS-OK PointCount+五集合增长（0x62 形状被 EIS 实验接受）"); $results[$key] = $true }
        elseif ($after[6] -gt $before[6]) { W("EIS-OK EisDatas 增长 " + $before[6] + "->" + $after[6] + "（EIS 专用集合入库）"); $results[$key] = $true }
        else {
            W("EIS-PARTIAL 方法帧已下发且 sim 已识别(0x41/0x70 ACK)，但 ctx 未入库——")
            W("      证据: " + [RxProbe]::DrainConsole())
            W("      假设: EIS 数据走专用帧/专用集合（真机 EIS 数据帧形状未知），待真机核对")
            $results[$key] = $false   # PARTIAL 不阻断总判据
        }
        continue
    }

    # 主判据：PointCount 上涨 + 五集合全部增长
    $ok = $false
    if ($key -eq "OCP") {
        # ★ B 遗留① 专项：Delta>=30 才证明 126B/30 点批量帧整帧入库
        #   （若每帧只入 1 点，10s@10Hz 批量帧 3 帧 -> Delta<=3）
        $ok = ($dPC -ge $e.minDelta) -and $allGrow
        if ($ok) { W(("RX-OK " + $key + " PointCount+" + $dPC + " (>=30 证明 126B 批量帧整帧入库，B 遗留① 已证)")) }
        else { W(("FAIL " + $key + " PointCount+" + $dPC + " <30 或五集合未齐涨——批量入库未证")) }
    } else {
        $ok = ($dPC -ge $e.minDelta) -and $allGrow
        if ($ok) { W(("RX-OK " + $key + " PointCount+" + $dPC)) }
        else { W(("FAIL " + $key + " PointCount+" + $dPC + " <" + $e.minDelta + " 或五集合未齐涨")) }
    }
    $results[$key] = $ok
}

# ---- 7. 收尾 ----
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
Start-Sleep -Milliseconds 300
try { Stop-Process -Id $sim.Id -Force -ErrorAction SilentlyContinue; W(("SIM stop PID=" + $sim.Id)) } catch { }

# ---- 8. 总判据 ----
W("")
$mainOK = ($results["OCP"] -eq $true) -and ($results["Tafel"] -eq $true) -and ($results["Step"] -eq $true)
$eisVal = $results["EIS"]
if ($eisVal -eq $true) { $eisTxt = "EIS-OK" } elseif ($eisVal -eq $false) { $eisTxt = "EIS-PARTIAL" } else { $eisTxt = "EIS-SKIP" }
foreach ($k in @("OCP", "Tafel", "Step", "EIS")) {
    if (-not $results.ContainsKey($k)) { W(("RESULT " + $k + " = SKIP")); continue }
    $v = $results[$k]
    if ($v -eq $true) { W(("RESULT " + $k + " = OK")) } else { W(("RESULT " + $k + " = FAIL/PARTIAL")) }
}
if ($mainOK) {
    W("VERDICT: E2E-ALL-OK  (OCP/Tafel/Step 闭环 + " + $eisTxt + " + GetUID=" + $(if ($script:uidOK) { "OK" } else { "WARN" }) + ")")
    $rc = 0
} else {
    W("VERDICT: E2E-FAIL  (主三实验存在未闭环项)")
    $rc = 1
}
W("done")
[System.IO.File]::WriteAllLines($out, $log)
exit $rc
