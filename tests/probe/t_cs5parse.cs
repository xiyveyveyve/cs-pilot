// t_cs5parse.cs -- 解析端反推应答格式 + CorrCom 壳侦查 + ICorrCom 成员清单
//
// 背景（2026-11-10 接替 zcode）：
//   S3 GetOcpValueAutoRange NRE = SendReturnPackage 返回 null → GetVoltValue 解引用挂
//   S4 SendMethodParams False   = SendReturnBoolThree 一直不认模拟器的 ACK
//   zcode 最后一轮发现 CorrCom 侧 SendReturnBool*/SendReturnPackage 全是 IL=4B（疑似壳），
//   而 CorrData 侧（OcpParams 等）反汇编正常 → 怀疑只有通信层被保护。
//
// 本探针四步：
//   PART1  CorrCom.dll 方法体大小分布（判断是否壳/伪实现）
//   PART2  SendReturnBool* / SendReturnPackage 原始 IL hex（CS5 vs CS6 对照）
//   PART3  ICorrCom 接口完整成员清单（为 mock ICorrCom 绕行做准备）
//   PART4  ParsingParams 解析端反汇编（CS5 + CS6 对照，反推应答帧格式）
//
// 输出：logs/t_cs5parse.txt
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

static class P5 {
  const string D5 = @"D:\sci\CS Studio5\CS Studio5";
  const string D6 = @"D:\sci\MDI Jade 9";
  static readonly string[] DLLS = new string[] {
    "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
    "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
    "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll",
    "CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"
  };
  static StringBuilder S = new StringBuilder();
  static void L(string s){ S.AppendLine(s); }
  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }

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

  static void Disasm(MethodInfo m, string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" : (no body)"); return; }
    byte[] il=null; try{il=body.GetILAsByteArray();}catch{}
    if(il==null){ L(tag+" : (il null)"); return; }
    string lv="";
    try{ foreach(var v in body.LocalVariables) lv+=v.LocalType.Name+" "; }catch{}
    L(tag+"  IL="+il.Length+"B maxstack="+body.MaxStackSize+" locals=["+lv+"]");
    if(il.Length<=96) L("   HEX: "+BitConverter.ToString(il).Replace("-"," "));
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
    foreach(var n in DLLS){ string p=Path.Combine(D5,n); if(File.Exists(p)){try{A5.Add(Assembly.LoadFrom(p));}catch{}} }
    foreach(var n in DLLS){ string p=Path.Combine(D6,n); if(File.Exists(p)){try{A6.Add(Assembly.LoadFrom(p));}catch{}} }
    L("CS5 asms="+A5.Count+"  CS6 asms="+A6.Count);
    var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static|BindingFlags.DeclaredOnly;

    // ---------- PART1: CorrCom 壳侦查 ----------
    L(""); L("########## PART1: CorrCom.dll 方法体大小分布 ##########");
    foreach(var a in A5){
      if(a.GetName().Name!="CorrTest.CorrCom") continue;
      int tot=0,big=0,small=0,nobody=0;
      var bigList=new List<string>();
      foreach(var t in T(a)){ if(t==null)continue;
        MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
        foreach(var m in ms){
          int len=-9; try{var b=m.GetMethodBody(); len=(b==null)?-1:b.GetILAsByteArray().Length;}catch{len=-9;}
          tot++;
          if(len<=0) nobody++;
          else if(len<=16) small++;
          else { big++; if(len>80&&bigList.Count<30) bigList.Add(t.Name+"."+m.Name+"("+m.GetParameters().Length+"p) "+len+"B"); }
        }
      }
      L("CorrCom: methods="+tot+" noBody/0="+nobody+" <=16B="+small+" >16B="+big);
      foreach(var s in bigList) L("   BIG: "+s);
    }

    // ---------- PART2: SendReturnBool* 原始 IL hex ----------
    L(""); L("########## PART2: SendReturnBool* / SendReturnPackage IL ##########");
    string[] tgt = new string[]{"SendReturnBool","SendReturnBool2","SendReturnBoolThree","SendReturnPackage"};
    for(int side=0;side<2;side++){
      var Asms = (side==0)?A5:A6;
      L(""); L("---- "+(side==0?"CS5":"CS6")+" ----");
      foreach(var a in Asms)
        foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
          MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
          foreach(var m in ms){
            bool hit=false; for(int k=0;k<tgt.Length;k++) if(m.Name==tgt[k]){hit=true;break;}
            if(!hit) continue;
            Disasm(m, m.ReturnType.Name+" "+m.Name+"("+m.GetParameters().Length+"p) @ "+t.Name);
          }
        }
    }

    // ---------- PART3: ICorrCom 接口成员清单 ----------
    L(""); L("########## PART3: ICorrCom 接口成员（CS5）##########");
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||!t.IsInterface||t.Name!="ICorrCom")continue;
      L("=== "+t.FullName+" ===");
      foreach(var p in t.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name);
      foreach(var m in t.GetMethods()){ if(m.IsSpecialName)continue;
        var ps=m.GetParameters(); var arr=new string[ps.Length];
        for(int i=0;i<ps.Length;i++){ var pp=ps[i]; arr[i]=pp.ParameterType.Name+(pp.ParameterType.IsByRef?"&":"")+" "+pp.Name; }
        L("  M "+m.ReturnType.Name+" "+m.Name+"("+string.Join(", ",arr)+")");
      }
    }

    // ---------- PART4: ParsingParams 解析端（CS5 + CS6 对照）----------
    L(""); L("########## PART4: ParsingParams 解析端 ##########");
    for(int side=0;side<2;side++){
      var Asms = (side==0)?A5:A6;
      string sideName=(side==0)?"CS5":"CS6";
      L(""); L("---- "+sideName+" ParsingParamsClass ----");
      Type pp=null;
      foreach(var a in Asms) foreach(var t in T(a)){
        if(t==null||t.IsInterface)continue;
        if(t.Name=="ParsingParamsClass"){ pp=t; break; }
        if(pp==null&&t.Name=="ParsingParams") pp=t;
      }
      if(pp==null){ L("(ParsingParamsClass 未找到)"); continue; }
      L("=== "+pp.FullName+" asm="+pp.Assembly.GetName().Name+" ===");
      foreach(var f in pp.GetFields(bf)) L("  F "+f.FieldType.Name+" "+f.Name);
      foreach(var p in pp.GetProperties()) L("  P "+p.PropertyType.Name+" "+p.Name+(p.CanWrite?" rw":" ro"));
      foreach(var m in pp.GetMethods(bf)){ if(m.IsSpecialName)continue;
        if(m.Name=="GetVoltValue"||m.Name=="GetCurrValue"||m.Name=="ParsingParams"||m.Name=="Parsing")
          Disasm(m,"  M "+m.ReturnType.Name+" "+m.Name+"("+m.GetParameters().Length+"p)");
      }
    }

    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5parse.txt",S.ToString());
    Console.WriteLine("done chars="+S.Length);
    return 0;
  }
}
