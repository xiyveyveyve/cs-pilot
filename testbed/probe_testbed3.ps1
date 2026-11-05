# probe_testbed2.ps1 -- 纯代码协议测试床 v2
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

$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)

$opened = $false
try {
    $mOpen1 = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
    $r1 = $mOpen1.Invoke($conn, @("COM90"))
    W(("1) Open(CNCA0) -> " + $r1 + "  IsOpen=" + $conn.IsOpen()))
    $opened = ($r1 -eq $true)
    if (-not $opened) {
        $mOpen2 = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 2 } | Select-Object -First 1
        $r2 = $mOpen2.Invoke($conn, @("COM90", [int]115200))
        W(("   重试 Open(CNCA0,115200) -> " + $r2 + "  IsOpen=" + $conn.IsOpen()))
        $opened = ($r2 -eq $true)
    }
} catch {
    W(("1) Open 异常: " + $_.Exception.InnerException.Message))
}

$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
try { $ctxType.GetMethod("InitCom").Invoke($ctx, @("COM90")) } catch { }
W(("2) SetConnect/InitCom 完成"))

$send = $ctx.ExpComSend
$sendType = $send.GetType()

if ($opened) {
    try {
        $uid = $sendType.GetMethod("GetUID").Invoke($send, @())
        W(("3) GetUID() -> '" + $uid + "'"))
    } catch {
        W(("3) GetUID 抛出: " + $_.Exception.InnerException.Message))
    }
    try {
        $pt = $sendType.GetMethod("GetPstType").Invoke($send, @())
        W(("4) GetPstType() -> '" + $pt + "'"))
    } catch {
        W(("4) GetPstType 抛出: " + $_.Exception.InnerException.Message))
    }
    $cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
    $ocpType = $cd.GetTypes() | Where-Object { $_.Name -eq "OcpParams" } | Select-Object -First 1
    $ocp = [Activator]::CreateInstance($ocpType)
    try {
        $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($ocp))
        W(("5) SendMethodBytes(OcpParams) -> " + $r))
    } catch {
        W(("5) SendMethodBytes 抛出: " + $_.Exception.InnerException.Message))
    }
    try {
        $r = $sendType.GetMethod("SysStart").Invoke($send, @($true))
        W(("6) SysStart(True) -> " + $r))
        Start-Sleep -Seconds 6
        W(("   6s 后 PointCount=" + $ctx.PointCount + " StartSample=" + $ctx.StartSample + " State=" + $ctx.ExpMethodState))
        $r2 = $sendType.GetMethod("SysStop").Invoke($send, @())
        W(("   SysStop() -> " + $r2))
        Start-Sleep -Seconds 1
        W(("   停后 PointCount=" + $ctx.PointCount))
    } catch {
        W(("6) SysStart/Stop 抛出: " + $_.Exception.InnerException.Message))
    }
} else {
    W("!! 串口没开成，跳过协议测试")
}

try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("7) done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
