// t_cs5v.cs —— 反查 SendRotatingSpeed 的 IL，找它访问 ctx 哪些成员
using System; using System.IO; using System.Reflection; using System.Text; using System.Collections.Generic;
class T {
  static StreamWriter w; static void L(string s){ w.WriteLine(s); w.Flush(); }
  static Type[] Types(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static Type Find(Assembly a,string n){ foreach(var t in Types(a)) if(t!=null&&t.Name==n) return t; return null; }
  static void Main(){
    w=new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5v.log",false);
    string dir5=@"D:\sci\CS Studio5\CS Studio5";
    var asms=new Dictionary<string,Assembly>();
    foreach(var n in new[]{"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"}){try{asms[n]=Assembly.LoadFrom(Path.Combine(dir5,n));}catch{}}
    var cd=asms["CorrTest.CorrData.dll"];
    Type esT=Find(cd,"ExpComSendClass");
    var m=esT.GetMethod("SendRotatingSpeed");
    var body=m.GetMethodBody();
    var il=body.GetILAsByteArray();
    L("SendRotatingSpeed IL "+il.Length+" B");
    var mod=m.Module;
    // 简易 IL 走查：找 call/callvirt/newobj + 字符串/token
    int i=0;
    while(i<il.Length){
      byte op=il[i];
      try{
        if(op==0x28||op==0x6F||op==0x73||op==0x7B||op==0x7E||op==0x72||op==0x74||op==0x8C){
          int tok=BitConverter.ToInt32(il,i+1);
          string nm="?";
          try{
            var mem=mod.ResolveMember(tok, esT.GetGenericArguments(), m.GetGenericArguments());
            if(mem!=null) nm=mem.DeclaringType.Name+"."+mem.Name;
          }catch(Exception e){ nm="resolve fail: "+e.GetType().Name; }
          string opn = op==0x28?"call":op==0x6F?"callvirt":op==0x73?"newobj":op==0x7B?"ldfld":op==0x7E?"ldsfld":op==0x72?"ldstr":op==0x74?"castclass":"box";
          L("  +"+i+" "+opn+" → "+nm);
          i+=5; continue;
        }
      }catch{}
      i++;
    }
    w.Close(); Environment.Exit(0);
  }
}
