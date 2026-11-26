// t_cs5ead.cs -- 查 ExtAmpData 是字段还是属性 + 构造方式 + VotCoefficient
using System; using System.Collections.Generic; using System.IO; using System.Reflection; using System.Text;
static class E {
  const string D=@"D:\sci\CS Studio5\CS Studio5";
  static readonly string[] N={"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
  static readonly List<Assembly> A=new List<Assembly>(); static readonly StringBuilder S=new StringBuilder();
  static void L(string s){S.AppendLine(s);}
  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type F(string n){ foreach(var a in A) foreach(var t in T(a)) if(t!=null&&t.Name==n) return t; return null; }
  static int Main(){
    foreach(var n in N){ var p=Path.Combine(D,n); if(File.Exists(p)){ try{A.Add(Assembly.LoadFrom(p));}catch{} } }
    var ctx=F("BaseContext");
    L("=== BaseContext 里 ExtAmpData 相关成员 ===");
    foreach(var f in ctx.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public))
      if(f.Name.ToLower().Contains("extamp")||f.FieldType.Name.Contains("ExtAmp")) L("  FIELD "+f.FieldType.Name+" "+f.Name);
    foreach(var p in ctx.GetProperties(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public))
      if(p.Name.ToLower().Contains("extamp")) L("  PROP "+p.PropertyType.Name+" "+p.Name+" write="+p.CanWrite);

    var ead=F("ExtAmpData");
    L(""); L("=== ExtAmpData 类型 ===");
    L("  type="+(ead==null?"未找到":ead.FullName));
    if(ead!=null){
      foreach(var c in ead.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance))
        L("  C("+string.Join(", ",Array.ConvertAll(c.GetParameters(),x=>x.ParameterType.Name+" "+x.Name))+") pub="+c.IsPublic);
      L("  -- 属性 --");
      foreach(var p in ead.GetProperties(BindingFlags.Public|BindingFlags.Instance)) L("    P "+p.PropertyType.Name+" "+p.Name+" rw="+p.CanWrite);
      L("  -- 字段 --");
      foreach(var f in ead.GetFields(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)) L("    F "+f.FieldType.Name+" "+f.Name);
      // 试着构造
      foreach(var c in ead.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance)){
        try{
          var ps=c.GetParameters(); var args=new object[ps.Length];
          for(int k=0;k<ps.Length;k++) args[k]=ps[k].ParameterType.IsValueType?Activator.CreateInstance(ps[k].ParameterType):null;
          var inst=Activator.CreateInstance(ead,args);
          L("  ★ 构造成功: ("+ps.Length+"参) → "+inst.GetType().Name);
          var vc=ead.GetProperty("VotCoefficient");
          if(vc!=null){ try{ L("     VotCoefficient="+vc.GetValue(inst,null)); }catch(Exception e){ L("     VotCoefficient 读失败: "+e.GetType().Name); } }
          break;
        }catch(Exception e){ L("  构造失败("+c.GetParameters().Length+"参): "+(e.InnerException??e).GetType().Name+": "+(e.InnerException??e).Message); }
      }
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5ead.log",S.ToString());
    Console.WriteLine(S.ToString()); Environment.Exit(0); return 0;
  }
}
