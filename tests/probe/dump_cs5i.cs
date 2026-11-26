using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string P(MethodBase m){var ps=m.GetParameters();var s=new string[ps.Length];for(int i=0;i<ps.Length;i++)s[i]=ps[i].ParameterType.Name+" "+ps[i].Name+(ps[i].IsOut?" [out]":"");return string.Join(", ",s);}
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n)));}catch{}}
    // ExpComSendClass 全部方法（CS5 控制面）
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="ExpComSendClass") continue;
      L("=== "+t.FullName+" ===");
      foreach(var c in t.GetConstructors()) L("  C("+P(c)+")");
      foreach(var m in t.GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly)){
        if(m.Name.StartsWith("get_")||m.Name.StartsWith("set_")) continue;
        byte[] il=null; try{ il=m.GetMethodBody()!=null?m.GetMethodBody().GetILAsByteArray():null; }catch{}
        L("  M "+m.ReturnType.Name+" "+m.Name+"("+P(m)+")  IL="+(il==null?"?":il.Length+"B"));
      }
    }
    // Experiment 枚举（CS5 实值）
    foreach(var a in asms) foreach(var t in Types(a)){
      if(t==null||t.Name!="Experiment"||!t.IsEnum) continue;
      L("\n=== CS5 Experiment 枚举 ("+a.GetName().Name+") ===");
      var names=Enum.GetNames(t);
      foreach(var n in new[]{"ID_OCP","ID_PotDynamic","ID_AnyPotStatic","ID_EISVSFRQ"}){
        bool has=false; foreach(var x in names) if(x==n){has=true;break;}
        if(has) L("  "+n+"="+Convert.ToInt32(Enum.Parse(t,n)));
      }
      L("  总项数="+Enum.GetNames(t).Length);
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5i.txt",sb.ToString()); Environment.Exit(0);
  }
}
