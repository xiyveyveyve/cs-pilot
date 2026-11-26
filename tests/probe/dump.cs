using System;
using System.IO;
using System.Reflection;
using System.Text;
class D {
  static StringBuilder sb = new StringBuilder();
  static void L(string s){ sb.AppendLine(s); }
  static void Main(string[] a){
    string dir = @"D:\sci\MDI Jade 9";
    string[] need = {"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll",
                     "CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll",
                     "CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"};
    var asms = new System.Collections.Generic.List<Assembly>();
    foreach(var n in need){ try{ asms.Add(Assembly.LoadFrom(Path.Combine(dir,n))); L("LOAD "+n+" ok"); }catch(Exception e){ L("LOAD "+n+" FAIL "+e.Message);} }
    L("PF64="+Environment.Is64BitProcess);
    // 1. Connect 实现类
    L("\n=== Connect types ===");
    foreach(var t in asms[2].GetTypes()) if(t.IsPublic && t.Name.IndexOf("Connect")>=0) L("  "+t.FullName+" abstract="+t.IsAbstract);
    L("\n=== IConnect interface ===");
    foreach(var t in asms[2].GetTypes()) if(t.Name=="IConnect"||t.Name=="SockectConnect"||t.Name=="SerialConnect"){
      L("TYPE "+t.FullName);
      foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) L("  M "+m.ReturnType.Name+" "+m.Name+"("+Params(m)+")");
      foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name);
      foreach(var c in t.GetConstructors()) L("  C ("+Params(c)+")");
    }
    // 2. cs5
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    try{ var a5=Assembly.LoadFrom(Path.Combine(dir5,"CorrTest.CorrCom.dll")); L("\nLOAD CS5 CorrCom ok");
      foreach(var t in a5.GetTypes()) if(t.IsPublic && (t.Name=="SockectCom"||t.Name.IndexOf("Sockect")>=0||t.Name=="IConnect")){
        L("CS5 TYPE "+t.FullName);
        foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) L("  M "+m.ReturnType.Name+" "+m.Name+"("+Params(m)+")");
        foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name);
        foreach(var c in t.GetConstructors()) L("  C ("+Params(c)+")");
      }
    }catch(Exception e){ L("LOAD CS5 FAIL "+e.Message); }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump1.txt", sb.ToString());
    Environment.Exit(0);
  }
  static string Params(MethodBase m){ var ps=m.GetParameters(); var s=new string[ps.Length]; for(int i=0;i<ps.Length;i++) s[i]=ps[i].ParameterType.Name+" "+ps[i].Name; return string.Join(", ",s); }
}
