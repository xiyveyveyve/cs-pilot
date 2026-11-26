// t_cs5j.cs —— 按依赖顺序装配 CS5 ctx，再试 ExpClass
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5j.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom");

    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31033"});
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    L("连接注入 OK\n");

    Func<string,object> setP=(prop)=>{ return null; };
    Action<string,object> put=(prop,val)=>{ try{ ctxT.GetProperty(prop).SetValue(ctx,val,null); L("  "+prop+" ← "+val.GetType().Name+" OK"); }catch(Exception e){ var ie=e.InnerException??e; L("  "+prop+" FAIL "+ie.GetType().Name+": "+ie.Message); } };

    // 1) ParsingParams（无参）
    object pp=null, ppa=null, eth=null;
    try{ pp=Activator.CreateInstance(Find(cd,"ParsingParamsClass")); put("ParsingParms",pp); }catch(Exception e){ L("  ParsingParms 构造失败 "+e.Message); }
    try{ ppa=Activator.CreateInstance(Find(cd,"ParsingParamsClass")); put("ParsingParmsAux",ppa); }catch(Exception e){ L("  ParsingParmsAux 失败 "+e.Message); }
    try{ eth=Activator.CreateInstance(Find(cd,"ExpTimeHlpClass")); put("ExpTimeHlp",eth); }catch(Exception e){ L("  ExpTimeHlp 失败 "+e.Message); }
    // 2) ExpParamsBytes(IParsingParams)
    try{ var epb=Activator.CreateInstance(Find(cd,"ExpParamsBytesClass"),new object[]{pp}); put("ExpParamsBytes",epb); }catch(Exception e){ L("  ExpParamsBytes 失败 "+(e.InnerException??e).Message); }
    // 3) ctx 依赖型
    foreach(var nm in new[]{"ExpComSendClass","CellsSwitchClass","ExtComHlpClass"}){
      try{ var o=Activator.CreateInstance(Find(cd,nm),new object[]{ctx}); put(nm.Replace("Class",""),o); }
      catch(Exception e){ L("  "+nm+" 失败 "+(e.InnerException??e).GetType().Name+": "+(e.InnerException??e).Message); }
    }
    // 4) BaseIOClass(byte[])
    try{ var io=Activator.CreateInstance(Find(cd,"BaseIOClass"),new object[]{new byte[64]}); put("BaseIO",io); put("BaseIOAux",Activator.CreateInstance(Find(cd,"BaseIOClass"),new object[]{new byte[64]})); }
    catch(Exception e){ L("  BaseIO 失败 "+(e.InnerException??e).GetType().Name+": "+(e.InnerException??e).Message); }

    L("\n=== 试 set_baseContext ===");
    object prm=Activator.CreateInstance(ocpT);
    try{ ocpT.GetProperty("baseContext").SetValue(prm,ctx,null); L("  ★ OK"); }
    catch(Exception e){ var ie=e.InnerException??e; L("  FAIL "+ie.GetType().Name+": "+ie.Message); }

    L("\n=== 试 ExpClass(ctx, prm) ===");
    try{ var ec=Activator.CreateInstance(expT,new object[]{ctx,prm}); L("  ★★ ExpClass OK → "+ec.GetType().Name); }
    catch(Exception e){ var ie=e.InnerException??e; L("  FAIL "+ie.GetType().Name+": "+ie.Message+"\n   "+(ie.StackTrace??"").Split('\n')[0]); }
    w.Close(); Environment.Exit(0);
  }
}
