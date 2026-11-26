// t7: 唯一差异 —— 先置 ExpMethodState=SysRuning 再调 BeginStartWriteFile
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t7.log",false);
    string dir=@"D:\sci\MDI Jade 9";
    foreach(var n in new[]{"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"}){try{Assembly.LoadFrom(Path.Combine(dir,n));}catch{}}
    var bi=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.BaseInterface.dll"));
    var cd=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.CorrData.dll"));
    var ca=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.Connect.dll"));
    Type ctxT=null; foreach(var t in bi.GetTypes()) if(t.Name=="BaseContext"&&!t.IsAbstract){ctxT=t;break;}
    var ctx=Activator.CreateInstance(ctxT);
    var connT=ca.GetType("CSStudio6.Connect.Com.SockectConnect"); var conn=Activator.CreateInstance(connT);
    L("open="+connT.GetMethod("Open",new[]{typeof(string)}).Invoke(conn,new object[]{"127.0.0.1:31001"}));
    ca.GetType("CSStudio6.Connect.Base.IConnect").GetMethod("CheckPackReceiveThread").Invoke(conn,null);
    ctxT.GetMethod("SetConnect").Invoke(ctx,new object[]{conn});

    Type prmT=null; foreach(var t in cd.GetTypes()) if(t.Name=="OcpParams"){prmT=t;break;}
    var prm=Activator.CreateInstance(prmT);
    prmT.GetProperty("baseContext").SetValue(prm,ctx,null);
    prmT.GetProperty("FileName").SetValue(prm,"t7_ocp",null);
    prmT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t7\t7_ocp.cor",null);
    ctxT.GetProperty("BaseParam").SetValue(ctx,prm,null);
    ctxT.GetProperty("ThisExp").SetValue(ctx,Enum.Parse(bi.GetType("CSStudio6.BaseInterface.enums.Experiment"),"ID_OCP"));

    var msT=bi.GetType("CSStudio6.BaseInterface.enums.MethodState");
    ctxT.GetProperty("ExpMethodState").SetValue(ctx,Enum.Parse(msT,"SysRuning"));
    L("ExpMethodState="+ctxT.GetProperty("ExpMethodState").GetValue(ctx,null));

    var m=ctxT.GetMethod("BeginStartWriteFile");
    Exception err=null;
    var th=new Thread(()=>{try{m.Invoke(ctx,new object[]{false});}catch(Exception e){err=e;}});
    th.IsBackground=true; th.Start();
    if(!th.Join(8000)) L("HUNG >8s  ==> SysRuning 是写盘阻塞的根因！");
    else if(err!=null) L("EXC "+(err.InnerException!=null?err.InnerException.Message:err.Message));
    else L("OK");
    string f=@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t7\t7_ocp.cor";
    L("file exists="+File.Exists(f)+" size="+(File.Exists(f)?new FileInfo(f).Length:0));
    w.Close(); Environment.Exit(0);
  }
}
