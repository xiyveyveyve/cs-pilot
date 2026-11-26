// t_cs5srb.cs -- 反汇编 ICorrCom.SendReturnBoolThree，查清它到底在等什么
//
// 背景（2026-11-10）：
//   OcpParams.SendMethodParams 返回 False，其返回值来自 ICorrCom.SendReturnBoolThree。
//   而 BaseParams.SendMethodParams 用的是 SendReturnBool（非 Three）。
//   "Three" 暗示三帧/三次握手，必须先搞清语义。
//
// 用法：t_cs5srb.exe
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

static class Srb
{
    const string DIR5 = @"D:\sci\CS Studio5\CS Studio5";
    static readonly string[] DLLS = {
        "CorrTest.CorrInterface.dll", "CorrTest.CorrData.dll", "CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll", "CorrTest.CorrMath.dll", "CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll", "CorrTest.CorrUSControl.dll",
        "CorrTest.NetSkin.dll", "CorrTest.NetUtility.dll", "CorrTest.CorrCSType.dll"
    };
    static readonly List<Assembly> A = new List<Assembly>();
    static readonly StringBuilder S = new StringBuilder();
    static void L(string s) { S.AppendLine(s); }

    static Type[] T(Assembly a)
    {
        try { return a.GetTypes(); }
        catch (ReflectionTypeLoadException e) { return e.Types; }
        catch { return new Type[0]; }
    }

    static void Dump(MethodInfo m)
    {
        var body = m.GetMethodBody();
        if (body == null) { L("  (no body)"); return; }
        var il = body.GetILAsByteArray();
        L("  IL=" + il.Length + "B");
        int i = 0;
        while (i < il.Length)
        {
            byte op = il[i];
            if (op == 0x28 || op == 0x6F || op == 0x73 || op == 0x7B || op == 0x7E
                || op == 0x72 || op == 0x74 || op == 0x8C || op == 0x7D || op == 0x6E)
            {
                int tk = BitConverter.ToInt32(il, i + 1);
                string nm;
                try
                {
                    var mem = m.Module.ResolveMember(tk, m.DeclaringType.GetGenericArguments(), m.GetGenericArguments());
                    nm = mem == null ? "<null>" : ((mem.DeclaringType == null ? "" : mem.DeclaringType.Name + ".") + mem.Name);
                }
                catch (Exception e) { nm = "<x:" + e.GetType().Name + ">"; }
                string o = op == 0x28 ? "call" : op == 0x6F ? "callvirt" : op == 0x73 ? "newobj" :
                           op == 0x7B ? "ldfld" : op == 0x7E ? "ldsfld" : op == 0x72 ? "ldstr" :
                           op == 0x74 ? "castclass" : op == 0x7D ? "stfld" : "box";
                L("    +" + i + " " + o + " -> " + nm);
                i += 5; continue;
            }
            i++;
        }
    }

    static int Main()
    {
        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (File.Exists(p)) { try { A.Add(Assembly.LoadFrom(p)); } catch { } }
        }
        L("assemblies: " + A.Count);

        var bf = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
               | BindingFlags.Static | BindingFlags.DeclaredOnly;

        L("");
        L("=== SendReturnBool* 的实现位置与 IL 大小 ===");
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null) continue;
                MethodInfo[] ms;
                try { ms = t.GetMethods(bf); } catch { continue; }
                foreach (var m in ms)
                {
                    if (m.Name != "SendReturnBoolThree" && m.Name != "SendReturnBool"
                        && m.Name != "SendReturnPackage" && m.Name != "SendReturnBool2") continue;
                    int len = -1;
                    try { var b = m.GetMethodBody(); len = b == null ? -1 : b.GetILAsByteArray().Length; } catch { }
                    L("  " + m.Name + " @ " + t.FullName + "  IL=" + len + "B  params=" + m.GetParameters().Length);
                }
            }

        // 反汇编 CorrCom 里的实现（最可能是真正的收发逻辑）
        L("");
        L("=== 反汇编 ===");
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null) continue;
                if (t.Name != "SockectCom" && t.Name != "CSTSockect" && t.Name != "SerialCom"
                    && t.Name != "BaseCorrCom" && t.Name != "CorrComClass") continue;
                MethodInfo[] ms;
                try { ms = t.GetMethods(bf); } catch { continue; }
                foreach (var m in ms)
                {
                    if (m.Name != "SendReturnBoolThree" && m.Name != "SendReturnBool") continue;
                    L("");
                    L("=== " + t.FullName + "." + m.Name + " ===");
                    Dump(m);
                }
            }

        File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5srb.log", S.ToString());
        Console.WriteLine(S.ToString());
        Environment.Exit(0);
        return 0;
    }
}
