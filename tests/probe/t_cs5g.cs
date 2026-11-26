// t_cs5g.cs —— baseContext setter 的 NRE 定位（逐项补齐 ctx 依赖）
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5g.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    Type baseP=null; foreach(var t in Types(cd)) if(t.Name=="BaseParams") baseP=t;
    Type ocpT=null; foreach(var t in Types(cd)) if(t.Name=="OcpParams") ocpT=t;

    L("=== BaseParams 属性（找 setter 依赖）===");
    foreach(var p in baseP.GetProperties(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
      L("   P "+p.PropertyType.Name+" "+p.Name+" write="+p.CanWrite);

    L("\n=== BaseParams.set_baseContext 是否 stub ===");
    var sp=baseP.GetProperty("baseContext");
    L("   property="+(sp==null?"NULL":sp.PropertyType.Name));
    if(sp!=null){
      var setm=sp.GetSetMethod();
      L("   setter="+(setm==null?"NULL":setm.Name+" public="+setm.IsPublic));
    }

    // 试：ctx 上补齐常见依赖再挂
    object ctx=Activator.CreateInstance(ctxT);
    L("\n=== ctx 关键成员当前值 ===");
    foreach(var pn in new[]{"IsDefaultContext","ExpComSend","BaseIO","BaseIOAux","CellsSwitch","ExtComHlp","ParsingParms","BaseParam","ActiveExpClass"}){
      var p=ctxT.GetProperty(pn); if(p==null){ L("   "+pn+" 无"); continue; }
      object v=null; try{v=p.GetValue(ctx,null);}catch(Exception e){ L("   "+pn+" 读取异常"); continue; }
      L("   "+pn+"="+(v==null?"NULL":"非空")+" 可写="+p.CanWrite);
    }

    // 逐步试：先挂一个最小 ctx（不设任何东西）
    foreach(var variant in new[]{"bare"}){
      object prm=Activator.CreateInstance(ocpT);
      try{ sp.SetValue(prm,ctx,null); L("\n["+variant+"] set baseContext OK"); }
      catch(Exception e){
        var ie=e.InnerException??e;
        L("\n["+variant+"] set baseContext FAIL: "+ie.GetType().Name+": "+ie.Message);
        L("   stack: "+(ie.StackTrace??"").Split('\n')[0]);
      }
    }
    // 用 OcpParams 自己的 baseContext（继承来的）也确认一次
    var sp2=ocpT.GetProperty("baseContext");
    L("\nOcpParams.baseContext 声明于="+(sp2==null?"NULL":sp2.DeclaringType.Name));
    w.Close(); Environment.Exit(0);
  }
}
