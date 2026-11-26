using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    // 这次把 CorrModules 也加载上
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ var a=Assembly.LoadFrom(Path.Combine(dir5,n)); asms.Add(a); L("LOAD "+n); }catch(Exception e){ L("LOAD FAIL "+n+" "+e.GetType().Name); } }
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="WriteFile") continue;
      L("\n=== "+t.FullName+" (asm="+a.GetName().Name+") ===");
      foreach(var c in t.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)) L("  C("+P(c)+") public="+c.IsPublic);
      foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
        if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
      foreach(var f in t.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)) L("  F "+f.FieldType.Name+" "+f.Name);
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5h.txt",sb.ToString()); Environment.Exit(0);
  }
}
