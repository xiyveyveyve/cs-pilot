using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n)));}catch{}}
    // BaseContext 全部成员（含私有），找 com 相关
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="BaseContext") continue;
      L("=== "+t.FullName+" ===");
      L("-- 字段（找 com/Com/ICorrCom）--");
      foreach(var f in t.GetFields(BindingFlags.Instance|BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic))
        if(f.Name.ToLower().Contains("com")) L("   F "+f.FieldType.Name+" "+f.Name+(f.IsPublic?" public":" private"));
      L("-- 全部方法（名字含 Com/Init/Connect）--");
      foreach(var m in t.GetMethods(BindingFlags.Instance|BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic))
        if(m.Name.ToLower().Contains("com")||m.Name.ToLower().Contains("init")||m.Name.ToLower().Contains("connect"))
          L("   M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")"+(m.IsPublic?"":" [non-public]"));
    }
    // ExpClass 构造内部依赖
    L("\n=== ExpClass 构造器 + 反编译线索 ===");
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="ExpClass") continue;
      foreach(var c in t.GetConstructors()) L("  C("+P(c)+")");
      L("  -- 字段 --");
      foreach(var f in t.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)) L("   F "+f.FieldType.Name+" "+f.Name);
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5e.txt",sb.ToString()); Environment.Exit(0);
  }
}
