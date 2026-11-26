// t_cs5il.cs —— 反汇编 CS5 StartMethod / InitExp 的 IL，找它们访问的 ctx 成员
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(string n){ foreach(var a in _asms.Values) foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static Dictionary<string,Assembly> _asms=new Dictionary<string,Assembly>();
  static void Dump(string typeName, string methodName){
    Type t=Find(typeName);
    if(t==null){ L(typeName+" 未找到"); return; }
    var m=t.GetMethod(methodName);
    if(m==null){ L(typeName+"."+methodName+" 未找到"); return; }
    var body=m.GetMethodBody();
    if(body==null){ L(typeName+"."+methodName+" 无方法体"); return; }
    var il=body.GetILAsByteArray();
    L("\n=== "+typeName+"."+methodName+"  IL="+il.Length+" B ===");
    int i=0;
    while(i<il.Length){
      byte op=il[i];
      if(op==0x28||op==0x6F||op==0x73||op==0x7B||op==0x7E||op==0x72||op==0x74||op==0x8C||op==0x7D){
        int tok=BitConverter.ToInt32(il,i+1);
        string nm="?";
        try{
          var mem=m.Module.ResolveMember(tok, t.GetGenericArguments(), m.GetGenericArguments());
          if(mem!=null){
            var dt=mem.DeclaringType;
            nm=(dt==null?"":dt.Name+".")+mem.Name;
          }
        }catch(Exception e){ nm="<resolve:"+e.GetType().Name+">"; }
        string opn = op==0x28?"call":op==0x6F?"callvirt":op==0x73?"newobj":op==0x7B?"ldfld":op==0x7E?"ldsfld":op==0x72?"ldstr":op==0x74?"castclass":op==0x7D?"stfld":"box";
        L("  +"+i+" "+opn+" → "+nm);
        i+=5; continue;
      }
      i++;
    }
  }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5il.log",false);
    string d5=@"D:\sci\CS Studio5\CS Studio5";
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{_asms[n]=Assembly.LoadFrom(Path.Combine(d5,n));}catch{}}
    Dump("ExpComSendClass","InitExp");
    Dump("ExpComSendClass","StartMethod");
    w.Close(); Environment.Exit(0);
  }
}
