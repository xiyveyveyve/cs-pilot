# csdotnet.ps1 -- build CS Studio6 method-parameter objects in pure .NET and
# emit their GetSaveString() serialization as JSON.
#
# Why this exists: CSStudio6.CorrData.MethodParams.* are public, un-obfuscated
# classes with parameterless constructors. Their GetSaveString() produces the
# exact "Key=Value&-&Key=Value..." payload the software itself persists/loads
# (InitByString parses it back). So experiment parameters can be built and
# verified WITHOUT the GUI and WITHOUT a device.
#
# Usage (from python, see csdotnet.py):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File csdotnet.ps1 `
#       -Kind step -Area 1.35 -Density 7.93 -Temp 25 -Out result.json
#
# All output is ASCII/UTF-8 with no console encoding tricks.

param(
    [string]$Kind = "step",
    [double]$Area = 1.0,
    [double]$Density = 7.93,
    [double]$TempVal = 25.0,
    [double]$Dangliang = 28.0,
    [string]$Out = ""
)

$ErrorActionPreference = "Continue"
$dir = "D:\sci\MDI Jade 9"

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.Management -ErrorAction SilentlyContinue

$need = @(
    "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll", "CSStudio6.MathHlp.dll",
    "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll", "CSStudio6.SysLog.dll",
    "CSStudio6.USControl.dll", "CSStudio6.NetSkin.dll"
)
foreach ($n in $need) {
    $p = Join-Path $dir $n
    if (Test-Path $p) { try { [void][System.Reflection.Assembly]::LoadFrom($p) } catch { } }
}
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $dir "CSStudio6.CorrData.dll"))

$warn = New-Object System.Collections.ArrayList
function NW($s) { [void]$warn.Add([string]$s) }

function SetP($obj, $name, $val) {
    $p = $obj.GetType().GetProperty($name)
    if ($null -eq $p) { NW "no property: $name"; return $false }
    try {
        if ($p.PropertyType.IsEnum) {
            $ev = [System.Enum]::Parse($p.PropertyType, [string]$val, $true)
            $p.SetValue($obj, $ev, $null)
        } else {
            $p.SetValue($obj, [System.Convert]::ChangeType($val, $p.PropertyType), $null)
        }
        return $true
    } catch { NW ("set " + $name + " failed: " + $_.Exception.Message); return $false }
}

function GetP($obj, $name) {
    $p = $obj.GetType().GetProperty($name)
    if ($null -eq $p) { return $null }
    try { return $p.GetValue($obj, $null) } catch { return $null }
}

# ---- build the parameter object per Kind -------------------------------------
$typeName = $null
switch ($Kind) {
    "ocp"   { $typeName = "CSStudio6.CorrData.MethodParams.OcpParams" }
    "step"  { $typeName = "CSStudio6.CorrData.MethodParams.PotSquareParams" }
    "tafel" { $typeName = "CSStudio6.CorrData.MethodParams.PotDynamicParams" }
    default { throw "unknown -Kind: $Kind" }
}
$t = $cd.GetType($typeName)
if ($null -eq $t) { throw "type not found: $typeName" }
$obj = [System.Activator]::CreateInstance($t)

switch ($Kind) {
    "ocp" {
        # 1800 s total, 10 Hz sampling, software-side stop conditions OFF
        [void](SetP $obj "TestTime" 1800)
        [void](SetP $obj "TestTimeUnit" 0)
        [void](SetP $obj "UseStop" "False")
        [void](SetP $obj "UseStop2" "False")
        [void](SetP $obj "SampleFrq" 10)
        [void](SetP $obj "AxisType" "EvsTime")
    }
    "step" {
        # -0.2 V -> 0.5 V, 2 s per segment, intermediate steps disabled, 20 cycles
        [void](SetP $obj "Initial_E" -0.2)
        [void](SetP $obj "Final_E" 0.5)
        [void](SetP $obj "InitialTime" 2)
        [void](SetP $obj "FinalTime" 2)
        [void](SetP $obj "TimeUnit" 1)
        for ($i = 1; $i -le 10; $i++) { [void](SetP $obj ("Step" + $i + "Enable") "False") }
        [void](SetP $obj "Cycles" 20)
        [void](SetP $obj "VsOcp" "vsOCP")
    }
    "tafel" {
        # -0.2 V -> 0.5 V, 0.33 mV/s, stop at 1e-3 A/cm2
        [void](SetP $obj "InitE" -0.2)
        [void](SetP $obj "FinalE" 0.5)
        [void](SetP $obj "ScanRate" 0.33)
        [void](SetP $obj "ScanRateUnit" 0)
        [void](SetP $obj "InitEVsOcp" "vsOCP")
        [void](SetP $obj "FinalEVsOcp" "vsOCP")
        [void](SetP $obj "StopCurrent" 1)
        [void](SetP $obj "StopCurrentUnit" 1)
        [void](SetP $obj "AxisType" "EvsLogi")
    }
}

# ---- electrolysis cell -------------------------------------------------------
$cell = GetP $obj "CellParam"
if ($null -ne $cell) {
    [void](SetP $cell "Area" $Area)
    [void](SetP $cell "Density" $Density)
    [void](SetP $cell "Temp" $TempVal)
    [void](SetP $cell "Dangliang" $Dangliang)
} else { NW "CellParam is null" }

# ---- serialize ---------------------------------------------------------------
$s1 = $t.GetMethod("GetSaveString").Invoke($obj, @())

# ---- round-trip --------------------------------------------------------------
$rt = $null
$rtOk = $false
try {
    $obj2 = [System.Activator]::CreateInstance($t)
    [void]$t.GetMethod("InitByString").Invoke($obj2, @($s1))
    $s2 = $t.GetMethod("GetSaveString").Invoke($obj2, @())
    $rt = @{ length = $s2.Length; identical = ($s1 -eq $s2) }
    $keyFields = @{}
    foreach ($k in @("Initial_E","Final_E","InitialTime","FinalTime","Cycles","TimeUnit","InitE","FinalE","ScanRate","TestTime","TestTimeUnit","UseStop","SampleFrq")) {
        $v = GetP $obj2 $k
        if ($null -ne $v) { $keyFields[$k] = "$v" }
    }
    $c2 = GetP $obj2 "CellParam"
    if ($null -ne $c2) {
        $keyFields["Cell.Area"] = "$(GetP $c2 'Area')"
        $keyFields["Cell.Density"] = "$(GetP $c2 'Density')"
        $keyFields["Cell.Temp"] = "$(GetP $c2 'Temp')"
    }
    $rt["fields"] = $keyFields
    $rtOk = $true
} catch { NW ("round-trip failed: " + $_.Exception.Message) }

$result = [ordered]@{
    kind       = $Kind
    type       = $t.FullName
    assembly   = $cd.FullName
    savestring = $s1
    length     = $s1.Length
    roundtrip  = $rt
    warnings   = @($warn)
}

$json = $result | ConvertTo-Json -Depth 6
if ($Out -ne "") {
    [System.IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "wrote $Out"
} else {
    Write-Output $json
}
