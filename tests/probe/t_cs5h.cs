// t_cs5h.cs —— 定位 BaseParams.set_baseContext 内部依赖哪个 ctx 成员为 NULL
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5h.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    Type ocpT=null; foreach(var t in Types(cd)) if(t.Name=="OcpParams") ocpT=t;

    object ctx=Activator.CreateInstance(ctxT);
    // 打印 ctx 所有可写的接口/类属性当前为 NULL 的
    L("=== ctx 中所有 NULL 且可写的属性 ===");
    var nullProps=new List<PropertyInfo>();
    foreach(var p in ctxT.GetProperties(BindingFlags.Public|BindingFlags.Instance)){
      if(!p.CanWrite) continue;
      object v=null; try{ v=p.GetValue(ctx,null); }catch{ continue; }
      if(v==null){ nullProps.Add(p); L("   NULL: "+p.PropertyType.Name+" "+p.Name); }
    }
    // 找出这些属性类型里有无参构造的，逐个补上再看 set_baseContext 是否还炸
    L("\n=== 逐个补 null 属性，观察 set_baseContext ===");
    foreach(var p in nullProps){
      Type pt=p.PropertyType;
      if(pt.IsInterface||pt.IsAbstract){ L("   skip(接口) "+p.Name); continue; }
      object inst=null;
      try{ inst=Activator.CreateInstance(pt); }catch{ L("   skip(无无参构造) "+p.Name); continue; }
      try{ p.SetValue(ctx,inst,null); }catch{ L("   skip(写入失败) "+p.Name); continue; }
      object prm=Activator.CreateInstance(ocpT);
      try{
        ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
        L("   ★ 补上 "+p.Name+"("+pt.Name+") 后 set_baseContext 成功！");
      }catch(Exception e){
        var ie=e.InnerException??e;
        L("   补 "+p.Name+" 仍失败: "+ie.GetType().Name);
      }
      try{ p.SetValue(ctx,null,null); }catch{}
    }
    w.Close(); Environment.Exit(0);
  }
}
