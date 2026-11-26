// t_cs5k.cs —— CS5 端到端：装配 → 下发 → 启动 → 收数 → 落盘
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static string Try(Func<object> f,int ms,string tag){
    Exception err=null; object res=null;
    var th=new Thread(()=>{try{res=f();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start();
    bool ok=th.Join(ms);
    string s=(ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"HANG>"+ms);
    if(res!=null) s+=" → "+res;
    L("    ["+tag+"] "+s);
    return s;
  }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5k.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom");

    L("[1] 装配");
    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    L("    Open="+sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31033"}));
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    object pp=Activator.CreateInstance(Find(cd,"ParsingParamsClass"));
    ctxT.GetProperty("ParsingParms").SetValue(ctx,pp,null);
    ctxT.GetProperty("ParsingParmsAux").SetValue(ctx,Activator.CreateInstance(Find(cd,"ParsingParamsClass")),null);
    ctxT.GetProperty("ExpTimeHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpTimeHlpClass")),null);
    ctxT.GetProperty("ExpParamsBytes").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpParamsBytesClass"),new object[]{pp}),null);
    ctxT.GetProperty("ExpComSend").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExpComSendClass"),new object[]{ctx}),null);
    ctxT.GetProperty("CellsSwitch").SetValue(ctx,Activator.CreateInstance(Find(cd,"CellsSwitchClass"),new object[]{ctx}),null);
    ctxT.GetProperty("ExtComHlp").SetValue(ctx,Activator.CreateInstance(Find(cd,"ExtComHlpClass"),new object[]{ctx}),null);
    L("    ctx 装配完成");

    L("[2] 参数");
    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,30f,null);
    ocpT.GetProperty("TestTimeUnit").SetValue(prm,1,null);
    ocpT.GetProperty("FileName").SetValue(prm,"cs5k_ocp",null);
    string fp=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5\cs5k_ocp.cor";
    ocpT.GetProperty("FilePath").SetValue(prm,fp,null);
    L("    FilePath="+ocpT.GetProperty("FilePath").GetValue(prm,null));

    L("[3] ExpClass");
    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null);
    ctxT.GetProperty("CurExp").SetValue(ctx,Enum.Parse(Find(ci,"Experiment"),"ID_OCP"),null);
    L("    ExpClass 就绪");

    L("[4] 落盘");
    Try(()=>{expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},8000,"BeginStartWriteFile");
    L("    文件存在="+File.Exists(fp)+" 大小="+(File.Exists(fp)?new FileInfo(fp).Length:0));

    L("[5] 下发+启动");
    var send=ctxT.GetProperty("ExpComSend").GetValue(ctx,null);
    var sendT=send.GetType();
    L("    ExpComSend 实现类="+sendT.FullName);
    foreach(var m in sendT.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly))
      if(m.Name.Contains("Start")||m.Name.Contains("Stop")||m.Name.Contains("InitExp")) L("      有方法 "+m.Name+"("+m.GetParameters().Length+"参)");
    w.Close(); Environment.Exit(0);
  }
}
