using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(dir5,n)));}catch{}}
    foreach(var iface in new[]{"IBaseIO","IParsingParams","IExpComSend","ICellsSwitch","IExtComHlp","IExpParamsBytes","IExpTimeHlp"}){
      L("\n=== "+iface+" 的实现类 ===");
      bool found=false;
      foreach(var a in asms) foreach(var t in Types(a)){
        if(t==null||t.IsInterface||t.IsAbstract) continue;
        try{ foreach(var i in t.GetInterfaces()) if(i.Name==iface){ L("   "+a.GetName().Name+" :: "+t.FullName); found=true; break; } }catch{}
      }
      if(!found) L("   （无公开实现类）");
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5f.txt",sb.ToString()); Environment.Exit(0);
  }
}
