# probe_testbed.ps1 -- 纯代码协议测试床：BaseContext+SerialConnect(CNCA0) <-> simdevice(CNCB0)
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

# 1) 造连接
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
$opened = $connType.GetMethod("Open", @([System.String])).Invoke($conn, @("CNCA0"))
W(("1) SerialConnect.Open(CNCA0) -> " + $opened + "  IsOpen=" + $conn.IsOpen()))

# 2) 挂上 BaseContext
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$setConn = $ctxType.GetMethod("SetConnect")
$setConn.Invoke($ctx, @($conn))
W(("2) SetConnect OK; ComName=" + $ctx.ComName))
try {
    $initCom = $ctxType.GetMethod("InitCom")
    $initCom.Invoke($ctx, @("CNCA0"))
    W("   InitCom(CNCA0) OK")
} catch {
    W(("   InitCom 异常: " + $_.Exception.InnerException.Message))
}

$send = $ctx.ExpComSend
$sendType = $send.GetType()

# 3) GetUID —— 模拟器应答 SN
try {
    $uidM = $sendType.GetMethod("GetUID", @())
    $uid = $uidM.Invoke($send, @())
    W(("3) GetUID() -> '" + $uid + "'  (期望 CS350M24030650)"))
} catch {
    W(("3) GetUID 抛出: " + $_.Exception.InnerException.Message))
}

# 4) GetPstType
try {
    $ptM = $sendType.GetMethod("GetPstType", @())
    $pt = $ptM.Invoke($send, @())
    W(("4) GetPstType() -> '" + $pt + "'"))
} catch {
    W(("4) GetPstType 抛出: " + $_.Exception.InnerException.Message))
}

# 5) SendMethodBytes(OcpParams)
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))
$ocpType = $cd.GetTypes() | Where-Object { $_.Name -eq "OcpParams" } | Select-Object -First 1
$ocp = [Activator]::CreateInstance($ocpType)
try {
    $sm = $sendType.GetMethod("SendMethodBytes")
    $r = $sm.Invoke($send, @($ocp))
    W(("5) SendMethodBytes(OcpParams) -> " + $r))
} catch {
    W(("5) SendMethodBytes 抛出: " + $_.Exception.InnerException.Message))
}

# 6) SysStart -> 等 6 s 收数据 -> SysStop
try {
    $ss = $sendType.GetMethod("SysStart")
    $r = $ss.Invoke($send, @($true))
    W(("6) SysStart(True) -> " + $r))
    Start-Sleep -Seconds 6
    W(("   6s 后 ctx.PointCount=" + $ctx.PointCount + "  StartSample=" + $ctx.StartSample + "  ExpMethodState=" + $ctx.ExpMethodState))
    $sp = $sendType.GetMethod("SysStop")
    $r2 = $sp.Invoke($send, @())
    W(("   SysStop() -> " + $r2))
    Start-Sleep -Seconds 1
    W(("   停后 PointCount=" + $ctx.PointCount))
} catch {
    W(("6) SysStart/Stop 抛出: " + $_.Exception.InnerException.Message))
}

try { $connType.GetMethod("Close").Invoke($conn, @()) } catch { }
W("7) 连接已关闭")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
