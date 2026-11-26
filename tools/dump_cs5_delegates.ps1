# dump_cs5_delegates.ps1 —— 查 CS5 收包分发委托挂点（离线，不碰设备）
$DIR = 'D:\sci\CS Studio5\CS Studio5'
$need = @('CorrTest.CorrInterface.dll','CorrTest.CorrData.dll','CorrTest.CorrCom.dll',
          'CorrTest.CorrModules.dll','CorrTest.CorrMath.dll','CorrTest.CorrLog.dll',
          'CorrTest.CorrLanguage.dll','CorrTest.CorrUSControl.dll',
          'CorrTest.NetSkin.dll','CorrTest.NetUtility.dll','CorrTest.CorrCSType.dll')
foreach ($n in $need) { $p = Join-Path $DIR $n; if (Test-Path $p) { [void][System.Reflection.Assembly]::LoadFrom($p) } }

function Find-Type($name) {
  foreach ($a in [AppDomain]::CurrentDomain.GetAssemblies()) {
    if ($a.GetName().Name -notlike 'CorrTest*') { continue }
    try { foreach ($t in $a.GetTypes()) { if ($t -and $t.Name -eq $name) { return $t } } } catch {}
  }
  return $null
}

foreach ($tn in @('BaseCorrCom','CorCom','SockectCom','BaseContext')) {
  $t = Find-Type $tn
  if (-not $t) { Write-Output "=== $tn : NOT FOUND"; continue }
  Write-Output "=== $tn ($($t.FullName))"
  Write-Output '  -- 与 PackReceive/OnPack/DataEvent 相关的成员:'
  foreach ($m in $t.GetMembers([System.Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly')) {
    if ($m.Name -match 'Pack|DataEvent|OnPack|AddToData|Parsing|Dispatch|Received') {
      $kind = $m.MemberType
      $extra = ''
      if ($m -is [System.Reflection.MethodInfo]) { $extra = ' (' + (($m.GetParameters() | ForEach-Object { $_.ParameterType.Name }) -join ',') + ')' }
      if ($m -is [System.Reflection.FieldInfo]) { $extra = ' : ' + $m.FieldType.FullName }
      if ($m -is [System.Reflection.PropertyInfo]) { $extra = ' : ' + $m.PropertyType.FullName }
      if ($m -is [System.Reflection.EventInfo]) { $extra = ' : ' + $m.EventHandlerType.FullName }
      Write-Output ('    {0,-8} {1,-34}{2}' -f $kind, $m.Name, $extra)
    }
  }
}
