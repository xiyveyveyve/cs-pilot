// t_cs5start.cs — 反汇编 CS5 ExpComSendClass.StartMethod(588B)：找 err='指令下发失败，请稍后重试!' 的写入分支
// PART1 StartMethod 全 IL；PART2 ExpComSendClass 全方法 ldstr 扫「失败/成功」；PART3 SendSysStop/SendSysStart 小方法
using System;
using System.IO;
using System.Linq;
using System.Reflection;

static class P{
  static StreamWriter w;
  static void L(string s){ w.WriteLine(s); }

  static string Tok(Module mod,int tk){
    try{
      MemberInfo mi=mod.ResolveMember(tk);
      MethodBase mb=mi as MethodBase; if(mb!=null) return mb.DeclaringType.Name+"."+mb.Name;
      FieldInfo f=mi as FieldInfo; if(f!=null) return "fld:"+f.Name;
      Type t=mi as Type; if(t!=null) return "typ:"+t.Name;
      return mi.ToString();
    }catch{return "0x"+tk.ToString("X8");}
  }

  static string StrTok(Module mod,int tk){
    try{ string s=mod.ResolveString(tk); return "\""+s.Replace("\n","\\n")+"\""; }
    catch{ return "str:0x"+tk.ToString("X8"); }
  }

  static void DumpIL(MethodBase m,string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" [no body]"); return; }
    byte[] il=body.GetILAsByteArray();
    L(tag+" IL="+il.Length+"B  sig="+m.ToString());
    int i=0;
    while(i<il.Length){
      int op=il[i]; string mn="??"+op.ToString("X2"); int adv=1;
      int need=1;
      if(op==0x1F||op==0x2B||op==0x2C||op==0x2D||op==0x2E||op==0x2F||op==0x30||op==0x31||op==0x32||op==0x33||op==0xDE) need=2;
      else if(op==0x20||op==0x28||op==0x29||op==0x38||op==0x39||op==0x3A||op==0x6F||op==0x72||op==0x73||op==0x74||op==0x75||op==0x7B||op==0x7D||op==0x7E||op==0x80||op==0x8C||op==0x8D||op==0xA3||op==0xA4||op==0xD0||op==0xDD) need=5;
      else if(op==0xFE) need=2;
      if(i+need>il.Length){ L("  +"+i.ToString().PadLeft(3)+" <truncated op "+op.ToString("X2")+">"); break; }
      switch(op){
        case 0x00: mn="nop"; break;
        case 0x02: mn="ldarg.0"; break;
        case 0x03: mn="ldarg.1"; break;
        case 0x04: mn="ldarg.2"; break;
        case 0x05: mn="ldarg.3"; break;
        case 0x06: case 0x07: case 0x08: case 0x09: mn="ldloc."+(op-6); break;
        case 0x0A: case 0x0B: case 0x0C: case 0x0D: mn="stloc."+(op-0x0A); break;
        case 0x0E: case 0x0F: case 0x10: case 0x11: mn="ldarg.s "+il[i+1]; adv=2; break;
        case 0x12: case 0x13: mn="ldloc.s "+il[i+1]; adv=2; break;
        case 0x14: mn="ldnull"; break;
        case 0x15: mn="ldc.i4.m1"; break;
        case 0x16: case 0x17: case 0x18: case 0x19: case 0x1A: case 0x1B: case 0x1C: case 0x1D: case 0x1E:
          mn="ldc.i4."+(op-0x16); break;
        case 0x1F: mn="ldc.i4.s "+il[i+1]; adv=2; break;
        case 0x20: mn="ldc.i4 "+BitConverter.ToInt32(il,i+1); adv=5; break;
        case 0x21: mn="ldc.i8 "+BitConverter.ToInt64(il,i+1); adv=9; break;
        case 0x22: mn="ldc.r4 "+BitConverter.ToSingle(il,i+1); adv=5; break;
        case 0x23: mn="ldc.r8 "+BitConverter.ToDouble(il,i+1); adv=9; break;
        case 0x25: mn="dup"; break;
        case 0x26: mn="pop"; break;
        case 0x28: mn="call -> "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x29: mn="calli"; adv=5; break;
        case 0x2A: mn="ret"; break;
        case 0x2B: mn="br.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x2C: mn="brfalse.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x2D: mn="brtrue.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x2E: mn="beq.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x2F: mn="bge.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x30: mn="bgt.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x31: mn="ble.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x32: mn="blt.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x33: mn="bne.un.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0x38: mn="br "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x39: mn="brfalse "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x3A: mn="brtrue "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x3B: mn="beq "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x40: mn="blt "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x58: mn="add"; break;
        case 0x59: mn="sub"; break;
        case 0x5A: mn="mul"; break;
        case 0x5B: mn="div"; break;
        case 0x5F: mn="and"; break;
        case 0x60: mn="or"; break;
        case 0x61: mn="xor"; break;
        case 0x6F: mn="callvirt -> "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x72: mn="ldstr "+StrTok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x73: mn="newobj -> "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x74: mn="castclass "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x75: mn="isinst "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x76: mn="conv.r4"; break;
        case 0x77: mn="conv.r8"; break;
        case 0x78: mn="conv.i4"; break;
        case 0x6A: mn="conv.i"; break;
        case 0x6B: mn="conv.i8"; break;
        case 0x8C: mn="box "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x8D: mn="newarr "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x8E: mn="ldlen"; break;
        case 0x91: mn="ldelem.ref"; break;
        case 0x9A: mn="ldelem.ref"; break;
        case 0xA2: mn="stelem.ref"; break;
        case 0xA3: mn="stelem "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0xA4: mn="ldelem "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0xD0: mn="ldtoken "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0xDD: mn="leave "+(i+5+BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0xDE: mn="leave.s "+(i+2+(sbyte)il[i+1]); adv=2; break;
        case 0xFE:
          int op2=il[i+1]; adv=2;
          if(op2==0x01) mn="ceq";
          else if(op2==0x02) mn="cgt";
          else if(op2==0x04) mn="clt";
          else mn="fe:"+op2.ToString("X2");
          break;
        default:
          if(op>=0x7B&&op<=0x7E){
            string t2=Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5;
            mn=(op==0x7B?"ldflda":op==0x7C?"ldflda":op==0x7D?"ldfld":"ldsfld")+" "+t2;
          }
          else if(op>=0x7F&&op<=0x82){
            string t2=Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5;
            mn=(op==0x7F?"stfld":op==0x80?"stfld":op==0x81?"stfld":"stsfld")+" "+t2;
          }
          break;
      }
      L("  +"+i.ToString().PadLeft(3)+" "+mn);
      i+=adv;
    }
    // 局部变量表
    try{
      var lv=body.LocalVariables;
      if(lv!=null&&lv.Count>0){
        L(tag+" locals:");
        foreach(var v in lv) L("    ["+v.LocalIndex+"] "+v.LocalType.FullName);
      }
    }catch{}
  }

  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }

  static void Main(){
    try{
    string baseDir=@"D:\sci\CS Studio5\CS Studio5";
    string logPath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,@"..\..\logs\t_cs5start.txt");
    logPath=Path.GetFullPath(logPath);
    using(w=new StreamWriter(logPath,false)){
      L("[t_cs5start] CS5 StartMethod 侦查 "+DateTime.Now);
      string[] dlls=new string[]{
        "CorrTest.BaseInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll",
        "CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
      Type sendC=null; Assembly sendA=null; string sendAsm="";
      foreach(var n in dlls){
        string p=Path.Combine(baseDir,n); if(!File.Exists(p)) continue;
        try{
          Assembly a=Assembly.LoadFrom(p);
          foreach(var t in T(a)){
            if(t!=null&&t.Name=="ExpComSendClass"){ sendC=t; sendA=a; sendAsm=n; break; }
          }
          if(sendC!=null) break;
        }catch{}
      }
      if(sendC==null){ L("ExpComSendClass 未找到"); return; }
      L("[found] ExpComSendClass @ "+sendAsm);
      var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;

      // PART1: StartMethod 全 IL
      foreach(var m in sendC.GetMethods(bf).Where(x=>x.Name=="StartMethod"))
        DumpIL(m,"[P1] StartMethod");

      // PART2: ExpComSendClass 全方法 ldstr 扫「失败/成功」
      L("[P2] ExpComSendClass ldstr 扫描（失败/成功/下发）：");
      foreach(var m in sendC.GetMethods(bf)){
        MethodBody body=null; try{body=m.GetMethodBody();}catch{}
        if(body==null) continue;
        byte[] il=body.GetILAsByteArray();
        for(int i=0;i+5<=il.Length;i++){
          if(il[i]==0x72){
            int tk=BitConverter.ToInt32(il,i+1);
            try{
              string s=m.Module.ResolveString(tk);
              if(s!=null&&(s.IndexOf("失败")>=0||s.IndexOf("成功")>=0||s.IndexOf("下发")>=0))
                L("    "+m.Name+" : \""+s+"\"");
            }catch{}
          }
        }
      }

      // PART3: SendSysStop/SendSysStart/SendSysPause/SendPolarON 小方法全 dump
      foreach(var n in new[]{"SendSysStop","SendSysStart","SendSysPause","SendPolarON","SendSysData","SendIOBytes"}){
        foreach(var m in sendC.GetMethods(bf).Where(x=>x.Name==n))
          DumpIL(m,"[P3] "+n);
      }

      // PART4: 扫全 CorrTest 程序集：谁的 ldstr 是「指令下发失败，请稍后重试!」
      L("[P4] 全程序集 ldstr=指令下发失败 来源：");
      foreach(var n in dlls){
        string p=Path.Combine(baseDir,n); if(!File.Exists(p)) continue;
        try{
          Assembly a=Assembly.LoadFrom(p);
          foreach(var t in T(a)){
            if(t==null) continue;
            MethodInfo[] ms=null; try{ms=t.GetMethods(bf);}catch{}
            if(ms==null) continue;
            foreach(var m in ms){
              MethodBody body=null; try{body=m.GetMethodBody();}catch{}
              if(body==null) continue;
              byte[] il=body.GetILAsByteArray();
              for(int i=0;i+5<=il.Length;i++){
                if(il[i]==0x72){
                  int tk=BitConverter.ToInt32(il,i+1);
                  try{
                    string s=m.Module.ResolveString(tk);
                    if(s!=null&&s.IndexOf("指令下发失败")>=0)
                      L("    "+t.FullName+"."+m.Name+" : \""+s+"\"");
                  }catch{}
                }
              }
            }
          }
        }catch{}
      }

      L("[done]");
    }
    Console.WriteLine("OK t_cs5start");
    }catch(Exception e){ Console.WriteLine("FATAL "+e); }
  }
}
