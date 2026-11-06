# probe_send3.ps1 (ASCII only) -- send one experiment's method bytes via the working recipe.
# Usage: powershell -File probe_send3.ps1 -Exp tafel|eis|step [-SendMode bytes|eissetup] [-Step1On]
param([string]$Exp = "tafel", [string]$SendMode = "bytes", [switch]$Step1On, [switch]$MidOn, [switch]$EisVar, [switch]$EisVar2)
$ErrorActionPreference = "Continue"

$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\testbed_send3_" + $Exp + ".log"
$log = New-Object System.Collections.ArrayList
function W($s) {
  $line = ([DateTime]::Now.ToString("HH:mm:ss.fff")) + " [" + [DateTimeOffset]::Now.ToUnixTimeMilliseconds() + "] " + $s
  [void]$log.Add($line)
  Write-Output $line
}

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))

# ---- experiment-specific setup (all enums/classes resolved BY NAME, never by number)
$enumName  = @{ tafel = "ID_PotDynamic"; eis = "ID_EISVSFRQ"; step = "ID_AnyPotStatic" }[$Exp]
$className = @{ tafel = "PotDynamicParams"; eis = "EISVSfrqParams"; step = "PotSquareParams" }[$Exp]
if (-not $enumName) { W("unknown Exp " + $Exp); [System.IO.File]::WriteAllLines($out, $log); exit 2 }

$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
$expVal = [Enum]::Parse($enumExp, $enumName)
W("ThisExp enum " + $enumName + " = " + [int]$expVal)

# ---- connection
$connType = $connAsm = $null
$connAsm = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.Connect.dll"))
$connType = $connAsm.GetType("CSStudio6.Connect.Com.SerialConnect")
$conn = [Activator]::CreateInstance($connType)
$mOpen = $connType.GetMethods() | Where-Object { $_.Name -eq "Open" -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
$r = $mOpen.Invoke($conn, @("COM91"))
W("SerialConnect.Open(COM91) -> " + $r)
if (-not $r) { W("FATAL: open failed"); [System.IO.File]::WriteAllLines($out, $log); exit 1 }
try { $connType.GetMethod("CheckPackReceiveThread").Invoke($conn, @()) ; W("CheckPackReceiveThread ok") } catch { W("CheckPackReceiveThread threw: " + $_.Exception.Message) }

# ---- context
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
$ctx = [Activator]::CreateInstance($ctxType)
$ctxType.GetMethod("SetConnect").Invoke($ctx, @($conn))
$ctxType.GetProperty("ThisExp").SetValue($ctx, $expVal)
W("ctx.ThisExp set")

# ---- param object
$pt = $cd.GetTypes() | Where-Object { $_.Name -eq $className } | Select-Object -First 1
$prm = [Activator]::CreateInstance($pt)
W("param class " + $pt.FullName)

function SetP([string]$name, $val) {
  try {
    $pp = $pt.GetProperty($name)
    if (-not $pp) { W("  SET " + $name + " : property not found"); return }
    $t = $pp.PropertyType
    if ($t.Name -eq "Single") { $val = [single][double]($val -as [double]) }
    elseif ($t.Name -eq "Double") { $val = [double]$val }
    elseif ($t.Name -eq "Int32") { $val = [int]$val }
    elseif ($t.Name -eq "UInt16") { $val = [uint16]$val }
    elseif ($t.Name -eq "UInt32") { $val = [uint32]$val }
    elseif ($t.Name -eq "Byte") { $val = [byte]$val }
    elseif ($t.Name -eq "Boolean") { $val = [bool]$val }
    $pp.SetValue($prm, $val, $null)
    W("  SET " + $name + " = " + $val)
  } catch { W("  SET " + $name + " threw: " + $_.Exception.InnerException.Message) }
}
function SetVs([string]$name, [string]$val) {
  try {
    $pp = $pt.GetProperty($name)
    $enumT = $pp.PropertyType
    $v = [Enum]::Parse($enumT, $val)
    $pp.SetValue($prm, $v, $null)
    W("  SET " + $name + " = " + $val + " (" + [int]$v + ")")
  } catch { W("  SET " + $name + " threw: " + $_.Exception.InnerException.Message) }
}

if ($Exp -eq "tafel") {
  SetP "InitE"   "-0.05"
  SetP "FinalE"  "0.05"
  SetP "ScanRate" "0.5"
  SetP "MidEOneEnable" $false
  SetP "MidETwoEnable" $false
  SetVs "InitEVsOcp"  "vsOCP"
  SetVs "MidEOneVsOcp" "vsOCP"
  SetVs "MidETwoVsOcp" "vsOCP"
  SetVs "FinalEVsOcp" "vsOCP"
  # Frq modes (runtime-proven): IsFrq=true -> Frq=SampleFrq*BaseFreqRate ; IsFrq=false -> Frq=BaseFreqRate/SampleInter
  # GUI convention Frq=ScanRate(mV/s)*2 -> SampleFrq=1.0 for ScanRate=0.5
  SetP "SampleInter" "1.0"
  SetP "BaseFreqRate" "1.0"
  SetP "ScanRateUnit" 0
  SetP "IsFrq" $true
  SetP "SampleFrq" "1.0"
  if ($MidOn) {
    SetP "MidEOneEnable" $true
    SetP "MidEOne" "0.1"
    SetP "MidETwoEnable" $true
    SetP "MidETwo" "0.2"
  }
}
if ($Exp -eq "eis") {
  SetP "SineAmp"   "10.0"
  SetP "Init_Fre"  "1000.0"
  SetP "Final_Fre" "0.1"
  SetP "TenTwice"  "10.0"
  SetVs "VsOcp" "vsOCP"
  SetP "IsFrq" $true
  if ($EisVar) {
    # diff-run variant: make as many fields distinctive as possible
    SetP "SineBias" "0.25"
    SetP "TenTwice" "20.0"
    SetP "TestPoints" 123
    SetP "Integral_Time" 77
    SetP "Integral_Period" 78
    SetP "DelayTime" 88
    SetP "ParamsType" 1
    SetP "Mode" 2
    SetP "MeasurementSpeedMode" 3
    SetP "ADS_EN" 1
    SetP "ADS_Fre" "1234.0"
    SetP "Filter_Fre" "99.0"
    SetP "PrePolTime" 66
    SetP "AttenualSet" 4
  }
  if ($EisVar2) {
    # single-change diff: pin the 0x41 byte that went 1 -> 0 in the EisVar run
    SetP "IsAutoDelayTime" $false
  }
}
if ($Exp -eq "step") {
  SetP "Initial_E" "0.01"
  SetP "Final_E"   "-0.01"
  SetP "InitialTime" "2.0"
  SetP "FinalTime" "100.0"
  SetP "Cycles"    20
  if ($Step1On) {
    SetP "Step1Enable" $true
    SetP "Step1" "0.03"
    SetP "Time1" "50.0"
  }
  SetVs "VsOcp" "vsOCP"
  SetP "IsFrq" $true
}
SetP "ExpType" $expVal   # property type is Experiment enum; SetValue with boxed enum value works via reflection? try
W("---- GetSaveString BEFORE send ----")
try { W($prm.GetType().GetMethod("GetSaveString").Invoke($prm, @())) } catch { W("GetSaveString threw: " + $_.Exception.InnerException.Message) }
W("---- end savestring ----")

# baseContext back-hook (SendMethodBytes NullRef fix)
$hooked = $false
foreach ($pn in @("baseContext","BaseContext","context","Context")) {
  $pp = $pt.GetProperty($pn)
  if ($pp) { try { $pp.SetValue($prm, $ctx, $null); W("param." + $pn + " <- ctx"); $hooked = $true } catch { W("param." + $pn + " set threw: " + $_.Exception.InnerException.Message) } }
}
W("baseContext hooked = " + $hooked)

# ctx.BaseParam <- param (recipe step; EIS override dereferences it)
try { $ctxType.GetProperty("BaseParam").SetValue($ctx, $prm, $null); W("ctx.BaseParam <- " + $className) } catch { W("ctx.BaseParam set threw: " + $_.Exception.InnerException.Message) }

# ---- send class
$sendCls = $bi.GetTypes() | Where-Object { $_.Name -eq "ExpComSendClass" } | Select-Object -First 1
$send = [Activator]::CreateInstance($sendCls, @($ctx))
$ctxType.GetMethod("set_ExpComSend").Invoke($ctx, @($send))
$sendType = $send.GetType()

W(">>> calling SendMethodBytes (mode=" + $SendMode + ")")
if ($SendMode -eq "bytes") {
  try {
    $r = $sendType.GetMethod("SendMethodBytes").Invoke($send, @($prm))
    W("SendMethodBytes(" + $className + ") -> " + $r)
  } catch {
    $inner = $_.Exception.InnerException
    W("SendMethodBytes threw: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message }))
    if ($inner -and $inner.StackTrace) { W(($inner.StackTrace -split "`n" | Select-Object -First 4) -join " | ") }
  }
} elseif ($SendMode -eq "eissetup") {
  try {
    $r = $sendType.GetMethod("SendEisSetup").Invoke($send, @($prm, $false))
    W("SendEisSetup(" + $className + ", isDev360=false) -> " + $r)
  } catch {
    $inner = $_.Exception.InnerException
    W("SendEisSetup threw: " + $(if ($inner) { $inner.Message } else { $_.Exception.Message }))
    if ($inner -and $inner.StackTrace) { W(($inner.StackTrace -split "`n" | Select-Object -First 4) -join " | ") }
  }
}

Start-Sleep -Milliseconds 500
W(">>> SysStart")
try {
  $r = $sendType.GetMethod("SysStart").Invoke($send, @($true))
  W("SysStart -> " + $r)
} catch { W("SysStart threw: " + $_.Exception.InnerException.Message) }

Start-Sleep -Seconds 6
W("PointCount=" + $ctx.PointCount + " StartSample=" + $ctx.StartSample + " State=" + $ctx.ExpMethodState)

W(">>> SysStop")
try {
  $r = $sendType.GetMethod("SysStop").Invoke($send, @())
  W("SysStop -> " + $r)
} catch { W("SysStop threw: " + $_.Exception.InnerException.Message) }
Start-Sleep -Milliseconds 800

try { $connType.GetMethod("Close").Invoke($conn, @()) ; W("conn closed") } catch { }
W("done")
[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
