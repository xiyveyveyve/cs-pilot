// t_cs5c.cs —— 验证 CS5 BaseContext 构造卡住的条件
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static bool Try(Action a,int ms,out string why){ Exception err=null; var th=new Thread(()=>{try{a();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start(); bool ok=th.Join(ms); why=ok?(err==null?"OK":(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"卡住>"+ms+"ms"; return ok&&err==null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5c.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var ci=asms["CorrTest.CorrInterface.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    string why;

    // A) 第 1 个实例（无连接）
    L("[A] 无连接 第1次: "+(Try(()=>{Activator.CreateInstance(ctxT);},8000,out why)?why:why));

    // B) 建连接后再造第 2 个
    Type sockT=null; foreach(var t in Types(cc)) if(t.Name=="SockectCom") sockT=t;
    object com=null;
    bool cok=Try(()=>{ com=Activator.CreateInstance(sockT); sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31032"}); sockT.GetMethod("StartThread").Invoke(com,null); },10000,out why);
    L("[B] 建连接: "+(cok?why:why));

    // C) 有连接时造第 2 个 ctx（不带 MainFrm）
    Action mk=()=>{Activator.CreateInstance(ctxT);};
    L("[C] 有连接 第2次: "+(Try(mk,8000,out why)?why:why));
    L("    再试一次(第3次): "+(Try(mk,8000,out why)?why:why));

    // D) 看构造器签名
    L("[D] BaseContext 构造器:");
    foreach(var c in ctxT.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance))
      L("    C("+string.Join(", ",Array.ConvertAll(c.GetParameters(),p=>p.ParameterType.Name+" "+p.Name))+") public="+c.IsPublic);

    // E) 看是否有静态字段缓存（重复构造卡住的常见原因）
    L("[E] 静态字段:");
    foreach(var f in ctxT.GetFields(BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)) L("    F "+f.FieldType.Name+" "+f.Name);
    w.Close(); Environment.Exit(0);
  }
}
