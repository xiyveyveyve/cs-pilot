// t6: 验证假设 —— 探测(GetSerialNumber)超时残留线程是否会把后续 BeginStartWriteFile 拖死
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t6.log",false);
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

    Type prmT=null; foreach(var t in cd.GetTypes()) if(t.Name=="OcpParams"){prmT=t;break;}
    var prm=Activator.CreateInstance(prmT);
    prmT.GetProperty("baseContext").SetValue(prm,ctx,null);
    prmT.GetProperty("FileName").SetValue(prm,"t6_ocp",null);
    prmT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t6\t6_ocp.cor",null);
    ctxT.GetProperty("BaseParam").SetValue(ctx,prm,null);
    ctxT.GetProperty("ThisExp").SetValue(ctx,Enum.Parse(bi.GetType("CSStudio6.BaseInterface.enums.Experiment"),"ID_OCP"));

    // === 模拟宿主的探测：起 SendReturnPackage 类调用 + 3s 超时放弃 ===
    Type sendT=null; foreach(var t in bi.GetTypes()) if(t.Name=="ExpComSendClass") sendT=t;
    var send=Activator.CreateInstance(sendT,new object[]{ctx});
    ctxT.GetProperty("ExpComSend").SetValue(ctx,send,null);
    L("--- probe GetSerialNumber (3s guard, will be abandoned) ---");
    var th=new Thread(()=>{ try{ var r=sendT.GetMethod("GetSerialNumber").Invoke(send,null); L("  GetSN returned '"+r+"'"); }catch(Exception e){ L("  GetSN EXC "+(e.InnerException!=null?e.InnerException.Message:e.Message)); } });
    th.IsBackground=true; th.Start();
    L("  joined="+th.Join(3000)+" (false=abandoned, thread still blocked)");
    L("  thread alive after abandon="+th.IsAlive);

    // === 关键：现在调 BeginStartWriteFile ===
    L("--- BeginStartWriteFile after abandoned probe ---");
    var m=ctxT.GetMethod("BeginStartWriteFile");
    Exception err=null;
    var th2=new Thread(()=>{try{m.Invoke(ctx,new object[]{false});}catch(Exception e){err=e;}});
    th2.IsBackground=true; th2.Start();
    if(!th2.Join(8000)) L("  HUNG >8s  ==> 假设成立：探测残留线程阻塞了写盘");
    else if(err!=null) L("  EXC "+(err.InnerException!=null?err.InnerException.Message:err.Message));
    else L("  OK（假设不成立）");
    w.Close(); Environment.Exit(0);
  }
}
