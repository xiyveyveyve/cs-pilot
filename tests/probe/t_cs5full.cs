// t_cs5full.cs —— CS5 完整装配验证：连接 → BaseContext → ExpClass → 参数 → 落盘
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static bool Guard(Action a, int ms, string tag){ Exception err=null; var th=new Thread(()=>{try{a();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start(); bool ok=th.Join(ms); L("    ["+tag+"] "+(ok?(err==null?"OK":"EXC "+(err.InnerException!=null?err.InnerException.GetType().Name+": "+err.InnerException.Message:err.Message)):"卡住 >"+ms+"ms")); return ok && err==null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5full.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n)); }catch{} }
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];
    Func<Assembly,string,Type> F=(a,n)=>{ foreach(var t in Types(a)) if(t.Name==n) return t; return null; };

    Type ctxT=F(ci,"BaseContext"), sockT=F(cc,"SockectCom"), expT=F(cd,"ExpClass"), ocpT=F(cd,"OcpParams");
    object com=null, ctx=null, ec=null, prm=null;

    L("[1] 连接");
    if(!Guard(()=>{ com=Activator.CreateInstance(sockT); sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31033"}); },10000,"ctor+Open")) { w.Close(); Environment.Exit(0); }
    L("    IsOpen="+sockT.GetMethod("IsOpen").Invoke(com,null));
    Guard(()=>{ var st=sockT.GetMethod("StartThread"); if(st!=null) st.Invoke(com,null); },5000,"StartThread");

    L("[2] BaseContext");
    if(!Guard(()=>{ ctx=Activator.CreateInstance(ctxT); },10000,"ctor")) { w.Close(); Environment.Exit(0); }
    // 把连接塞进 ctx（CS5 无 SetConnect，看有没有 baseContext/Com 相关）
    L("    GetCom()="+(ctxT.GetMethod("GetCom").Invoke(ctx,null)==null?"NULL":"非空"));

    L("[3] 参数对象");
    if(!Guard(()=>{ prm=Activator.CreateInstance(ocpT); },5000,"OcpParams ctor")) { w.Close(); Environment.Exit(0); }
    Guard(()=>{ ocpT.GetProperty("baseContext").SetValue(prm,ctx,null); },3000,"反挂");
    Guard(()=>{ ocpT.GetProperty("TestTime").SetValue(prm,30f,null); },3000,"TestTime");
    Guard(()=>{ ocpT.GetProperty("FileName").SetValue(prm,"cs5_ocp",null); },3000,"FileName");
    Guard(()=>{ ocpT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5\cs5_ocp.cor",null); },3000,"FilePath");
    object fp=ocpT.GetProperty("FilePath").GetValue(prm,null); L("    FilePath="+fp);

    L("[4] ExpClass(ctx, prm)");
    if(!Guard(()=>{ ec=Activator.CreateInstance(expT,new object[]{ctx,prm}); },10000,"ExpClass ctor")) { w.Close(); Environment.Exit(0); }
    Guard(()=>{ ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null); },3000,"挂 ActiveExpClass");
    L("    ActiveExpClass="+(ctxT.GetProperty("ActiveExpClass").GetValue(ctx,null)==null?"NULL":"非空"));

    L("[5] 落盘 BeginStartWriteFile");
    string f=(string)fp;
    if(Guard(()=>{ expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null); },8000,"BeginStartWriteFile")){
      L("    文件存在="+File.Exists(f)+" 大小="+(File.Exists(f)?new FileInfo(f).Length:0));
    }
    L("[6] 数据集合");
    foreach(var pn in new[]{"TimeList","VoltList","CurrList"}){
      var p=expT.GetProperty(pn);
      if(p==null){ L("    "+pn+" 无此属性"); continue; }
      var lst=p.GetValue(ec,null); L("    "+pn+"="+(lst==null?"NULL":(lst as System.Collections.IList).Count.ToString()));
    }
    Guard(()=>{ expT.GetMethod("EndWriteFile",Type.EmptyTypes).Invoke(ec,null); },5000,"EndWriteFile");
    w.Close(); Environment.Exit(0);
  }
}
