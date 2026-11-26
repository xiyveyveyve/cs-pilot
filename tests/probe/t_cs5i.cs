// t_cs5i.cs —— 用具体实现类补齐 ctx 接口成员，再试 ExpClass
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5i.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];

    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass");
    Type sockT=Find(cc,"SockectCom");

    // 打印实现类构造器
    foreach(var nm in new[]{"BaseIOClass","ParsingParamsClass","ExpComSendClass","CellsSwitchClass","ExtComHlpClass","ExpParamsBytesClass","ExpTimeHlpClass"}){
      var t=Find(cd,nm);
      if(t==null){ L(nm+" 找不到"); continue; }
      var cs=t.GetConstructors();
      L(nm+" 构造器: "+(cs.Length==0?"无公开":string.Join(" | ",Array.ConvertAll(cs,c=>"("+P(c)+")"))));
    }

    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    bool opened=(bool)sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31033"});
    L("\nOpen="+opened);
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    L("_com 注入后 GetCom()="+(ctxT.GetMethod("GetCom").Invoke(ctx,null)==null?"NULL":"非空"));

    // 逐个装配
    // 局部函数改用 lambda 变量（C#5 不支持局部函数里的默认参数）
    Action<string,Type,object[]> SetP = null;
    SetP = (prop, impl, args) => {
      var t=Find(cd,impl.Name);
      if(t==null){ L("  "+prop+": 实现类缺失"); return; }
      try{
        object inst = args==null ? Activator.CreateInstance(t) : Activator.CreateInstance(t,args);
        var p=ctxT.GetProperty(prop);
        p.SetValue(ctx,inst,null);
        L("  "+prop+" ← "+t.Name+"("+(args==null?"无参":args.Length+"参数")+") OK");
      }catch(Exception e){
        var ie=e.InnerException??e;
        L("  "+prop+" ← "+impl.Name+" FAIL: "+ie.GetType().Name+": "+ie.Message);
      }
    };
    L("\n=== 装配 ctx 接口成员 ===");
    var impls=new[]{"BaseIOClass","ParsingParamsClass","ExpComSendClass","CellsSwitchClass","ExtComHlpClass","ExpParamsBytesClass","ExpTimeHlpClass"};
    // 先看这些实现类需要的参数
    foreach(var nm in impls){
      var t=Find(cd,nm); if(t==null) continue;
      var c0=t.GetConstructor(Type.EmptyTypes);
      L("  "+nm+" 无参构造="+(c0!=null));
    }

    L("\n=== 试 set_baseContext（不带任何补齐）===");
    try{ var prm=Activator.CreateInstance(ocpT); ocpT.GetProperty("baseContext").SetValue(prm,ctx,null); L("  OK"); }
    catch(Exception e){ var ie=e.InnerException??e; L("  FAIL "+ie.GetType().Name+": "+ie.Message); }
    w.Close(); Environment.Exit(0);
  }
}
