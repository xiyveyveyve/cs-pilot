// t_cs5io.cs —— 验证 BaseIO 补全后 InitExp/StartMethod 是否通过
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
using System.Threading;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Dictionary<string,Assembly> A=new Dictionary<string,Assembly>();
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type F(string n){ foreach(var a in A.Values) foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static string TR(Func<object> f,int ms,out object res){
    Exception err=null; object r=null;
    var th=new Thread(()=>{try{r=f();}catch(Exception e){err=e;}}); th.IsBackground=true; th.Start();
    bool ok=th.Join(ms); res=r;
    if(!ok) return "HANG>"+ms;
    if(err!=null){ var ie=err is TargetInvocationException&&err.InnerException!=null?err.InnerException:err; return "EXC "+ie.GetType().Name+": "+ie.Message; }
    return "OK";
  }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5io.log",false);
    string d5=@"D:\sci\CS Studio5\CS Studio5";
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{A[n]=Assembly.LoadFrom(Path.Combine(d5,n));}catch{}}
    Type ctxT=F("BaseContext"), ocpT=F("OcpParams"), expT=F("ExpClass"), sockT=F("SockectCom"), expEnum=F("Experiment");

    object ctx=Activator.CreateInstance(ctxT);
    object com=Activator.CreateInstance(sockT);
    object res;
    L("[1] Open="+sockT.GetMethod("Open",new[]{typeof(string)}).Invoke(com,new object[]{"127.0.0.1:31080"}));
    ctxT.GetField("_com",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(ctx,com);
    object pp; TR(()=>Activator.CreateInstance(F("ParsingParamsClass")),5000,out pp);
    ctxT.GetProperty("ParsingParms").SetValue(ctx,pp,null);
    ctxT.GetProperty("ParsingParmsAux").SetValue(ctx,Activator.CreateInstance(F("ParsingParamsClass")),null);
    ctxT.GetProperty("ExpTimeHlp").SetValue(ctx,Activator.CreateInstance(F("ExpTimeHlpClass")),null);
    ctxT.GetProperty("ExpParamsBytes").SetValue(ctx,Activator.CreateInstance(F("ExpParamsBytesClass"),new object[]{pp}),null);
    object send; TR(()=>Activator.CreateInstance(F("ExpComSendClass"),new object[]{ctx}),5000,out send);
    ctxT.GetProperty("ExpComSend").SetValue(ctx,send,null);
    ctxT.GetProperty("CellsSwitch").SetValue(ctx,Activator.CreateInstance(F("CellsSwitchClass"),new object[]{ctx}),null);
    ctxT.GetProperty("ExtComHlp").SetValue(ctx,Activator.CreateInstance(F("ExtComHlpClass"),new object[]{ctx}),null);
    var edhF=ctxT.GetField("ExtDevHlp",BindingFlags.Instance|BindingFlags.Public);
    if(edhF!=null) edhF.SetValue(ctx,Activator.CreateInstance(F("ExtDevHlpClass"),new object[]{ctx}));
    L("[2] ctx 装配完成");

    object prm=Activator.CreateInstance(ocpT);
    ocpT.GetProperty("baseContext").SetValue(prm,ctx,null);
    ocpT.GetProperty("TestTime").SetValue(prm,20f,null);
    ocpT.GetProperty("TestTimeUnit").SetValue(prm,1,null);
    ocpT.GetProperty("FilePath").SetValue(prm,@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\data\cs5run\io_echo",null);
    ocpT.GetProperty("FileName").SetValue(prm,"io_echo",null);
    ocpT.GetProperty("ExpType").SetValue(prm,Enum.Parse(expEnum,"ID_OCP"),null);
    ctxT.GetProperty("CurExp").SetValue(ctx,Enum.Parse(expEnum,"ID_OCP"),null);

    // ★ 关键：补 BaseIO
    L("\n[3] BaseIO 现状");
    var bioP=ocpT.GetProperty("BaseIO");
    object bio=null; TR(()=>{bio=bioP.GetValue(prm,null);return bio;},3000,out res);
    L("    prm.BaseIO="+(bio==null?"NULL":"非空("+bio.GetType().Name+")"));
    if(bio==null){
      Type bioT=F("BaseIOClass");
      L("    BaseIOClass 构造器: "+string.Join(" | ",Array.ConvertAll(bioT.GetConstructors(),c=>"("+string.Join(",",Array.ConvertAll(c.GetParameters(),p=>p.ParameterType.Name))+")")));
      // 试 3 种：null byte[]、64 零、16 零
      foreach(var len in new[]{0,16,64}){
        string r=TR(()=>{var inst=Activator.CreateInstance(bioT,new object[]{new byte[len]}); bioP.SetValue(prm,inst,null); return inst;},5000,out res);
        L("    byte["+len+"] → "+r+" "+(res!=null?" 实例="+res.GetType().Name:""));
        if(r=="OK" && res!=null){ bio=res; break; }
      }
    }
    // DevParam.BaseIO 也要补
    var devP=ocpT.GetProperty("DevParam");
    object dev=null; try{dev=devP.GetValue(prm,null);}catch{}
    if(dev!=null && bio!=null){
      try{ var dbo=dev.GetType().GetProperty("BaseIO"); if(dbo!=null){ dbo.SetValue(dev,bio,null); L("    DevParam.BaseIO ← 同一实例 OK"); } }catch(Exception e){ L("    DevParam.BaseIO 失败 "+e.Message); }
    }

    object ec; string r2=TR(()=>Activator.CreateInstance(expT,new object[]{ctx,prm}),8000,out ec);
    L("\n[4] ExpClass → "+r2);
    if(r2!="OK"){ w.Close(); Environment.Exit(0); }
    ctxT.GetProperty("ActiveExpClass").SetValue(ctx,ec,null);
    TR(()=>{expT.GetMethod("BeginStartWriteFile",Type.EmptyTypes).Invoke(ec,null);return null;},6000,out res);

    var sendT=send.GetType();
    L("[5] InitExp → "+TR(()=>sendT.GetMethod("InitExp").Invoke(send,new object[]{prm}),12000,out res));
    object[] sa=new object[]{prm,true,false,""};
    L("[6] StartMethod → "+TR(()=>sendT.GetMethod("StartMethod").Invoke(send,sa),20000,out res)+" ret="+res+" err='"+sa[3]+"'");

    Thread.Sleep(4000);
    try{
      var tL=expT.GetProperty("TimeList").GetValue(ec,null) as System.Collections.IList;
      var vL=expT.GetProperty("VoltList").GetValue(ec,null) as System.Collections.IList;
      L("[7] 数据 Time="+(tL==null?-1:tL.Count)+" Volt="+(vL==null?-1:vL.Count));
    }catch{}
    TR(()=>sendT.GetMethod("SendSysStop").Invoke(send,null),8000,out res);
    w.Close(); Environment.Exit(0);
  }
}
