// t5: U1 深挖 —— BeginStartWriteFile 在 TCP + 已连接 + 已起收包线程下的行为
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t5.log",false);
    string dir=@"D:\sci\MDI Jade 9";
    foreach(var n in new[]{"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"}){try{Assembly.LoadFrom(Path.Combine(dir,n));}catch{}}
    var bi=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.BaseInterface.dll"));
    var cd=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.CorrData.dll"));
    var ca=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.Connect.dll"));
    Type ctxT=null; foreach(var t in bi.GetTypes()) if(t.Name=="BaseContext"&&!t.IsAbstract){ctxT=t;break;}
    var ctx=Activator.CreateInstance(ctxT);
    var connT=ca.GetType("CSStudio6.Connect.Com.SockectConnect"); var conn=Activator.CreateInstance(connT);
    L("open="+connT.GetMethod("Open",new[]{typeof(string)}).Invoke(conn,new object[]{"127.0.0.1:31001"}));
    var iface=ca.GetType("CSStudio6.Connect.Base.IConnect");
    iface.GetMethod("CheckPackReceiveThread").Invoke(conn,null);
    ctxT.GetMethod("SetConnect").Invoke(ctx,new object[]{conn});
    L("connected");

    // 关键实验：不提前调用任何东西，直接测 BeginStartWriteFile
    var m=ctxT.GetMethod("BeginStartWriteFile");
    L("--- test A: no baseParam set ---");
    TryCall(m,ctx,"A");

    Type prmT=null; foreach(var t in cd.GetTypes()) if(t.Name=="OcpParams"){prmT=t;break;}
    var prm=Activator.CreateInstance(prmT);
    prmT.GetProperty("baseContext").SetValue(prm,ctx,null);
    prmT.GetProperty("FileName").SetValue(prm,"t5_ocp",null);
    prmT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t5\t5_ocp.cor",null);
    ctxT.GetProperty("BaseParam").SetValue(ctx,prm,null);
    ctxT.GetProperty("ThisExp").SetValue(ctx,Enum.Parse(bi.GetType("CSStudio6.BaseInterface.enums.Experiment"),"ID_OCP"));
    L("--- test B: baseParam+thisExp set ---");
    TryCall(m,ctx,"B");

    L("--- ctx.MainFrm = " + (ctxT.GetProperty("MainFrm").GetValue(ctx,null)==null?"NULL":"set"));
    L("--- ctx.IsDemoMode = " + ctxT.GetProperty("IsDemoMode").GetValue(ctx,null));
    L("--- ctx.Enable = " + ctxT.GetProperty("Enable").GetValue(ctx,null));
    string f=Path.Combine(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t5","t5_ocp.cor");
    L("file exists="+File.Exists(f)+" size="+(File.Exists(f)?new FileInfo(f).Length:0));
    w.Close(); Environment.Exit(0);
  }
  static void TryCall(MethodInfo m, object ctx, string tag){
    Exception err=null;
    var th=new Thread(()=>{try{m.Invoke(ctx,new object[]{false});}catch(Exception e){err=e;}});
    th.IsBackground=true; th.Start();
    if(!th.Join(6000)) L(tag+" HUNG >6s");
    else if(err!=null) L(tag+" EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message+"\n"+err.InnerException.StackTrace:err.Message));
    else L(tag+" OK");
  }
}
