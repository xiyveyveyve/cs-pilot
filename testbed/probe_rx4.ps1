# probe_rx4.ps1 -- RX 第四轮：ExpMethodState=SysRuning + DataItem.ExpType 激活后再 sweep/stream
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_rx4.log"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

Add-Type -TypeDefinition (Get-Content "D:\deepseek\cspilot-parasite\testbed\rxprobe_helper.cs" -Raw) `
    -ReferencedAssemblies @("System.dll","System.Core.dll","D:\sci\MDI Jade 9\CSStudio6.Connect.dll","D:\sci\MDI Jade 9\CSStudio6.BaseInterface.dll") -ErrorAction Stop

$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

[RxProbe]::CaptureConsole()
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
W("setup done")

# ---- 激活：DataItem.ExpType=ID_OCP + ExpMethodState=SysRuning ----
$di = $ctxType.GetProperty("DataItem").GetValue($ctx, $null)
$diType = $di.GetType()
$ppExpType = $diType.GetProperty("ExpType")
W(("DataItem.ExpType(默认)=" + $ppExpType.GetValue($di, $null)))
$ppExpType.SetValue($di, $ocpVal)
W(("DataItem.ExpType -> " + $ocpVal))

$ppState = $ctxType.GetProperty("ExpMethodState")
$runVal = [Enum]::Parse($enumMs, "SysRuning")
$ppState.SetValue($ctx, $runVal)
W(("ExpMethodState -> " + $runVal))
W("activated dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- SysRuning 状态下 sweep（console 逐条flush） ----
$cmds = @(
    @{c=0x60; n="CSDataE-1f";   f=[float](-0.5)},
    @{c=0x61; n="CSDataI-1f";   f=[float](1.5e-3)},
    @{c=0x62; n="CSDataEI-2f";  f=$null},
    @{c=0x67; n="CSDataCY-1f";  f=[float]0.25},
    @{c=0x68; n="CSDataOCP-1f"; f=[float](-0.6)},
    @{c=0x71; n="CellYWGet-1B"; f=[byte]1}
)
foreach ($e in $cmds) {
    if ($e.c -eq 0x62) { $payload = [System.BitConverter]::GetBytes([float](-0.5)) + [System.BitConverter]::GetBytes([float](1.5e-3)) }
    elseif ($e.f -is [byte]) { $payload = [byte[]]@($e.f) }
    elseif ($null -ne $e.f) { $payload = [System.BitConverter]::GetBytes([float]$e.f) }
    else { $payload = $null }
    $rxBefore = [RxProbe]::GetCounters()
    $injectRet = [RxProbe]::InjectToCtx($ctx, [byte]$e.c, $payload)
    Start-Sleep -Milliseconds 300
    W(("SWEEP cmd={0:X2} {1}: {2}" -f $e.c, $e.n, $injectRet))
    W(("SWEEP dump: " + [RxProbe]::DumpState($conn, $ctx)))
    W(("SWEEP console-tail: " + ($rxBefore) + " || " + [RxProbe]::DrainConsole()))
}

# ---- 真实链路：SendMethodBytes + SysStart（模拟器推 0x68 @10Hz） ----
try { $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp)); W(("SendMethodBytes -> " + $r)) } catch { W(("SendMethodBytes 抛出: " + $_.Exception.InnerException.Message)) }
Start-Sleep -Seconds 1
try { $r = $sendType.GetMethod("SysStart").Invoke($send, @($true)); W(("SysStart -> " + $r)) } catch { W(("SysStart 抛出: " + $_.Exception.InnerException.Message)) }
for ($k = 1; $k -le 5; $k++) {
    Start-Sleep -Seconds 2
    W("T+$($k*2)s dump: " + [RxProbe]::DumpState($conn, $ctx))
    W("console: " + [RxProbe]::DrainConsole())
}

# ---- GetUID 复测（流中） ----
try { $uid = $sendType.GetMethod("GetUID").Invoke($send, @()); W(("GetUID(stream) -> '" + $uid + "'")) } catch { }

try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()) } catch { }
Start-Sleep -Seconds 1
W("final dump: " + [RxProbe]::DumpState($conn, $ctx))
W("console-final: " + [RxProbe]::DrainConsole())
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
