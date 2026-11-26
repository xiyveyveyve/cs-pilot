// t_cs5parse3.cs -- 命令帧模板 + AA85 构造逻辑 + ParsingParams context 注入链
//
// 前情：
//   OcpParams.SendMethodParams = SendReturnBoolThree(GetMethodBytes()=16B静态帧) + Sleep(10)
//                                + SendReturnBoolThree(GetDoubleChannelSampleBytes())
//   GetDoubleChannelSampleBytes → CommandPackage.GetDoubleSingleSampleBytes(ctx, cmd, len)
//   GetVoltValue 末尾 get_baseContext→get_ExtAmpData→get_VotCoefficient（S3 NRE 嫌疑）
//
// PART1  反射读 OcpParams.GetMethodBytes 的 16B 静态数组真实内容
// PART2  CommandPackage 全部静态 byte[] 字段（命令帧模板全清单）
// PART3  GetDoubleSingleSampleBytes + CommandPackage 里 *Sample* 方法反汇编
// PART4  ParsingParamsClass..ctor / BaseContext.get_ParsingParms / ParsingParms 字段注入链
// 输出：logs/t_cs5parse3.txt
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;

static class P5c {
  const string D5 = @"D:\sci\CS Studio5\CS Studio5";
  static readonly string[] DLLS5 = new string[] {
    "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
    "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
    "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll",
    "CorrTest.NetSkin.dll","CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"
  };
  static StringBuilder S = new StringBuilder();
  static void L(string s){ S.AppendLine(s); }
  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }
  static string Sig(MethodBase m){
    var ps=m.GetParameters(); var arr=new string[ps.Length];
    for(int i=0;i<ps.Length;i++) arr[i]=ps[i].ParameterType.Name+" "+ps[i].Name;
    return m.Name+"("+string.Join(", ",arr)+")";
  }

  // 正确模式：ldc.i4.s N → 8D newarr → 25 dup → D0 ldtoken → 28 call InitializeArray
  static void DumpRvaArrays(MethodBase m, string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null) return;
    byte[] il=body.GetILAsByteArray();
    for(int i=0;i+6<=il.Length;i++){
      if(il[i]!=0x25||il[i+1]!=0xD0) continue;   // dup; ldtoken
      int tk=BitConverter.ToInt32(il,i+2);
      // 向前找 0x8D (newarr)，再往前找 ldc.i4.s / ldc.i4.N
      int len=-1;
      for(int k=i-1;k>=System.Math.Max(0,i-12);k--){
        if(il[k]==0x8D){
          for(int q=k-1;q>=System.Math.Max(0,k-6);q--){
            if(il[q]==0x1F&&q+1<il.Length){ len=il[q+1]; break; }
            if(il[q]>=0x16&&il[q]<=0x1E){ len=il[q]-0x16; break; }
            if(il[q]==0x20&&q+4<il.Length){ len=BitConverter.ToInt32(il,q+1); break; }
          }
          break;
        }
      }
      if(len<0||len>512) continue;
      try{
        var f=m.Module.ResolveField(tk);
        byte[] buf=new byte[len];
        RuntimeHelpers.InitializeArray(buf, f.FieldHandle);
        L(tag+" RVA数组 token=0x"+tk.ToString("X8")+" len="+len+" HEX: "+BitConverter.ToString(buf).Replace("-"," "));
      }catch(Exception e){ L(tag+" RVA读取失败 token=0x"+tk.ToString("X8")+" : "+e.Message); }
    }
  }

  static void Disasm(MethodBase m, string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" : (no body)"); return; }
    byte[] il=null; try{il=body.GetILAsByteArray();}catch{}
    if(il==null){ L(tag+" : (il null)"); return; }
    string lv="";
    try{ foreach(var v in body.LocalVariables) lv+=v.LocalType.Name+" "; }catch{}
    L(tag+"  IL="+il.Length+"B locals=["+lv+"]");
    if(il.Length<=200) L("   HEX: "+BitConverter.ToString(il).Replace("-"," "));
    int i=0;
    while(i<il.Length){
      byte op=il[i];
      if(op==0xFE){
        if(i+1>=il.Length) break;
        byte op2=il[i+1]; int len;
        if(op2==0x06||op2==0x07||op2==0x14||op2==0x1A) len=6;
        else if(op2==0x09||op2==0x0A||op2==0x0B||op2==0x0C||op2==0x0D||op2==0x0E||op2==0x15) len=4;
        else len=2;
        i+=len; continue;
      }
      if(op==0x45){ if(i+5>il.Length) break; int n=BitConverter.ToInt32(il,i+1); L("  +"+i+" switch n="+n); i+=5+4*n; continue; }
      int len2;
      switch(op){
        case 0x1F: len2=2; break;
        case 0x20: case 0x22: len2=5; break;
        case 0x21: case 0x23: len2=9; break;
        case 0x2B: case 0x2C: case 0x2D: case 0x2E: case 0x2F: case 0x30: case 0x31: case 0x32:
        case 0x33: case 0x34: case 0x35: case 0x36: case 0x37:
          if(i+2<=il.Length) L("  +"+i+" "+op.ToString("X2")+" sbr "+il[i+1]);
          len2=2; break;
        case 0x38: case 0x39: case 0x3A: case 0x3B: case 0x3C: case 0x3D: case 0x3E: case 0x3F:
        case 0x40: case 0x41: case 0x42: case 0x43: case 0x44: len2=5; break;
        case 0x27: case 0x28: case 0x29: case 0x6F: case 0x73: case 0x7B: case 0x7C: case 0x7D:
        case 0x7E: case 0x7F: case 0x72: case 0x74: case 0x75: case 0x79: case 0x8C: case 0xA5:
        case 0xD0: case 0xC6:
          if(i+5<=il.Length){
            int tk=BitConverter.ToInt32(il,i+1);
            string nm;
            try{ MemberInfo mem=m.Module.ResolveMember(tk);
              nm=mem==null?"<null>":((mem.DeclaringType==null?"":mem.DeclaringType.Name+".")+mem.Name);
            }catch(Exception e){ nm="<x:"+e.GetType().Name+">"; }
            string tok=TokName(op);
            L("  +"+i+" "+tok+" -> "+nm);
            if(op==0x72){ // ldstr 打字符串内容
              try{ L("       \""+m.Module.ResolveString(tk)+"\""); }catch{}
            }
            if(tok=="ldtoken") DumpRvaArrays(m, "  ["+i+"]");
          }
          len2=5; break;
        default: len2=1; break;
      }
      i+=len2;
    }
  }
  static string TokName(byte op){
    switch(op){ case 0x28:return "call"; case 0x6F:return "callvirt"; case 0x73:return "newobj";
    case 0x7B:return "ldfld"; case 0x7C:return "ldflda"; case 0x7D:return "stfld"; case 0x7E:return "ldsfld";
    case 0x7F:return "stsfld"; case 0x72:return "ldstr"; case 0x74:return "castclass"; case 0x75:return "isinst";
    case 0x79:return "unbox"; case 0x8C:return "box"; case 0xA5:return "unbox.any"; case 0xD0:return "ldtoken"; case 0x27:return "jmp";}
    return op.ToString("X2");
  }

  static int Main(){
    var A5=new List<Assembly>();
    foreach(var n in DLLS5){ string p=Path.Combine(D5,n); if(File.Exists(p)){try{A5.Add(Assembly.LoadFrom(p));}catch{}} }
    L("CS5 asms="+A5.Count);
    var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static|BindingFlags.DeclaredOnly;

    // ---------- PART1: OcpParams.GetMethodBytes 16B 静态数组 ----------
    L(""); L("########## PART1: OcpParams.GetMethodBytes 静态帧内容 ##########");
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface||t.Name!="OcpParams")continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){ if(m.Name!="GetMethodBytes")continue;
        L("[P1] "+Sig(m)+" @ "+t.Name);
        DumpRvaArrays(m,"[P1]");
        Disasm(m,"[P1] full");
      }
    }

    // ---------- PART2: CommandPackage 静态 byte[] 字段 ----------
    L(""); L("########## PART2: CommandPackage 静态命令帧模板 ##########");
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface||t.Name!="CommandPackage")continue;
      L("[P2] === "+t.FullName+" @ "+a.GetName().Name+" ===");
      foreach(var f in t.GetFields(bf)){
        if(!f.FieldType.Name.StartsWith("Byte[]")) continue;
        try{
          object v=f.GetValue(null);
          byte[] b=v as byte[];
          L("  F "+f.Name+" = "+((b==null)?"null":BitConverter.ToString(b).Replace("-"," ")));
        }catch(Exception e){ L("  F "+f.Name+" <读取失败:"+e.GetType().Name+">"); }
      }
    }

    // ---------- PART3: GetDoubleSingleSampleBytes 等 ----------
    L(""); L("########## PART3: CommandPackage 帧构造方法 ##########");
    string[] p3 = new string[]{"GetDoubleSingleSampleBytes","GetSingleSampleBytes","GetDoubleChannelSampleBytes"};
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
      foreach(var m in ms){
        bool hit=false; for(int k=0;k<p3.Length;k++) if(m.Name==p3[k]){hit=true;break;}
        if(!hit) continue;
        Disasm(m,"[P3] "+Sig(m)+" @ "+t.Name);
      }
    }

    // ---------- PART4: ParsingParams context 注入链 ----------
    L(""); L("########## PART4: ParsingParams context 注入链 ##########");
    foreach(var a in A5) foreach(var t in T(a)){ if(t==null||t.IsInterface)continue;
      if(t.Name=="ParsingParamsClass"){
        ConstructorInfo[] cs; try{cs=t.GetConstructors(bf);}catch{cs=new ConstructorInfo[0];}
        foreach(var c in cs) Disasm(c,"[P4] ParsingParamsClass..ctor("+c.GetParameters().Length+"p)");
      }
      if(t.Name=="BaseContext"){
        MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
        foreach(var m in ms){ if(m.Name=="get_ParsingParms") Disasm(m,"[P4] BaseContext.get_ParsingParms"); }
        foreach(var f in t.GetFields(bf)) if(f.Name.ToLower().Contains("parsing")) L("[P4] BaseContext.F "+f.FieldType.Name+" "+f.Name);
        foreach(var p in t.GetProperties()) if(p.Name.ToLower().Contains("parsing")) L("[P4] BaseContext.P "+p.PropertyType.Name+" "+p.Name);
      }
      if(t.Name=="BaseParams"){
        foreach(var f in t.GetFields(bf)) if(f.Name=="ExtData") L("[P4] BaseParams.F ExtData "+f.FieldType.Name);
        MethodInfo[] ms; try{ms=t.GetMethods(bf);}catch{continue;}
        foreach(var m in ms){ if(m.Name=="get_ExtData") Disasm(m,"[P4] BaseParams.get_ExtData"); }
      }
    }

    File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5parse3.txt",S.ToString());
    Console.WriteLine("done chars="+S.Length);
    return 0;
  }
}
