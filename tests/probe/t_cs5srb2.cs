// t_cs5srb2.cs -- 验证 SendReturnBoolThree 是否 return-false 桩 + 查 ICorrCom 真实实现类
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

static class Srb2
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

    static string Hex(byte[] b)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < b.Length; i++) sb.Append(b[i].ToString("X2")).Append(' ');
        return sb.ToString().TrimEnd();
    }

    static int Main()
    {
        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (File.Exists(p)) { try { A.Add(Assembly.LoadFrom(p)); } catch { } }
        }

        var bfAll = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
                  | BindingFlags.Static | BindingFlags.DeclaredOnly;

        L("=== 1) SendReturnBool* 的原始 IL 字节（判断是否 return-false 桩）===");
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null) continue;
                MethodInfo[] ms;
                try { ms = t.GetMethods(bfAll); } catch { continue; }
                foreach (var m in ms)
                {
                    if (m.Name != "SendReturnBoolThree" && m.Name != "SendReturnBool"
                        && m.Name != "SendReturnPackage") continue;
                    var body = m.GetMethodBody();
                    if (body == null) continue;
                    var il = body.GetILAsByteArray();
                    if (il == null) continue;
                    L("  " + t.Name + "." + m.Name + " (" + m.GetParameters().Length + "p)  " + Hex(il));
                }
            }

        L("");
        L("=== 2) ICorrCom 的所有实现类 ===");
        Type icorr = null;
        foreach (var a in A) foreach (var t in T(a)) if (t != null && t.Name == "ICorrCom") { icorr = t; break; }
        L("  ICorrCom = " + (icorr == null ? "未找到" : icorr.FullName));
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null || t.IsInterface || t.IsAbstract) continue;
                bool impl = false;
                try { foreach (var i in t.GetInterfaces()) if (i.Name == "ICorrCom") { impl = true; break; } } catch { }
                if (impl)
                {
                    var body = t.GetMethod("SendReturnBoolThree", bfAll | BindingFlags.Public);
                    int len = -1;
                    try { var b = body.GetMethodBody(); len = b == null ? -1 : b.GetILAsByteArray().Length; } catch { }
                    L("  " + t.FullName + "  (base=" + (t.BaseType == null ? "-" : t.BaseType.Name)
                      + ") SendReturnBoolThree IL=" + len + "B");
                }
            }

        L("");
        L("=== 3) SockectCom 的基类/接口 ===");
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null || t.Name != "SockectCom") continue;
                L("  " + t.FullName + "  base=" + (t.BaseType == null ? "-" : t.BaseType.FullName));
                try
                {
                    foreach (var i in t.GetInterfaces()) L("    impl " + i.FullName);
                }
                catch { }
            }

        L("");
        L("=== 4) 哪些类型有 SendReturnBoolThree 的真实实现（IL>8B）===");
        foreach (var a in A)
            foreach (var t in T(a))
            {
                if (t == null || t.IsInterface) continue;
                MethodInfo m = null;
                try { m = t.GetMethod("SendReturnBoolThree", bfAll | BindingFlags.Public); } catch { }
                if (m == null) continue;
                var body = m.GetMethodBody();
                if (body == null) continue;
                var il = body.GetILAsByteArray();
                if (il != null && il.Length > 8)
                    L("  ★ " + t.FullName + "  IL=" + il.Length + "B  " + Hex(il).Substring(0, Math.Min(48, Hex(il).Length)));
            }

        File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5srb2.log", S.ToString());
        Console.WriteLine(S.ToString());
        Environment.Exit(0);
        return 0;
    }
}
