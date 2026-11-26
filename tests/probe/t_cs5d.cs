// t_cs5d.cs —— 定位 CS5 BaseContext 卡住的确切条件（逐项二分）
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string Try(Action a,int ms){ Exception err=null; object res=null;
    var th=new Thread(()=>{try{a();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start();
    bool ok=th.Join(ms); return ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"HANG>"+ms; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5d.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    Type sockT=null; foreach(var t in Types(cc)) if(t.Name=="SockectCom") sockT=t;

    // 步骤 1: 先建连接（模拟 t_cs5full 的顺序）
    object com=null;
    L("[1] ctor SockectCom: "+Try(()=>{com=Activator.CreateInstance(sockT);},5000));
    if(com!=null){
      L("[2] Open: "+Try(()=>{sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31032"});},8000));
      L("    IsOpen="+sockT.GetMethod("IsOpen").Invoke(com,null));
      L("[3] StartThread: "+Try(()=>{sockT.GetMethod("StartThread").Invoke(com,null);},5000));
    }
    // 步骤 4: 现在造 ctx（t_cs5full 就是死在这）
    object ctx=null;
    L("[4] BaseContext ctor: "+Try(()=>{ctx=Activator.CreateInstance(ctxT);},12000));
    if(ctx!=null){
      L("[5] GetCom: "+Try(()=>{var r=ctxT.GetMethod("GetCom").Invoke(ctx,null); L("    →"+(r==null?"NULL":"非空"));},5000));
    }
    L("结束");
    w.Close(); Environment.Exit(0);
  }
}
