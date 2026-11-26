using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n)));}catch{}}
    // WriteFile 类
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null) continue;
      if(t.Name=="WriteFile"){
        L("=== "+t.FullName+" ===");
        foreach(var c in t.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)) L("  C("+P(c)+") public="+c.IsPublic);
        foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
          if(!m.Name.StartsWith("get_")&&!m.Name.StartsWith("set_")) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
        foreach(var f in t.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)) L("  F "+f.FieldType.Name+" "+f.Name);
      }
    }
    // ExpClass 的 BeginStartWriteFile / WriteContext / WriteDataNow 是否 stub
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="ExpClass") continue;
      L("\n=== ExpClass 写盘方法 IL 长度（判断是否 stub）===");
      foreach(var mn in new[]{"BeginStartWriteFile","WriteContext","WriteDataNow","EndWriteFile","BeginStartWriteUnitFile"}){
        var m=t.GetMethod(mn,Type.EmptyTypes);
        if(m==null){ L("  "+mn+" 不存在"); continue; }
        byte[] il=null;
        try{ il=m.GetMethodBody()!=null?m.GetMethodBody().GetILAsByteArray():null; }catch{}
        L("  "+mn+" IL="+(il==null?"无方法体":il.Length+" B")+" public="+m.IsPublic);
      }
      // 字段 writeFile 类型
      var wf=t.GetField("writeFile",BindingFlags.Instance|BindingFlags.NonPublic);
      L("  writeFile 字段类型="+(wf==null?"无":wf.FieldType.FullName));
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5g.txt",sb.ToString()); Environment.Exit(0);
  }
}
