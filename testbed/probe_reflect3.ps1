# probe_reflect3.ps1 (ASCII only) -- reflect param classes + enums for the 3 experiments
$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"
$out = "D:\deepseek\_probe\reflect3.txt"
$log = New-Object System.Collections.ArrayList
function W($s) { [void]$log.Add([string]$s) }

$need = @("CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.Connect.dll")
foreach ($n in $need) { $p = Join-Path $dir $n; if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } } }
$bi = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.BaseInterface.dll"))
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))

W("=== Experiment enum values ===")
$enumExp = $bi.GetTypes() | Where-Object { $_.Name -eq "Experiment" -and $_.IsEnum } | Select-Object -First 1
if ($enumExp) {
  foreach ($n in @("ID_OCP","ID_PotDynamic","ID_EISVSFRQ","ID_AnyPotStatic","ID_PotSquareWave")) {
    try { W(($n + " = " + [int][Enum]::Parse($enumExp, $n))) } catch { W(($n + " MISSING")) }
  }
} else { W("Experiment enum not found in BaseInterface") }

W("")
W("=== Param classes in CorrData (MethodParams ns) ===")
foreach ($cn in @("PotDynamicParams","EisParams","EISVSfrqParams","PotSquareParams","OcpParams")) {
  $t = $cd.GetTypes() | Where-Object { $_.Name -eq $cn } | Select-Object -First 1
  if ($t) {
    W($cn + " : FOUND  FullName=" + $t.FullName + "  Base=" + $t.BaseType.FullName)
    W("  Interfaces: " + (($t.GetInterfaces() | ForEach-Object { $_.Name }) -join ", "))
    $props = $t.GetProperties() | ForEach-Object { $_.PropertyType.Name + " " + $_.Name }
    W("  Props(" + $props.Count + "): " + ($props -join "; "))
  } else { W($cn + " : not found") }
  W("")
}

W("=== IEisParams interface ===")
$ieis = $bi.GetTypes() + $cd.GetTypes() | Where-Object { $_.Name -eq "IEisParams" } | Select-Object -First 1
if ($ieis) {
  W("IEisParams FullName=" + $ieis.FullName)
  $props = $ieis.GetProperties() | ForEach-Object { $_.PropertyType.Name + " " + $_.Name }
  W("  Props(" + $props.Count + "): " + ($props -join "; "))
} else { W("IEisParams not found") }

W("")
W("=== IDeviceParams interface ===")
$idp = $bi.GetTypes() + $cd.GetTypes() | Where-Object { $_.Name -eq "IDeviceParams" } | Select-Object -First 1
if ($idp) {
  W("IDeviceParams FullName=" + $idp.FullName)
  $props = $idp.GetProperties() | ForEach-Object { $_.PropertyType.Name + " " + $_.Name }
  W("  Props(" + $props.Count + "): " + ($props -join "; "))
} else { W("IDeviceParams not found") }

W("")
W("=== IBaseParams interface ===")
$ibp = $bi.GetTypes() + $cd.GetTypes() | Where-Object { $_.Name -eq "IBaseParams" } | Select-Object -First 1
if ($ibp) {
  W("IBaseParams FullName=" + $ibp.FullName)
  $props = $ibp.GetProperties() | ForEach-Object { $_.PropertyType.Name + " " + $_.Name }
  W("  Props(" + $props.Count + "): " + ($props -join "; "))
} else { W("IBaseParams not found") }

W("")
W("=== BaseContext props/methods of interest ===")
$ctxType = $bi.GetTypes() | Where-Object { $_.Name -eq "BaseContext" -and -not $_.IsAbstract } | Select-Object -First 1
if ($ctxType) {
  foreach ($pn in @("ThisExp","BaseParam","ExpComSend","PointCount")) {
    $pp = $ctxType.GetProperty($pn)
    if ($pp) { W("  prop " + $pn + " : " + $pp.PropertyType.FullName) } else { W("  prop " + $pn + " : NONE") }
  }
  foreach ($mn in @("set_ExpComSend","SetConnect","InitCom")) {
    $mm = $ctxType.GetMethods() | Where-Object { $_.Name -eq $mn } | Select-Object -First 1
    if ($mm) { W("  method " + $mn + "(" + (($mm.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ",") + ")") } else { W("  method " + $mn + " : NONE") }
  }
}

W("")
W("=== VsType enum ===")
$vs = ($bi.GetTypes() + $cd.GetTypes()) | Where-Object { $_.Name -eq "VsType" -and $_.IsEnum } | Select-Object -First 1
if ($vs) { foreach ($v in [Enum]::GetValues($vs)) { W("  " + $v + " = " + [int]$v) } } else { W("VsType not found") }

[System.IO.File]::WriteAllLines($out, $log)
Write-Output ("WROTE " + $out)
