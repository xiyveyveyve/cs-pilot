using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.FullName+" "+ps[i].Name+(ps[i].IsOptional?"=opt":"");return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n)));}catch{}}
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null) continue;
      if(t.Name=="ExpClass"||t.Name=="MultiExpClass"){
        L("=== "+t.FullName+" ===");
        foreach(var c in t.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)) L("  C ("+P(c)+") public="+c.IsPublic);
        L("  -- 属性 --");
        foreach(var p in t.GetProperties()) L("   P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
        L("  -- public 方法 --");
        foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
          if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("   M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
      }
    }
    // 参数类：BaseParams 与 Ocp 相关
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||!t.IsPublic) continue;
      if(t.Name=="OcpParams"||t.Name=="PotDynamicParams"||t.Name=="BaseParams"){
        L("\n=== PARAM "+t.FullName+" base="+(t.BaseType==null?"-":t.BaseType.Name)+" ===");
        foreach(var c in t.GetConstructors()) L("  C ("+P(c)+")");
        foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) L("   P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
      }
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5d.txt",sb.ToString()); Environment.Exit(0);
  }
}
