# probe_rx3.ps1 -- RX 第三轮：Console 捕获 + 全数据命令码 sweep + MAdd 直调 + GetUID 队列抢占假设
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_rx3.log"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

Add-Type -TypeDefinition (Get-Content "D:\deepseek\cspilot-parasite\testbed\rxprobe_helper.cs" -Raw) `
    -ReferencedAssemblies @("System.dll","System.Core.dll","D:\sci\MDI Jade 9\CSStudio6.Connect.dll","D:\sci\MDI Jade 9\CSStudio6.BaseInterface.dll") -ErrorAction Stop

$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

[RxProbe]::CaptureConsole()
W("console captured")

$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
[RxProbe]::WireLog($conn)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
[void]$mOpen.Invoke($conn, @("COM90"))
W(("Open(COM90) IsOpen=" + $connType.GetMethod("IsOpen").Invoke($conn, @())))
[void]$connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @())

$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))

$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
$ctxType.GetProperty("ThisExp").SetValue($ctx, [Enum]::Parse($enumExp, "ID_OCP"))
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
W("setup done")

# ---- UNIT-A: MAdd 直调（经 IDataItem 接口） ----
W("UNIT-MAdd: " + [RxProbe]::DirectMAdd($ctx, [UInt64]1, 0.5, -0.139, 1.2e-3, 0.0))
W("UNIT-MAdd dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- UNIT-B: StartSample=true 后全命令码 sweep ----
$ctxType.GetProperty("StartSample").SetValue($ctx, $true)
$cmds = @(
    @{c=0x30; n="CSStart-ack";     d=$null},
    @{c=0x60; n="CSDataE-1f";      d=[float](-0.5)},
    @{c=0x61; n="CSDataI-1f";      d=[float](1.5e-3)},
    @{c=0x62; n="CSDataEI-2f";     d=$null},
    @{c=0x63; n="CSDataEIS-2f";    d=$null},
    @{c=0x67; n="CSDataCY-1f";     d=[float]0.25},
    @{c=0x68; n="CSDataOCP-1f";    d=[float](-0.6)},
    @{c=0x69; n="CSDataWait-1f";   d=[float]0.7},
    @{c=0x71; n="StartCellYWGet";  d=[byte]1},
    @{c=0x72; n="CSExpStop-ack";   d=$null}
)
foreach ($e in $cmds) {
    if ($e.c -eq 0x62) { $payload = [System.BitConverter]::GetBytes([float](-0.5)) + [System.BitConverter]::GetBytes([float](1.5e-3)) }
    elseif ($e.c -eq 0x63) { $payload = [System.BitConverter]::GetBytes([float]1000.0) + [System.BitConverter]::GetBytes([float](2.5e-3)) }
    elseif ($null -eq $e.d) { $payload = $null }
    elseif ($e.d -is [byte]) { $payload = [byte[]]@($e.d) }
    else { $payload = [System.BitConverter]::GetBytes([float]$e.d) }
    W(("SWEEP cmd={0:X2} {1}: {2}" -f $e.c, $e.n, [RxProbe]::InjectToCtx($ctx, [byte]$e.c, $payload)))
    W(("SWEEP cmd={0:X2} dump: {1}" -f $e.c, [RxProbe]::DumpState($conn, $ctx)))
}

# ---- 真实链路（模拟器仍推 0x68，预期不涨；随后 GetUID 队列抢占测试） ----
try {
    $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp))
    W(("SendMethodBytes -> " + $r))
} catch { $inner=$_.Exception.InnerException; W(("SendMethodBytes 抛出: " + $(if ($inner) { $inner.Message }))) }
Start-Sleep -Seconds 2
W("after method dump: " + [RxProbe]::DumpState($conn, $ctx))

try { $r = $sendType.GetMethod("SysStart").Invoke($send, @($true)); W(("SysStart -> " + $r)) } catch { }
Start-Sleep -Seconds 3
W("stream dump: " + [RxProbe]::DumpState($conn, $ctx))

# GetUID 抢占测试：清队列 → 立即 GetUID（bool 消费一个 0x68，package 应拿到 0x17 应答）
W("GetUID-primed: " + [RxProbe]::ClearQueue($conn))
try {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $uid = $sendType.GetMethod("GetUID").Invoke($send, @())
    $sw.Stop()
    W(("GetUID(primed) -> '" + $uid + "' (" + $sw.ElapsedMilliseconds + " ms)"))
} catch { $inner=$_.Exception.InnerException; W(("GetUID 抛出: " + $(if ($inner) { $inner.Message }))) }
W("GetUID-primed dump: " + [RxProbe]::DumpState($conn, $ctx))

# 再来一次不清队列（队列里有积压 0x68）
try {
    $uid2 = $sendType.GetMethod("GetUID").Invoke($send, @())
    W(("GetUID(backlog) -> '" + $uid2 + "'"))
} catch { }

try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()) } catch { }
Start-Sleep -Seconds 1
W("final dump: " + [RxProbe]::DumpState($conn, $ctx))
W("---- tail(40) ----")
W([RxProbe]::Tail(40))
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
