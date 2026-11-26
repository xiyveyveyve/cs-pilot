// t_cs5t.cs —— 修 SendRotatingSpeed 的 NRE（CellParams 依赖）
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5t.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var cd=asms["CorrTest.CorrData.dll"];

    L("=== CS5 CellParams 属性 ===");
    Type cpT=null; foreach(var a in asms.Values){ cpT=Find(a,"CellParams"); if(cpT!=null) break; }
    foreach(var p in cpT.GetProperties(BindingFlags.Public|BindingFlags.Instance))
      L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));

    L("\n=== CellParams 实例默认值（看哪个为 NULL）===");
    object cp=Activator.CreateInstance(cpT);
    foreach(var p in cpT.GetProperties(BindingFlags.Public|BindingFlags.Instance)){
      if(!p.CanRead) continue;
      object v=null; try{ v=p.GetValue(cp,null); }catch{ continue; }
      if(v==null) L("  NULL: "+p.PropertyType.Name+" "+p.Name);
    }

    L("\n=== SendRotatingSpeed 方法体依赖：看它读 CellParams 哪些属性 ===");
    Type esT=null; foreach(var a in asms.Values){ esT=Find(a,"ExpComSendClass"); if(esT!=null) break; }
    var m=esT.GetMethod("SendRotatingSpeed");
    L("  签名: SendRotatingSpeed("+string.Join(",",Array.ConvertAll(m.GetParameters(),p=>p.ParameterType.Name+" "+p.Name))+")");
    L("  ICellParams 接口属性:");
    Type icp=null; foreach(var a in asms.Values){ icp=Find(a,"ICellParams"); if(icp!=null) break; }
    if(icp!=null) foreach(var p in icp.GetProperties()) L("    "+p.PropertyType.Name+" "+p.Name);
    w.Close(); Environment.Exit(0);
  }
}
