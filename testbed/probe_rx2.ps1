# probe_rx2.ps1 -- RX 第二轮：查 ctx.IsDemoMode / 自动接线委托身份 / 直调 MAdd / 状态机条件
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_rx2.log"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s); Write-Host $s }

Add-Type -TypeDefinition (Get-Content "D:\deepseek\cspilot-parasite\testbed\rxprobe_helper.cs" -Raw) `
    -ReferencedAssemblies @("System.dll","System.Core.dll","D:\sci\MDI Jade 9\CSStudio6.Connect.dll") -ErrorAction Stop

$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
[RxProbe]::WireLog($conn)

$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
[void]$mOpen.Invoke($conn, @("COM90"))
W(("Open(COM90) IsOpen=" + $connType.GetMethod("IsOpen").Invoke($conn, @())))
[void]$connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @())

$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)

# ---- ctx 开关字段全 dump（SetConnect 前） ----
function DumpFlags($tag) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($pn in @("IsDemoMode","IsSilentMode","IsBusy","MaxDataCount","UserClickStop","ComName","IsMultiChannelMode","IsClearNextDataFlag","WaitrtPoint")) {
        try {
            $pp = $ctxType.GetProperty($pn)
            if ($pp) { $v = $pp.GetValue($ctx, $null); [void]$sb.Append($pn).Append('=').Append($v).Append(' ') }
        } catch { [void]$sb.Append($pn).Append('=ERR ') }
    }
    W(($tag + " " + $sb.ToString()))
}
DumpFlags("FLAGS-beforeSetConnect:")
$cdm = $connType.GetProperty("IsDemoMode")
if ($cdm) { W(("conn.IsDemoMode=" + $cdm.GetValue($conn, $null))) }

$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))

# ---- 自动接线委托身份 ----
$pi = $connType.GetProperty("OnPackReceive")
$cur = $pi.GetValue($conn, @())
if ($null -ne $cur) {
    W(("auto-wired delegate: Target=" + $cur.Target + "  TargetType=" + $(if ($cur.Target) { $cur.Target.GetType().FullName } else { "<null>" }) + "  Method=" + $cur.Method.Name))
    $sameAsCtx = $false
    try {
        $mCtx = $ctxType.GetMethod("PackReceive")
        $sameAsCtx = ($cur.Target -eq $ctx -and $cur.Method.Equals($mCtx))
    } catch { }
    W(("  -> 指向 ctx.PackReceive? " + $sameAsCtx))
} else {
    W("SetConnect 后 OnPackReceive=NULL")
    [void][RxProbe]::WireReceive($conn, $ctx)
    W("手动接线完成")
}

DumpFlags("FLAGS-afterSetConnect:")

# ---- 实验上下文 ----
$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
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

# ---- 合成帧直调 DataItem.MAdd（存储层单元测试） ----
$di = $ctxType.GetProperty("DataItem").GetValue($ctx, $null)
if ($di) {
    $diType = $di.GetType()
    $madd = $diType.GetMethods() | Where-Object { $_.Name -eq "MAdd" } | Select-Object -First 1
    W(("DataItem.MAdd 签名: " + $madd.ToString()))
    try {
        [void]$madd.Invoke($di, @([ulong]1, 0.0, -0.139, 0.0, 0.0))
        W("MAdd(1,0,-0.139,0,0) 直调 OK")
    } catch {
        $inner = $_.Exception.InnerException
        W(("MAdd 直调失败: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message })))
    }
    W("UNIT-MAdd dump: " + [RxProbe]::DumpState($conn, $ctx))
}

# ---- 合成帧走 ctx.PackReceive（此时 ThisExp=ID_OCP 已设） ----
$payload = [System.BitConverter]::GetBytes([float](-0.139))
W("UNIT-inject: " + [RxProbe]::InjectToCtx($ctx, 0x68, $payload))
W("UNIT-inject dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- IsDemoMode 若为 true：关掉再试 ----
$ctxDemo = $ctxType.GetProperty("IsDemoMode")
if ($ctxDemo) {
    $dv = $ctxDemo.GetValue($ctx, $null)
    if ($dv -eq $true) {
        W("ctx.IsDemoMode=true -> 设为 false 后重试注入")
        $ctxDemo.SetValue($ctx, $false)
        W("UNIT-inject2: " + [RxProbe]::InjectToCtx($ctx, 0x68, $payload))
        W("UNIT-inject2 dump: " + [RxProbe]::DumpState($conn, $ctx))
    }
}

# ---- StartCheckThread 试试 ----
try { $ctxType.GetMethod("StartCheckThread").Invoke($ctx, @()); W("StartCheckThread OK") } catch { W(("StartCheckThread 失败: " + $_.Exception.InnerException.Message)) }

# ---- 空闲 GetUID ×2（模拟器 verbose 日志可对照 TX 是否出门、应答是否回） ----
try {
    $uid1 = $sendType.GetMethod("GetUID").Invoke($send, @())
    W(("GetUID#1 -> '" + $uid1 + "'"))
} catch { $inner=$_.Exception.InnerException; W(("GetUID#1 抛出: " + $(if ($inner) { $inner.Message }))) }
try {
    $uid2 = $sendType.GetMethod("GetUID").Invoke($send, @())
    W(("GetUID#2 -> '" + $uid2 + "'"))
} catch { $inner=$_.Exception.InnerException; W(("GetUID#2 抛出: " + $(if ($inner) { $inner.Message }))) }
W("after GetUID dump: " + [RxProbe]::DumpState($conn, $ctx))

# ---- 真实链路 ----
try {
    $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp))
    W(("SendMethodBytes -> " + $r))
} catch { $inner=$_.Exception.InnerException; W(("SendMethodBytes 抛出: " + $(if ($inner) { $inner.Message }))) }
Start-Sleep -Seconds 2
W("after method dump: " + [RxProbe]::DumpState($conn, $ctx))

try {
    $r = $sendType.GetMethod("SysStart").Invoke($send, @($true))
    W(("SysStart -> " + $r))
} catch { $inner=$_.Exception.InnerException; W(("SysStart 抛出: " + $(if ($inner) { $inner.Message }))) }
Start-Sleep -Seconds 5
W("T+5s dump: " + [RxProbe]::DumpState($conn, $ctx))
Start-Sleep -Seconds 5
W("T+10s dump: " + [RxProbe]::DumpState($conn, $ctx))

try { [void]$sendType.GetMethod("SysStop").Invoke($send, @()) } catch { }
Start-Sleep -Seconds 1
W("final dump: " + [RxProbe]::DumpState($conn, $ctx))
W("---- tail ----")
W([RxProbe]::Tail(30))
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
