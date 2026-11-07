<#
emergency_stop.ps1 —— 纯代码紧急停止 CS350M 工作站（0x32 CSStop 直发设备）。

用途：runner 崩溃/被杀后实验仍在跑时的紧急停止（此时软件已关、COM16 空闲）。
用法：powershell -File emergency_stop.ps1 [-Port COM16]
返回：JSON 一行 {"sent":..,"ack":..,"uid":..}

#>
param([string]$Port = "COM16")
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\emergency_stop_result.json"

$need = @("CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll", "CSStudio6.MathHlp.dll",
          "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll", "CSStudio6.SysLog.dll",
          "CSStudio6.USControl.dll", "CSStudio6.NetSkin.dll", "CSStudio6.Connect.dll")
foreach ($n in $need) {
    $p = Join-Path $dir $n
    if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } }
}

$res = New-Object System.Collections.ArrayList
function J($k, $v) { [void]$res.Add('"' + $k + '": ' + $v) }

# 1) 连接（软件已关 → COM16 空闲）
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
$opened = $mOpen.Invoke($conn, @($Port))
J "opened" ($opened.ToString().ToLower())

# 2) BaseContext + ExpComSend
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()

# 3) SysStop（0x32 CSStop）——设备收到即停
$sysStop = $sendType.GetMethod("SysStop")
$ack = $sysStop.Invoke($send, @())
Start-Sleep -Milliseconds 800
J "sysstop_ack" ($ack.ToString().ToLower())

# 4) 再发一发 GetUID 探活（可选诊断）
try {
    $uidM = $sendType.GetMethod("GetUID")
    $uid = $uidM.Invoke($send, @())
    J "uid" ('"' + ($uid -replace '"', '') + '"')
} catch { }

try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
J "done" "true"
[System.IO.File]::WriteAllText($out, "{" + ($res -join ", ") + "}")
Write-Output ("{" + ($res -join ", ") + "}")
