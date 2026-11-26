using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class D {
  static StringBuilder sb=new StringBuilder(); static void L(string s){sb.AppendLine(s);}
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Main(){
    string d5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new List<Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms.Add(Assembly.LoadFrom(Path.Combine(d5,n)));}catch{}}
    foreach(var a in asms){
      Type cp=null;
      foreach(var t in Types(a)) if(t!=null&&t.Name=="CommandPackage"){cp=t;break;}
      if(cp==null) continue;
      L("=== "+cp.FullName+" (asm="+a.GetName().Name+") ===");
      L("-- 静态字段（字节模板）--");
      foreach(var f in cp.GetFields(BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)){
        object v=null; try{v=f.GetValue(null);}catch{}
        string hex="";
        var ba=v as byte[];
        if(ba!=null) hex=BitConverter.ToString(ba).Replace("-"," ");
        L("  F "+f.FieldType.Name+" "+f.Name+" = "+(hex.Length>0?hex:Convert.ToString(v)));
      }
      L("-- 静态方法 --");
      foreach(var m in cp.GetMethods(BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.DeclaredOnly))
        L("  M "+m.ReturnType.Name+" "+m.Name+"("+m.GetParameters().Length+"参)");
      break;
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\dump_cs5k.txt",sb.ToString()); Environment.Exit(0);
  }
}
