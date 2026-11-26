// t_cs5w.cs —— CS5 落盘：BeginStartWriteFile 各阶段观察 + 手工 WriteFile 对照
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static string St(string f){ try{ return File.Exists(f)?(new FileInfo(f).Length+" B"):"不存在"; }catch(Exception e){ return "err "+e.Message; } }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5w.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"]; var cm=asms["CorrTest.CorrModules.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom"), wfT=Find(cm,"WriteFile");

    L("[A] 先单测 WriteFile 本身");
    string fpA=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5\wf_test.cor";
    try{
      object wf=Activator.CreateInstance(wfT,new object[]{fpA});
      L("    ctor OK → "+St(fpA));
      wfT.GetMethod("WriteHeard").Invoke(wf,new object[]{new string[]{"CORRW ASCII","test"}});
      L("    WriteHeard → "+St(fpA));
      wfT.GetMethod("WriteData").Invoke(wf,new object[]{new string[]{"-1.23456E-01\t1.00E-10\t0.00000"}});
      L("    WriteData → "+St(fpA));
      try{ wfT.GetMethod("WriteDataToFile").Invoke(wf,null); L("    WriteDataToFile → "+St(fpA)); }catch(Exception e){ L("    WriteDataToFile EXC "+(e.InnerException??e).Message); }
      try{ wfT.GetMethod("Dispose").Invoke(wf,null); L("    Dispose → "+St(fpA)); }catch(Exception e){ L("    Dispose EXC "+(e.InnerException??e).Message); }
      if(File.Exists(fpA)){ L("    内容预览:"); foreach(var ln in File.ReadAllLines(fpA)) L("      | "+ln); }
    }catch(Exception e){ L("    WriteFile 失败 "+(e.InnerException??e).GetType().Name+": "+(e.InnerException??e).Message); }

    L("\n[B] ExpClass.BeginStartWriteFile 前后对照");
    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31035"});
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    object pp=Activator.CreateInstance(Find(cd,"ParsingParamsClass"));
    ctxT.GetProperty("ParsingParms").SetValue(ctx,pp,null);
    ctxT.GetProperty("ParsingParmsAux").SetValue(ctx,Activator.CreateInstance(Find(cd,"ParsingParamsClass")),null);
    ctxT.GetProperty("ExpTimeHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpTimeHlpClass")),null);
    ctxT.GetProperty("ExpParamsBytes").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpParamsBytesClass"),new object[]{pp}),null);
    ctxT.GetProperty("ExpComSend").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpComSendClass"),new object[]{ctx}),null);
    ctxT.GetProperty("CellsSwitch").SetValue(ctx,Activator.CreateInstance(Find(cd,"CellsSwitchClass"),new object[]{ctx}),null);
    ctxT.GetProperty("ExtComHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExtComHlpClass"),new object[]{ctx}),null);

    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,30f,null);
    string fp=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5\exp_wf.cor";
    ocpT.GetProperty("FilePath").SetValue(prm,fp,null);
    ocpT.GetProperty("FileName").SetValue(prm,"exp_wf",null);
    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    L("    ExpClass 就绪, 文件="+St(fp));
    var wfField=expT.GetField("writeFile",BindingFlags.Instance|BindingFlags.NonPublic);
    L("    writeFile 字段="+(wfField.GetValue(ec)==null?"NULL":"非空"));
    try{ expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null); }catch(Exception e){ L("    BeginStartWriteFile EXC "+(e.InnerException??e).Message); }
    L("    调用后 writeFile 字段="+(wfField.GetValue(ec)==null?"NULL":"非空")+", 文件="+St(fp));
    try{ expT.GetMethod("WriteContext",Type.EmptyTypes).Invoke(ec,null); L("    WriteContext OK, 文件="+St(fp)); }catch(Exception e){ L("    WriteContext EXC "+(e.InnerException??e).Message); }
    try{ expT.GetMethod("WriteDataNow",Type.EmptyTypes).Invoke(ec,null); L("    WriteDataNow OK, 文件="+St(fp)); }catch(Exception e){ L("    WriteDataNow EXC "+(e.InnerException??e).Message); }
    // 加一点数据再写
    try{
      expT.GetMethod("AddData").Invoke(ec,new object[]{-0.15,1e-10,0.0});
      L("    AddData OK");
      expT.GetMethod("WriteDataNow",Type.EmptyTypes).Invoke(ec,null);
      L("    再 WriteDataNow, 文件="+St(fp));
    }catch(Exception e){ L("    AddData 链 EXC "+(e.InnerException??e).Message); }
    w.Close(); Environment.Exit(0);
  }
}
