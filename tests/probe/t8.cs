// t8: 复现宿主的真实时序 —— GetSerialNumber 真的挂起被放弃(残留阻塞线程) -> BeginStartWriteFile
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t8.log",false);
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
    prmT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t8\t8_ocp.cor",null);
    prmT.GetProperty("FileName").SetValue(prm,"t8_ocp",null);
    ctxT.GetProperty("BaseParam").SetValue(ctx,prm,null);
    ctxT.GetProperty("ThisExp").SetValue(ctx,Enum.Parse(bi.GetType("CSStudio6.BaseInterface.enums.Experiment"),"ID_OCP"));

    Type sendT=null; foreach(var t in bi.GetTypes()) if(t.Name=="ExpComSendClass") sendT=t;
    var send=Activator.CreateInstance(sendT,new object[]{ctx});
    ctxT.GetProperty("ExpComSend").SetValue(ctx,send,null);

    // 连续 3 个探测，每个 3s 超时后放弃（完全照搬宿主）
    foreach(var mn in new[]{"GetSerialNumber","GetPstType","GetRomVersion"}){
      var t1=new Thread(()=>{ try{ var r=sendT.GetMethod(mn).Invoke(send,null); L("  "+mn+" returned '"+(r==null?"<null>":r)+"'"); }catch(Exception e){ L("  "+mn+" EXC "+(e.InnerException!=null?e.InnerException.Message:e.Message)); } });
      t1.IsBackground=true; t1.Start();
      bool j=t1.Join(3000);
      L(mn+" joined="+j+" alive_after="+t1.IsAlive);
      Thread.Sleep(200);
    }
    L("alive thread count="+AliveCount());

    // 现在测写盘
    var m=ctxT.GetMethod("BeginStartWriteFile");
    Exception err=null;
    var th=new Thread(()=>{try{m.Invoke(ctx,new object[]{false});}catch(Exception e){err=e;}});
    th.IsBackground=true; th.Start();
    if(!th.Join(8000)) L("RESULT: HUNG >8s ==> 泄漏的探测线程阻塞了写盘（假设成立）");
    else if(err!=null) L("RESULT: EXC "+(err.InnerException!=null?err.InnerException.Message:err.Message));
    else L("RESULT: OK（假设不成立）");
    w.Close(); Environment.Exit(0);
  }
  static int AliveCount(){ int n=0; foreach(var p in System.Diagnostics.Process.GetCurrentProcess().Threads) n++; return n; }
}
