// t_cs5.cs —— CS5 纯代码宿主可行性首探（独立进程 + 自我保护）
using System; using System.IO; using System.Reflection; using System.Text; using System.Threading; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n)); L("LOAD "+n+" OK"); }catch(Exception e){ L("LOAD "+n+" FAIL "+e.GetType().Name+": "+e.Message); }
    }
    var ci=asms["CorrTest.CorrInterface.dll"]; var cd=asms["CorrTest.CorrData.dll"]; var cc=asms["CorrTest.CorrCom.dll"];

    // 1) 连接（网口）
    Type sockT=null; foreach(var t in Types(cc)) if(t.Name=="SockectCom") sockT=t;
    L("\n[1] SockectCom="+(sockT==null?"NULL":sockT.FullName));
    object com=null;
    try{
      com=Activator.CreateInstance(sockT);
      var open=sockT.GetMethod("Open",new[]{typeof(string)});
      L("    Open('127.0.0.1:31031') = "+open.Invoke(com,new object[]{"127.0.0.1:31031"}));
      L("    IsOpen = "+sockT.GetMethod("IsOpen").Invoke(com,null));
      var st=sockT.GetMethod("StartThread");
      if(st!=null){ st.Invoke(com,null); L("    StartThread OK"); }
    }catch(Exception e){ L("    连接失败: "+(e.InnerException!=null?e.InnerException.GetType().Name+": "+e.InnerException.Message:e.Message)); }

    // 2) BaseContext 装配
    Type ctxT=null; foreach(var t in Types(ci)) if(t.Name=="BaseContext") ctxT=t;
    L("\n[2] BaseContext="+(ctxT==null?"NULL":ctxT.FullName));
    object ctx=null;
    try{
      ctx=Activator.CreateInstance(ctxT);
      L("    ctor OK");
      foreach(var pn in new[]{"IsDefaultContext","Enable","IsDemoMode"}){
        var p=ctxT.GetProperty(pn); if(p!=null&&p.CanWrite){ try{ p.SetValue(ctx,true,null); L("    "+pn+"=true"); }catch(Exception e){ L("    "+pn+" set 失败"); } }
      }
    }catch(Exception e){ L("    ctor 失败: "+(e.InnerException!=null?e.InnerException.Message:e.Message)); }

    // 3) ExpClass 能否构造
    L("\n[3] ExpClass");
    foreach(var t in Types(cd)){
      if(t==null||t.Name!="ExpClass") continue;
      L("    type="+t.FullName);
      foreach(var c in t.GetConstructors()) L("      C ("+P(c)+")");
      try{
        var ec=Activator.CreateInstance(t);
        L("      无参构造 OK");
      }catch(Exception e){ L("      构造失败: "+(e.InnerException!=null?e.InnerException.Message:e.Message)); }
    }

    // 4) 参数类
    L("\n[4] CS5 参数类");
    foreach(var t in Types(cd)){
      if(t==null||!t.IsPublic) continue;
      if(t.Name=="OcpParams"||t.Name=="PotDynamicParams"||t.Name=="PotSquareParams"||t.Name=="EISVSfrqParams"||t.Name=="BaseParams"){
        L("    "+t.FullName+" base="+(t.BaseType==null?"-":t.BaseType.Name));
        try{ var inst=Activator.CreateInstance(t); L("      构造 OK"); }catch(Exception e){ L("      构造失败: "+(e.InnerException!=null?e.InnerException.Message:e.Message)); }
      }
    }
    w.Close(); Environment.Exit(0);
  }
}
