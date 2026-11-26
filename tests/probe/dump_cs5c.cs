using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){
      try{ asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n))); }catch{}
    }
    L("=== IExpClass 的实现类 ===");
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.IsInterface||t.IsAbstract) continue;
      bool impl=false;
      try{ foreach(var i in t.GetInterfaces()) if(i.Name=="IExpClass"){impl=true;break;} }catch{}
      if(impl) L("  "+a.GetName().Name+" :: "+t.FullName);
    }
    L("\n=== 所有 ExpClass 名字含 Exp 的类 ===");
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||!t.IsPublic) continue;
      if(t.Name.EndsWith("ExpClass")||t.Name.Contains("ActiveExp"))
        L("  "+a.GetName().Name+" :: "+t.FullName+" iface="+t.IsInterface+" abstract="+t.IsAbstract);
    }
    L("\n=== SockectCom 构造 + 关键方法（CS5 网口连接）===");
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="SockectCom") continue;
      L("  "+t.FullName);
      foreach(var c in t.GetConstructors()) L("    C ("+string.Join(", ",Array.ConvertAll(c.GetParameters(),p=>p.ParameterType.Name+" "+p.Name))+")");
    }
    L("\n=== BaseContext 是否有 InitCom 参数重载 / SetConnect ===");
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="BaseContext") continue;
      foreach(var m in t.GetMethods()) if(m.Name.Contains("InitCom")||m.Name.Contains("SetConnect")||m.Name.Contains("GetCom")||m.Name.Contains("RetCom"))
        L("  "+m.Name+"("+string.Join(", ",Array.ConvertAll(m.GetParameters(),p=>p.ParameterType.Name+" "+p.Name))+")");
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5c.txt", sb.ToString());
    Environment.Exit(0);
  }
}
