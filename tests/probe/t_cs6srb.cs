// t_cs6srb.cs — 反汇编 CS6(无壳) BaseConnect 的应答判定逻辑：
// SendReturnBoolBytes / SendReturnBool / OnRecePackage / 数据接收处理
// 目的：确定 ACK 匹配规则（什么帧算应答成功），指导 sim_cs5.py
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

  // 反汇编：逐字节输出助记（简化版，重点看 call/callvirt 目标与字段访问）
  static void DumpIL(MethodBase m,string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" [no body]"); return; }
    byte[] il=body.GetILAsByteArray();
    L(tag+" IL="+il.Length+"B");
    int i=0;
    while(i<il.Length){
      int op=il[i]; string mn="??"+op.ToString("X2"); int adv=1;
      // 按指令需要的操作数长度统一查界
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
        case 0x14: mn="ldnull"; break;
        case 0x15: mn="ldc.i4.m1"; break;
        case 0x16: case 0x17: case 0x18: case 0x19: case 0x1A: case 0x1B: case 0x1C: case 0x1D: case 0x1E:
          mn="ldc.i4."+(op-0x16); break;
        case 0x1F: mn="ldc.i4.s "+il[i+1]; adv=2; break;
        case 0x20: mn="ldc.i4 "+BitConverter.ToInt32(il,i+1); adv=5; break;
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
        case 0x58: mn="add"; break;
        case 0x59: mn="sub"; break;
        case 0x5A: mn="mul"; break;
        case 0x5D: mn="div"; break;
        case 0x6F: mn="callvirt -> "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x72: mn="ldstr"; adv=5; break;
        case 0x73: mn="newobj -> "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x74: mn="castclass "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x75: mn="isinst "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x7B: mn="ldfld "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x7D: mn="stfld "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x7E: mn="ldsfld "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x80: mn="stsfld "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x8C: mn="box "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x8D: mn="newarr "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0x8E: mn="ldlen"; break;
        case 0x91: mn="ldind.i1"; break;
        case 0x92: mn="ldind.u1"; break;
        case 0x94: mn="ldind.i2"; break;
        case 0x95: mn="ldind.u2"; break;
        case 0x9A: mn="ldelem.ref"; break;
        case 0xA2: mn="stelem.ref"; break;
        case 0xA3: mn="ldelem "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
        case 0xA4: mn="stelem "+Tok(m.Module,BitConverter.ToInt32(il,i+1)); adv=5; break;
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
      }
      L("  +"+i.ToString().PadLeft(3)+" "+mn);
      i+=adv;
    }
  }

  static Type[] T(Assembly a){ try{return a.GetTypes();}catch(ReflectionTypeLoadException e){return e.Types;}catch{return new Type[0];} }

  static void Main(){
    try{
    string baseDir=@"D:\sci\MDI Jade 9";
    string logPath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,@"..\..\logs\t_cs6srb.txt");
    logPath=Path.GetFullPath(logPath);
    using(w=new StreamWriter(logPath,false)){
      L("[t_cs6srb] CS6 BaseConnect 应答判定侦查 "+DateTime.Now);
      string[] dlls=new string[]{
        "CSStudio6.BaseInterface.dll","CSStudio6.CorrData.dll","CSStudio6.Connect.dll",
        "CSStudio6.CorrForm.dll","CSStudio6.Analysis.dll","CSStudio6.MathHlp.dll",
        "CSStudio6.USControl.dll","CSStudio6.NetSkin.dll","CSStudio6.NetUtility.dll",
        "CSStudio6.SysLog.dll","CSStudio6.ExtModule.dll","CSStudio6.Language.dll"};
      Type bc=null; Assembly connAsm=null;
      foreach(var n in dlls){
        string p=Path.Combine(baseDir,n); if(!File.Exists(p)) continue;
        try{
          Assembly a=Assembly.LoadFrom(p);
          foreach(var t in T(a)){
            if(t!=null&&t.Name=="BaseConnect"){ bc=t; connAsm=a; L("[found] BaseConnect @ "+n); break; }
          }
          if(bc!=null) break;
        }catch{}
      }
      if(bc==null){ L("BaseConnect 未找到"); return; }
      var bf=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static;
      // 1) SendReturnBoolBytes 本体（应答字节发送+等待标志?）
      foreach(var n in new[]{"SendReturnBoolBytes","SendReturnBool","SendReturnBoolThree","EnableDataEvent"}){
        MethodInfo m=null;
        try{ foreach(var mm in bc.GetMethods(bf)) if(mm.Name==n){ m=mm; break; } }
        catch(Exception e){ L("[M] "+n+" 枚举失败: "+e.GetType().Name); continue; }
        if(m!=null) DumpIL(m,"[M] "+n);
        else L("[M] "+n+" 未找到");
      }
      // 2) 找数据接收/包处理方法（OnRecePackage/ReceData/AnalyzePackage 等）
      L("[methods] BaseConnect 全方法:");
      MethodInfo[] all=null; try{all=bc.GetMethods(bf);}catch{}
      if(all!=null) foreach(var m in all)
        L("  "+m.Name+" ("+string.Join(",",m.GetParameters().Select(p=>p.ParameterType.Name))+")");
      foreach(var n in new[]{"ParsingPack","AddToDataPack","IsStopPack","SendPack","PackReceivedThread","ClearData","CheckPackReceiveThread"}){
        MethodInfo m=null;
        try{ foreach(var mm in bc.GetMethods(bf)) if(mm.Name==n){ m=mm; break; } }
        catch{ continue; }
        if(m!=null) DumpIL(m,"[RX] "+n);
      }
      // 3) 字段清单（boolReturn/returnBytes 类）
      L("[fields] BaseConnect 字段:");
      FieldInfo[] fls=null; try{fls=bc.GetFields(bf);}catch{}
      if(fls!=null) foreach(var f in fls)
        L("  "+f.FieldType.Name+" "+f.Name);
      // 4) CorrPackage 的 IsMsgPack / CheckPack 判定
      Type cp=null;
      foreach(var t2 in T(connAsm)){ if(t2!=null&&t2.Name=="CorrPackage"){ cp=t2; break; } }
      if(cp!=null){
        L("[CP] CorrPackage @ "+connAsm.GetName().Name);
        foreach(var n in new[]{"IsMsgPack","CheckPack","IsDataPack","get_Command","get_Length","get_IsCSTModel","CheckCRC16"}){
          MethodInfo m=null;
          try{ foreach(var mm in cp.GetMethods(bf)) if(mm.Name==n){ m=mm; break; } }
          catch{ continue; }
          if(m!=null) DumpIL(m,"[CP] "+n);
        }
        L("[CP-fields]");
        try{ foreach(var f2 in cp.GetFields(bf)) L("  "+f2.FieldType.Name+" "+f2.Name); }catch{}
      } else L("[CP] CorrPackage 未找到");
      L("[done]");
    }
    }catch(Exception e){ Console.WriteLine("[FATAL] "+e.GetType().Name+": "+e.Message+"\n"+e.StackTrace); }
  }
}
