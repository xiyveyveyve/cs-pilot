using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Dump(Assembly a, string name){
    foreach(var t in Types(a)){
      if(t==null||t.Name!=name) continue;
      L("\n=== "+a.GetName().Name+" :: "+t.FullName+" abstract="+t.IsAbstract+" iface="+t.IsInterface);
      try{
        foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance)) L("   P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
        foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
          if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("   M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
        foreach(var c in t.GetConstructors()) L("   C ("+P(c)+")");
      }catch(Exception e){ L("   ERR "+e.Message); }
    }
  }
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n))); }catch{}
    }
    foreach(var nm in new[]{"ICorrCom","IExpClass","BaseMainFrm","IExpComSend","IExpParamsBytes","IBaseParams"})
      foreach(var a in asms) Dump(a, nm);
    L("\n=== CorrData 里的 *Params 类（前 25 个）===");
    int k=0;
    foreach(var a in asms){
      foreach(var t in Types(a)){
        if(t==null||!t.IsPublic||!t.Name.EndsWith("Params")) continue;
        if(k++>=25) break;
        L("  "+a.GetName().Name+" :: "+t.FullName+" base="+(t.BaseType==null?"-":t.BaseType.Name));
      }
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5b.txt", sb.ToString());
    Environment.Exit(0);
  }
}
