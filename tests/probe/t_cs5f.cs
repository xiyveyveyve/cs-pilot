// t_cs5f.cs —— 找 CS5 连接注入路径：GetCom/RetCom/InitCom/_com 字段
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string Try(Func<object> f,int ms){ Exception err=null; object res=null;
    var th=new Thread(()=>{try{res=f();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start();
    bool ok=th.Join(ms);
    return (ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"HANG>"+ms)
      + (res!=null?" → "+Preview(res):""); }
  static string Preview(object o){ try{ var l=o as System.Collections.IList; if(l!=null) return "List["+l.Count+"]"; return o.ToString(); }catch{ return "<obj>"; } }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5f.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    Type sockT=null; foreach(var t in Types(cc)) if(t.Name=="SockectCom") sockT=t;

    object ctx=Activator.CreateInstance(ctxT);
    L("[a] ctx 建好");
    var comField=ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic);
    L("[b] _com 初始="+(comField==null?"无字段":(comField.GetValue(ctx)==null?"NULL":"非空")));

    L("[c] GetCom(): "+Try(()=>ctxT.GetMethod("GetCom").Invoke(ctx,null),5000));
    L("[d] InitCom(): "+Try(()=>ctxT.GetMethod("InitCom").Invoke(ctx,null),8000));
    L("[e] InitCom 后 _com="+(comField.GetValue(ctx)==null?"NULL":"非空"));
    L("[f] InitCom 后 GetCom(): "+Try(()=>ctxT.GetMethod("GetCom").Invoke(ctx,null),5000));

    // 手工注入：直接写 _com 私有字段
    object com=null;
    L("[g] 建连接: "+Try(()=>{com=Activator.CreateInstance(sockT);
        sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31033"}); return com;},10000));
    if(com!=null && comField!=null){
      L("[h] 写 _com 字段: "+Try(()=>{comField.SetValue(ctx,com); return null;},3000));
      L("[i] 写后 GetCom(): "+Try(()=>ctxT.GetMethod("GetCom").Invoke(ctx,null),5000));
      // 看 ExpClass 能否构造了
      var cd=asms["CorrTest.CorrData.dll"];
      Type expT=null; foreach(var t in Types(cd)) if(t.Name=="ExpClass") expT=t;
      Type ocpT=null; foreach(var t in Types(cd)) if(t.Name=="OcpParams") ocpT=t;
      object prm=Activator.CreateInstance(ocpT);
      try{ ocpT.GetProperty("baseContext").SetValue(prm,ctx,null); L("[j] 反挂 OK"); }
      catch(Exception e){ L("[j] 反挂失败: "+(e.InnerException!=null?e.InnerException.GetType().Name+": "+e.InnerException.Message:e.Message)); }
      L("[k] ExpClass(ctx,prm): "+Try(()=>Activator.CreateInstance(expT,new object[]{ctx,prm}),10000));
    }
    w.Close(); Environment.Exit(0);
  }
}
