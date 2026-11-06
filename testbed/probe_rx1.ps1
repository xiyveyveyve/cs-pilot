# probe_rx1.ps1 -- RX 收包入库第一轮：接线 OnPackReceive→ctx.PackReceive + 合成帧单元测试 + GetUID
# 前置：simdevice 已在 CNCB0 运行（扮演 CS350M），COM90 别名已建
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_rx1.log"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

# ---- C# 助手（引用 Connect.dll，强类型挂委托） ----
try {
    Add-Type -TypeDefinition (Get-Content "D:\deepseek\cspilot-parasite\testbed\rxprobe_helper.cs" -Raw) `
        -ReferencedAssemblies @("System.dll","System.Core.dll","D:\sci\MDI Jade 9\CSStudio6.Connect.dll") -ErrorAction Stop
    W("Add-Type RxProbe OK")
} catch {
    W(("Add-Type FAILED: " + $_.Exception.Message))
    if ($_.Exception.InnerException) { W(("  inner: " + $_.Exception.InnerException.Message)) }
    [System.IO.File]::WriteAllLines($out, $log); exit 1
}

# ---- 加载程序集 ----
$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
[RxProbe]::WireLog($conn)
W("WireLog OK")

# ---- 开口 + 接收线程 ----
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
[void]$mOpen.Invoke($conn, @("COM90"))
$isOpen = $connType.GetMethod("IsOpen").Invoke($conn, @())
W(("Open(COM90) -> IsOpen=" + $isOpen))
if (-not $isOpen) { W("端口没开，退出"); [System.IO.File]::WriteAllLines($out, $log); exit 2 }
[void]$connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @())
W("CheckPackReceiveThread OK")

# ---- BaseContext ----
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
W(("new BaseContext OK type=" + $ctxType.FullName))

# ---- 合成帧单元测试（SetConnect 之前）：ctx.PackReceive 能否直接入库 ----
$payload = [System.BitConverter]::GetBytes([float](-0.139))
W("UNIT1(before SetConnect): " + [RxProbe]::InjectToCtx($ctx, 0x68, $payload))
W("UNIT1 dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- SetConnect + 检查是否自动接线 ----
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
$pi = $connType.GetProperty("OnPackReceive")
$cur = $pi.GetValue($conn, @())
W(("after SetConnect: OnPackReceive=" + $(if ($null -eq $cur) { "NULL（需手动接线）" } else { "SET（SetConnect 自动接线了）" })))
$wireRet = [RxProbe]::WireReceive($conn, $ctx)
W(("WireReceive -> " + $wireRet))

# ---- 实验上下文 ----
$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
if ($enumExp) {
    $ocpVal = [Enum]::Parse($enumExp, "ID_OCP")
    $ctxType.GetProperty("ThisExp").SetValue($ctx, $ocpVal)
    W(("ThisExp -> " + $ocpVal))
}
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
$ocpType = $cd.GetTypes() | Where-Object { $_.Name -eq "OcpParams" } | Select-Object -First 1
$ocp = [Activator]::CreateInstance($ocpType)
$ctxType.GetProperty("BaseParam").SetValue($ctx, $ocp)
foreach ($pn in @("baseContext","BaseContext","context","Context")) {
    $pp = $ocpType.GetProperty($pn)
    if ($pp) { $pp.SetValue($ocp, $ctx); W(("  ocp." + $pn + " <- ctx")) }
}

$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()
W("ExpComSendClass wired")

# ---- 合成帧单元测试 2（全上下文就绪后） ----
W("UNIT2(after full setup): " + [RxProbe]::InjectToCtx($ctx, 0x68, $payload))
W("UNIT2 dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- GetUID 应答测试（模拟器应答 SN=CS350M24030650） ----
try {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $uid = $sendType.GetMethod("GetUID").Invoke($send, @())
    $sw.Stop()
    W(("GetUID -> '" + $uid + "' (" + $sw.ElapsedMilliseconds + " ms)"))
} catch {
    $inner = $_.Exception.InnerException
    W(("GetUID 抛出: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message })))
}
W("GetUID dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- 真实链路：SendMethodBytes → 模拟器 0x51 进 OCP 模式推 0x68 ----
try {
    $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp))
    W(("SendMethodBytes(OcpParams) -> " + $r))
} catch {
    $inner = $_.Exception.InnerException
    W(("SendMethodBytes 抛出: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message })))
}

Start-Sleep -Seconds 2
W("after method dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- SysStart ----
try {
    $r = $sendType.GetMethod("SysStart").Invoke($send, @($true))
    W(("SysStart -> " + $r))
} catch {
    $inner = $_.Exception.InnerException
    W(("SysStart 抛出: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message })))
}
Start-Sleep -Seconds 5
W("T+5s dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- PointCount 未涨的补救尝试：StartSample=true ----
$pc1 = [RxProbe]::DumpState($conn, $ctx)
if ($pc1 -match "PointCount=0 ") {
    W("PointCount==0，尝试 StartSample=true 后再 SysStart")
    $ctxType.GetProperty("StartSample").SetValue($ctx, $true)
    try { $r = $sendType.GetMethod("SysStart").Invoke($send, @($true)); W(("SysStart#2 -> " + $r)) } catch { }
    Start-Sleep -Seconds 5
    W("T+10s dump: " + [RxProbe]::DumpState($conn, $ctx))
}

# ---- GetUID 复测（实验已起步后的应答路径） ----
try {
    $uid2 = $sendType.GetMethod("GetUID").Invoke($send, @())
    W(("GetUID#2 -> '" + $uid2 + "'"))
} catch { }

# ---- 收尾 ----
try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()) } catch { }
Start-Sleep -Seconds 1
W("final dump: " + [RxProbe]::DumpState($conn, $ctx))
W("---- OnPackLog tail ----")
W([RxProbe]::Tail(60))
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
