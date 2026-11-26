// t_cs5u.cs —— SendRotatingSpeed 单独调用，定位内部 NRE
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5u.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), sockT=Find(cc,"SockectCom");

    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31040"});
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    object pp=Activator.CreateInstance(Find(cd,"ParsingParamsClass"));
    ctxT.GetProperty("ParsingParms").SetValue(ctx,pp,null);
    ctxT.GetProperty("ParsingParmsAux").SetValue(ctx,Activator.CreateInstance(Find(cd,"ParsingParamsClass")),null);
    ctxT.GetProperty("ExpTimeHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpTimeHlpClass")),null);
    ctxT.GetProperty("ExpParamsBytes").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpParamsBytesClass"),new object[]{pp}),null);
    object send=Activator.CreateInstance(Find(cd,"ExpComSendClass"),new object[]{ctx});
    ctxT.GetProperty("ExpComSend").SetValue(ctx,send,null);
    ctxT.GetProperty("CellsSwitch").SetValue(ctx,Activator.CreateInstance(Find(cd,"CellsSwitchClass"),new object[]{ctx}),null);
    ctxT.GetProperty("ExtComHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExtComHlpClass"),new object[]{ctx}),null);

    var sendT=send.GetType();
    Type cpT=Find(cd,"CellParams");
    object cp=Activator.CreateInstance(cpT);

    L("=== 直接调 SendRotatingSpeed ===");
    try{ L("  → "+sendT.GetMethod("SendRotatingSpeed").Invoke(send,new object[]{cp})); }
    catch(Exception e){
      var ie=e.InnerException??e;
      L("  EXC "+ie.GetType().Name+": "+ie.Message);
      var st=(ie.StackTrace??"").Split('\n');
      foreach(var l in st) L("    "+l.Trim());
    }
    L("\n=== EnableSpeed=false 时是否跳过 ===");
    cpT.GetProperty("EnableSpeed").SetValue(cp,false,null);
    try{ L("  → "+sendT.GetMethod("SendRotatingSpeed").Invoke(send,new object[]{cp})); }
    catch(Exception e){ var ie=e.InnerException??e; L("  EXC "+ie.GetType().Name+": "+ie.Message); }
    L("\n=== ctx.CellsSwitch 是否为空 ===");
    L("  CellsSwitch="+(ctxT.GetProperty("CellsSwitch").GetValue(ctx,null)==null?"NULL":"非空"));
    L("\n=== ExpComSendClass 的字段（找 null） ===");
    foreach(var f in sendT.GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)){
      object v=null; try{v=f.GetValue(send);}catch{}
      L("   "+f.FieldType.Name+" "+f.Name+"="+(v==null?"NULL":"非空"));
    }
    w.Close(); Environment.Exit(0);
  }
}
