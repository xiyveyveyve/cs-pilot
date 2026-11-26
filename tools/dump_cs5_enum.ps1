# dump_cs5_enum.ps1 —— CS5 Experiment/MethodState 枚举全值（离线，不碰设备）
$DIR = 'D:\sci\CS Studio5\CS Studio5'
$need = @('CorrTest.CorrInterface.dll','CorrTest.CorrData.dll','CorrTest.CorrCom.dll')
foreach ($n in $need) {
    $p = Join-Path $DIR $n
    if (Test-Path $p) { [void][System.Reflection.Assembly]::LoadFrom($p) }
}
$ci = [System.Reflection.Assembly]::LoadFrom((Join-Path $DIR 'CorrTest.CorrInterface.dll'))
foreach ($tn in @('Experiment','MethodState','VsType')) {
    $t = $null
    foreach ($tt in $ci.GetTypes()) { if ($tt.Name -eq $tn) { $t = $tt; break } }
    if ($null -eq $t) {
        # 全程序集找
        foreach ($a in [AppDomain]::CurrentDomain.GetAssemblies()) {
            if ($a.GetName().Name -notlike 'CorrTest*') { continue }
            try { foreach ($tt in $a.GetTypes()) { if ($tt.Name -eq $tn -and $tt.IsEnum) { $t = $tt; break } } } catch {}
            if ($t) { break }
        }
    }
    if ($null -eq $t) { Write-Output "=== $tn : NOT FOUND"; continue }
    Write-Output "=== $tn ($($t.FullName))"
    foreach ($nm in [Enum]::GetNames($t)) {
        Write-Output ("  {0} = {1}" -f $nm, [int][Enum]::Parse($t, $nm))
    }
}
# CorCom 串口连接类核实
$cc = [System.Reflection.Assembly]::LoadFrom((Join-Path $DIR 'CorrTest.CorrCom.dll'))
Write-Output "=== CorrCom 连接类:"
foreach ($tt in $cc.GetTypes()) {
    if ($tt.Name -match 'CorCom|SerialPort|Sockect') {
        $m = $tt.GetMethods([System.Reflection.BindingFlags]'Public,Instance') | Where-Object { $_.Name -eq 'Open' } | ForEach-Object { $_.ToString() }
        Write-Output ("  {0}  base={1}" -f $tt.FullName, $(if ($tt.BaseType) { $tt.BaseType.Name } else { '?' }))
        foreach ($x in $m) { Write-Output ("      Open: {0}" -f $x) }
    }
}
