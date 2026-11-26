// t_cs5il2.cs -- 反汇编 IBaseParams.GetOcpValueAutoRange / SendMethodParams / SendMethodInit
//
// 目标（2026-11-10 逐步探针定位）：
//   [S3] GetOcpValueAutoRange() : EXC NullReferenceException
//   [S4] SendMethodParams()     : ret False   ← 「指令下发失败」的直接来源
//
// 先找实现体在哪个类（接口 IBaseParams 声明在 CorrInterface，实现在 CorrData），
// 再反汇编其 IL，看它调用/读取了哪些成员。
//
// 用法：t_cs5il2.exe
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

static class Il2
{
    const string DIR5 = @"D:\sci\CS Studio5\CS Studio5";
    static readonly string[] DLLS = {
        "CorrTest.CorrInterface.dll", "CorrTest.CorrData.dll", "CorrTest.CorrCom.dll",
        "CorrTest.CorrModules.dll", "CorrTest.CorrMath.dll", "CorrTest.CorrLog.dll",
        "CorrTest.CorrLanguage.dll", "CorrTest.CorrUSControl.dll",
        "CorrTest.NetSkin.dll", "CorrTest.NetUtility.dll", "CorrTest.CorrCSType.dll"
    };
    static readonly List<Assembly> _asms = new List<Assembly>();
    static readonly StringBuilder _sb = new StringBuilder();

    static void L(string s) { _sb.AppendLine(s); }

    static Type[] Types(Assembly a)
    {
        try { return a.GetTypes(); }
        catch (ReflectionTypeLoadException e) { return e.Types; }
        catch { return new Type[0]; }
    }

    static void Dump(Type t, string name, BindingFlags bf)
    {
        MethodInfo m = null;
        foreach (var x in t.GetMethods(bf))
            if (x.Name == name) { m = x; break; }
        if (m == null) { L("  " + t.Name + "." + name + " : NOT FOUND"); return; }

        var body = m.GetMethodBody();
        if (body == null) { L("  " + t.Name + "." + name + " : no body"); return; }
        var il = body.GetILAsByteArray();
        L("");
        L("=== " + t.FullName + "." + name + "  IL=" + il.Length + "B  static=" + m.IsStatic
          + " params=" + m.GetParameters().Length + " ===");

        int i = 0;
        while (i < il.Length)
        {
            byte op = il[i];
            if (op == 0x28 || op == 0x6F || op == 0x73 || op == 0x7B || op == 0x7E
                || op == 0x72 || op == 0x74 || op == 0x8C || op == 0x7D || op == 0x6E)
            {
                int tok = BitConverter.ToInt32(il, i + 1);
                string nm;
                try
                {
                    var mem = m.Module.ResolveMember(tok, t.GetGenericArguments(), m.GetGenericArguments());
                    if (mem == null) nm = "<null>";
                    else
                    {
                        var dt = mem.DeclaringType;
                        nm = (dt == null ? "" : dt.Name + ".") + mem.Name;
                    }
                }
                catch (Exception e) { nm = "<x:" + e.GetType().Name + ">"; }
                string opn =
                    op == 0x28 ? "call" : op == 0x6F ? "callvirt" : op == 0x73 ? "newobj" :
                    op == 0x7B ? "ldfld" : op == 0x7E ? "ldsfld" : op == 0x72 ? "ldstr" :
                    op == 0x74 ? "castclass" : op == 0x7D ? "stfld" : op == 0x6E ? "box" : "?";
                L("  +" + i + " " + opn + " -> " + nm);
                i += 5;
                continue;
            }
            i++;
        }
    }

    static int Main()
    {
        foreach (var n in DLLS)
        {
            string p = Path.Combine(DIR5, n);
            if (!File.Exists(p)) continue;
            try { _asms.Add(Assembly.LoadFrom(p)); }
            catch { }
        }
        L("assemblies loaded: " + _asms.Count);

        var bfAll = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

        // 1) 先找这三个方法的所有实现体在哪些类
        L("");
        L("=== 方法实现位置 ===");
        foreach (var mn in new[] { "GetOcpValueAutoRange", "SendMethodParams", "SendMethodInit", "GetMethodBytes" })
        {
            bool any = false;
            foreach (var a in _asms)
                foreach (var t in Types(a))
                {
                    if (t == null) continue;
                    MethodInfo[] ms;
                    try { ms = t.GetMethods(bfAll | BindingFlags.DeclaredOnly); }
                    catch { continue; }
                    foreach (var m in ms)
                    {
                        if (m.Name != mn) continue;
                        var body = m.GetMethodBody();
                        int len = 0;
                        try { len = body == null ? -1 : body.GetILAsByteArray().Length; } catch { }
                        L("  " + mn + " -> " + t.FullName + "  IL=" + len + "B");
                        any = true;
                    }
                }
            if (!any) L("  " + mn + " -> 未找到");
        }

        // 2) 反汇编实现体
        foreach (var a in _asms)
            foreach (var t in Types(a))
            {
                if (t == null) continue;
                if (t.Name != "OcpParams" && t.Name != "BaseParams") continue;
                Dump(t, "GetOcpValueAutoRange", bfAll);
                Dump(t, "SendMethodParams", bfAll);
                Dump(t, "SendMethodInit", bfAll);
            }

        File.WriteAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs5il2.log", _sb.ToString());
        Console.WriteLine(_sb.ToString());
        Environment.Exit(0);
        return 0;
    }
}
