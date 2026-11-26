// t_cs5rx.cs — CS5 收线程侦查：dump SockectCom 继承链方法表 + 反汇编可疑收包方法（2026-11-10）
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

static class T5RX
{
    static BindingFlags AI = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    static BindingFlags AS = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;
    static StreamWriter W;

    static void P(string s) { W.WriteLine(s); Console.WriteLine(s); }

    static string OpName(byte op)
    {
        switch (op)
        {
            case 0x00: return "nop"; case 0x02: return "ldarg.0"; case 0x06: return "ldarg.1";
            case 0x07: return "ldarg.2"; case 0x0E: return "stloc.0"; case 0x0A: return "stloc.0";
            case 0x0B: return "stloc.1"; case 0x0C: return "stloc.2"; case 0x0D: return "stloc.3";
            case 0x16: return "ldc.i4.0"; case 0x17: return "ldc.i4.1"; case 0x18: return "ldc.i4.2";
            case 0x19: return "ldc.i4.3"; case 0x1A: return "ldc.i4.s"; case 0x1F: return "ldc.i4.s";
            case 0x20: return "ldc.i4"; case 0x25: return "dup"; case 0x26: return "pop";
            case 0x2A: return "ret"; case 0x2B: return "br.s"; case 0x2C: return "brfalse.s";
            case 0x2D: return "brtrue.s"; case 0x2E: return "beq.s"; case 0x30: return "br";
            case 0x31: return "brfalse"; case 0x32: return "brtrue"; case 0x33: return "beq";
            case 0x36: return "blt"; case 0x3A: return "ble"; case 0x3B: return "ble.s";
            case 0x40: return "bne.un"; case 0x45: return "switch";
            case 0x58: return "add"; case 0x59: return "sub"; case 0x5A: return "mul";
            case 0x5F: return "and"; case 0x60: return "or"; case 0x61: return "xor";
            case 0x6F: return "callvirt"; case 0x72: return "ldstr"; case 0x73: return "newobj";
            case 0x74: return "castclass"; case 0x75: return "isinst"; case 0x79: return "unbox.any";
            case 0x7B: return "ldfld"; case 0x7D: return "stfld"; case 0x7E: return "ldsfld";
            case 0x80: return "stsfld"; case 0x8C: return "box"; case 0x8D: return "newarr";
            case 0x8E: return "ldlen"; case 0x8F: return "ldelema"; case 0x90: return "ldelem.i1";
            case 0x91: return "ldelem.u1"; case 0x92: return "ldelem.i2"; case 0x94: return "ldelem.i4";
            case 0x96: return "ldelem.r4"; case 0x98: return "ldelem.ref"; case 0x9C: return "stelem.i4";
            case 0xA2: return "stelem.ref"; case 0xA3: return "ldelem"; case 0xA5: return "unbox.any";
            case 0xD0: return "ldtoken"; case 0x6B: return "conv.i4"; case 0x69: return "conv.i8";
            case 0x6A: return "conv.u8"; case 0x67: return "conv.u2"; case 0x68: return "conv.u1";
            case 0xFE: return "fe.xx";
            default: return "0x" + op.ToString("X2");
        }
    }

    // 简化反汇编：只关心调用目标与关键 ldc
    static void DumpMethod(MethodInfo m)
    {
        var body = m.GetMethodBody();
        if (body == null) { P("  " + m.Name + " (no body)"); return; }
        var il = body.GetILAsByteArray();
        P("  [RX] " + m.Name + " IL=" + il.Length + "B sig=" + m.ToString());
        int i = 0;
        var sb = new StringBuilder();
        while (i < il.Length)
        {
            byte op = il[i]; int start = i; i++;
            switch (op)
            {
                case 0xFE: i++; break;
                case 0x1F: case 0x2B: case 0x2C: case 0x2D: case 0x2E: case 0x3B: i++; break;
                case 0x1A: sb.Append(" ").Append(il[i]); i++; break;
                case 0x20: case 0x30: case 0x31: case 0x32: case 0x33: case 0x36: case 0x3A: case 0x40:
                    i += 4; break;
                case 0x6F: case 0x73: case 0x72: case 0x28: case 0x29: case 0x7B: case 0x7D: case 0x7E:
                case 0x80: case 0xA3: case 0xA5: case 0x79: case 0x8F: case 0xD0:
                    {
                        int tok = BitConverter.ToInt32(il, i); i += 4;
                        string name = "";
                        try
                        {
                            var mi = m.Module.ResolveMember(tok);
                            if (mi != null) name = mi.DeclaringType.Name + "::" + mi.Name;
                        }
                        catch { }
                        sb.Append(" " + OpName(op) + "(" + name + ")");
                        break;
                    }
                case 0x45: i += 4 + BitConverter.ToInt32(il, i) * 4; break;
                default: break;
            }
        }
        P("      calls:" + sb.ToString());
    }

    static int Main()
    {
        W = new StreamWriter(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5rx.txt", false, Encoding.UTF8);
        Console.OutputEncoding = Encoding.UTF8;
        string dir = @"D:\sci\CS Studio5\CS Studio5";
        string[] dlls = {
            "CorrTest.CorrInterface.dll","CorrTest.CorrData.dll","CorrTest.CorrCom.dll",
            "CorrTest.CorrModules.dll","CorrTest.CorrMath.dll","CorrTest.CorrLog.dll",
            "CorrTest.CorrLanguage.dll","CorrTest.CorrUSControl.dll","CorrTest.NetSkin.dll",
            "CorrTest.NetUtility.dll","CorrTest.CorrCSType.dll"};
        foreach (var n in dlls) { try { Assembly.LoadFrom(Path.Combine(dir, n)); } catch { } }

        Type sockT = null;
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            try { foreach (var t in a.GetTypes()) if (t.Name == "SockectCom") { sockT = t; break; } } catch { }
            if (sockT != null) break;
        }
        if (sockT == null) { P("[FATAL] SockectCom 未找到"); W.Close(); return 1; }

        P("[1] 继承链: " + sockT.FullName);
        Type bt = sockT.BaseType;
        while (bt != null && bt != typeof(object))
        {
            P("  ← " + bt.FullName + " @ " + bt.Assembly.GetName().Name);
            // 收包可疑方法
            foreach (var m in bt.GetMethods(AI | AS).Where(m =>
                m.Name.ToLower().Contains("rece") || m.Name.ToLower().Contains("thread") ||
                m.Name.ToLower().Contains("parsing") || m.Name.ToLower().Contains("buffer") ||
                m.Name.ToLower().Contains("unin") || m.Name.ToLower().Contains("read") ||
                m.Name.ToLower().Contains("pack") || m.Name.ToLower().Contains("data")))
                DumpMethod(m);
            bt = bt.BaseType;
        }

        // SockectCom 自身的接收入口
        P("[2] SockectCom 自身收包可疑方法:");
        foreach (var m in sockT.GetMethods(AI | AS).Where(m =>
            m.Name.ToLower().Contains("rece") || m.Name.ToLower().Contains("thread") ||
            m.Name.ToLower().Contains("parsing") || m.Name.ToLower().Contains("buffer") ||
            m.Name.ToLower().Contains("unin") || m.Name.ToLower().Contains("read") ||
            m.Name.ToLower().Contains("pack")))
            DumpMethod(m);

        // 字段全 dump（找 TCP client / stream / 收缓冲）
        P("[3] SockectCom 字段:");
        foreach (var f in sockT.GetFields(AI))
            P("    " + f.FieldType.Name + " " + f.Name);
        P("[4] 基类字段:");
        bt = sockT.BaseType;
        while (bt != null && bt != typeof(object))
        {
            foreach (var f in bt.GetFields(AI))
                P("    [" + bt.Name + "] " + f.FieldType.Name + " " + f.Name);
            bt = bt.BaseType;
        }
        P("[done]");
        W.Close();
        return 0;
    }
}
