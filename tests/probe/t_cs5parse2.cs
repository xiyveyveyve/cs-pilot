// t_cs5parse2.cs -- 核心解析器反汇编 + CS6 修正对照 + 包类型结构
//
// 前情（t_cs5parse.txt）：
//   - CorrCom.dll(CS5) 是混淆壳：SendReturnBool* stub = 00 00 17 2A (return true)，SendReturnPackage = 00 00 14 2A (return null)
//     → S3 NRE 根源：GetOcpValue 拿到 null 包继续解析
//   - GetVoltValue = GetBaseVoltValue → clamp ±10 → *ExtAmpData.VotCoefficient
//   - CS6 程序集名是 CSStudio6.*（Connect/CorrData/BaseInterface...），不是 CorrTest.*
//
// 本探针：
//   PART1  核心解析器：GetBaseVoltValue / GetBaseCurrValue（CS5 完整反汇编）
//   PART2  S4 依赖链：SendMethodParams / GetMethodBytes / GetDoubleChannelSampleBytes（完整 hex）
//   PART3  S3 链：GetOcpValue / ReadOcpBytes / AutoSwitchVoltRangeForOcp
//   PART4  包类型字段：RecePackage / CorrPackage / CSTPackage（CS5）
//   PART5  CS6 对照：SendReturnBool* / SendReturnPackage / GetBaseVoltValue / GetOcpValue（CSStudio6.*）
// 输出：logs/t_cs5parse2.txt
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

static class P5b {
  const string D5 = @"D:\sci\CS Studio5\CS Studio5";
  const string D6 = @"D:\sci\MDI Jade 9";
  static readonly string[] DLLS5 = new string[] {
    "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
    "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
    "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll",
    "CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"
  };
  static readonly string[] DLLS6 = new string[] {
    "CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll",
    "CSStudio6.CorrForm.dll","CSStudio6.Analysis.dll","CSStudio6.MathHlp.dll",
    "CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.NetUtility.dll",
    "CSStudio6.SysLog.dll","CSStudio6.ExtModule.dll","CSStudio6.Language.dll"
  };
  static StringBuilder S = new StringBuilder();
  static void L(string s){ S.AppendLine(s); }
  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }

  static string Sig(MethodBase m){
    var ps=m.GetParameters(); var arr=new string[ps.Length];
    for(int i=0;i<ps.Length;i++) arr[i]=ps[i].ParameterType.Name+" "+ps[i].Name;
    return m.Name+"("+string.Join(", ",arr)+")";
  }

  static int ILLen(byte op){
    switch(op){
      case 0x1F: return 2;
      case 0x20: case 0x22: return 5;
      case 0x21: case 0x23: return 9;
      case 0x2B: case 0x2C: case 0x2D: case 0x2E: case 0x2F: case 0x30: case 0x31: case 0x32:
      case 0x33: case 0x34: case 0x35: case 0x36: case 0x37: return 2;
      case 0x38: case 0x39: case 0x3A: case 0x3B: case 0x3C: case 0x3D: case 0x3E: case 0x3F:
      case 0x40: case 0x41: case 0x42: case 0x43: case 0x44: return 5;
      case 0x45: return -1;
      case 0x27: case 0x28: case 0x29: case 0x6F: case 0x73: case 0x7B: case 0x7C: case 0x7D:
      case 0x7E: case 0x7F: case 0x72: case 0x74: case 0x75: case 0x79: case 0x8C: case 0xA5:
      case 0xD0: case 0xC6: return 5;
      case 0xFE: return -2;
    }
    return 1;
  }
  static string TokName(byte op){
    switch(op){ case 0x28:return "call"; case 0x6F:return "callvirt"; case 0x73:return "newobj";
    case 0x7B:return "ldfld"; case 0x7C:return "ldflda"; case 0x7D:return "stfld"; case 0x7E:return "ldsfld";
    case 0x7F:return "stsfld"; case 0x72:return "ldstr"; case 0x74:return "castclass"; case 0x75:return "isinst";
    case 0x79:return "unbox"; case 0x8C:return "box"; case 0xA5:return "unbox.any"; case 0xD0:return "ldtoken"; case 0x27:return "jmp";}
    return op.ToString("X2");
  }

  static void Disasm(MethodBase m, string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" : (no body)"); return; }
    byte[] il=null; try{il=body.GetILAsByteArray();}catch{}
    if(il==null){ L(tag+" : (il null)"); return; }
    string lv="";
    try{ foreach(var v in body.LocalVariables) lv+=v.LocalType.Name+" "; }catch{}
    L(tag+"  IL="+il.Length+"B maxstack="+body.MaxStackSize+" locals=["+lv+"]");
    if(il.Length<=160) L("   HEX: "+BitConverter.ToString(il).Replace("-"," "));
    int i=0;
    while(i<il.Length){
      byte op=il[i];
      if(op==0xFE){
        if(i+1>=il.Length) break;
        byte op2=il[i+1];
        int len;
        if(op2==0x06||op2==0x07||op2==0x14||op2==0x1A) len=6;
        else if(op2==0x09||op2==0x0A||op2==0x0B||op2==0x0C||op2==0x0D||op2==0x0E||op2==0x15) len=4;
        else len=2;
        if(len==6&&i+6<=il.Length){
          int tk=BitConverter.ToInt32(il,i+2);
          string nm="?";
          try{ var mem=m.Module.ResolveMember(tk); nm=(mem==null?"?":(mem.DeclaringType==null?"":mem.DeclaringType.Name+".")+mem.Name); }catch{}
          L("  +"+i+" FE"+op2.ToString("X2")+" -> "+nm);
        }
        i+=len; continue;
      }
      if(op==0x45){
        if(i+5>il.Length) break;
        int n=BitConverter.ToInt32(il,i+1);
        L("  +"+i+" switch n="+n);
        i+=5+4*n; continue;
      }
      int len2=ILLen(op);
      if(len2==5&&i+5<=il.Length){
        int tk=BitConverter.ToInt32(il,i+1);
        string nm;
        try{ MemberInfo mem=m.Module.ResolveMember(tk);
          nm=mem==null?"<null>":((mem.DeclaringType==null?"":mem.DeclaringType.Name+".")+mem.Name);
        }catch(Exception e){ nm="<x:"+e.GetType().Name+">"; }
        L("  +"+i+" "+TokName(op)+" -> "+nm);
        i+=5; continue;
      }
      if(len2==2&&i+2<=il.Length){ L("  +"+i+" "+op.ToString("X2")+" sbr "+il[i+1]); i+=2; continue; }
      if(len2>=3){ if(i+len2>il.Length) break; i+=len2; continue; }
      i+=1;
    }
  }

  static int Main(){
    var A5=new List<Assembly>(); var A6=new List<Assembly>();
    foreach(var n in DLLS5){ string p=Path.Combine(D5,n); if(File.Exists(p)){try{A5.Add(Assembly.LoadFrom(p));}catch{}} }
    foreach(var n in DLLS6){ string p=Path.Combine(D6,n); if(File.Exists(p)){try{A6.Add(Assembly.LoadFrom(p));}catch{}} }
    L("CS5 asms="+A5.Count+"  CS6 asms="+A6.Count);
    var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static|BindingFlags.DeclaredOnly;

    // ---------- PART1: GetBaseVoltValue / GetBaseCurrValue ----------
    L(""); L("########## PART1: 核心解析器（CS5）##########");
    string[] p1 = new string[]{"GetBaseVoltValue","GetBaseCurrValue"};
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){
        bool hit=false; for(int k=0;k<p1.Length;k++) if(m.Name==p1[k]){hit=true;break;}
        if(!hit) continue;
        Disasm(m,"[P1] "+Sig(m)+" @ "+t.Name);
      }
    }

    // ---------- PART2: S4 依赖链 ----------
    L(""); L("########## PART2: SendMethodParams 依赖链（CS5）##########");
    string[] p2 = new string[]{"SendMethodParams","GetMethodBytes","GetDoubleChannelSampleBytes"};
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){
        bool hit=false; for(int k=0;k<p2.Length;k++) if(m.Name==p2[k]){hit=true;break;}
        if(!hit) continue;
        Disasm(m,"[P2] "+Sig(m)+" @ "+t.Name);
      }
    }

    // ---------- PART3: S3 链 ----------
    L(""); L("########## PART3: GetOcpValue 链（CS5）##########");
    string[] p3 = new string[]{"GetOcpValue","ReadOcpBytes","AutoSwitchVoltRangeForOcp"};
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){
        bool hit=false; for(int k=0;k<p3.Length;k++) if(m.Name==p3[k]){hit=true;break;}
        if(!hit) continue;
        Disasm(m,"[P3] "+Sig(m)+" @ "+t.Name);
      }
    }

    // ---------- PART4: 包类型字段 ----------
    L(""); L("########## PART4: 包类型结构（CS5）##########");
    string[] pk = new string[]{"RecePackage","CorrPackage","CSTPackage"};
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      bool hit=false; for(int k=0;k<pk.Length;k++) if(t.Name==pk[k]){hit=true;break;}
      if(!hit) continue;
      L("[P4] === "+t.FullName+" @ "+a.GetName().Name+" ===");
      foreach(var f in t.GetFields(bf)) L("  F "+f.FieldType.Name+" "+f.Name);
      foreach(var p in t.GetProperties(bf)) L("  P "+p.PropertyType.Name+" "+p.Name);
      foreach(var ctor in t.GetConstructors(bf)){ var cps=ctor.GetParameters(); var arr=new string[cps.Length];
        for(int i=0;i<cps.Length;i++) arr[i]=cps[i].ParameterType.Name; L("  C ("+string.Join(", ",arr)+")"); }
    }

    // ---------- PART5: CS6 对照 ----------
    L(""); L("########## PART5: CS6 对照 ##########");
    string[] p5 = new string[]{"SendReturnBool","SendReturnBoolThree","SendReturnPackage","GetBaseVoltValue","GetOcpValue","GetVoltValue"};
    foreach(var a in A6) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){
        bool hit=false; for(int k=0;k<p5.Length;k++) if(m.Name==p5[k]){hit=true;break;}
        if(!hit) continue;
        MethodBody b=null; try{b=m.GetMethodBody();}catch{}
        int iln=(b==null)?-1:b.GetILAsByteArray().Length;
        if(iln<0||iln>700) continue; // 壳stub(-1)或超长跳过细节
        if(iln<=16){ Disasm(m,"[P5] "+Sig(m)+" @ "+t.Name+"  (SHORT!)"); continue; }
        Disasm(m,"[P5] "+Sig(m)+" @ "+t.Name);
      }
    }

    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5parse2.txt",S.ToString());
    Console.WriteLine("done chars="+S.Length);
    return 0;
  }
}
