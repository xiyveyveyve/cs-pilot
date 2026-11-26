// t_cs5il3.cs -- 反汇编 GetDoubleChannelSampleBytes / GetMethodBytes / GetOcpValue
using System; using System.Collections.Generic; using System.IO; using System.Reflection; using System.Text;
static class Il3 {
  const string D=@"D:\sci\CS Studio5\CS Studio5";
  static readonly string[] N={"CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll","CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll","CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
  static readonly List<Assembly> A=new List<Assembly>(); static readonly StringBuilder S=new StringBuilder();
  static void L(string s){S.AppendLine(s);}
  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static void Dump(Type t,string n,BindingFlags bf){
    MethodInfo m=null; foreach(var x in t.GetMethods(bf)) if(x.Name==n){m=x;break;}
    if(m==null) return;
    var b=m.GetMethodBody(); if(b==null) return;
    var il=b.GetILAsByteArray();
    L(""); L("=== "+t.Name+"."+n+"  IL="+il.Length+"B ===");
    int i=0;
    while(i<il.Length){
      byte op=il[i];
      if(op==0x28||op==0x6F||op==0x73||op==0x7B||op==0x7E||op==0x72||op==0x74||op==0x8C||op==0x7D||op==0x6E){
        int tk=BitConverter.ToInt32(il,i+1); string nm;
        try{ var mem=m.Module.ResolveMember(tk,t.GetGenericArguments(),m.GetGenericArguments());
          nm=mem==null?"<null>":((mem.DeclaringType==null?"":mem.DeclaringType.Name+".")+mem.Name); }
        catch(Exception e){ nm="<x:"+e.GetType().Name+">"; }
        string o=op==0x28?"call":op==0x6F?"callvirt":op==0x73?"newobj":op==0x7B?"ldfld":op==0x7E?"ldsfld":op==0x72?"ldstr":op==0x74?"castclass":op==0x7D?"stfld":op==0x6E?"box":"?";
        L("  +"+i+" "+o+" -> "+nm); i+=5; continue;
      }
      i++;
    }
  }
  static int Main(){
    foreach(var n in N){ var p=Path.Combine(D,n); if(File.Exists(p)){ try{A.Add(Assembly.LoadFrom(p));}catch{} } }
    var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
    L("=== 目标方法实现位置 ===");
    foreach(var mn in new[]{"GetDoubleChannelSampleBytes","GetOcpValue","GetMethodBytes","AutoSwitchVoltRangeForOcp","SendMethodInit"}){
      bool any=false;
      foreach(var a in A) foreach(var t in T(a)){
        if(t==null) continue;
        MethodInfo[] ms; try{ ms=t.GetMethods(bf|BindingFlags.DeclaredOnly); }catch{ continue; }
        foreach(var m in ms){
          if(m.Name!=mn) continue;
          var b=m.GetMethodBody(); int len=-1; try{ len=b==null?-1:b.GetILAsByteArray().Length; }catch{}
          L("  "+mn+" -> "+t.FullName+" IL="+len+"B"); any=true;
        }
      }
      if(!any) L("  "+mn+" -> 未找到");
    }
    L(""); L("=== IL 反汇编 ===");
    foreach(var a in A) foreach(var t in T(a)){
      if(t==null) continue;
      if(t.Name=="OcpParams"||t.Name=="BaseParams"){
        Dump(t,"GetDoubleChannelSampleBytes",bf);
        Dump(t,"GetOcpValue",bf);
        Dump(t,"GetMethodBytes",bf);
      }
      if(t.Name=="PublicMethod") Dump(t,"AutoSwitchVoltRangeForOcp",bf);
    }
    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5il3.log",S.ToString());
    Console.WriteLine(S.ToString()); Environment.Exit(0); return 0;
  }
}
