// t_cs5w2.cs —— 找 ExtDevHlp（StartMethod 链路的关键缺失成员）
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5w2.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"];
    Type ctxT=Find(ci,"BaseContext");

    L("=== BaseContext 全部字段（找 Ext*） ===");
    foreach(var f in ctxT.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public))
      L("  F "+f.FieldType.FullName+" "+f.Name+" public="+f.IsPublic);

    L("\n=== BaseContext 全部含 Ext 的成员 ===");
    foreach(var f in ctxT.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public))
      if(f.Name.Contains("Ext")||f.FieldType.Name.Contains("Ext")) L("  F "+f.FieldType.Name+" "+f.Name);
    foreach(var p in ctxT.GetProperties(BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic))
      if(p.Name.Contains("Ext")) L("  P "+p.PropertyType.Name+" "+p.Name);

    L("\n=== ExtDevHlpClass 类型 ===");
    Type edh=null; foreach(var a in asms.Values){ edh=Find(a,"ExtDevHlpClass"); if(edh!=null){ L("  找到: "+edh.FullName+" (asm="+a.GetName().Name+")"); break; } }
    if(edh!=null){
      foreach(var c in edh.GetConstructors()) L("  C("+string.Join(",",Array.ConvertAll(c.GetParameters(),p=>p.ParameterType.Name+" "+p.Name))+")");
      L("  -- 方法 --");
      foreach(var m in edh.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
        if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("   M "+m.ReturnType.Name+" "+m.Name+"("+m.GetParameters().Length+"参)");
      L("  -- 字段 --");
      foreach(var f in edh.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)) L("   F "+f.FieldType.Name+" "+f.Name);
    } else L("  ExtDevHlpClass 未找到");

    L("\n=== 搜索所有类型里名字含 ExtDevHlp 的 ===");
    foreach(var a in asms.Values) foreach(var t in Types(a))
      if(t!=null&&t.Name.Contains("ExtDevHlp")) L("  "+a.GetName().Name+" :: "+t.FullName);
    w.Close(); Environment.Exit(0);
  }
}
