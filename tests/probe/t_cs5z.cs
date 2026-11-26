// t_cs5z.cs —— 补 ExtDevHlp 后走完整启动链
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static int Cnt(object o){ var l=o as System.Collections.IList; return l==null?-1:l.Count; }
  static string T2(Func<object> f,int ms,string tag){
    Exception err=null; object res=null;
    var th=new Thread(()=>{try{res=f();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start();
    bool ok=th.Join(ms);
    string s=ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"HANG>"+ms;
    if(res!=null) s+=" → "+res;
    L("    ["+tag+"] "+s); return s;
  }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5z.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=Find(ci,"BaseContext"), ocpT=Find(cd,"OcpParams"), expT=Find(cd,"ExpClass"), sockT=Find(cc,"SockectCom");

    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    L("[1] Open="+sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31042"}));
    var stM=sockT.GetMethod("StartThread"); if(stM!=null){ stM.Invoke(com,null); L("    StartThread OK"); }
    System.Threading.Thread.Sleep(300);
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

    // ★ 关键：补 ExtDevHlp 公有字段
    var edhField=ctxT.GetField("ExtDevHlp",BindingFlags.Instance|BindingFlags.Public);
    L("[2] ExtDevHlp 字段="+(edhField==null?"无":edhField.FieldType.Name));
    if(edhField!=null){
      Type edhT=Find(ci,"ExtDevHlpClass");
      object edh=Activator.CreateInstance(edhT,new object[]{ctx});
      edhField.SetValue(ctx,edh);
      L("    ExtDevHlp 注入 OK → IsSpeedMode()="+edhT.GetMethod("IsSpeedMode").Invoke(edh,null)+" IsTempMode()="+edhT.GetMethod("IsTempMode").Invoke(edh,null));
    }

    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,20f,null);
    ocpT.GetProperty("TestTimeUnit").SetValue(prm,1,null);
    string bn=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5run\zz2_ocp";
    ocpT.GetProperty("FilePath").SetValue(prm,bn,null);
    ocpT.GetProperty("FileName").SetValue(prm,"zz2_ocp",null);
    var expEnum=Find(ci,"Experiment");
    ocpT.GetProperty("ExpType").SetValue(prm,Enum.Parse(expEnum,"ID_OCP"),null);
    ctxT.GetProperty("CurExp").SetValue(ctx,Enum.Parse(expEnum,"ID_OCP"),null);
    L("[3] 参数就绪 FilePath="+ocpT.GetProperty("FilePath").GetValue(prm,null));

    object ec=Activator.CreateInstance(expT,new object[]{ctx,prm});
    ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null);
    var sendT=send.GetType();
    L("[4] ExpClass 就绪");

    T2(()=>{expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},8000,"BeginStartWriteFile");
    L("    文件="+(File.Exists(bn)?new FileInfo(bn).Length+" B":"不存在"));
    T2(()=>sendT.GetMethod("InitExp").Invoke(send,new object[]{prm}),15000,"InitExp");
    T2(()=>{ object[] a=new object[]{prm,true,false,""}; var r=sendT.GetMethod("StartMethod").Invoke(send,a); return "ret="+r+" err='"+a[3]+"'"; },25000,"StartMethod");

    L("[5] 采集");
    var tL=expT.GetProperty("TimeList"); var vL=expT.GetProperty("VoltList"); var cL=expT.GetProperty("CurrList");
    for(int k=1;k<=5;k++){
      Thread.Sleep(2000);
      L("    T+"+(k*2)+"s T="+Cnt(tL.GetValue(ec,null))+" V="+Cnt(vL.GetValue(ec,null))+" I="+Cnt(cL.GetValue(ec,null))+" 文件="+(File.Exists(bn)?new FileInfo(bn).Length+" B":"无"));
    }
    T2(()=>sendT.GetMethod("SendSysStop").Invoke(send,null),10000,"SendSysStop");
    T2(()=>{expT.GetMethod("EndWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},8000,"EndWriteFile");
    L("[6] 最终="+(File.Exists(bn)?new FileInfo(bn).Length+" B":"不存在"));
    if(File.Exists(bn)){ var ln=File.ReadAllLines(bn); L("    行数="+ln.Length); for(int i=Math.Max(0,ln.Length-4);i<ln.Length;i++) L("    | "+ln[i]); }
    w.Close(); Environment.Exit(0);
  }
}
