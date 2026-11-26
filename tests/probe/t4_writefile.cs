// t4: 单独验证 U1 —— BeginStartWriteFile 在无 MainFrm 时是否可用（独立进程，防连带崩）
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading;
class T {
  static StreamWriter w;
  static void L(string s){ w.WriteLine(s); w.Flush(); }
  static void Main(string[] a){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t4.log", false);
    string dir=@"D:\sci\MDI Jade 9";
    foreach(var n in new[]{"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"}) { try{Assembly.LoadFrom(Path.Combine(dir,n));}catch{} }
    var bi=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.BaseInterface.dll"));
    var cd=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.CorrData.dll"));
    var connAsm=Assembly.LoadFrom(Path.Combine(dir,"CSStudio6.Connect.dll"));
    Type ctxT=null; foreach(var t in bi.GetTypes()) if(t.Name=="BaseContext"&&!t.IsAbstract){ctxT=t;break;}
    var ctx=Activator.CreateInstance(ctxT);
    var connT=connAsm.GetType("CSStudio6.Connect.Com.SockectConnect");
    var conn=Activator.CreateInstance(connT);
    L("open="+connT.GetMethod("Open",new[]{typeof(string)}).Invoke(conn,new object[]{"127.0.0.1:31001"}));
    var iface=connAsm.GetType("CSStudio6.Connect.Base.IConnect"); var cprt=iface.GetMethod("CheckPackReceiveThread"); L("cprt="+(cprt!=null)); cprt.Invoke(conn,null); L("cprt ok");
    ctxT.GetMethod("SetConnect").Invoke(ctx,new object[]{conn});
    L("connected");
    Type prmT=null; foreach(var t in cd.GetTypes()) if(t.Name=="OcpParams"){prmT=t;break;}
    var prm=Activator.CreateInstance(prmT);
    foreach(var pn in new[]{"baseContext","BaseContext"}){var p=prmT.GetProperty(pn); if(p!=null&&p.CanWrite){p.SetValue(prm,ctx,null);L("hooked "+pn);break;}}
    prmT.GetProperty("FileName").SetValue(prm,"t4_ocp",null);
    prmT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\t4\t4_ocp.cor",null);
    ctxT.GetProperty("BaseParam").SetValue(ctx,prm,null);
    ctxT.GetProperty("ThisExp").SetValue(ctx, Enum.Parse(bi.GetType("CSStudio6.BaseInterface.enums.Experiment"),"ID_OCP"));
    L("params ready");

    // 关键：在工作线程里调 BeginStartWriteFile，主线程 3s 超时判定 => 不卡死整个探针
    Exception err=null; bool done=false;
    var th=new Thread(()=>{ try{ ctxT.GetMethod("BeginStartWriteFile").Invoke(ctx,new object[]{false}); }catch(Exception e){err=e;} finally{done=true;} });
    th.IsBackground=true; th.Start();
    if(!th.Join(5000)) L("BeginStartWriteFile HUNG >5s (U1 = 不可用/需窗体)");
    else L("BeginStartWriteFile returned, err="+(err==null?"none":err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message));
    L("done flag="+done);
    string f=prmT.GetProperty("FilePath").GetValue(prm).ToString();
    L("file exists="+File.Exists(f)+" size="+(File.Exists(f)?new FileInfo(f).Length:0));
    w.Close();
    Environment.Exit(0);
  }
}
