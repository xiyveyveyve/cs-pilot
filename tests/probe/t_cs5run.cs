// t_cs5run.cs —— CS5 启动链路 + 数据入库验证
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
    string s=ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"HANG>"+ms;
    if(res!=null) s+=" → "+res;
    L("    ["+tag+"] "+s); return s;
  }
  static int Count(object o){ var l=o as System.Collections.IList; return l==null?-1:l.Count; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5run.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom");

    // --- 装配 ---
    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    L("[1] Open="+sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31040"}));
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
    L("[2] ctx 装配完成");

    // --- 参数 ---
    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,20f,null);
    ocpT.GetProperty("TestTimeUnit").SetValue(prm,1,null);
    string baseName=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5run\cs5run_ocp";
    ocpT.GetProperty("FilePath").SetValue(prm,baseName,null);
    ocpT.GetProperty("FileName").SetValue(prm,"cs5run_ocp",null);
    var expEnum=Find(ci,"Experiment");
    ocpT.GetProperty("ExpType").SetValue(prm,Enum.Parse(expEnum,"ID_OCP"),null);
    ctxT.GetProperty("CurExp").SetValue(ctx,Enum.Parse(expEnum,"ID_OCP"),null);
    L("[3] 参数就绪 FilePath="+ocpT.GetProperty("FilePath").GetValue(prm,null));

    // --- ExpClass ---
    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null);
    L("[4] ExpClass 就绪");

    // --- 落盘 ---
    Try(()=>{expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},8000,"BeginStartWriteFile");
    L("    文件="+(File.Exists(baseName)?new FileInfo(baseName).Length+" B":"不存在"));

    // --- 启动 ---
    var sendT=send.GetType();
    Try(()=>sendT.GetMethod("InitExp").Invoke(send,new object[]{prm}),15000,"InitExp");
    // StartMethod(IBaseParams, bool, bool, ref string)
    Try(()=>{
      object[] a=new object[]{prm,true,false,""};
      var r=sendT.GetMethod("StartMethod").Invoke(send,a);
      return "ret="+r+" sError='"+a[3]+"'";
    },20000,"StartMethod");

    // --- 采集 ---
    L("[5] 采集 8 秒");
    var tList=expT.GetProperty("TimeList"); var vList=expT.GetProperty("VoltList"); var cList=expT.GetProperty("CurrList");
    for(int k=1;k<=4;k++){
      Thread.Sleep(2000);
      object t0=tList.GetValue(ec,null), v0=vList.GetValue(ec,null), c0=cList.GetValue(ec,null);
      L("    T+"+(k*2)+"s Time="+Count(t0)+" Volt="+Count(v0)+" Curr="+Count(c0));
    }
    // --- 停止 ---
    Try(()=>sendT.GetMethod("SendSysStop").Invoke(send,null),10000,"SendSysStop");
    Try(()=>{expT.GetMethod("EndWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},8000,"EndWriteFile");
    L("[6] 最终文件="+(File.Exists(baseName)?new FileInfo(baseName).Length+" B":"不存在"));
    w.Close(); Environment.Exit(0);
  }
}
