using System;
using System.IO;
using System.Reflection;
using System.Text;
using System.Collections.Generic;
class D {
  static StringBuilder sb = new StringBuilder();
  static void L(string s){ sb.AppendLine(s); }
  static string P(MethodBase m){ var ps=m.GetParameters(); var s=new string[ps.Length]; for(int i=0;i<ps.Length;i++) s[i]=ps[i].ParameterType.Name+" "+ps[i].Name; return string.Join(", ",s); }
  static void Main(){
    string dir = @"D:\sci\MDI Jade 9";
    string[] need = {"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll",
                     "CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll",
                     "CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"};
    var asms = new List<Assembly>();
    foreach(var n in need){ try{ asms.Add(Assembly.LoadFrom(Path.Combine(dir,n))); }catch{} }
    var bi = asms[0]; var cd = asms[1];
    L("=== BaseContext ===");
    var ctx = bi.GetType("CSStudio6.BaseInterface.Context.BaseContext");
    foreach(var m in ctx.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) if(m.Name.IndexOf("get_")!=0&&m.Name.IndexOf("set_")!=0) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
    foreach(var p in ctx.GetProperties(BindingFlags.Public|BindingFlags.Instance)) L("  P "+p.PropertyType.Name+" "+p.Name+" ro="+(p.CanWrite?"rw":"ro"));
    foreach(var c in ctx.GetConstructors()) L("  C ("+P(c)+")");
    L("\n=== ExpComSendClass ===");
    Type send=null; foreach(var t in bi.GetTypes()) if(t.Name=="ExpComSendClass") send=t;
    L("type="+send.FullName+" abstract="+send.IsAbstract);
    foreach(var m in send.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) if(m.Name.IndexOf("get_")!=0) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
    foreach(var c in send.GetConstructors()) L("  C ("+P(c)+")");
    L("\n=== IDataItem ===");
    Type di=null; foreach(var t in bi.GetTypes()) if(t.Name=="IDataItem") di=t;
    if(di!=null){ foreach(var m in di.GetMethods()) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
      foreach(var p in di.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name); }
    L("\n=== BaseParams classes (Ocp/PotDynamic/EISVSfrq/PotSquare) ===");
    foreach(var t in cd.GetTypes()) if(t.IsPublic&&(t.Name=="OcpParams"||t.Name=="PotDynamicParams"||t.Name=="EISVSfrqParams"||t.Name=="PotSquareParams")){
      L("CLASS "+t.FullName+" base="+t.BaseType.Name);
      foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
    }
    L("\n=== CorrPackage ===");
    var cp = asms[2].GetType("CSStudio6.Connect.Base.CorrPackage");
    if(cp!=null){ foreach(var p in cp.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
      foreach(var c in cp.GetConstructors()) L("  C ("+P(c)+")"); }
    L("\n=== Experiment enum ===");
    foreach(var t in bi.GetTypes()) if(t.Name=="Experiment"&&t.IsEnum){
      L("name="+t.FullName);
      foreach(var n in Enum.GetNames(t)) if(n=="ID_OCP"||n=="ID_PotDynamic"||n=="ID_EISVSFRQ"||n=="ID_AnyPotStatic") L("  "+n+"="+(int)Enum.Parse(t,n));
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump2.txt", sb.ToString());
    Environment.Exit(0);
  }
}
