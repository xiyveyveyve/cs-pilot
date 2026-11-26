// t_cs6ui.cs — CS6 UI 窗体侦查：CorrForm.dll 的 Form 类清单 + ctor 可 new 性
using System;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

static class T
{
    const string DIR = @"D:\sci\MDI Jade 9";
    static void P(string s) { Console.WriteLine(s); try { File.AppendAllText(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6ui.txt", s + "\r\n"); } catch {} }

    [STAThread]
    static int Main()
    {
        try { File.Delete(@"C:\Users\xiyve\Desktop\CS-Pilot-纯代码\logs\t_cs6ui.txt"); } catch {}
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string n = new AssemblyName(e.Name).Name + ".dll";
            string p = Path.Combine(DIR, n);
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        string[] dlls = { "CSStudio6.NetSkin.dll", "CSStudio6.BaseInterface.dll", "CSStudio6.CorrData.dll",
            "CSStudio6.MathHlp.dll", "CSStudio6.NetUtility.dll", "CSStudio6.Language.dll",
            "CSStudio6.SysLog.dll", "CSStudio6.USControl.dll", "CSStudio6.CorrForm.dll" };
        Assembly cf = null;
        foreach (string d in dlls) { string p = Path.Combine(DIR, d); if (File.Exists(p)) { var a = Assembly.LoadFrom(p); if (d.Contains("CorrForm")) cf = a; } }
        if (cf == null) { P("FATAL no CorrForm"); return 1; }

        // ★ 主 exe 也是程序集：找继承 BaseMainFrm 的类
        Assembly exe = Assembly.LoadFrom(Path.Combine(DIR, "CorrTest.CSStudio.exe"));
        Type bm = null;
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (!a.GetName().Name.Contains("CSStudio6")) continue;
            foreach (Type t in a.GetTypes()) if (t.Name == "BaseMainFrm") { bm = t; break; }
            if (bm != null) break;
        }
        if (bm != null) P("[BASE] BaseMainFrm @ " + bm.Assembly.GetName().Name);
        foreach (Type t in exe.GetTypes())
        {
            if (!typeof(Form).IsAssignableFrom(t)) continue;
            if (bm != null && !bm.IsAssignableFrom(t)) continue;
            string cs = "";
            foreach (var c in t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                cs += (cs == "" ? "" : " | ") + "(" + c.GetParameters().Length + "p)";
            P("[MAINEXE-FORM] " + t.FullName + "  base=" + t.BaseType.Name + "  ctor" + cs);
        }
        // 入口 Main
        MethodInfo mi = exe.EntryPoint;
        P("[ENTRY] " + (mi == null ? "null" : mi.DeclaringType.FullName + "." + mi.Name + " " + mi.GetParameters().Length + "p"));

        foreach (Type t in cf.GetTypes())
        {
            if (!typeof(Form).IsAssignableFrom(t)) continue;
            var ctors = t.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            string cs = "";
            foreach (var c in ctors) cs += (cs == "" ? "" : " | ") + "(" + c.GetParameters().Length + "p)";
            P("[FORM] " + t.FullName + "  base=" + t.BaseType.Name + "  ctor" + cs);
        }
        // BaseMainFrm 在哪
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            if (!a.GetName().Name.Contains("CSStudio6")) continue;
            foreach (Type t in a.GetTypes())
                if (t.Name == "BaseMainFrm") P("[BASE] BaseMainFrm @ " + a.GetName().Name + " abstract=" + t.IsAbstract + " ctor=" + t.GetConstructors(BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance).Length);
        }
        P("DONE");
        return 0;
    }
}
