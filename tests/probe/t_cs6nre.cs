// t_cs6nre.cs — 反汇编 CS6 三个 Params 类的 NRE 源头：
//   BaseParams.Wgpq6nKYUbvlIDq8meH / SendMethodParams
//   EISVSfrqParams.hera1bZ0KXCOcsNe7RO / PotDynamicParams.nGcoF7hx1gq4pDKhGmW
// 并 dump OcpParams 实例字段清单（对照 UI 宿主装配缺什么）
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

  static void DumpIL(MethodBase m,string tag){
    MethodBody body=null; try{body=m.GetMethodBody();}catch{}
    if(body==null){ L(tag+" [no body]"); return; }
    byte[] il=body.GetILAsByteArray();
    Module mod=m.Module;
    L(tag+" "+m.ToString()+" IL="+il.Length+"B");
    int i=0;
    while(i<il.Length){
      int op=il[i]; string mn="??"+op.ToString("X2"); int adv=1; string tok="";
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
        case 0x06: mn="ldloc.0"; break;
        case 0x07: mn="ldloc.1"; break;
        case 0x08: mn="ldloc.2"; break;
        case 0x0A: mn="stloc.0"; break;
        case 0x0B: mn="stloc.1"; break;
        case 0x0C: mn="stloc.2"; break;
        case 0x0E: mn="ldarg.s"; break;
        case 0x16: mn="ldc.i4.0"; break;
        case 0x17: mn="ldc.i4.1"; break;
        case 0x18: mn="ldc.i4.2"; break;
        case 0x19: mn="ldc.i4.3"; break;
        case 0x1F: mn="ldc.i4.s "+il[i+1]; break;
        case 0x20: mn="ldc.i4 "+BitConverter.ToInt32(il,i+1); break;
        case 0x25: mn="dup"; break;
        case 0x26: mn="pop"; break;
        case 0x28: mn="call"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x29: mn="calli"; break;
        case 0x2A: mn="ret"; break;
        case 0x2B: mn="br.s +"+((sbyte)il[i+1]+i+2); break;
        case 0x2C: mn="brfalse.s +"+((sbyte)il[i+1]+i+2); break;
        case 0x2D: mn="brtrue.s +"+((sbyte)il[i+1]+i+2); break;
        case 0x2E: mn="beq.s"; break;
        case 0x38: mn="br +"+((int)BitConverter.ToInt32(il,i+1)+i+5); break;
        case 0x39: mn="brfalse +"+((int)BitConverter.ToInt32(il,i+1)+i+5); break;
        case 0x3A: mn="brtrue +"+((int)BitConverter.ToInt32(il,i+1)+i+5); break;
        case 0x58: mn="add"; break;
        case 0x59: mn="sub"; break;
        case 0x5A: mn="mul"; break;
        case 0x5B: mn="div"; break;
        case 0x6F: mn="callvirt"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x72: mn="ldstr"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x73: mn="newobj"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x74: mn="castclass"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x75: mn="isinst"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x7B: mn="ldfld"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x7E: mn="ldsfld"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x7D: mn="stfld"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x80: mn="stsfld"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x8C: mn="box"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x8D: mn="newarr"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0x9A: mn="ldrefanyval"; break;
        case 0xA2: mn="stelem.ref"; break;
        case 0xA3: mn="ldelem"; break;
        case 0xA4: mn="stelem"; break;
        case 0xD0: mn="ldtoken"; tok=Tok(mod,BitConverter.ToInt32(il,i+1)); break;
        case 0xDD: mn="leave +"+((int)BitConverter.ToInt32(il,i+1)+i+5); break;
        case 0xFE:
          int op2=il[i+1];
          if(op2==0x01) mn="ceq"; else if(op2==0x02) mn="cgt"; else if(op2==0x04) mn="clt";
          else mn="fe."+op2.ToString("X2");
          adv=2; L("  +"+i.ToString().PadLeft(3)+" "+mn); i+=adv; continue;
      }
      L("  +"+i.ToString().PadLeft(3)+" "+mn+(tok==""?"":"  →"+tok));
      i+=adv;
    }
  }

  static void DumpMethods(Type t,string tag,string contains){
    L("=== "+tag+" "+t.FullName+" 方法清单 ===");
    foreach(MethodInfo m in t.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static))
      L("  M "+m.ToString()+" "+(m.IsPrivate?"priv":"pub"));
    foreach(MethodBase m in t.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static))
      if(m.Name.Contains(contains)) DumpIL(m,tag);
  }

  static void DumpFields(Type t,string tag){
    L("=== "+tag+" "+t.FullName+" 字段 ===");
    for(Type tt=t; tt!=null && tt!=typeof(object); tt=tt.BaseType)
      foreach(FieldInfo f in tt.GetFields(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static))
        L("  F ["+tt.Name+"] "+f.FieldType.Name+" "+f.Name);
  }

  static int Main(){
    string log=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,@"..\..\logs\t_cs6nre.txt");
    Directory.CreateDirectory(Path.GetDirectoryName(log));
    using(w=new StreamWriter(log,false)){ w.AutoFlush=true;
      try{
        string dir=@"D:\sci\MDI Jade 9";
        foreach(string f in Directory.GetFiles(dir,"CSStudio6.*.dll"))
          try{ Assembly.LoadFrom(f); }catch{}
        Assembly.LoadFrom(Path.Combine(dir,"CorrTest.CSStudio.exe"));
        Assembly.LoadFrom(Path.Combine(dir,"CorrTest.CSStudioMulti.exe"));
        L("程序集加载完成");

        // 1) BaseParams + 子类
        Type bp=AppDomain.CurrentDomain.GetAssemblies()
          .SelectMany(a=>{try{return a.GetTypes();}catch{return new Type[0];}})
          .FirstOrDefault(t=>t.FullName=="CSStudio6.CorrData.MethodParams.BaseParams");
        L("BaseParams="+(bp==null?"null":bp.FullName));
        if(bp!=null){
          DumpFields(bp,"BP");
          DumpMethods(bp,"BP","Wgpq6nKYUbvlIDq8meH");
          foreach(MethodBase m in bp.GetMethods(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance|BindingFlags.Static))
            if(m.Name=="SendMethodParams") DumpIL(m,"BP.SendMethodParams");
          DumpIL(bp.GetMethod("GetMethodBytes",BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance),"BP.GetMethodBytes");
        }
        // 2) EISVSfrqParams / PotDynamicParams
        foreach(string tn in new string[]{"EISVSfrqParams","PotDynamicParams","OcpParams"}){
          Type t=AppDomain.CurrentDomain.GetAssemblies()
            .SelectMany(a=>{try{return a.GetTypes();}catch{return new Type[0];}})
            .FirstOrDefault(x=>x.FullName=="CSStudio6.CorrData.MethodParams."+tn);
          if(t==null){ L("MISS "+tn); continue; }
          L("### "+tn);
          DumpMethods(t,tn,null);
        }
        L("DONE");
      }catch(Exception e){ L("FATAL "+e); }
    }
    Console.WriteLine("OK t_cs6nre.txt");
    return 0;
  }
}
