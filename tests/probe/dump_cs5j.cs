// dump_cs5j.cs —— BaseIOClass 构造 + IBaseIO 成员
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type FindIn(List<Assembly> asms, string n){ foreach(var a in asms) foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string d5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(d5,n)));}catch{}}
    foreach(var nm in new[]{"BaseIOClass","IBaseIO","IDeviceParams","DeviceParams"}){
      var t=FindIn(asms,nm);
      if(t==null){ L(nm+" 未找到"); continue; }
      L("\n=== "+t.FullName+" iface="+t.IsInterface+" ===");
      if(!t.IsInterface){
        foreach(var c in t.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)) L("  C("+P(c)+")");
      }
      foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
      if(t.IsInterface) foreach(var m in t.GetMethods()) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
    }
    // BaseParams.BaseIO 属性
    var bp=FindIn(asms,"BaseParams");
    if(bp!=null){
      L("\n=== BaseParams.BaseIO / BaseIO 相关属性 ===");
      foreach(var p in bp.GetProperties()) if(p.Name.ToLower().Contains("io")) L("  P "+p.PropertyType.Name+" "+p.Name+" rw="+p.CanWrite);
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5j.txt",sb.ToString()); Environment.Exit(0);
  }
}
