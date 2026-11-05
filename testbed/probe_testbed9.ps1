﻿# probe_testbed8.ps1 -- 最后一轮：补 ThisExp/BaseParam 上下文 + 查 m_tdData
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed.txt"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s) }

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
[void]$mOpen.Invoke($conn, @("COM90"))
try { $connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @()) } catch { }

$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))

# 补实验上下文
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
W("BaseParam -> OcpParams")
# 参数对象反挂 ctx（SendMethodParams 内部要用的可能就是它）
foreach ($pn in @("baseContext","BaseContext","context","Context")) {
    $pp = $ocpType.GetProperty($pn)
    if ($pp) { $pp.SetValue($ocp, $ctx); W(("  ocp." + $pn + " <- ctx")) }
}

$mtd = $connType.GetField("m_tdData", [System.Reflection.BindingFlags]"NonPublic,Public,Instance")
W(("m_tdData(启动后) = " + $(if ($null -eq $mtd.GetValue($conn)) { "<null>（接收线程没起来）" } else { "已启动" })))

$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()

try {
    $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp))
    W(("SendMethodBytes(OcpParams) -> " + $r))
} catch {
    $inner = $_.Exception.InnerException
    $stack = ""
    if ($inner -and $inner.StackTrace) { $stack = ($inner.StackTrace -split "`n" | Select-Object -First 3) -join " | " }
    W(("SendMethodBytes 抛出: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message }) + "  @" + $stack))
}

Start-Sleep -Seconds 2
try {
    $r = $sendType.GetMethod("SysStart").Invoke($send, @($true))
    W(("SysStart -> " + $r))
    Start-Sleep -Seconds 8
    W(("PointCount=" + $ctx.PointCount + " StartSample=" + $ctx.StartSample + " State=" + $ctx.ExpMethodState))
    [void]$sendType.GetMethod("SysStop").Invoke($send, @())
} catch {
    W(("SysStart/Stop 抛出: " + $_.Exception.InnerException.Message))
}
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
