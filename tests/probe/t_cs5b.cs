// t_cs5b.cs —— CS5 BaseContext 构造是否阻塞（超时隔离）
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5b.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n)); }catch{}
    }
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;

    // A) 纯构造，10s 超时
    object ctx=null; Exception err=null;
    var th=new Thread(()=>{ try{ ctx=Activator.CreateInstance(ctxT); }catch(Exception e){ err=e; } });
    th.IsBackground=true; th.Start();
    bool joined=th.Join(10000);
    L("[A] BaseContext 构造 joined="+joined+" err="+(err==null?"none":(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)));

    if(joined && ctx!=null){
      // B) 再试 ExpClass 构造
      Type expT=null; foreach(var t in Types(cd)) if(t.Name=="ExpClass") expT=t;
      object ec=null; Exception e2=null;
      var th2=new Thread(()=>{ try{ ec=Activator.CreateInstance(expT); }catch(Exception e){ e2=e; } });
      th2.IsBackground=true; th2.Start();
      bool j2=th2.Join(10000);
      L("[B] ExpClass 构造 joined="+j2+" err="+(e2==null?"none":(e2.InnerException!=null?e2.InnerException.GetType().Name+": "+e2.InnerException.Message:e2.Message)));
      if(j2 && ec!=null){
        try{
          var p=expT.GetProperty("baseContext");
          L("[C] baseContext 可写="+(p!=null&&p.CanWrite));
          if(p!=null&&p.CanWrite){ p.SetValue(ec,ctx,null); L("    反挂 ctx OK"); }
        }catch(Exception e){ L("[C] 反挂失败: "+(e.InnerException!=null?e.InnerException.Message:e.Message)); }
        try{
          var ac=ctxT.GetProperty("ActiveExpClass");
          L("[D] ActiveExpClass 可写="+(ac!=null&&ac.CanWrite));
          if(ac!=null&&ac.CanWrite){ ac.SetValue(ctx,ec,null); L("    赋值 OK → "+ctxT.GetProperty("ActiveExpClass").GetValue(ctx,null)); }
        }catch(Exception e){ L("[D] 赋值失败: "+(e.InnerException!=null?e.InnerException.Message:e.Message)); }
      }
    } else {
      L("[B] 跳过（A 未返回）");
    }
    L("结束");
    w.Close(); Environment.Exit(0);
  }
}
