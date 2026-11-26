# dump_gal_params.ps1 —— Gal* 参数类属性 dump（夜间自动化延续，2026-11-13）
$DIR = 'D:\sci\MDI Jade 9'
foreach ($n in @('CSStudio6.BaseInterface.dll','CSStudio6.CorrData.dll','CSStudio6.Connect.dll',
                 'CSStudio6.MathHlp.dll','CSStudio6.NetUtility.dll','CSStudio6.Language.dll',
                 'CSStudio6.SysLog.dll')) {
    [void][System.Reflection.Assembly]::LoadFrom((Join-Path $DIR $n))
}
$cd = [System.Reflection.Assembly]::LoadFrom((Join-Path $DIR 'CSStudio6.CorrData.dll'))

foreach ($cn in @('GalSquareParams','GalStaticParams','GalDynamicParams','GalChargeParams')) {
    $t = $cd.GetType('CSStudio6.CorrData.MethodParams.' + $cn)
    $ctor = $t.GetConstructor([Type[]]@())
    $obj = $ctor.Invoke(@())
    Write-Output ('=== ' + $cn)
    $t.GetProperties([System.Reflection.BindingFlags]'Public,Instance') | ForEach-Object {
        $rw = 'r'; if ($_.CanWrite) { $rw = 'rw' }
        $val = ''
        try {
            $v = $_.GetValue($obj, $null)
            if ($v -ne $null) { $val = ' = ' + $v.ToString() }
        } catch { $val = ' = <err>' }
        Write-Output ('  {0,-30} {1,-14} {2}{3}' -f $_.Name, $_.PropertyType.Name, $rw, $val)
    }
    # GetSaveString 直出（默认值参数串，字段语义的独立证据）
    $gs = $t.GetMethod('GetSaveString')
    if ($gs) {
        try {
            $sv = $gs.Invoke($obj, @())
            if ($sv.Length -gt 600) { $sv = $sv.Substring(0,600) + ' ...[截断,共' + $sv.Length + '字符]' }
            Write-Output ('  [GetSaveString 默认] ' + $sv)
        } catch { Write-Output ('  [GetSaveString 异常] ' + $_.Exception.Message) }
    }
}
