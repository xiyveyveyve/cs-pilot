# probe_rx_final.ps1 -- RX 收包入库一条龙验收脚本（CS-Pilot 方案3 · Agent B）
#
# 判据（日志输出两行 RX-OK 即全通）：
#   RX-OK PointCount=N (N>=10)     -- 模拟器推 0x60 CSDataE @10Hz，PointCount 持续上涨
#   RX-OK GetUID=CS350M24030650    -- GetUID 应答被消费（流中调用，hex 解码回 ASCII）
#
# 前置（可一行起模拟器）：
#   python D:\deepseek\cspilot-parasite\testbed\make_alias2.py COM90
#   python D:\deepseek\cspilot-parasite\testbed\sim_rx.py --port CNCB0   （后台）
#
# 配方要点（全部运行期实证，见 _probe/testbed_rx1~4.log）：
#   1) probe_testbed9 工作配方（LoadFrom → Open("COM90") → CheckPackReceiveThread
#      → BaseContext.SetConnect（自动接线 OnPackReceive=ctx.PackReceive，绝不调 InitCom）
#      → ThisExp=ID_OCP → BaseParam=OcpParams+反挂 ctx → ExpComSendClass）
#   2) ★ ctx.ExpMethodState = SysRuning（公开 setter）：CSStart 的 ack 走同步队列
#      （SendReturnBoolBytes 出队即丢）到不了 ctx，无头装配必须手动置运行态；
#      置了之后 ctx.PackReceive 才会入库
#   3) ★ 模拟器 OCP 数据必须推 0x60 CSDataE（0x68 CSDataOCP 在本版 BaseContext
#      的分发表里是「未识别数据包类型：68」，真实设备 OCP 流样本也是 0x60）
#   4) GetUID 用 SendReturnPackage 双出队机理：bool 消费 1 包 + payload 再消费 1 包，
#      空闲单应答必超时；流中有积包自然补位，必须在数据流中调用
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_rx_final.log"
$log = New-Object System.Collections.ArrayList
$script:okPC = $false
$script:okUID = $false
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

# ---- C# 助手 ----
Add-Type -TypeDefinition (Get-Content "D:\deepseek\cspilot-parasite\testbed\rxprobe_helper.cs" -Raw) `
    -ReferencedAssemblies @("System.dll","System.Core.dll","D:\sci\MDI Jade 9\CSStudio6.Connect.dll","D:\sci\MDI Jade 9\CSStudio6.BaseInterface.dll") -ErrorAction Stop
[RxProbe]::CaptureConsole()

# ---- 程序集 ----
$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

# ---- 连接 ----
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
[RxProbe]::WireLog($conn)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
[void]$mOpen.Invoke($conn, @("COM90"))
$isOpen = $connType.GetMethod("IsOpen").Invoke($conn, @())
W(("STEP1 Open(COM90) -> " + $isOpen))
if (-not $isOpen) { W("FAIL: 端口未开（检查 COM90 别名 / sim_rx 是否已占 CNCB0）"); [System.IO.File]::WriteAllLines($out, $log); exit 1 }
[void]$connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @())

# ---- 上下文 ----
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
$autoWired = $connType.GetProperty("OnPackReceive").GetValue($conn, @())
W(("STEP2 SetConnect -> OnPackReceive 自动接线=" + $(if ($null -ne $autoWired) { "OK(" + $autoWired.Method.Name + ")" } else { "NULL" })))

$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
$enumMs  = $bi.GetTypes() | Where-Object { $_.Name -eq "MethodState" -and $_.IsEnum } | Select-Object -First 1
$ocpVal = [Enum]::Parse($enumExp, "ID_OCP")
$ctxType.GetProperty("ThisExp").SetValue($ctx, $ocpVal)
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
$ocpType = $cd.GetTypes() | Where-Object { $_.Name -eq "OcpParams" } | Select-Object -First 1
$ocp = [Activator]::CreateInstance($ocpType)
$ctxType.GetProperty("BaseParam").SetValue($ctx, $ocp)
foreach ($pn in @("baseContext","BaseContext","context","Context")) {
    $pp = $ocpType.GetProperty($pn)
    if ($pp) { $pp.SetValue($ocp, $ctx) }
}
$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()
W("STEP3 上下文接线完成（ThisExp=ID_OCP, BaseParam=OcpParams+反挂, ExpComSendClass）")

# ---- ★ 激活运行态（无头装配的关键缺口：CSStart ack 走队列到不了 ctx） ----
$ctxType.GetProperty("ExpMethodState").SetValue($ctx, [Enum]::Parse($enumMs, "SysRuning"))
W(("STEP4 ExpMethodState=SysRuning（数据入库的激活开关）"))

# ---- 方法下发 + 启动 ----
try { $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp)); W(("STEP5 SendMethodBytes(OcpParams) -> " + $r)) }
catch { W(("FAIL SendMethodBytes: " + $_.Exception.InnerException.Message)); [System.IO.File]::WriteAllLines($out, $log); exit 1 }
Start-Sleep -Milliseconds 500
try { $r = $sendType.GetMethod("SysStart").Invoke($send, @($true)); W(("STEP6 SysStart(true) -> " + $r)) }
catch { W(("FAIL SysStart: " + $_.Exception.InnerException.Message)); [System.IO.File]::WriteAllLines($out, $log); exit 1 }

# ---- 收包验收：PointCount 应以 ~10/s 上涨 ----
$pc0 = 0
for ($k = 1; $k -le 5; $k++) {
    Start-Sleep -Seconds 2
    $dump = [RxProbe]::DumpState($conn, $ctx)
    if ($dump -match "PointCount=(\d+)") { $script:pc = [int]$Matches[1] } else { $script:pc = 0 }
    W(("STEP7 T+" + ($k*2) + "s " + $dump))
    if ($script:pc -ge 10) { $script:okPC = $true }
}
$pc1 = $script:pc
if ($script:okPC) { W(("RX-OK PointCount=" + $pc1 + " (起始 " + $pc0 + "，10Hz×10s 预期 ~100)")) }
else { W(("FAIL PointCount=" + $pc1 + " <10")) }

# ---- 数据抽样：三个 List 的首/尾值 ----
try {
    $di = $ctxType.GetProperty("DataItem").GetValue($ctx, $null)
    $diType = $di.GetType()
    foreach ($pn in @("TimeValues","VolteValues","CurrentValues")) {
        $lst = $diType.GetProperty($pn).GetValue($di, $null)
        $n = $lst.Count
        if ($n -gt 0) {
            $fv = [Math]::Round($lst[0], 6)
            $lv = [Math]::Round($lst[$n-1], 6)
            W(("DATA " + $pn + " n=" + $n + " first=" + $fv + " last=" + $lv))
        } else { W(("DATA " + $pn + " n=0")) }
    }
} catch { W(("DATA dump 失败: " + $_.Exception.Message)) }

# ---- GetUID 验收（流中调用） ----
try {
    $uidHex = $sendType.GetMethod("GetUID").Invoke($send, @())
    $sn = ""
    if ($uidHex -and $uidHex.Length -ge 2) {
        try {
            $bytes = New-Object byte[] ($uidHex.Length / 2)
            for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($uidHex.Substring($i*2, 2), 16) }
            $sn = [System.Text.Encoding]::ASCII.GetString($bytes)
        } catch { $sn = "" }
    }
    W(("STEP8 GetUID(stream) -> '" + $uidHex + "' -> SN='" + $sn + "'"))
    if ($sn -like "CS350*") { $script:okUID = $true; W(("RX-OK GetUID=" + $sn)) }
    else { W("FAIL GetUID 应答未消费（空/不符）") }
} catch { W(("FAIL GetUID 抛出: " + $_.Exception.InnerException.Message)) }

# ---- 收尾 ----
try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()); W("STEP9 SysStop -> True") } catch { }
Start-Sleep -Milliseconds 800
W("final " + [RxProbe]::DumpState($conn, $ctx))
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }

# ---- 总判据 ----
if ($script:okPC -and $script:okUID) { W("VERDICT: RX-ALL-OK"); $rc = 0 }
else { W("VERDICT: RX-FAIL"); $rc = 1 }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
exit $rc
