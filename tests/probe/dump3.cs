using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name;return string.Join(", ",s);}
  static void Main(){
    string dir=@"D:\sci\MDI Jade 9";
    string[] need={"CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll","CSStudio6.MathHlp.dll","CSStudio6.NetUtility.dll","CSStudio6.Language.dll","CSStudio6.SysLog.dll","CSStudio6.USControl.dll","CSStudio6.NetSkin.dll"};
    var asms=new List<Assembly>(); foreach(var n in need){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir,n)));}catch{}}
    var bi=asms[0]; var cd=asms[1];
    L("=== IBaseParams ===");
    foreach(var t in bi.GetTypes()) if(t.Name=="IBaseParams"){ foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
      foreach(var m in t.GetMethods()) if(m.Name.IndexOf("get_")!=0&&m.Name.IndexOf("set_")!=0) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")"); }
    L("\n=== BaseParams class (CorrData) ===");
    Type bp=null; foreach(var t in cd.GetTypes()) if(t.Name=="BaseParams") bp=t;
    L("base="+bp.FullName+" abstract="+bp.IsAbstract);
    foreach(var p in bp.GetProperties(BindingFlags.Public|BindingFlags.Instance)) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro"));
    foreach(var m in bp.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)) if(m.Name.IndexOf("get_")!=0&&m.Name.IndexOf("set_")!=0) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")");
    L("\n=== enums ===");
    foreach(var nm in new[]{"VsType","MethodState"}){
      foreach(var t in bi.GetTypes()) if(t.Name==nm&&t.IsEnum){ L(nm+":"); foreach(var n in Enum.GetNames(t)) L("   "+n+"="+Convert.ToInt32(Enum.Parse(t,n))); }
      foreach(var a in asms) foreach(var t in a.GetTypesSafe()) if(t.Name==nm&&t.IsEnum){ L(nm+" ("+a.GetName().Name+"):"); foreach(var n in Enum.GetNames(t)) L("   "+n+"="+Convert.ToInt32(Enum.Parse(t,n))); }
    }
    L("\n=== IExpComSend ===");
    foreach(var t in bi.GetTypes()) if(t.Name=="IExpComSend"){ foreach(var m in t.GetMethods()) L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")"); }
    L("\n=== ZDataItem ===");
    foreach(var t in bi.GetTypes()) if(t.Name=="ZDataItem"){ foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name+" "+(p.CanWrite?"rw":"ro")); }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump3.txt",sb.ToString()); Environment.Exit(0);
  }
}
static class Ext { public static IEnumerable<Type> GetTypesSafe(this Assembly a){ try{return a.GetTypes();}catch{return new Type[0];} } }
