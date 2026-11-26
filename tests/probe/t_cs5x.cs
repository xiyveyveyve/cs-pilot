// t_cs5x.cs —— 查 BeginStartWriteFile 之后 writeFile 字段的真实路径
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static object GF(object o,string n){ var t=o.GetType(); var f=t.GetField(n,BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public); return f==null?null:f.GetValue(o); }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5x.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"]; var cm=asms["CorrTest.CorrModules.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom"), wfT=Find(cm,"WriteFile");

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
    string fp=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5\exp_wf2.cor";
    ocpT.GetProperty("FilePath").SetValue(prm,fp,null);
    ocpT.GetProperty("FileName").SetValue(prm,"exp_wf2",null);
    L("FilePath 属性="+ocpT.GetProperty("FilePath").GetValue(prm,null));
    L("FileName 属性="+ocpT.GetProperty("FileName").GetValue(prm,null));

    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null);

    object wf=GF(ec,"writeFile");
    L("\nwriteFile 对象="+(wf==null?"NULL":wf.GetType().FullName));
    if(wf!=null){
      L("--- WriteFile 全部字段值 ---");
      foreach(var f in wf.GetType().GetFields(BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public)){
        object v=null; try{ v=f.GetValue(wf); }catch{}
        string sv;
        try{ sv = v==null?"NULL":(v is System.Collections.IList?("List["+((System.Collections.IList)v).Count+"]"):v.ToString()); }catch{ sv="<obj>"; }
        L("   "+f.FieldType.Name+" "+f.Name+" = "+sv);
      }
    }
    L("\n--- 目录 contents ---");
    string d=Path.GetDirectoryName(fp);
    try{ foreach(var x in Directory.GetFiles(d)) L("   "+Path.GetFileName(x)+" ("+new FileInfo(x).Length+" B)"); }catch(Exception e){ L("   读取失败 "+e.Message); }

    // 强制刷盘
    L("\n--- 强制 WriteDataToFile ---");
    if(wf!=null){
      try{ wfT.GetMethod("WriteDataToFile").Invoke(wf,null); L("   WriteDataToFile OK, 文件="+(File.Exists(fp)?new FileInfo(fp).Length+" B":"不存在")); }
      catch(Exception e){ L("   EXC "+(e.InnerException??e).GetType().Name+": "+(e.InnerException??e).Message); }
    }
    // EndWriteFile 后再看
    try{ expT.GetMethod("EndWriteFile",Type.EmptyTypes).Invoke(ec,null); L("\nEndWriteFile OK, 文件="+(File.Exists(fp)?new FileInfo(fp).Length+" B":"不存在")); }
    catch(Exception e){ L("\nEndWriteFile EXC "+(e.InnerException??e).Message); }
    w.Close(); Environment.Exit(0);
  }
}
