﻿﻿# probe_testbed4.ps1 -- SetConnect 后重建 ExpComSendClass（修复旧引用 NullRef）
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed.txt"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s) }

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$need = @(
    "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll", "CSStudio6.MathHlp.dll",
    "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll", "CSStudio6.SysLog.dll",
    "CSStudio6.USControl.dll", "CSStudio6.NetSkin.dll", "CSStudio6.Connect.dll"
)
foreach ($n in $need) {
    $p = Join-Path $dir $n
    if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } }
}
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))

$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
$r = $mOpen.Invoke($conn, @("COM90"))
W(("1) Open(COM90) -> " + $r))

$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
# InitCom 已跳过：实测它会按默认配置自建 SockectConnect 覆盖 SetConnect（fields 探针实证）

# 重建 ExpComSendClass（此时 ctx 里已有连接）
$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
W(("2) ExpComSendClass: " + $sendCls.FullName))
$send2 = $null
try {
    $send2 = [Activator]::CreateInstance($sendCls, @($ctx))
    W("   NEW(ctx) OK")
} catch {
    W(("   NEW(ctx) 失败: " + $_.Exception.InnerException.Message))
    try {
        $send2 = [Activator]::CreateInstance($sendCls)
        W("   NEW() OK")
    } catch {
        W(("   NEW() 也失败: " + $_.Exception.InnerException.Message))
    }
}
if ($send2) {
    $setter = $ctxType.GetMethod("set_ExpComSend")
    if ($setter) { $setter.Invoke($ctx, @($send2)); W("   ctx.set_ExpComSend OK") }
    $sendType = $send2.GetType()
    # 顺带看私有 connect 字段
    $fs = $sendType.GetFields([System.Reflection.BindingFlags]"NonPublic,Public,Instance") | Where-Object { $_.FieldType.Name -match "IConnect|BaseConnect|SerialConnect" }
    foreach ($f in $fs) {
        $v = $f.GetValue($send2)
        W(("   字段 " + $f.Name + " [" + $f.FieldType.Name + "] = " + $(if ($null -eq $v) { "<null>" } else { "已设置" })))
    }

    try {
        $uid = $sendType.GetMethod("GetUID").Invoke($send2, @())
        W(("3) GetUID() -> '" + $uid + "'"))
    } catch {
        W(("3) GetUID 抛出: " + $_.Exception.InnerException.Message))
    }
    try {
        $gsn = $sendType.GetMethods() | Where-Object { $_.Name -eq "GetSerialNumber" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
        $sn2 = $gsn.Invoke($send2, @($conn))
        W(("3b) GetSerialNumber(conn) -> '" + $sn2 + "'"))
    } catch {
        W(("3b) GetSerialNumber(conn) 抛出: " + $_.Exception.InnerException.Message))
    }
    # SendMethodBytes 也可能有带 IConnect 的重载
    foreach ($sm in $sendType.GetMethods() | Where-Object { $_.Name -match "Method|Send" }) {
        $ps = ($sm.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ","
        W(("   方法 " + $sm.Name + "(" + $ps + ")"))
    }
    $cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
    $ocpType = $cd.GetTypes() | Where-Object { $_.Name -eq "OcpParams" } | Select-Object -First 1
    $ocp = [Activator]::CreateInstance($ocpType)
    try {
        $r = $sendType.GetMethod("SendMethodBytes").Invoke($send2, @($ocp))
        W(("4) SendMethodBytes(OcpParams) -> " + $r))
    } catch {
        W(("4) SendMethodBytes 抛出: " + $_.Exception.InnerException.Message))
    }
    try {
        $r = $sendType.GetMethod("SysStart").Invoke($send2, @($true))
        W(("5) SysStart(True) -> " + $r))
        Start-Sleep -Seconds 6
        W(("   6s 后 PointCount=" + $ctx.PointCount + " State=" + $ctx.ExpMethodState))
        $r2 = $sendType.GetMethod("SysStop").Invoke($send2, @())
        W(("   SysStop() -> " + $r2))
    } catch {
        W(("5) 抛出: " + $_.Exception.InnerException.Message))
    }
}
try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("6) done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
