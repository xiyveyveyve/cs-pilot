// t_cs5s.cs —— 定位 StartMethod 的 NRE 依赖
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5s.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom");

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

    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,20f,null);
    ocpT.GetProperty("TestTimeUnit").SetValue(prm,1,null);
    ocpT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5run\x",null);
    ocpT.GetProperty("FileName").SetValue(prm,"x",null);
    var expEnum=Find(ci,"Experiment");
    ocpT.GetProperty("ExpType").SetValue(prm,Enum.Parse(expEnum,"ID_OCP"),null);
    ctxT.GetProperty("CurExp").SetValue(ctx,Enum.Parse(expEnum,"ID_OCP"),null);

    L("=== 参数对象里仍为 NULL 的关键引用 ===");
    foreach(var pn in new[]{"DevParam","CellParam","BaseIO","AuxIO","ChannelCellParam","AuxDeviceParams","BestGraph"}){
      var p=ocpT.GetProperty(pn); if(p==null){ L("  "+pn+" 无此属性"); continue; }
      object v=null; try{v=p.GetValue(prm,null);}catch(Exception e){ L("  "+pn+" 读异常"); continue; }
      L("  "+pn+"="+(v==null?"NULL":"非空("+v.GetType().Name+")")+" 可写="+p.CanWrite);
    }
    L("\n=== ctx 里仍为 NULL 的 ===");
    foreach(var pn in new[]{"BaseIO","BaseIOAux","MainFrm","MainFrm2","ContextRelationMain"}){
      var p=ctxT.GetProperty(pn); if(p==null) continue;
      object v=null; try{v=p.GetValue(ctx,null);}catch{}
      L("  "+pn+"="+(v==null?"NULL":"非空"));
    }
    L("\n=== 补齐 DevParam/CellParam 后再试 StartMethod ===");
    // 找实现类
    foreach(var nm in new[]{"DeviceParams","CellParams"}){
      Type t=null; foreach(var a in asms.Values){ t=Find(a,nm); if(t!=null) break; }
      if(t==null){ L("  "+nm+" 实现类未找到"); continue; }
      L("  "+nm+" 构造器: "+string.Join(" | ",Array.ConvertAll(t.GetConstructors(),c=>"("+c.GetParameters().Length+"参)")));
      try{ var inst=Activator.CreateInstance(t); L("    无参构造 OK");
        string prop=nm=="DeviceParams"?"DevParam":"CellParam";
        ocpT.GetProperty(prop).SetValue(prm,inst,null); L("    "+prop+" ← "+nm+" OK");
      }catch(Exception e){ L("    失败: "+(e.InnerException??e).Message); }
    }

    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null);
    var sendT=send.GetType();
    try{ L("  InitExp → "+sendT.GetMethod("InitExp").Invoke(send,new object[]{prm})); }catch(Exception e){ L("  InitExp EXC "+(e.InnerException??e).Message); }
    try{
      object[] a=new object[]{prm,true,false,""};
      object r=sendT.GetMethod("StartMethod").Invoke(send,a);
      L("  ★ StartMethod → ret="+r+" sError='"+a[3]+"'");
    }catch(Exception e){
      var ie=e.InnerException??e;
      L("  StartMethod EXC "+ie.GetType().Name+": "+ie.Message);
      L("   stack: "+(ie.StackTrace??"").Split('\n')[0]);
    }
    w.Close(); Environment.Exit(0);
  }
}
